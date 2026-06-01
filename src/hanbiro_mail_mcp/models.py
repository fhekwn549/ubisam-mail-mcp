from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


VALID_STATUSES = {"draft", "scheduled", "sending", "sent", "failed"}


@dataclass(slots=True)
class MessageDraft:
    id: str
    subject: str
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    text_body: str = ""
    html_body: str = ""
    from_address: str = ""
    status: str = "draft"
    scheduled_for: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    sent_at: datetime | None = None
    last_error: str | None = None

    def validate(self) -> None:
        if not self.subject.strip():
            raise ValueError("subject is required")
        if not self.to:
            raise ValueError("at least one recipient is required")
        if not (self.text_body or self.html_body):
            raise ValueError("text_body or html_body is required")
        if self.status not in VALID_STATUSES:
            raise ValueError(f"invalid status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "to": self.to,
            "cc": self.cc,
            "bcc": self.bcc,
            "text_body": self.text_body,
            "html_body": self.html_body,
            "from_address": self.from_address,
            "status": self.status,
            "scheduled_for": _datetime_to_iso(self.scheduled_for),
            "created_at": _datetime_to_iso(self.created_at),
            "updated_at": _datetime_to_iso(self.updated_at),
            "sent_at": _datetime_to_iso(self.sent_at),
            "last_error": self.last_error,
        }


def _datetime_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
