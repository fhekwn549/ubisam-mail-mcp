from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .models import ClosingTemplate, DraftAttachment, GreetingTemplate, MessageDraft, SignatureProfile, SignatureTemplate


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
                    reply_to_list TEXT NOT NULL DEFAULT '[]',
                    text_body TEXT NOT NULL,
                    html_body TEXT NOT NULL,
                    attachments_json TEXT NOT NULL DEFAULT '[]',
                    from_address TEXT NOT NULL,
                    from_name TEXT NOT NULL DEFAULT '',
                    in_reply_to TEXT NOT NULL DEFAULT '',
                    references_json TEXT NOT NULL DEFAULT '[]',
                    greeting_template_id TEXT,
                    closing_template_id TEXT,
                    signature_id TEXT,
                    signature_profile_id TEXT,
                    status TEXT NOT NULL,
                    scheduled_for TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    sent_at TEXT,
                    last_error TEXT
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(drafts)").fetchall()
            }
            if "signature_id" not in columns:
                connection.execute("ALTER TABLE drafts ADD COLUMN signature_id TEXT")
            if "greeting_template_id" not in columns:
                connection.execute("ALTER TABLE drafts ADD COLUMN greeting_template_id TEXT")
            if "closing_template_id" not in columns:
                connection.execute("ALTER TABLE drafts ADD COLUMN closing_template_id TEXT")
            if "signature_profile_id" not in columns:
                connection.execute("ALTER TABLE drafts ADD COLUMN signature_profile_id TEXT")
            if "attachments_json" not in columns:
                connection.execute("ALTER TABLE drafts ADD COLUMN attachments_json TEXT NOT NULL DEFAULT '[]'")
            if "reply_to_list" not in columns:
                connection.execute("ALTER TABLE drafts ADD COLUMN reply_to_list TEXT NOT NULL DEFAULT '[]'")
            if "from_name" not in columns:
                connection.execute("ALTER TABLE drafts ADD COLUMN from_name TEXT NOT NULL DEFAULT ''")
            if "in_reply_to" not in columns:
                connection.execute("ALTER TABLE drafts ADD COLUMN in_reply_to TEXT NOT NULL DEFAULT ''")
            if "references_json" not in columns:
                connection.execute("ALTER TABLE drafts ADD COLUMN references_json TEXT NOT NULL DEFAULT '[]'")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS signatures (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    text_template TEXT NOT NULL,
                    html_template TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'wrap_body',
                    is_default INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            signature_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(signatures)").fetchall()
            }
            if "mode" not in signature_columns:
                connection.execute(
                    "ALTER TABLE signatures ADD COLUMN mode TEXT NOT NULL DEFAULT 'wrap_body'"
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS greeting_templates (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    text_template TEXT NOT NULL,
                    html_template TEXT NOT NULL,
                    is_default INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS closing_templates (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    text_template TEXT NOT NULL,
                    html_template TEXT NOT NULL,
                    is_default INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS signature_profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    fields_json TEXT NOT NULL,
                    logo_image_path TEXT NOT NULL,
                    is_default INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
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
                    id, subject, to_list, cc_list, bcc_list, reply_to_list, text_body, html_body, attachments_json,
                    from_address, from_name, in_reply_to, references_json, greeting_template_id, closing_template_id, signature_id, signature_profile_id, status, scheduled_for, created_at,
                    updated_at, sent_at, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    subject=excluded.subject,
                    to_list=excluded.to_list,
                    cc_list=excluded.cc_list,
                    bcc_list=excluded.bcc_list,
                    reply_to_list=excluded.reply_to_list,
                    text_body=excluded.text_body,
                    html_body=excluded.html_body,
                    attachments_json=excluded.attachments_json,
                    from_address=excluded.from_address,
                    from_name=excluded.from_name,
                    in_reply_to=excluded.in_reply_to,
                    references_json=excluded.references_json,
                    greeting_template_id=excluded.greeting_template_id,
                    closing_template_id=excluded.closing_template_id,
                    signature_id=excluded.signature_id,
                    signature_profile_id=excluded.signature_profile_id,
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
                    json.dumps(draft.reply_to),
                    draft.text_body,
                    draft.html_body,
                    json.dumps([attachment.to_dict() for attachment in draft.attachments]),
                    draft.from_address,
                    draft.from_name,
                    draft.in_reply_to,
                    json.dumps(draft.references),
                    draft.greeting_template_id,
                    draft.closing_template_id,
                    draft.signature_id,
                    draft.signature_profile_id,
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

    def upsert_signature(self, signature: SignatureTemplate) -> SignatureTemplate:
        now = datetime.now(timezone.utc)
        if signature.created_at is None:
            signature.created_at = now
        signature.updated_at = now
        if signature.is_default:
            self._clear_default_signature(except_id=signature.id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO signatures (
                    id, name, text_template, html_template, mode, is_default, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    text_template=excluded.text_template,
                    html_template=excluded.html_template,
                    mode=excluded.mode,
                    is_default=excluded.is_default,
                    updated_at=excluded.updated_at
                """,
                (
                    signature.id,
                    signature.name,
                    signature.text_template,
                    signature.html_template,
                    signature.mode,
                    int(signature.is_default),
                    _datetime_to_iso(signature.created_at),
                    _datetime_to_iso(signature.updated_at),
                ),
            )
        return signature

    def upsert_greeting_template(self, template: GreetingTemplate) -> GreetingTemplate:
        now = datetime.now(timezone.utc)
        if template.created_at is None:
            template.created_at = now
        template.updated_at = now
        if template.is_default:
            self._clear_default("greeting_templates", except_id=template.id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO greeting_templates (
                    id, name, text_template, html_template, is_default, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    text_template=excluded.text_template,
                    html_template=excluded.html_template,
                    is_default=excluded.is_default,
                    updated_at=excluded.updated_at
                """,
                (
                    template.id,
                    template.name,
                    template.text_template,
                    template.html_template,
                    int(template.is_default),
                    _datetime_to_iso(template.created_at),
                    _datetime_to_iso(template.updated_at),
                ),
            )
        return template

    def upsert_closing_template(self, template: ClosingTemplate) -> ClosingTemplate:
        now = datetime.now(timezone.utc)
        if template.created_at is None:
            template.created_at = now
        template.updated_at = now
        if template.is_default:
            self._clear_default("closing_templates", except_id=template.id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO closing_templates (
                    id, name, text_template, html_template, is_default, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    text_template=excluded.text_template,
                    html_template=excluded.html_template,
                    is_default=excluded.is_default,
                    updated_at=excluded.updated_at
                """,
                (
                    template.id,
                    template.name,
                    template.text_template,
                    template.html_template,
                    int(template.is_default),
                    _datetime_to_iso(template.created_at),
                    _datetime_to_iso(template.updated_at),
                ),
            )
        return template

    def get_closing_template(self, template_id: str) -> ClosingTemplate | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM closing_templates WHERE id = ?",
                (template_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_closing_template(row)

    def get_default_closing_template(self) -> ClosingTemplate | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM closing_templates WHERE is_default = 1 ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return self._row_to_closing_template(row)

    def list_closing_templates(self) -> list[ClosingTemplate]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM closing_templates ORDER BY is_default DESC, name ASC, created_at ASC"
            ).fetchall()
        return [self._row_to_closing_template(row) for row in rows]

    def delete_closing_template(self, template_id: str) -> bool:
        with self._connect() as connection:
            deleted = connection.execute(
                "DELETE FROM closing_templates WHERE id = ?",
                (template_id,),
            )
        return deleted.rowcount > 0

    def get_greeting_template(self, template_id: str) -> GreetingTemplate | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM greeting_templates WHERE id = ?",
                (template_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_greeting_template(row)

    def get_default_greeting_template(self) -> GreetingTemplate | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM greeting_templates WHERE is_default = 1 ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return self._row_to_greeting_template(row)

    def list_greeting_templates(self) -> list[GreetingTemplate]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM greeting_templates ORDER BY is_default DESC, name ASC, created_at ASC"
            ).fetchall()
        return [self._row_to_greeting_template(row) for row in rows]

    def delete_greeting_template(self, template_id: str) -> bool:
        with self._connect() as connection:
            deleted = connection.execute(
                "DELETE FROM greeting_templates WHERE id = ?",
                (template_id,),
            )
        return deleted.rowcount > 0

    def upsert_signature_profile(self, profile: SignatureProfile) -> SignatureProfile:
        now = datetime.now(timezone.utc)
        if profile.created_at is None:
            profile.created_at = now
        profile.updated_at = now
        if profile.is_default:
            self._clear_default("signature_profiles", except_id=profile.id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO signature_profiles (
                    id, name, fields_json, logo_image_path, is_default, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    fields_json=excluded.fields_json,
                    logo_image_path=excluded.logo_image_path,
                    is_default=excluded.is_default,
                    updated_at=excluded.updated_at
                """,
                (
                    profile.id,
                    profile.name,
                    json.dumps(profile.fields, ensure_ascii=False),
                    profile.logo_image_path,
                    int(profile.is_default),
                    _datetime_to_iso(profile.created_at),
                    _datetime_to_iso(profile.updated_at),
                ),
            )
        return profile

    def get_signature_profile(self, profile_id: str) -> SignatureProfile | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM signature_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_signature_profile(row)

    def get_default_signature_profile(self) -> SignatureProfile | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM signature_profiles WHERE is_default = 1 ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return self._row_to_signature_profile(row)

    def list_signature_profiles(self) -> list[SignatureProfile]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM signature_profiles ORDER BY is_default DESC, name ASC, created_at ASC"
            ).fetchall()
        return [self._row_to_signature_profile(row) for row in rows]

    def delete_signature_profile(self, profile_id: str) -> bool:
        with self._connect() as connection:
            deleted = connection.execute(
                "DELETE FROM signature_profiles WHERE id = ?",
                (profile_id,),
            )
        return deleted.rowcount > 0

    def get_signature(self, signature_id: str) -> SignatureTemplate | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM signatures WHERE id = ?",
                (signature_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_signature(row)

    def get_default_signature(self) -> SignatureTemplate | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM signatures WHERE is_default = 1 ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return self._row_to_signature(row)

    def list_signatures(self) -> list[SignatureTemplate]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM signatures ORDER BY is_default DESC, name ASC, created_at ASC"
            ).fetchall()
        return [self._row_to_signature(row) for row in rows]

    def delete_signature(self, signature_id: str) -> bool:
        with self._connect() as connection:
            deleted = connection.execute(
                "DELETE FROM signatures WHERE id = ?",
                (signature_id,),
            )
        return deleted.rowcount > 0

    def _clear_default_signature(self, except_id: str | None = None) -> None:
        self._clear_default("signatures", except_id=except_id)

    def _clear_default(self, table: str, except_id: str | None = None) -> None:
        with self._connect() as connection:
            if except_id is None:
                connection.execute(f"UPDATE {table} SET is_default = 0 WHERE is_default = 1")
                return
            connection.execute(
                f"UPDATE {table} SET is_default = 0 WHERE is_default = 1 AND id != ?",
                (except_id,),
            )

    @staticmethod
    def _row_to_draft(row: sqlite3.Row) -> MessageDraft:
        return MessageDraft(
            id=row["id"],
            subject=row["subject"],
            to=json.loads(row["to_list"]),
            cc=json.loads(row["cc_list"]),
            bcc=json.loads(row["bcc_list"]),
            reply_to=json.loads(row["reply_to_list"] or "[]"),
            text_body=row["text_body"],
            html_body=row["html_body"],
            attachments=[
                DraftAttachment.from_dict(item)
                for item in json.loads(row["attachments_json"] or "[]")
            ],
            from_address=row["from_address"],
            from_name=row["from_name"] or "",
            in_reply_to=row["in_reply_to"] or "",
            references=json.loads(row["references_json"] or "[]"),
            greeting_template_id=row["greeting_template_id"],
            closing_template_id=row["closing_template_id"],
            signature_id=row["signature_id"],
            signature_profile_id=row["signature_profile_id"],
            status=row["status"],
            scheduled_for=_parse_datetime(row["scheduled_for"]),
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
            sent_at=_parse_datetime(row["sent_at"]),
            last_error=row["last_error"],
        )

    @staticmethod
    def _row_to_signature(row: sqlite3.Row) -> SignatureTemplate:
        return SignatureTemplate(
            id=row["id"],
            name=row["name"],
            text_template=row["text_template"],
            html_template=row["html_template"],
            mode=row["mode"],
            is_default=bool(row["is_default"]),
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )

    @staticmethod
    def _row_to_greeting_template(row: sqlite3.Row) -> GreetingTemplate:
        return GreetingTemplate(
            id=row["id"],
            name=row["name"],
            text_template=row["text_template"],
            html_template=row["html_template"],
            is_default=bool(row["is_default"]),
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )

    @staticmethod
    def _row_to_closing_template(row: sqlite3.Row) -> ClosingTemplate:
        return ClosingTemplate(
            id=row["id"],
            name=row["name"],
            text_template=row["text_template"],
            html_template=row["html_template"],
            is_default=bool(row["is_default"]),
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )

    @staticmethod
    def _row_to_signature_profile(row: sqlite3.Row) -> SignatureProfile:
        return SignatureProfile(
            id=row["id"],
            name=row["name"],
            fields=json.loads(row["fields_json"]),
            logo_image_path=row["logo_image_path"],
            is_default=bool(row["is_default"]),
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )


def _datetime_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)
