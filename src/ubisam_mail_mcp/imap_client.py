from __future__ import annotations

import email
import imaplib
import re
import ssl
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email import policy
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterator

from .config import AppConfig
from .models import MessageDraft
from .smtp_client import build_email_message

_FLAGS_RE = re.compile(r"FLAGS \((?P<flags>[^)]*)\)")
_SIZE_RE = re.compile(r"RFC822\.SIZE (?P<size>\d+)")
_MAILBOX_RE = re.compile(r'^\((?P<attrs>[^)]*)\)\s+"(?P<delimiter>[^"]*)"\s+(?P<name>.+)$')
_APPENDUID_RE = re.compile(r"APPENDUID (?P<uidvalidity>\d+) (?P<uid>\d+)")


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

    def get_unread_status(
        self,
        *,
        mailbox: str = "INBOX",
        sample_limit: int = 10,
    ) -> dict[str, Any]:
        self._require_ready()
        with self._connect() as client:
            with self._select_mailbox(client, mailbox):
                unread_uids = _search_uids(client, "UNSEEN")
                selected_uids = list(reversed(unread_uids[-sample_limit:])) if sample_limit else []
                return {
                    "mailbox": mailbox,
                    "has_unread": bool(unread_uids),
                    "unread_count": len(unread_uids),
                    "latest_unread_messages": [
                        self._fetch_message_summary(client, uid) for uid in selected_uids
                    ],
                }

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

    def get_reply_context(
        self,
        *,
        mailbox: str = "INBOX",
        uid: str,
    ) -> dict[str, Any]:
        self._require_ready()
        with self._connect() as client:
            with self._select_mailbox(client, mailbox):
                status, data = client.uid("fetch", uid, "(FLAGS RFC822.SIZE BODY.PEEK[])")
                _expect_ok(status, data, f"fetch message for UID {uid}")
                metadata_text, payload = _parse_fetch_data(data)
                message = email.message_from_bytes(payload, policy=policy.default)
                flags = _parse_flags(metadata_text)
                return {
                    "uid": uid,
                    "subject": _decode_header_value(message.get("Subject")),
                    "from": _parse_address_header(message.get("From")),
                    "to": _parse_address_header(message.get("To")),
                    "cc": _parse_address_header(message.get("Cc")),
                    "reply_to": _parse_address_header(message.get("Reply-To")),
                    "references": _parse_message_ids_header(message.get("References")),
                    "message_id": _decode_header_value(message.get("Message-Id")),
                    "date": _parse_date_header(message.get("Date")),
                    "flags": flags,
                    "is_unread": _is_unread(flags),
                    "text_body": _extract_text_body(message),
                    "html_body": _extract_html_body(message),
                }

    def search_messages(
        self,
        *,
        mailbox: str = "INBOX",
        limit: int = 20,
        subject_contains: str = "",
        from_contains: str = "",
        to_contains: str = "",
        body_contains: str = "",
        is_unread: bool | None = None,
        has_attachments: bool | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[dict[str, Any]]:
        self._require_ready()
        terms = _build_search_terms(
            subject_contains=subject_contains,
            from_contains=from_contains,
            to_contains=to_contains,
            body_contains=body_contains,
            is_unread=is_unread,
            date_from=date_from,
            date_to=date_to,
        )
        with self._connect() as client:
            with self._select_mailbox(client, mailbox):
                uids = _search_uids_with_terms(client, terms)
                selected_uids = list(reversed(uids[-limit:]))
                messages = [self._fetch_message_summary(client, uid) for uid in selected_uids]
                if has_attachments is None:
                    return messages
                filtered: list[dict[str, Any]] = []
                for message in messages:
                    status, data = client.uid("fetch", message["uid"], "(BODYSTRUCTURE FLAGS RFC822.SIZE)")
                    _expect_ok(status, data, f"fetch bodystructure for UID {message['uid']}")
                    details = _format_imap_data(data)
                    message["has_attachments"] = _bodystructure_has_attachments(details)
                    if message["has_attachments"] is has_attachments:
                        filtered.append(message)
                return filtered

    def upload_draft(
        self,
        *,
        draft: MessageDraft,
        mailbox: str | None = None,
    ) -> dict[str, Any]:
        self._require_ready()
        with self._connect() as client:
            resolved_mailbox = mailbox or self._find_special_use_mailbox(client, "\\Drafts")
            if not resolved_mailbox:
                raise ValueError("IMAP drafts mailbox could not be found")
            message = build_email_message(draft, config=self._config)
            timestamp = draft.updated_at or draft.created_at or datetime.now(timezone.utc)
            internaldate = imaplib.Time2Internaldate(timestamp)
            status, data = client.append(
                resolved_mailbox,
                "(\\Draft)",
                internaldate,
                message.as_bytes(policy=policy.SMTP),
            )
            _expect_ok(status, data, f"append draft to mailbox {resolved_mailbox}")
            append_uid = _parse_append_uid(data)
            return {
                "mailbox": resolved_mailbox,
                "append_uid": append_uid,
                "subject": draft.subject,
            }

    def create_mailbox(self, *, mailbox: str) -> dict[str, Any]:
        self._require_ready()
        with self._connect() as client:
            status, data = client.create(mailbox)
            _expect_ok(status, data, f"create mailbox {mailbox}")
            return {"mailbox": mailbox, "created": True}

    def set_message_read_status(
        self,
        *,
        mailbox: str = "INBOX",
        uids: list[str],
        is_unread: bool,
    ) -> dict[str, Any]:
        self._require_ready()
        uid_set = _join_uid_set(uids)
        with self._connect() as client:
            with self._select_mailbox(client, mailbox, readonly=False):
                command = "-FLAGS.SILENT" if is_unread else "+FLAGS.SILENT"
                status, data = client.uid("store", uid_set, command, "(\\Seen)")
                _expect_ok(status, data, f"update read status for UIDs {uid_set}")
                return {
                    "mailbox": mailbox,
                    "uids": uids,
                    "is_unread": is_unread,
                    "updated": len(uids),
                }

    def move_messages(
        self,
        *,
        from_mailbox: str,
        to_mailbox: str,
        uids: list[str],
    ) -> dict[str, Any]:
        self._require_ready()
        uid_set = _join_uid_set(uids)
        with self._connect() as client:
            with self._select_mailbox(client, from_mailbox, readonly=False):
                status, data = client.uid("MOVE", uid_set, to_mailbox)
                if status != "OK":
                    copy_status, copy_data = client.uid("COPY", uid_set, to_mailbox)
                    _expect_ok(copy_status, copy_data, f"copy UIDs {uid_set} to mailbox {to_mailbox}")
                    delete_status, delete_data = client.uid("store", uid_set, "+FLAGS.SILENT", "(\\Deleted)")
                    _expect_ok(delete_status, delete_data, f"mark UIDs {uid_set} deleted")
                    expunge_status, expunge_data = client.expunge()
                    _expect_ok(expunge_status, expunge_data, f"expunge moved UIDs {uid_set}")
                return {
                    "from_mailbox": from_mailbox,
                    "to_mailbox": to_mailbox,
                    "uids": uids,
                    "moved": len(uids),
                }

    def copy_messages(
        self,
        *,
        from_mailbox: str,
        to_mailbox: str,
        uids: list[str],
    ) -> dict[str, Any]:
        self._require_ready()
        uid_set = _join_uid_set(uids)
        with self._connect() as client:
            with self._select_mailbox(client, from_mailbox, readonly=True):
                copy_status, copy_data = client.uid("COPY", uid_set, to_mailbox)
                _expect_ok(copy_status, copy_data, f"copy UIDs {uid_set} to mailbox {to_mailbox}")
                return {
                    "from_mailbox": from_mailbox,
                    "to_mailbox": to_mailbox,
                    "uids": uids,
                    "copied": len(uids),
                }

    def delete_messages(
        self,
        *,
        mailbox: str,
        uids: list[str],
    ) -> dict[str, Any]:
        trash_mailbox = None
        with self._connect() as client:
            trash_mailbox = self._find_special_use_mailbox(client, "\\Trash")
        if trash_mailbox and trash_mailbox != mailbox:
            moved = self.move_messages(from_mailbox=mailbox, to_mailbox=trash_mailbox, uids=uids)
            return {
                "mailbox": mailbox,
                "trash_mailbox": trash_mailbox,
                "uids": uids,
                "deleted": moved["moved"],
                "method": "move-to-trash",
            }
        self._require_ready()
        uid_set = _join_uid_set(uids)
        with self._connect() as client:
            with self._select_mailbox(client, mailbox, readonly=False):
                status, data = client.uid("store", uid_set, "+FLAGS.SILENT", "(\\Deleted)")
                _expect_ok(status, data, f"mark UIDs {uid_set} deleted")
                expunge_status, expunge_data = client.expunge()
                _expect_ok(expunge_status, expunge_data, f"expunge deleted UIDs {uid_set}")
                return {
                    "mailbox": mailbox,
                    "trash_mailbox": None,
                    "uids": uids,
                    "deleted": len(uids),
                    "method": "mark-deleted-expunge",
                }

    def download_attachment(
        self,
        *,
        mailbox: str = "INBOX",
        uid: str,
        attachment_index: int,
        target_path: str | None = None,
    ) -> dict[str, Any]:
        self._require_ready()
        with self._connect() as client:
            with self._select_mailbox(client, mailbox):
                status, data = client.uid("fetch", uid, "(BODY.PEEK[])")
                _expect_ok(status, data, f"fetch message for UID {uid}")
                _metadata_text, payload = _parse_fetch_data(data)
                message = email.message_from_bytes(payload, policy=policy.default)
                attachments = _extract_attachments(message)
                try:
                    attachment = attachments[attachment_index]
                except IndexError as exc:
                    raise ValueError(f"attachment_index out of range: {attachment_index}") from exc
                destination = self._resolve_download_path(
                    uid=uid,
                    attachment_filename=attachment.filename,
                    target_path=target_path,
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(attachment.payload)
                return {
                    "uid": uid,
                    "attachment": attachment.to_dict(include_payload=False),
                    "saved_to": str(destination.resolve()),
                }

    def _fetch_message_summary(self, client: imaplib.IMAP4, uid: str) -> dict[str, Any]:
        status, data = client.uid(
            "fetch",
            uid,
            "(FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO DATE)])",
        )
        _expect_ok(status, data, f"fetch summary for UID {uid}")
        metadata_text, payload = _parse_fetch_data(data)
        message = email.message_from_bytes(payload, policy=policy.default)
        flags = _parse_flags(metadata_text)
        return {
            "uid": uid,
            "subject": _decode_header_value(message.get("Subject")),
            "from": _parse_address_header(message.get("From")),
            "to": _parse_address_header(message.get("To")),
            "date": _parse_date_header(message.get("Date")),
            "flags": flags,
            "is_unread": _is_unread(flags),
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
        attachments = _extract_attachments(message)
        flags = _parse_flags(metadata_text)
        return {
            "uid": uid,
            "subject": _decode_header_value(message.get("Subject")),
            "from": _parse_address_header(message.get("From")),
            "to": _parse_address_header(message.get("To")),
            "cc": _parse_address_header(message.get("Cc")),
            "reply_to": _parse_address_header(message.get("Reply-To")),
            "message_id": _decode_header_value(message.get("Message-Id")),
            "date": _parse_date_header(message.get("Date")),
            "flags": flags,
            "is_unread": _is_unread(flags),
            "size": _parse_size(metadata_text),
            "text_body_preview": text_body[:body_preview_chars],
            "html_body_preview": html_body[:body_preview_chars],
            "has_attachments": bool(attachments),
            "attachments": [attachment.to_dict(include_payload=False) for attachment in attachments],
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
    def _select_mailbox(self, client: imaplib.IMAP4, mailbox: str, *, readonly: bool = True) -> Iterator[None]:
        status, data = client.select(mailbox, readonly=readonly)
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

    def _resolve_download_path(
        self,
        *,
        uid: str,
        attachment_filename: str,
        target_path: str | None,
    ) -> Path:
        if target_path:
            return Path(target_path).expanduser()
        # attachment_filename is attacker-controlled (set by the message sender).
        # Strip any directory components so a crafted name like "../../x" or an
        # absolute path cannot escape the configured download directory.
        safe_name = Path(attachment_filename.replace("\\", "/")).name
        if not safe_name or safe_name in {".", ".."}:
            safe_name = f"uid_{uid}_attachment"
        base = self._config.attachment_download_dir.expanduser().resolve()
        destination = (base / f"uid_{uid}" / safe_name).resolve()
        if not destination.is_relative_to(base):
            raise ValueError("resolved attachment path escapes the download directory")
        return destination

    def _find_special_use_mailbox(self, client: imaplib.IMAP4, special_use_attr: str) -> str | None:
        status, data = client.list()
        _expect_ok(status, data, "list mailboxes")
        normalized_attr = special_use_attr.lower()
        for item in data or []:
            if not item:
                continue
            mailbox = _parse_mailbox_line(item)
            attributes = [str(value).lower() for value in mailbox.get("attributes", [])]
            if normalized_attr in attributes:
                return str(mailbox["name"])
        return None


def _search_uids(client: imaplib.IMAP4, criteria: str) -> list[str]:
    status, data = client.uid("search", None, criteria)
    _expect_ok(status, data, f"search messages with criteria {criteria}")
    if not data or not data[0]:
        return []
    return [item.decode("utf-8") for item in data[0].split()]


def _search_uids_with_terms(client: imaplib.IMAP4, terms: list[str]) -> list[str]:
    status, data = client.uid("search", None, *terms)
    _expect_ok(status, data, f"search messages with terms {' '.join(terms)}")
    if not data or not data[0]:
        return []
    return [item.decode("utf-8") for item in data[0].split()]


def _is_unread(flags: list[str]) -> bool:
    return "\\Seen" not in flags


def _parse_append_uid(data: list[Any] | tuple[Any, ...] | None) -> str | None:
    details = _format_imap_data(data)
    match = _APPENDUID_RE.search(details)
    if not match:
        return None
    return match.group("uid")


def _imap_quote(value: str) -> str:
    # IMAP quoted-string: backslash and double-quote must be escaped so a
    # crafted search term cannot break out and inject extra search keys.
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _build_search_terms(
    *,
    subject_contains: str,
    from_contains: str,
    to_contains: str,
    body_contains: str,
    is_unread: bool | None,
    date_from: date | None,
    date_to: date | None,
) -> list[str]:
    terms: list[str] = ["ALL"]
    if subject_contains.strip():
        terms.extend(["SUBJECT", _imap_quote(subject_contains.strip())])
    if from_contains.strip():
        terms.extend(["FROM", _imap_quote(from_contains.strip())])
    if to_contains.strip():
        terms.extend(["TO", _imap_quote(to_contains.strip())])
    if body_contains.strip():
        terms.extend(["TEXT", _imap_quote(body_contains.strip())])
    if is_unread is True:
        terms.append("UNSEEN")
    elif is_unread is False:
        terms.append("SEEN")
    if date_from is not None:
        terms.extend(["SINCE", _format_imap_date(date_from)])
    if date_to is not None:
        terms.extend(["BEFORE", _format_imap_date(date_to + timedelta(days=1))])
    return terms


def _format_imap_date(value: date) -> str:
    return value.strftime("%d-%b-%Y")


def _join_uid_set(uids: list[str]) -> str:
    cleaned = [uid.strip() for uid in uids if uid.strip()]
    if not cleaned:
        raise ValueError("at least one uid is required")
    return ",".join(cleaned)


def _bodystructure_has_attachments(details: str) -> bool:
    upper = details.upper()
    return '("ATTACHMENT"' in upper or '("INLINE"' in upper


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


@dataclass(slots=True)
class _MessageAttachment:
    index: int
    filename: str
    content_type: str
    size_bytes: int
    payload: bytes

    def to_dict(self, *, include_payload: bool) -> dict[str, Any]:
        data = {
            "index": self.index,
            "filename": self.filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
        }
        if include_payload:
            data["payload"] = self.payload
        return data


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


def _parse_message_ids_header(value: str | None) -> list[str]:
    if not value:
        return []
    return re.findall(r"<[^>]+>", value)


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


def _extract_attachments(message: Message) -> list[_MessageAttachment]:
    attachments: list[_MessageAttachment] = []
    for part in message.walk():
        filename = part.get_filename()
        if not filename:
            continue
        payload = part.get_payload(decode=True) or b""
        attachments.append(
            _MessageAttachment(
                index=len(attachments),
                filename=_decode_header_value(filename),
                content_type=part.get_content_type(),
                size_bytes=len(payload),
                payload=payload,
            )
        )
    return attachments


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
