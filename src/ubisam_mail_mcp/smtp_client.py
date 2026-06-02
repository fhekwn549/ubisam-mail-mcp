from __future__ import annotations

import base64
import smtplib
import ssl
from email.message import EmailMessage

from .config import AppConfig
from .models import MessageDraft


class SmtpMailSender:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def send(self, draft: MessageDraft) -> None:
        message = EmailMessage()
        message["Subject"] = draft.subject
        message["From"] = draft.from_address
        message["To"] = ", ".join(draft.to)
        if draft.cc:
            message["Cc"] = ", ".join(draft.cc)
        if draft.text_body:
            message.set_content(draft.text_body)
        if draft.html_body:
            if not draft.text_body:
                message.set_content("HTML body attached. Use an HTML-capable client.")
            message.add_alternative(draft.html_body, subtype="html")

        recipients = draft.to + draft.cc + draft.bcc
        if self._config.smtp_use_tls:
            smtp = _SmtpSslWithServername(
                self._config.smtp_tls_servername,
                self._config.smtp_host,
                self._config.smtp_port,
                timeout=30,
                context=ssl.create_default_context(),
            )
            try:
                _smtp_login(smtp, self._config.smtp_username, self._config.smtp_password)
                smtp.send_message(message, to_addrs=recipients)
            finally:
                _close_smtp_session(smtp)
            return

        smtp = smtplib.SMTP(self._config.smtp_host, self._config.smtp_port, timeout=30)
        try:
            if self._config.smtp_use_starttls:
                context = ssl.create_default_context()
                smtp._host = self._config.smtp_tls_servername
                smtp.starttls(context=context)
            _smtp_login(smtp, self._config.smtp_username, self._config.smtp_password)
            smtp.send_message(message, to_addrs=recipients)
        finally:
            _close_smtp_session(smtp)


class _SmtpSslWithServername(smtplib.SMTP_SSL):
    def __init__(self, tls_servername: str, *args, **kwargs) -> None:
        self._tls_servername = tls_servername
        super().__init__(*args, **kwargs)

    def _get_socket(self, host, port, timeout):
        if self.debuglevel > 0:
            self._print_debug("connect:", (host, port))
        new_socket = super(smtplib.SMTP_SSL, self)._get_socket(host, port, timeout)
        return self.context.wrap_socket(new_socket, server_hostname=self._tls_servername)


def _smtp_login(smtp: smtplib.SMTP, username: str, password: str) -> tuple[int, bytes]:
    smtp.ehlo_or_helo_if_needed()
    if not smtp.has_extn("auth"):
        raise smtplib.SMTPNotSupportedError("SMTP AUTH extension not supported by server.")

    plain_token = base64.b64encode(f"\0{username}\0{password}".encode("utf-8")).decode("ascii")
    try:
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
