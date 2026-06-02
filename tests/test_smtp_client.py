from __future__ import annotations

import smtplib
from pathlib import Path

from ubisam_mail_mcp.config import AppConfig
from ubisam_mail_mcp.models import MessageDraft
from ubisam_mail_mcp.smtp_client import SmtpMailSender, _close_smtp_session, _smtp_login


class FakeSmtpBase:
    instances: list["FakeSmtpBase"] = []

    def __init__(self, *args, **kwargs) -> None:
        self.logged_in = False
        self.sent = False
        self.closed = False
        self.started_tls = False
        self._host = kwargs.get("host", "")
        type(self).instances.append(self)

    def login(self, username: str, password: str) -> None:
        self.logged_in = True

    def send_message(self, message, to_addrs) -> None:
        self.sent = True

    def starttls(self, context) -> None:
        self.started_tls = True

    def docmd(self, command: str, args: str = ""):
        if command == "QUIT":
            return (503, b"you're already authenticated")
        if command == "AUTH" and args.startswith("PLAIN "):
            self.logged_in = True
            return (235, b"ok")
        raise AssertionError(f"unexpected command: {(command, args)}")

    def close(self) -> None:
        self.closed = True

    def ehlo_or_helo_if_needed(self) -> None:
        return None

    def has_extn(self, name: str) -> bool:
        return name.lower() == "auth"


class FakeSmtpSsl(FakeSmtpBase):
    pass


class FakeSmtpStarttls(FakeSmtpBase):
    pass


class FakeSmtpPlainSuccess(FakeSmtpBase):
    def docmd(self, command: str, args: str = ""):
        if command == "AUTH" and args.startswith("PLAIN "):
            self.logged_in = True
            return (235, b"ok")
        if command == "QUIT":
            return (250, b"flushed")
        raise AssertionError(f"unexpected command: {(command, args)}")


class FakeSmtpLoginFallback(FakeSmtpBase):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._step = 0

    def docmd(self, command: str, args: str = ""):
        if command == "AUTH" and args.startswith("PLAIN "):
            raise smtplib.SMTPAuthenticationError(535, b"authorization failed")
        if command == "AUTH" and args == "LOGIN":
            self._step = 1
            return (334, b"Username:")
        if self._step == 1:
            self._step = 2
            return (334, b"Password:")
        if self._step == 2:
            self._step = 3
            self.logged_in = True
            return (235, b"ok")
        if command == "QUIT":
            return (250, b"flushed")
        raise AssertionError(f"unexpected command: {(command, args)}")


def make_config(*, use_tls: bool, use_starttls: bool) -> AppConfig:
    return AppConfig(
        smtp_host="smtp.example.com",
        smtp_port=465 if use_tls else 587,
        smtp_username="user@example.com",
        smtp_password="secret",
        smtp_use_tls=use_tls,
        smtp_use_starttls=use_starttls,
        smtp_tls_servername="smtp.example.com",
        imap_host="imap.example.com",
        imap_port=993,
        imap_username="user@example.com",
        imap_password="secret",
        imap_use_tls=True,
        imap_tls_servername="imap.example.com",
        default_from_address="user@example.com",
        sqlite_path=Path("/tmp/mail.db"),
    )


def make_draft() -> MessageDraft:
    return MessageDraft(
        id="draft-1",
        subject="subject",
        from_address="user@example.com",
        to=["to@example.com"],
        cc=[],
        bcc=[],
        text_body="body",
        html_body="",
        status="draft",
        created_at=None,
        updated_at=None,
        scheduled_for=None,
        sent_at=None,
        last_error=None,
    )


def test_close_smtp_session_accepts_503_and_closes():
    smtp = FakeSmtpBase()

    _close_smtp_session(smtp)

    assert smtp.closed is True


def test_send_tls_tolerates_503_on_quit(monkeypatch):
    FakeSmtpSsl.instances.clear()
    monkeypatch.setattr("ubisam_mail_mcp.smtp_client._SmtpSslWithServername", FakeSmtpSsl)
    sender = SmtpMailSender(make_config(use_tls=True, use_starttls=False))

    sender.send(make_draft())

    smtp = FakeSmtpSsl.instances[0]
    assert smtp.logged_in is True
    assert smtp.sent is True
    assert smtp.closed is True


def test_send_starttls_tolerates_503_on_quit(monkeypatch):
    FakeSmtpStarttls.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtpStarttls)
    sender = SmtpMailSender(make_config(use_tls=False, use_starttls=True))

    sender.send(make_draft())

    smtp = FakeSmtpStarttls.instances[0]
    assert smtp.started_tls is True
    assert smtp.logged_in is True
    assert smtp.sent is True
    assert smtp.closed is True


def test_smtp_login_prefers_plain_auth():
    smtp = FakeSmtpPlainSuccess()

    code, _response = _smtp_login(smtp, "user@example.com", "secret")

    assert code == 235
    assert smtp.logged_in is True


def test_smtp_login_falls_back_to_login_challenge():
    smtp = FakeSmtpLoginFallback()

    code, _response = _smtp_login(smtp, "user@example.com", "secret")

    assert code == 235
    assert smtp.logged_in is True
