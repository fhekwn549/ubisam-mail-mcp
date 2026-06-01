from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hanbiro_mail_mcp.config import AppConfig
from hanbiro_mail_mcp.repository import DraftRepository
from hanbiro_mail_mcp.service import MailService


class FakeSender:
    def __init__(self) -> None:
        self.sent_ids: list[str] = []

    def send(self, draft) -> None:
        self.sent_ids.append(draft.id)


def make_service(tmp_path):
    config = AppConfig(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="user",
        smtp_password="pass",
        smtp_use_tls=False,
        smtp_use_starttls=True,
        smtp_tls_servername="smtp.example.com",
        imap_host="imap.example.com",
        imap_port=993,
        imap_username="user",
        imap_password="pass",
        imap_use_tls=True,
        imap_tls_servername="imap.example.com",
        default_from_address="bot@example.com",
        sqlite_path=tmp_path / "mail.db",
    )
    sender = FakeSender()
    service = MailService(
        repository=DraftRepository(config.sqlite_path),
        sender=sender,
        config=config,
    )
    return service, sender


def test_create_draft_persists(tmp_path):
    service, _sender = make_service(tmp_path)

    draft = service.create_draft(
        subject="hello",
        to=["user@example.com"],
        text_body="body",
    )

    loaded = service.require_draft(draft.id)
    assert loaded.subject == "hello"
    assert loaded.status == "draft"
    assert loaded.from_address == "bot@example.com"


def test_schedule_draft_changes_status(tmp_path):
    service, _sender = make_service(tmp_path)
    draft = service.create_draft(
        subject="scheduled",
        to=["user@example.com"],
        text_body="body",
    )

    scheduled = service.schedule_draft(
        draft.id,
        datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    assert scheduled.status == "scheduled"
    assert scheduled.scheduled_for is not None


def test_send_draft_now_marks_sent(tmp_path):
    service, sender = make_service(tmp_path)
    draft = service.create_draft(
        subject="send now",
        to=["user@example.com"],
        text_body="body",
    )

    sent = service.send_draft_now(draft.id)

    assert sent.status == "sent"
    assert sent.sent_at is not None
    assert sender.sent_ids == [draft.id]


def test_dispatch_due_messages_sends_only_due(tmp_path):
    service, sender = make_service(tmp_path)
    due = service.create_draft(
        subject="due",
        to=["due@example.com"],
        text_body="body",
    )
    later = service.create_draft(
        subject="later",
        to=["later@example.com"],
        text_body="body",
    )
    service.schedule_draft(due.id, datetime.now(timezone.utc) + timedelta(seconds=1))
    service.schedule_draft(later.id, datetime.now(timezone.utc) + timedelta(hours=1))

    repo = service.repository
    due_draft = repo.get(due.id)
    assert due_draft is not None
    due_draft.scheduled_for = datetime.now(timezone.utc) - timedelta(seconds=1)
    repo.upsert(due_draft)

    sent = service.dispatch_due_messages()

    assert [item.id for item in sent] == [due.id]
    assert sender.sent_ids == [due.id]
