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
        "smtp_debug": config.smtp_debug,
        "imap_ready": config.imap_ready(),
        "imap_host": config.imap_host,
        "imap_port": config.imap_port,
        "imap_username": config.imap_username,
        "imap_use_tls": config.imap_use_tls,
        "default_from_address": config.default_from_address,
        "sqlite_path": str(config.sqlite_path),
        "attachment_download_dir": str(config.attachment_download_dir),
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
def get_unread_status(mailbox: str = "INBOX", sample_limit: int = 10) -> dict[str, Any]:
    """Return unread existence, count, and latest unread message summaries for a mailbox."""
    if not 0 <= sample_limit <= 20:
        raise ValueError("sample_limit must be between 0 and 20")
    return {"unread_status": _imap().get_unread_status(mailbox=mailbox, sample_limit=sample_limit)}


@mcp.tool()
def search_messages(
    mailbox: str = "INBOX",
    limit: int = 20,
    subject_contains: str = "",
    from_contains: str = "",
    to_contains: str = "",
    body_contains: str = "",
    is_unread: bool | None = None,
    has_attachments: bool | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Search IMAP messages with structured filters similar to Outlook MCP email search."""
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    return {
        "messages": _imap().search_messages(
            mailbox=mailbox,
            limit=limit,
            subject_contains=subject_contains,
            from_contains=from_contains,
            to_contains=to_contains,
            body_contains=body_contains,
            is_unread=is_unread,
            has_attachments=has_attachments,
            date_from=_parse_date(date_from),
            date_to=_parse_date(date_to),
        )
    }


@mcp.tool()
def get_message(uid: str, mailbox: str = "INBOX", body_preview_chars: int = 4000) -> dict[str, Any]:
    """Fetch one IMAP message by UID with body previews and attachment metadata."""
    if not 100 <= body_preview_chars <= 20000:
        raise ValueError("body_preview_chars must be between 100 and 20000")
    return {
        "message": _imap().get_message(
            mailbox=mailbox, uid=uid, body_preview_chars=body_preview_chars
        )
    }


@mcp.tool()
def download_message_attachment(
    uid: str,
    attachment_index: int,
    target_path: str | None = None,
    mailbox: str = "INBOX",
) -> dict[str, Any]:
    """Download one attachment from an IMAP message to a local file path."""
    if attachment_index < 0:
        raise ValueError("attachment_index must be non-negative")
    return {
        "download": _imap().download_attachment(
            mailbox=mailbox,
            uid=uid,
            attachment_index=attachment_index,
            target_path=target_path,
        )
    }


@mcp.tool()
def create_mailbox(mailbox: str) -> dict[str, Any]:
    """Create a new IMAP mailbox/folder."""
    if not mailbox.strip():
        raise ValueError("mailbox is required")
    return {"mailbox": _imap().create_mailbox(mailbox=mailbox.strip())}


@mcp.tool()
def set_message_read_status(
    uids: list[str],
    is_unread: bool,
    mailbox: str = "INBOX",
) -> dict[str, Any]:
    """Mark one or more IMAP messages as read or unread."""
    return {
        "result": _imap().set_message_read_status(
            mailbox=mailbox,
            uids=uids,
            is_unread=is_unread,
        )
    }


@mcp.tool()
def move_messages(
    uids: list[str],
    to_mailbox: str,
    from_mailbox: str = "INBOX",
) -> dict[str, Any]:
    """Move one or more IMAP messages to another mailbox/folder."""
    if not to_mailbox.strip():
        raise ValueError("to_mailbox is required")
    return {
        "result": _imap().move_messages(
            from_mailbox=from_mailbox,
            to_mailbox=to_mailbox.strip(),
            uids=uids,
        )
    }


@mcp.tool()
def delete_messages(
    uids: list[str],
    mailbox: str = "INBOX",
) -> dict[str, Any]:
    """Delete one or more IMAP messages, preferring Trash when available."""
    return {
        "result": _imap().delete_messages(
            mailbox=mailbox,
            uids=uids,
        )
    }


@mcp.tool()
def create_draft(
    subject: str,
    to: list[str],
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    reply_to: list[str] | None = None,
    text_body: str = "",
    html_body: str = "",
    attachment_paths: list[str] | None = None,
    from_address: str | None = None,
    from_name: str | None = None,
    in_reply_to: str = "",
    references: list[str] | None = None,
    greeting_template_id: str | None = None,
    closing_template_id: str | None = None,
    signature_id: str | None = None,
    signature_profile_id: str | None = None,
    apply_default_greeting_template: bool = True,
    apply_default_closing_template: bool = True,
    apply_default_signature: bool = True,
    apply_default_signature_profile: bool = True,
) -> dict[str, Any]:
    """Create a new draft mail. This does not send mail."""
    draft = _service().create_draft(
        subject=subject,
        to=to,
        cc=cc,
        bcc=bcc,
        reply_to=reply_to,
        text_body=text_body,
        html_body=html_body,
        attachment_paths=attachment_paths,
        from_address=from_address,
        from_name=from_name,
        in_reply_to=in_reply_to,
        references=references,
        greeting_template_id=greeting_template_id,
        closing_template_id=closing_template_id,
        signature_id=signature_id,
        signature_profile_id=signature_profile_id,
        apply_default_greeting_template=apply_default_greeting_template,
        apply_default_closing_template=apply_default_closing_template,
        apply_default_signature=apply_default_signature,
        apply_default_signature_profile=apply_default_signature_profile,
    )
    return {"draft": _draft_to_dict(draft)}


@mcp.tool()
def update_draft(
    draft_id: str,
    subject: str | None = None,
    to: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    reply_to: list[str] | None = None,
    text_body: str | None = None,
    html_body: str | None = None,
    attachment_paths: list[str] | None = None,
    from_address: str | None = None,
    from_name: str | None = None,
    in_reply_to: str | None = None,
    references: list[str] | None = None,
    greeting_template_id: str | None = None,
    closing_template_id: str | None = None,
    signature_id: str | None = None,
    signature_profile_id: str | None = None,
    apply_default_greeting_template: bool = False,
    clear_greeting_template: bool = False,
    apply_default_closing_template: bool = False,
    clear_closing_template: bool = False,
    apply_default_signature: bool = False,
    clear_signature: bool = False,
    apply_default_signature_profile: bool = False,
    clear_signature_profile: bool = False,
) -> dict[str, Any]:
    """Update an existing unsent draft."""
    updates = {
        "subject": subject,
        "to": to,
        "cc": cc,
        "bcc": bcc,
        "reply_to": reply_to,
        "text_body": text_body,
        "html_body": html_body,
        "attachment_paths": attachment_paths,
        "from_address": from_address,
        "from_name": from_name,
        "in_reply_to": in_reply_to,
        "references": references,
        "greeting_template_id": greeting_template_id,
        "closing_template_id": closing_template_id,
        "signature_id": signature_id,
        "signature_profile_id": signature_profile_id,
        "apply_default_greeting_template": apply_default_greeting_template,
        "clear_greeting_template": clear_greeting_template,
        "apply_default_closing_template": apply_default_closing_template,
        "clear_closing_template": clear_closing_template,
        "apply_default_signature": apply_default_signature,
        "clear_signature": clear_signature,
        "apply_default_signature_profile": apply_default_signature_profile,
        "clear_signature_profile": clear_signature_profile,
    }
    draft = _service().update_draft(draft_id, **updates)
    return {"draft": _draft_to_dict(draft)}


@mcp.tool()
def get_draft(draft_id: str) -> dict[str, Any]:
    """Get one draft by id."""
    draft = _service().require_draft(draft_id)
    return {"draft": _draft_to_dict(draft)}


@mcp.tool()
def list_drafts() -> dict[str, Any]:
    """List all drafts and sent messages stored in SQLite."""
    return {"drafts": [_draft_to_dict(draft) for draft in _service().repository.list_all()]}


@mcp.tool()
def upload_draft_to_imap(draft_id: str, mailbox: str | None = None) -> dict[str, Any]:
    """Upload one local draft into the remote IMAP Drafts mailbox using APPEND."""
    rendered_draft = _service().render_draft(draft_id)
    upload = _imap().upload_draft(draft=rendered_draft, mailbox=mailbox)
    return {"upload": upload, "draft": _draft_to_dict(_service().require_draft(draft_id))}


@mcp.tool()
def create_reply_draft(
    source_uid: str,
    mailbox: str = "INBOX",
    text_body: str = "",
    html_body: str = "",
    attachment_paths: list[str] | None = None,
    from_address: str | None = None,
    from_name: str | None = None,
    greeting_template_id: str | None = None,
    closing_template_id: str | None = None,
    signature_id: str | None = None,
    signature_profile_id: str | None = None,
    apply_default_greeting_template: bool = True,
    apply_default_closing_template: bool = True,
    apply_default_signature: bool = True,
    apply_default_signature_profile: bool = True,
) -> dict[str, Any]:
    """Create a reply draft with quoted original content and thread headers."""
    original_message = _imap().get_reply_context(mailbox=mailbox, uid=source_uid)
    draft = _service().create_reply_draft_from_message(
        original_message=original_message,
        reply_all=False,
        text_body=text_body,
        html_body=html_body,
        attachment_paths=attachment_paths,
        from_address=from_address,
        from_name=from_name,
        greeting_template_id=greeting_template_id,
        closing_template_id=closing_template_id,
        signature_id=signature_id,
        signature_profile_id=signature_profile_id,
        apply_default_greeting_template=apply_default_greeting_template,
        apply_default_closing_template=apply_default_closing_template,
        apply_default_signature=apply_default_signature,
        apply_default_signature_profile=apply_default_signature_profile,
    )
    return {"draft": _draft_to_dict(draft)}


@mcp.tool()
def create_reply_all_draft(
    source_uid: str,
    mailbox: str = "INBOX",
    text_body: str = "",
    html_body: str = "",
    attachment_paths: list[str] | None = None,
    from_address: str | None = None,
    from_name: str | None = None,
    greeting_template_id: str | None = None,
    closing_template_id: str | None = None,
    signature_id: str | None = None,
    signature_profile_id: str | None = None,
    apply_default_greeting_template: bool = True,
    apply_default_closing_template: bool = True,
    apply_default_signature: bool = True,
    apply_default_signature_profile: bool = True,
) -> dict[str, Any]:
    """Create a reply-all draft with quoted original content and thread headers."""
    original_message = _imap().get_reply_context(mailbox=mailbox, uid=source_uid)
    draft = _service().create_reply_draft_from_message(
        original_message=original_message,
        reply_all=True,
        text_body=text_body,
        html_body=html_body,
        attachment_paths=attachment_paths,
        from_address=from_address,
        from_name=from_name,
        greeting_template_id=greeting_template_id,
        closing_template_id=closing_template_id,
        signature_id=signature_id,
        signature_profile_id=signature_profile_id,
        apply_default_greeting_template=apply_default_greeting_template,
        apply_default_closing_template=apply_default_closing_template,
        apply_default_signature=apply_default_signature,
        apply_default_signature_profile=apply_default_signature_profile,
    )
    return {"draft": _draft_to_dict(draft)}


@mcp.tool()
def schedule_draft(draft_id: str, scheduled_for: str) -> dict[str, Any]:
    """Schedule a draft for later sending. Use ISO 8601 with timezone."""
    draft = _service().schedule_draft(draft_id, _parse_datetime(scheduled_for))
    return {"draft": _draft_to_dict(draft)}


@mcp.tool()
def send_draft_now(draft_id: str) -> dict[str, Any]:
    """Send a draft immediately after explicit confirmation by the user."""
    draft = _service().send_draft_now(draft_id)
    return {"draft": _draft_to_dict(draft)}


@mcp.tool()
def dispatch_due_messages() -> dict[str, Any]:
    """Send scheduled drafts whose time has arrived."""
    drafts = _service().dispatch_due_messages()
    return {"sent": [_draft_to_dict(draft) for draft in drafts], "count": len(drafts)}


@mcp.tool()
def list_greeting_templates() -> dict[str, Any]:
    """List saved greeting templates."""
    return {"greeting_templates": [item.to_dict() for item in _service().list_greeting_templates()]}


@mcp.tool()
def get_greeting_template(template_id: str) -> dict[str, Any]:
    """Get one greeting template by id."""
    return {"greeting_template": _service().require_greeting_template(template_id).to_dict()}


@mcp.tool()
def create_greeting_template(
    name: str,
    text_template: str = "",
    html_template: str = "",
    is_default: bool = False,
) -> dict[str, Any]:
    """Create a greeting template applied before the main body."""
    template = _service().create_greeting_template(
        name=name,
        text_template=text_template,
        html_template=html_template,
        is_default=is_default,
    )
    return {"greeting_template": template.to_dict()}


@mcp.tool()
def update_greeting_template(
    template_id: str,
    name: str | None = None,
    text_template: str | None = None,
    html_template: str | None = None,
    is_default: bool | None = None,
) -> dict[str, Any]:
    """Update a greeting template."""
    template = _service().update_greeting_template(
        template_id,
        name=name,
        text_template=text_template,
        html_template=html_template,
        is_default=is_default,
    )
    return {"greeting_template": template.to_dict()}


@mcp.tool()
def delete_greeting_template(template_id: str) -> dict[str, Any]:
    """Delete a greeting template."""
    _service().delete_greeting_template(template_id)
    return {"deleted": True, "template_id": template_id}


@mcp.tool()
def list_closing_templates() -> dict[str, Any]:
    """List saved closing phrase templates."""
    return {"closing_templates": [item.to_dict() for item in _service().list_closing_templates()]}


@mcp.tool()
def get_closing_template(template_id: str) -> dict[str, Any]:
    """Get one closing phrase template by id."""
    return {"closing_template": _service().require_closing_template(template_id).to_dict()}


@mcp.tool()
def create_closing_template(
    name: str,
    text_template: str = "",
    html_template: str = "",
    is_default: bool = False,
) -> dict[str, Any]:
    """Create a closing phrase template placed between body and footer."""
    template = _service().create_closing_template(
        name=name,
        text_template=text_template,
        html_template=html_template,
        is_default=is_default,
    )
    return {"closing_template": template.to_dict()}


@mcp.tool()
def update_closing_template(
    template_id: str,
    name: str | None = None,
    text_template: str | None = None,
    html_template: str | None = None,
    is_default: bool | None = None,
) -> dict[str, Any]:
    """Update a closing phrase template."""
    template = _service().update_closing_template(
        template_id,
        name=name,
        text_template=text_template,
        html_template=html_template,
        is_default=is_default,
    )
    return {"closing_template": template.to_dict()}


@mcp.tool()
def delete_closing_template(template_id: str) -> dict[str, Any]:
    """Delete a closing phrase template."""
    _service().delete_closing_template(template_id)
    return {"deleted": True, "template_id": template_id}


@mcp.tool()
def list_signature_profiles() -> dict[str, Any]:
    """List saved signature profiles."""
    return {"signature_profiles": [item.to_dict() for item in _service().list_signature_profiles()]}


@mcp.tool()
def get_signature_profile(profile_id: str) -> dict[str, Any]:
    """Get one signature profile by id."""
    return {"signature_profile": _service().require_signature_profile(profile_id).to_dict()}


@mcp.tool()
def create_signature_profile(
    name: str,
    fields: dict[str, str] | None = None,
    logo_image_path: str = "",
    is_default: bool = False,
) -> dict[str, Any]:
    """Create a signature profile with placeholder values and optional logo image path."""
    profile = _service().create_signature_profile(
        name=name,
        fields=fields,
        logo_image_path=logo_image_path,
        is_default=is_default,
    )
    return {"signature_profile": profile.to_dict()}


@mcp.tool()
def update_signature_profile(
    profile_id: str,
    name: str | None = None,
    fields: dict[str, str] | None = None,
    logo_image_path: str | None = None,
    is_default: bool | None = None,
) -> dict[str, Any]:
    """Update a signature profile."""
    profile = _service().update_signature_profile(
        profile_id,
        name=name,
        fields=fields,
        logo_image_path=logo_image_path,
        is_default=is_default,
    )
    return {"signature_profile": profile.to_dict()}


@mcp.tool()
def delete_signature_profile(profile_id: str) -> dict[str, Any]:
    """Delete a signature profile."""
    _service().delete_signature_profile(profile_id)
    return {"deleted": True, "profile_id": profile_id}


@mcp.tool()
def list_signatures() -> dict[str, Any]:
    """List saved signature templates."""
    return {"signatures": [signature.to_dict() for signature in _service().list_signatures()]}


@mcp.tool()
def get_signature(signature_id: str) -> dict[str, Any]:
    """Get one signature template by id."""
    return {"signature": _service().require_signature(signature_id).to_dict()}


@mcp.tool()
def create_signature(
    name: str,
    text_template: str = "",
    html_template: str = "",
    mode: str = "wrap_body",
    is_default: bool = False,
) -> dict[str, Any]:
    """Create a signature template. wrap_body requires {{body}}. closing_only renders a footer block."""
    signature = _service().create_signature(
        name=name,
        text_template=text_template,
        html_template=html_template,
        mode=mode,
        is_default=is_default,
    )
    return {"signature": signature.to_dict()}


@mcp.tool()
def update_signature(
    signature_id: str,
    name: str | None = None,
    text_template: str | None = None,
    html_template: str | None = None,
    mode: str | None = None,
    is_default: bool | None = None,
) -> dict[str, Any]:
    """Update a signature template."""
    signature = _service().update_signature(
        signature_id,
        name=name,
        text_template=text_template,
        html_template=html_template,
        mode=mode,
        is_default=is_default,
    )
    return {"signature": signature.to_dict()}


@mcp.tool()
def delete_signature(signature_id: str) -> dict[str, Any]:
    """Delete a signature template."""
    _service().delete_signature(signature_id)
    return {"deleted": True, "signature_id": signature_id}


@mcp.tool()
def preview_signature(
    text_body: str = "",
    html_body: str = "",
    greeting_template_id: str | None = None,
    closing_template_id: str | None = None,
    signature_id: str | None = None,
    signature_profile_id: str | None = None,
    apply_default_greeting_template: bool = True,
    apply_default_closing_template: bool = True,
    apply_default_signature: bool = True,
    apply_default_signature_profile: bool = True,
) -> dict[str, Any]:
    """Preview rendered bodies after applying greeting, signature template, and profile."""
    return {
        "preview": _service().preview_signature(
            text_body=text_body,
            html_body=html_body,
            greeting_template_id=greeting_template_id,
            closing_template_id=closing_template_id,
            signature_id=signature_id,
            signature_profile_id=signature_profile_id,
            apply_default_greeting_template=apply_default_greeting_template,
            apply_default_closing_template=apply_default_closing_template,
            apply_default_signature=apply_default_signature,
            apply_default_signature_profile=apply_default_signature_profile,
        )
    }


@mcp.tool()
def preview_closing_signature(
    signature_id: str | None = None,
    signature_profile_id: str | None = None,
    apply_default_signature: bool = True,
    apply_default_signature_profile: bool = True,
    export_dir: str | None = None,
) -> dict[str, Any]:
    """Preview only the closing signature block, optionally exporting a local HTML file."""
    return {
        "preview": _service().preview_closing_signature(
            signature_id=signature_id,
            signature_profile_id=signature_profile_id,
            apply_default_signature=apply_default_signature,
            apply_default_signature_profile=apply_default_signature_profile,
            export_dir=export_dir,
        )
    }


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("scheduled_for must include timezone information")
    return parsed.astimezone(timezone.utc)


def _parse_date(value: str | None):
    if value is None:
        return None
    return datetime.fromisoformat(value).date()


def _draft_to_dict(draft) -> dict[str, Any]:
    return draft.to_dict(
        signature=_service().signature_for_draft(draft),
        greeting=_service().greeting_for_draft(draft),
        closing=_service().closing_for_draft(draft),
        profile=_service().signature_profile_for_draft(draft),
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
