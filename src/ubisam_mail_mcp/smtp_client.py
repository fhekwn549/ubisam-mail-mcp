from __future__ import annotations

import base64
import mimetypes
import smtplib
import ssl
import sys
from datetime import datetime, timezone
from email.utils import format_datetime, formataddr, getaddresses, make_msgid
from email.message import EmailMessage

from .config import AppConfig
from .models import MessageDraft


class SmtpMailSender:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def send(self, draft: MessageDraft) -> None:
        message = build_email_message(draft, config=self._config)
        recipients = envelope_recipients(draft)
        if self._config.smtp_use_tls:
            _debug(
                self._config,
                f"connect mode=ssl host={self._config.smtp_host} port={self._config.smtp_port}",
            )
            smtp = _SmtpSslWithServername(
                self._config.smtp_tls_servername,
                self._config.smtp_host,
                self._config.smtp_port,
                timeout=30,
                context=ssl.create_default_context(),
            )
            try:
                _smtp_login(smtp, self._config.smtp_username, self._config.smtp_password, config=self._config)
                _debug(
                    self._config,
                    f"send_message recipients={len(recipients)} subject={draft.subject}",
                )
                smtp.send_message(message, to_addrs=recipients)
            except Exception as exc:
                _debug(self._config, f"error type={type(exc).__name__} detail={exc}")
                raise
            finally:
                _close_smtp_session(smtp)
            return

        _debug(
            self._config,
            f"connect mode=starttls host={self._config.smtp_host} port={self._config.smtp_port}",
        )
        smtp = smtplib.SMTP(self._config.smtp_host, self._config.smtp_port, timeout=30)
        try:
            if self._config.smtp_use_starttls:
                context = ssl.create_default_context()
                smtp._host = self._config.smtp_tls_servername
                _debug(
                    self._config,
                    f"starttls host={self._config.smtp_host} servername={self._config.smtp_tls_servername}",
                )
                smtp.starttls(context=context)
            _smtp_login(smtp, self._config.smtp_username, self._config.smtp_password, config=self._config)
            _debug(
                self._config,
                f"send_message recipients={len(recipients)} subject={draft.subject}",
            )
            smtp.send_message(message, to_addrs=recipients)
        except Exception as exc:
            _debug(self._config, f"error type={type(exc).__name__} detail={exc}")
            raise
        finally:
            _close_smtp_session(smtp)


def build_email_message(draft: MessageDraft, *, config: AppConfig | None = None) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = draft.subject
    contacts = config.load_contacts() if config is not None else {}
    from_name = draft.from_name.strip() or (
        config.default_from_name.strip() if config is not None else ""
    ) or contacts.get(draft.from_address.strip().lower(), "")
    message["From"] = _format_address(draft.from_address, from_name)
    message["To"] = ", ".join(_format_address_list(draft.to, contacts))
    if draft.cc:
        message["Cc"] = ", ".join(_format_address_list(draft.cc, contacts))
    if draft.reply_to:
        message["Reply-To"] = ", ".join(_format_address_list(draft.reply_to, contacts))
    if draft.in_reply_to:
        message["In-Reply-To"] = draft.in_reply_to
    if draft.references:
        message["References"] = " ".join(draft.references)
    message["Date"] = format_datetime(datetime.now(timezone.utc))
    message["Message-ID"] = make_msgid()
    if draft.text_body:
        message.set_content(draft.text_body)
    if draft.html_body:
        if not draft.text_body:
            message.set_content("HTML body attached. Use an HTML-capable client.")
        message.add_alternative(draft.html_body, subtype="html")
        html_part = message.get_payload()[-1]
        for inline_attachment in draft.inline_attachments:
            with inline_attachment.path.open("rb") as handle:
                payload = handle.read()
            maintype, subtype = _split_content_type(
                inline_attachment.content_type or _guess_content_type(inline_attachment.filename)
            )
            html_part.add_related(
                payload,
                maintype=maintype,
                subtype=subtype,
                cid=f"<{inline_attachment.cid}>",
                filename=inline_attachment.filename,
                disposition="inline",
            )
    for attachment in draft.attachments:
        with attachment.path.open("rb") as handle:
            payload = handle.read()
        maintype, subtype = _split_content_type(attachment.content_type or _guess_content_type(attachment.filename))
        message.add_attachment(
            payload,
            maintype=maintype,
            subtype=subtype,
            filename=attachment.filename,
        )
    return message


def envelope_recipients(draft: MessageDraft) -> list[str]:
    addresses = [address for _name, address in getaddresses([*draft.to, *draft.cc, *draft.bcc])]
    return [address.strip() for address in addresses if address.strip()]


def _format_address_list(addresses: list[str], contacts: dict[str, str]) -> list[str]:
    return [_format_single_address(value, contacts) for value in addresses]


def _format_single_address(value: str, contacts: dict[str, str]) -> str:
    parsed = getaddresses([value])
    if not parsed:
        return value
    display_name, address = parsed[0]
    if not address:
        return value
    final_name = display_name.strip() or contacts.get(address.strip().lower(), "")
    return _format_address(address, final_name)


def _format_address(address: str, display_name: str) -> str:
    if display_name.strip():
        return formataddr((display_name.strip(), address.strip()))
    return address.strip()


class _SmtpSslWithServername(smtplib.SMTP_SSL):
    def __init__(self, tls_servername: str, *args, **kwargs) -> None:
        self._tls_servername = tls_servername
        super().__init__(*args, **kwargs)

    def _get_socket(self, host, port, timeout):
        if self.debuglevel > 0:
            self._print_debug("connect:", (host, port))
        new_socket = super(smtplib.SMTP_SSL, self)._get_socket(host, port, timeout)
        return self.context.wrap_socket(new_socket, server_hostname=self._tls_servername)


def _smtp_login(
    smtp: smtplib.SMTP,
    username: str,
    password: str,
    *,
    config: AppConfig | None = None,
) -> tuple[int, bytes]:
    smtp.ehlo_or_helo_if_needed()
    if not smtp.has_extn("auth"):
        raise smtplib.SMTPNotSupportedError("SMTP AUTH extension not supported by server.")

    plain_token = base64.b64encode(f"\0{username}\0{password}".encode("utf-8")).decode("ascii")
    try:
        if config is not None:
            _debug(config, f"auth method=plain username={username}")
        return smtp.docmd("AUTH", f"PLAIN {plain_token}")
    except smtplib.SMTPAuthenticationError as exc:
        plain_error = exc
    except smtplib.SMTPResponseException as exc:
        if exc.smtp_code in (235, 503):
            return exc.smtp_code, exc.smtp_error
        plain_error = smtplib.SMTPAuthenticationError(exc.smtp_code, exc.smtp_error)
    else:
        return 235, b"ok"

    username_token = base64.b64encode(username.encode("utf-8")).decode("ascii")
    password_token = base64.b64encode(password.encode("utf-8")).decode("ascii")
    try:
        if config is not None:
            _debug(config, f"auth method=login username={username}")
        code, response = smtp.docmd("AUTH", "LOGIN")
        if code != 334:
            raise smtplib.SMTPAuthenticationError(code, response)
        code, response = smtp.docmd(username_token)
        if code != 334:
            raise smtplib.SMTPAuthenticationError(code, response)
        code, response = smtp.docmd(password_token)
        if code not in (235, 503):
            raise smtplib.SMTPAuthenticationError(code, response)
        return code, response
    except smtplib.SMTPAuthenticationError:
        raise plain_error


def _close_smtp_session(smtp: smtplib.SMTP) -> None:
    try:
        smtp.docmd("QUIT")
    except (smtplib.SMTPServerDisconnected, smtplib.SMTPResponseException, smtplib.SMTPException):
        pass
    finally:
        smtp.close()


def _debug(config: AppConfig, message: str) -> None:
    if not config.smtp_debug:
        return
    print(f"smtp-debug {message}", file=sys.stderr)


def _guess_content_type(filename: str) -> str:
    content_type, _encoding = mimetypes.guess_type(filename)
    return content_type or "application/octet-stream"


def _split_content_type(content_type: str) -> tuple[str, str]:
    if "/" not in content_type:
        return "application", "octet-stream"
    maintype, subtype = content_type.split("/", 1)
    return maintype, subtype
