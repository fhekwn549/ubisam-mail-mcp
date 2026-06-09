from __future__ import annotations

import smtplib
from io import StringIO
from pathlib import Path

from ubisam_mail_mcp.config import AppConfig
from ubisam_mail_mcp.models import DraftAttachment, InlineAttachment, MessageDraft
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
        self.message = message

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
        default_from_name="",
        sqlite_path=Path("/tmp/mail.db"),
        attachment_download_dir=Path("/tmp/downloads"),
        contacts_path=Path("/tmp/contacts.local.json"),
        smtp_debug=False,
    )


def make_draft() -> MessageDraft:
    return MessageDraft(
        id="draft-1",
        subject="subject",
        from_address="user@example.com",
        from_name="",
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


def make_attachment(tmp_path: Path) -> DraftAttachment:
    path = tmp_path / "hello.txt"
    path.write_text("attachment body", encoding="utf-8")
    return DraftAttachment(
        id="att-1",
        file_path=str(path),
        filename="hello.txt",
        content_type="text/plain",
        size_bytes=len("attachment body".encode("utf-8")),
    )


def make_inline_attachment(tmp_path: Path) -> InlineAttachment:
    path = tmp_path / "logo.png"
    path.write_bytes(
        bytes.fromhex(
            "89504E470D0A1A0A"
            "0000000D49484452000000010000000108060000001F15C489"
            "0000000D49444154789C6360000002000154A24F5D00000000"
            "49454E44AE426082"
        )
    )
    return InlineAttachment(
        cid="profile-logo-1",
        file_path=str(path),
        filename="logo.png",
        content_type="image/png",
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


def test_send_includes_attachments(monkeypatch, tmp_path):
    FakeSmtpStarttls.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtpStarttls)
    sender = SmtpMailSender(make_config(use_tls=False, use_starttls=True))
    draft = make_draft()
    draft.attachments = [make_attachment(tmp_path)]

    sender.send(draft)

    smtp = FakeSmtpStarttls.instances[0]
    attachments = list(smtp.message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "hello.txt"
    assert attachments[0].get_content_type() == "text/plain"


def test_send_includes_inline_html_related_images(monkeypatch, tmp_path):
    FakeSmtpStarttls.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtpStarttls)
    sender = SmtpMailSender(make_config(use_tls=False, use_starttls=True))
    draft = make_draft()
    draft.html_body = '<p><img src="cid:profile-logo-1"></p>'
    draft.inline_attachments = [make_inline_attachment(tmp_path)]

    sender.send(draft)

    smtp = FakeSmtpStarttls.instances[0]
    html_part = smtp.message.get_payload()[-1]
    related_parts = html_part.get_payload()[1:]
    assert len(related_parts) == 1
    assert related_parts[0].get_filename() == "logo.png"
    assert related_parts[0]["Content-ID"] == "<profile-logo-1>"


def test_send_logs_smtp_steps_when_debug_enabled(monkeypatch):
    FakeSmtpStarttls.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtpStarttls)
    config = make_config(use_tls=False, use_starttls=True)
    config.smtp_debug = True
    sender = SmtpMailSender(config)
    stderr = StringIO()
    monkeypatch.setattr("sys.stderr", stderr)

    sender.send(make_draft())

    log_output = stderr.getvalue()
    assert "smtp-debug connect mode=starttls host=smtp.example.com port=587" in log_output
    assert "smtp-debug starttls host=smtp.example.com servername=smtp.example.com" in log_output
    assert "smtp-debug auth method=plain username=user@example.com" in log_output
    assert "smtp-debug send_message recipients=1 subject_len=" in log_output
    assert "subject=subject" not in log_output


def test_send_formats_from_and_recipient_display_names(monkeypatch, tmp_path):
    contacts_path = tmp_path / "contacts.local.json"
    contacts_path.write_text(
        '{"contacts":[{"name":"김철수","email":"to@example.com"},{"name":"홍길동","email":"user@example.com"}]}',
        encoding="utf-8",
    )
    FakeSmtpStarttls.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtpStarttls)
    config = make_config(use_tls=False, use_starttls=True)
    config.contacts_path = contacts_path
    config.default_from_name = "홍길동"
    sender = SmtpMailSender(config)
    draft = make_draft()

    sender.send(draft)

    smtp = FakeSmtpStarttls.instances[0]
    assert smtp.message["From"] == "홍길동 <user@example.com>"
    assert smtp.message["To"] == "김철수 <to@example.com>"


def test_send_includes_reply_thread_headers(monkeypatch):
    FakeSmtpStarttls.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtpStarttls)
    sender = SmtpMailSender(make_config(use_tls=False, use_starttls=True))
    draft = make_draft()
    draft.reply_to = ["reply@example.com"]
    draft.in_reply_to = "<msg-1@example.com>"
    draft.references = ["<msg-0@example.com>", "<msg-1@example.com>"]

    sender.send(draft)

    smtp = FakeSmtpStarttls.instances[0]
    assert smtp.message["Reply-To"] == "reply@example.com"
    assert smtp.message["In-Reply-To"] == "<msg-1@example.com>"
    assert smtp.message["References"] == "<msg-0@example.com> <msg-1@example.com>"


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
