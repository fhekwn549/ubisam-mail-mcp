from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .models import MessageDraft


class DraftRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS drafts (
                    id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    to_list TEXT NOT NULL,
                    cc_list TEXT NOT NULL,
                    bcc_list TEXT NOT NULL,
                    text_body TEXT NOT NULL,
                    html_body TEXT NOT NULL,
                    from_address TEXT NOT NULL,
                    status TEXT NOT NULL,
                    scheduled_for TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    sent_at TEXT,
                    last_error TEXT
                )
                """
            )

    def upsert(self, draft: MessageDraft) -> MessageDraft:
        now = datetime.now(timezone.utc)
        if draft.created_at is None:
            draft.created_at = now
        draft.updated_at = now
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO drafts (
                    id, subject, to_list, cc_list, bcc_list, text_body, html_body,
                    from_address, status, scheduled_for, created_at, updated_at,
                    sent_at, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    subject=excluded.subject,
                    to_list=excluded.to_list,
                    cc_list=excluded.cc_list,
                    bcc_list=excluded.bcc_list,
                    text_body=excluded.text_body,
                    html_body=excluded.html_body,
                    from_address=excluded.from_address,
                    status=excluded.status,
                    scheduled_for=excluded.scheduled_for,
                    updated_at=excluded.updated_at,
                    sent_at=excluded.sent_at,
                    last_error=excluded.last_error
                """,
                (
                    draft.id,
                    draft.subject,
                    json.dumps(draft.to),
                    json.dumps(draft.cc),
                    json.dumps(draft.bcc),
                    draft.text_body,
                    draft.html_body,
                    draft.from_address,
                    draft.status,
                    _datetime_to_iso(draft.scheduled_for),
                    _datetime_to_iso(draft.created_at),
                    _datetime_to_iso(draft.updated_at),
                    _datetime_to_iso(draft.sent_at),
                    draft.last_error,
                ),
            )
        return draft

    def get(self, draft_id: str) -> MessageDraft | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM drafts WHERE id = ?",
                (draft_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_draft(row)

    def list_all(self) -> list[MessageDraft]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM drafts ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_draft(row) for row in rows]

    def list_due(self, *, before: datetime) -> list[MessageDraft]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM drafts
                WHERE status = 'scheduled'
                  AND scheduled_for IS NOT NULL
                  AND scheduled_for <= ?
                ORDER BY scheduled_for ASC
                """,
                (_datetime_to_iso(before),),
            ).fetchall()
        return [self._row_to_draft(row) for row in rows]

    @staticmethod
    def _row_to_draft(row: sqlite3.Row) -> MessageDraft:
        return MessageDraft(
            id=row["id"],
            subject=row["subject"],
            to=json.loads(row["to_list"]),
            cc=json.loads(row["cc_list"]),
            bcc=json.loads(row["bcc_list"]),
            text_body=row["text_body"],
            html_body=row["html_body"],
            from_address=row["from_address"],
            status=row["status"],
            scheduled_for=_parse_datetime(row["scheduled_for"]),
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
            sent_at=_parse_datetime(row["sent_at"]),
            last_error=row["last_error"],
        )


def _datetime_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)
