from __future__ import annotations

import email
import imaplib
import re
import ssl
from contextlib import contextmanager
from email import policy
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any, Iterator

from .config import AppConfig

_FLAGS_RE = re.compile(r"FLAGS \((?P<flags>[^)]*)\)")
_SIZE_RE = re.compile(r"RFC822\.SIZE (?P<size>\d+)")
_MAILBOX_RE = re.compile(r'^\((?P<attrs>[^)]*)\)\s+"(?P<delimiter>[^"]*)"\s+(?P<name>.+)$')


class ImapMailClient:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def list_mailboxes(self) -> list[dict[str, Any]]:
        self._require_ready()
        with self._connect() as client:
            status, data = client.list()
            _expect_ok(status, data, "list mailboxes")
            return [_parse_mailbox_line(item) for item in data or [] if item]

    def list_messages(
        self,
        *,
        mailbox: str = "INBOX",
        limit: int = 10,
        criteria: str = "ALL",
    ) -> list[dict[str, Any]]:
        self._require_ready()
        with self._connect() as client:
            with self._select_mailbox(client, mailbox):
                uids = _search_uids(client, criteria)
                selected_uids = list(reversed(uids[-limit:]))
                return [self._fetch_message_summary(client, uid) for uid in selected_uids]

    def get_message(
        self,
        *,
        mailbox: str = "INBOX",
        uid: str,
        body_preview_chars: int = 4000,
    ) -> dict[str, Any]:
        self._require_ready()
        with self._connect() as client:
            with self._select_mailbox(client, mailbox):
                return self._fetch_message(client, uid, body_preview_chars=body_preview_chars)

    def _fetch_message_summary(self, client: imaplib.IMAP4, uid: str) -> dict[str, Any]:
        status, data = client.uid(
            "fetch",
            uid,
            "(FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO DATE)])",
        )
        _expect_ok(status, data, f"fetch summary for UID {uid}")
        metadata_text, payload = _parse_fetch_data(data)
        message = email.message_from_bytes(payload, policy=policy.default)
        return {
            "uid": uid,
            "subject": _decode_header_value(message.get("Subject")),
            "from": _parse_address_header(message.get("From")),
            "to": _parse_address_header(message.get("To")),
            "date": _parse_date_header(message.get("Date")),
            "flags": _parse_flags(metadata_text),
            "size": _parse_size(metadata_text),
        }

    def _fetch_message(
        self,
        client: imaplib.IMAP4,
        uid: str,
        *,
        body_preview_chars: int,
    ) -> dict[str, Any]:
        status, data = client.uid("fetch", uid, "(FLAGS RFC822.SIZE BODY.PEEK[])")
        _expect_ok(status, data, f"fetch message for UID {uid}")
        metadata_text, payload = _parse_fetch_data(data)
        message = email.message_from_bytes(payload, policy=policy.default)
        text_body = _extract_text_body(message)
        html_body = _extract_html_body(message)
        return {
            "uid": uid,
            "subject": _decode_header_value(message.get("Subject")),
            "from": _parse_address_header(message.get("From")),
            "to": _parse_address_header(message.get("To")),
            "cc": _parse_address_header(message.get("Cc")),
            "reply_to": _parse_address_header(message.get("Reply-To")),
            "message_id": _decode_header_value(message.get("Message-Id")),
            "date": _parse_date_header(message.get("Date")),
            "flags": _parse_flags(metadata_text),
            "size": _parse_size(metadata_text),
            "text_body_preview": text_body[:body_preview_chars],
            "html_body_preview": html_body[:body_preview_chars],
            "has_attachments": _has_attachments(message),
        }

    @contextmanager
    def _connect(self) -> Iterator[imaplib.IMAP4]:
        if self._config.imap_use_tls:
            context = ssl.create_default_context()
            client = _Imap4SslWithServername(
                self._config.imap_tls_servername,
                self._config.imap_host,
                self._config.imap_port,
                ssl_context=context,
            )
        else:
            client = imaplib.IMAP4(self._config.imap_host, self._config.imap_port)
        try:
            status, data = client.login(self._config.imap_username, self._config.imap_password)
            _expect_ok(status, data, "log in")
            yield client
        finally:
            try:
                client.logout()
            except Exception:
                pass

    @contextmanager
    def _select_mailbox(self, client: imaplib.IMAP4, mailbox: str) -> Iterator[None]:
        status, data = client.select(mailbox, readonly=True)
        _expect_ok(status, data, f"select mailbox {mailbox}")
        try:
            yield
        finally:
            try:
                client.close()
            except Exception:
                pass

    def _require_ready(self) -> None:
        if not self._config.imap_ready():
            raise ValueError("IMAP configuration is incomplete")


def _search_uids(client: imaplib.IMAP4, criteria: str) -> list[str]:
    status, data = client.uid("search", None, criteria)
    _expect_ok(status, data, f"search messages with criteria {criteria}")
    if not data or not data[0]:
        return []
    return [item.decode("utf-8") for item in data[0].split()]


class _Imap4SslWithServername(imaplib.IMAP4_SSL):
    def __init__(
        self,
        tls_servername: str,
        host: str = "",
        port: int = imaplib.IMAP4_SSL_PORT,
        *,
        ssl_context: ssl.SSLContext | None = None,
        timeout: float | None = None,
    ) -> None:
        self._tls_servername = tls_servername
        super().__init__(host=host, port=port, ssl_context=ssl_context, timeout=timeout)

    def _create_socket(self, timeout: float | None):
        sock = imaplib.IMAP4._create_socket(self, timeout)
        return self.ssl_context.wrap_socket(sock, server_hostname=self._tls_servername)


def _parse_fetch_data(data: list[Any] | tuple[Any, ...] | None) -> tuple[str, bytes]:
    metadata_chunks: list[str] = []
    payload_chunks: list[bytes] = []
    for item in data or []:
        if isinstance(item, tuple):
            response, payload = item
            if isinstance(response, bytes):
                metadata_chunks.append(response.decode("utf-8", errors="replace"))
            if isinstance(payload, bytes):
                payload_chunks.append(payload)
        elif isinstance(item, bytes):
            metadata_chunks.append(item.decode("utf-8", errors="replace"))
    return " ".join(metadata_chunks), b"".join(payload_chunks)


def _parse_mailbox_line(raw_line: bytes) -> dict[str, Any]:
    decoded = raw_line.decode("utf-8", errors="replace")
    match = _MAILBOX_RE.match(decoded)
    if not match:
        return {"name": decoded, "attributes": [], "delimiter": None}
    attrs = [item for item in match.group("attrs").split() if item]
    name = match.group("name")
    if name.startswith('"') and name.endswith('"'):
        name = name[1:-1]
    return {
        "name": name,
        "attributes": attrs,
        "delimiter": match.group("delimiter"),
    }


def _parse_flags(metadata_text: str) -> list[str]:
    match = _FLAGS_RE.search(metadata_text)
    if not match:
        return []
    return [item for item in match.group("flags").split() if item]


def _parse_size(metadata_text: str) -> int | None:
    match = _SIZE_RE.search(metadata_text)
    if not match:
        return None
    return int(match.group("size"))


def _decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _parse_address_header(value: str | None) -> list[str]:
    if not value:
        return []
    return [address for _name, address in getaddresses([value]) if address]


def _parse_date_header(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).isoformat()
    except Exception:
        return value


def _extract_text_body(message: Message) -> str:
    parts: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_filename():
                continue
            if part.get_content_type() == "text/plain":
                parts.append(_safe_part_content(part))
    elif message.get_content_type() == "text/plain":
        parts.append(_safe_part_content(message))
    return "\n\n".join(item.strip() for item in parts if item.strip())


def _extract_html_body(message: Message) -> str:
    parts: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_filename():
                continue
            if part.get_content_type() == "text/html":
                parts.append(_safe_part_content(part))
    elif message.get_content_type() == "text/html":
        parts.append(_safe_part_content(message))
    return "\n\n".join(item.strip() for item in parts if item.strip())


def _safe_part_content(part: Message) -> str:
    try:
        content = part.get_content()
        if isinstance(content, str):
            return content
    except Exception:
        pass
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _has_attachments(message: Message) -> bool:
    for part in message.walk():
        if part.get_filename():
            return True
    return False


def _expect_ok(status: str, data: Any, action: str) -> None:
    if status == "OK":
        return
    details = _format_imap_data(data)
    raise ValueError(f"IMAP failed to {action}: {details}")


def _format_imap_data(data: Any) -> str:
    if data is None:
        return "no details"
    if isinstance(data, (list, tuple)):
        parts = []
        for item in data:
            if isinstance(item, bytes):
                parts.append(item.decode("utf-8", errors="replace"))
            else:
                parts.append(str(item))
        return " | ".join(parts)
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)
