from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import AppConfig
from .imap_client import ImapMailClient
from .repository import DraftRepository
from .service import MailService
from .smtp_client import SmtpMailSender

mcp = FastMCP("ubisam-mail-mcp")


@lru_cache(maxsize=1)
def _config() -> AppConfig:
    return AppConfig.from_env()


@lru_cache(maxsize=1)
def _imap() -> ImapMailClient:
    return ImapMailClient(_config())


@lru_cache(maxsize=1)
def _service() -> MailService:
    config = _config()
    return MailService(
        repository=DraftRepository(config.sqlite_path),
        sender=SmtpMailSender(config),
        config=config,
    )


@mcp.tool()
def config_status() -> dict[str, Any]:
    """Return SMTP, IMAP, and SQLite configuration status."""
    config = _config()
    return {
        "smtp_ready": config.smtp_ready(),
        "smtp_host": config.smtp_host,
        "smtp_port": config.smtp_port,
        "smtp_username": config.smtp_username,
        "smtp_use_tls": config.smtp_use_tls,
        "smtp_use_starttls": config.smtp_use_starttls,
        "imap_ready": config.imap_ready(),
        "imap_host": config.imap_host,
        "imap_port": config.imap_port,
        "imap_username": config.imap_username,
        "imap_use_tls": config.imap_use_tls,
        "default_from_address": config.default_from_address,
        "sqlite_path": str(config.sqlite_path),
    }


@mcp.tool()
def list_mailboxes() -> dict[str, Any]:
    """List IMAP mailboxes available to the configured account."""
    return {"mailboxes": _imap().list_mailboxes()}


@mcp.tool()
def list_messages(mailbox: str = "INBOX", limit: int = 10, criteria: str = "ALL") -> dict[str, Any]:
    """List recent IMAP messages from a mailbox."""
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    return {"messages": _imap().list_messages(mailbox=mailbox, limit=limit, criteria=criteria)}


@mcp.tool()
def get_message(uid: str, mailbox: str = "INBOX", body_preview_chars: int = 4000) -> dict[str, Any]:
    """Fetch one IMAP message by UID with a text/html body preview."""
    if not 100 <= body_preview_chars <= 20000:
        raise ValueError("body_preview_chars must be between 100 and 20000")
    return {
        "message": _imap().get_message(
            mailbox=mailbox, uid=uid, body_preview_chars=body_preview_chars
        )
    }


@mcp.tool()
def create_draft(
    subject: str,
    to: list[str],
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    text_body: str = "",
    html_body: str = "",
    from_address: str | None = None,
) -> dict[str, Any]:
    """Create a new draft mail. This does not send mail."""
    draft = _service().create_draft(
        subject=subject,
        to=to,
        cc=cc,
        bcc=bcc,
        text_body=text_body,
        html_body=html_body,
        from_address=from_address,
    )
    return {"draft": draft.to_dict()}


@mcp.tool()
def update_draft(
    draft_id: str,
    subject: str | None = None,
    to: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    text_body: str | None = None,
    html_body: str | None = None,
    from_address: str | None = None,
) -> dict[str, Any]:
    """Update an existing unsent draft."""
    updates = {
        "subject": subject,
        "to": to,
        "cc": cc,
        "bcc": bcc,
        "text_body": text_body,
        "html_body": html_body,
        "from_address": from_address,
    }
    draft = _service().update_draft(draft_id, **updates)
    return {"draft": draft.to_dict()}


@mcp.tool()
def get_draft(draft_id: str) -> dict[str, Any]:
    """Get one draft by id."""
    draft = _service().require_draft(draft_id)
    return {"draft": draft.to_dict()}


@mcp.tool()
def list_drafts() -> dict[str, Any]:
    """List all drafts and sent messages stored in SQLite."""
    return {"drafts": [draft.to_dict() for draft in _service().repository.list_all()]}


@mcp.tool()
def schedule_draft(draft_id: str, scheduled_for: str) -> dict[str, Any]:
    """Schedule a draft for later sending. Use ISO 8601 with timezone."""
    draft = _service().schedule_draft(draft_id, _parse_datetime(scheduled_for))
    return {"draft": draft.to_dict()}


@mcp.tool()
def send_draft_now(draft_id: str) -> dict[str, Any]:
    """Send a draft immediately after explicit confirmation by the user."""
    draft = _service().send_draft_now(draft_id)
    return {"draft": draft.to_dict()}


@mcp.tool()
def dispatch_due_messages() -> dict[str, Any]:
    """Send scheduled drafts whose time has arrived."""
    drafts = _service().dispatch_due_messages()
    return {"sent": [draft.to_dict() for draft in drafts], "count": len(drafts)}


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("scheduled_for must include timezone information")
    return parsed.astimezone(timezone.utc)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
