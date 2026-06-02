from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from .config import AppConfig
from .models import MessageDraft
from .repository import DraftRepository


class MailSender(Protocol):
    def send(self, draft: MessageDraft) -> None:
        ...


@dataclass(slots=True)
class MailService:
    repository: DraftRepository
    sender: MailSender
    config: AppConfig

    def create_draft(
        self,
        *,
        subject: str,
        to: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        text_body: str = "",
        html_body: str = "",
        from_address: str | None = None,
    ) -> MessageDraft:
        draft = MessageDraft(
            id=str(uuid.uuid4()),
            subject=subject,
            to=to,
            cc=cc or [],
            bcc=bcc or [],
            text_body=text_body,
            html_body=html_body,
            from_address=from_address or self.config.default_from_address,
            status="draft",
        )
        draft.validate()
        return self.repository.upsert(draft)

    def update_draft(self, draft_id: str, **updates: object) -> MessageDraft:
        draft = self.require_draft(draft_id)
        if draft.status == "sent":
            raise ValueError("sent draft cannot be modified")
        for field_name, value in updates.items():
            if value is not None and hasattr(draft, field_name):
                setattr(draft, field_name, value)
        draft.validate()
        return self.repository.upsert(draft)

    def schedule_draft(self, draft_id: str, scheduled_for: datetime) -> MessageDraft:
        draft = self.require_draft(draft_id)
        if draft.status == "sent":
            raise ValueError("sent draft cannot be scheduled")
        scheduled_utc = scheduled_for.astimezone(timezone.utc)
        if scheduled_utc <= datetime.now(timezone.utc):
            raise ValueError("scheduled_for must be in the future")
        draft.status = "scheduled"
        draft.scheduled_for = scheduled_utc
        draft.last_error = None
        draft.validate()
        return self.repository.upsert(draft)

    def send_draft_now(self, draft_id: str) -> MessageDraft:
        draft = self.require_draft(draft_id)
        return self._send(draft)

    def dispatch_due_messages(self) -> list[MessageDraft]:
        due = self.repository.list_due(before=datetime.now(timezone.utc))
        sent: list[MessageDraft] = []
        for draft in due:
            sent.append(self._send(draft))
        return sent

    def require_draft(self, draft_id: str) -> MessageDraft:
        draft = self.repository.get(draft_id)
        if draft is None:
            raise ValueError(f"draft not found: {draft_id}")
        return draft

    def _send(self, draft: MessageDraft) -> MessageDraft:
        if not self.config.smtp_ready():
            raise ValueError("SMTP configuration is incomplete")
        draft.validate()
        draft.status = "sending"
        draft.last_error = None
        self.repository.upsert(draft)
        try:
            self.sender.send(draft)
        except Exception as exc:
            draft.status = "failed"
            draft.last_error = str(exc)
            self.repository.upsert(draft)
            raise
        draft.status = "sent"
        draft.sent_at = datetime.now(timezone.utc)
        draft.scheduled_for = None
        draft.last_error = None
        return self.repository.upsert(draft)
