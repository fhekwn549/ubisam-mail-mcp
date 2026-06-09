from __future__ import annotations

import html
import mimetypes
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .config import AppConfig
from .models import ClosingTemplate, DraftAttachment, GreetingTemplate, MessageDraft, SignatureProfile, SignatureTemplate
from .repository import DraftRepository


# Files whose contents are credentials/secrets and must never be attached and
# mailed out. attachment_paths/logo_image_path are caller-controlled and can be
# driven by indirect prompt injection (e.g. text in a received message), so the
# attachment gate refuses these before a draft can carry them off the machine.
_DENY_ATTACHMENT_NAMES = {
    ".env", ".netrc", ".pgpass", ".htpasswd", "known_hosts",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials",
}
_DENY_ATTACHMENT_SUFFIXES = {
    ".pem", ".key", ".p12", ".pfx", ".pkcs12", ".keystore",
    ".jks", ".ppk", ".asc", ".gpg", ".kdbx",
}
_DENY_PATH_PARTS = {".ssh", ".aws", ".gnupg", ".kube", ".gcloud", ".azure"}


def _ensure_safe_attachment_source(path: Path) -> None:
    resolved = path.resolve()
    name = resolved.name.lower()
    if name in _DENY_ATTACHMENT_NAMES or name.startswith(".env."):
        raise ValueError(f"refusing to attach sensitive file: {resolved.name}")
    if resolved.suffix.lower() in _DENY_ATTACHMENT_SUFFIXES:
        raise ValueError(f"refusing to attach sensitive file type: {resolved.suffix}")
    blocked = {part.lower() for part in resolved.parts} & _DENY_PATH_PARTS
    if blocked:
        raise ValueError(
            f"refusing to attach file under sensitive directory: {sorted(blocked)[0]}"
        )


class MailSender(Protocol):
    def send(self, draft: MessageDraft) -> None:
        ...


class SentMailboxRecorder(Protocol):
    def upload_to_sent(self, *, draft: MessageDraft, mailbox: str | None = None) -> dict[str, Any]:
        ...


@dataclass(slots=True)
class MailService:
    repository: DraftRepository
    sender: MailSender
    config: AppConfig
    sent_recorder: SentMailboxRecorder | None = None

    def create_greeting_template(
        self,
        *,
        name: str,
        text_template: str = "",
        html_template: str = "",
        is_default: bool = False,
    ) -> GreetingTemplate:
        template = GreetingTemplate(
            id=str(uuid.uuid4()),
            name=name,
            text_template=text_template,
            html_template=html_template,
            is_default=is_default,
        )
        template.validate()
        return self.repository.upsert_greeting_template(template)

    def update_greeting_template(
        self,
        template_id: str,
        *,
        name: str | None = None,
        text_template: str | None = None,
        html_template: str | None = None,
        is_default: bool | None = None,
    ) -> GreetingTemplate:
        template = self.require_greeting_template(template_id)
        if name is not None:
            template.name = name
        if text_template is not None:
            template.text_template = text_template
        if html_template is not None:
            template.html_template = html_template
        if is_default is not None:
            template.is_default = is_default
        template.validate()
        return self.repository.upsert_greeting_template(template)

    def require_greeting_template(self, template_id: str) -> GreetingTemplate:
        template = self.repository.get_greeting_template(template_id)
        if template is None:
            raise ValueError(f"greeting template not found: {template_id}")
        return template

    def list_greeting_templates(self) -> list[GreetingTemplate]:
        return self.repository.list_greeting_templates()

    def delete_greeting_template(self, template_id: str) -> None:
        deleted = self.repository.delete_greeting_template(template_id)
        if not deleted:
            raise ValueError(f"greeting template not found: {template_id}")

    def create_signature_profile(
        self,
        *,
        name: str,
        fields: dict[str, str] | None = None,
        logo_image_path: str = "",
        is_default: bool = False,
    ) -> SignatureProfile:
        profile = SignatureProfile(
            id=str(uuid.uuid4()),
            name=name,
            fields=fields or {},
            logo_image_path=self._normalize_logo_path(logo_image_path),
            is_default=is_default,
        )
        profile.validate()
        return self.repository.upsert_signature_profile(profile)

    def update_signature_profile(
        self,
        profile_id: str,
        *,
        name: str | None = None,
        fields: dict[str, str] | None = None,
        logo_image_path: str | None = None,
        is_default: bool | None = None,
    ) -> SignatureProfile:
        profile = self.require_signature_profile(profile_id)
        if name is not None:
            profile.name = name
        if fields is not None:
            profile.fields = fields
        if logo_image_path is not None:
            profile.logo_image_path = self._normalize_logo_path(logo_image_path)
        if is_default is not None:
            profile.is_default = is_default
        profile.validate()
        return self.repository.upsert_signature_profile(profile)

    def require_signature_profile(self, profile_id: str) -> SignatureProfile:
        profile = self.repository.get_signature_profile(profile_id)
        if profile is None:
            raise ValueError(f"signature profile not found: {profile_id}")
        return profile

    def list_signature_profiles(self) -> list[SignatureProfile]:
        return self.repository.list_signature_profiles()

    def delete_signature_profile(self, profile_id: str) -> None:
        deleted = self.repository.delete_signature_profile(profile_id)
        if not deleted:
            raise ValueError(f"signature profile not found: {profile_id}")

    def create_closing_template(
        self,
        *,
        name: str,
        text_template: str = "",
        html_template: str = "",
        is_default: bool = False,
    ) -> ClosingTemplate:
        template = ClosingTemplate(
            id=str(uuid.uuid4()),
            name=name,
            text_template=text_template,
            html_template=html_template,
            is_default=is_default,
        )
        template.validate()
        return self.repository.upsert_closing_template(template)

    def update_closing_template(
        self,
        template_id: str,
        *,
        name: str | None = None,
        text_template: str | None = None,
        html_template: str | None = None,
        is_default: bool | None = None,
    ) -> ClosingTemplate:
        template = self.require_closing_template(template_id)
        if name is not None:
            template.name = name
        if text_template is not None:
            template.text_template = text_template
        if html_template is not None:
            template.html_template = html_template
        if is_default is not None:
            template.is_default = is_default
        template.validate()
        return self.repository.upsert_closing_template(template)

    def require_closing_template(self, template_id: str) -> ClosingTemplate:
        template = self.repository.get_closing_template(template_id)
        if template is None:
            raise ValueError(f"closing template not found: {template_id}")
        return template

    def list_closing_templates(self) -> list[ClosingTemplate]:
        return self.repository.list_closing_templates()

    def delete_closing_template(self, template_id: str) -> None:
        deleted = self.repository.delete_closing_template(template_id)
        if not deleted:
            raise ValueError(f"closing template not found: {template_id}")

    def create_signature(
        self,
        *,
        name: str,
        text_template: str = "",
        html_template: str = "",
        mode: str = "wrap_body",
        is_default: bool = False,
    ) -> SignatureTemplate:
        signature = SignatureTemplate(
            id=str(uuid.uuid4()),
            name=name,
            text_template=text_template,
            html_template=html_template,
            mode=mode,
            is_default=is_default,
        )
        signature.validate()
        return self.repository.upsert_signature(signature)

    def update_signature(
        self,
        signature_id: str,
        *,
        name: str | None = None,
        text_template: str | None = None,
        html_template: str | None = None,
        mode: str | None = None,
        is_default: bool | None = None,
    ) -> SignatureTemplate:
        signature = self.require_signature(signature_id)
        if name is not None:
            signature.name = name
        if text_template is not None:
            signature.text_template = text_template
        if html_template is not None:
            signature.html_template = html_template
        if mode is not None:
            signature.mode = mode
        if is_default is not None:
            signature.is_default = is_default
        signature.validate()
        return self.repository.upsert_signature(signature)

    def require_signature(self, signature_id: str) -> SignatureTemplate:
        signature = self.repository.get_signature(signature_id)
        if signature is None:
            raise ValueError(f"signature not found: {signature_id}")
        return signature

    def list_signatures(self) -> list[SignatureTemplate]:
        return self.repository.list_signatures()

    def delete_signature(self, signature_id: str) -> None:
        deleted = self.repository.delete_signature(signature_id)
        if not deleted:
            raise ValueError(f"signature not found: {signature_id}")

    def signature_for_draft(self, draft: MessageDraft) -> SignatureTemplate | None:
        if not draft.signature_id:
            return None
        return self.repository.get_signature(draft.signature_id)

    def greeting_for_draft(self, draft: MessageDraft) -> GreetingTemplate | None:
        if not draft.greeting_template_id:
            return None
        return self.repository.get_greeting_template(draft.greeting_template_id)

    def closing_for_draft(self, draft: MessageDraft) -> ClosingTemplate | None:
        if not draft.closing_template_id:
            return None
        return self.repository.get_closing_template(draft.closing_template_id)

    def signature_profile_for_draft(self, draft: MessageDraft) -> SignatureProfile | None:
        if not draft.signature_profile_id:
            return None
        return self.repository.get_signature_profile(draft.signature_profile_id)

    def create_draft(
        self,
        *,
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
    ) -> MessageDraft:
        greeting = self._resolve_greeting_template(
            greeting_template_id,
            apply_default_greeting_template=apply_default_greeting_template,
        )
        closing = self._resolve_closing_template(
            closing_template_id,
            apply_default_closing_template=apply_default_closing_template,
        )
        signature = self._resolve_signature(signature_id, apply_default_signature=apply_default_signature)
        profile = self._resolve_signature_profile(
            signature_profile_id,
            apply_default_signature_profile=apply_default_signature_profile,
        )
        draft = MessageDraft(
            id=str(uuid.uuid4()),
            subject=subject,
            to=to,
            cc=cc or [],
            bcc=bcc or [],
            reply_to=reply_to or [],
            text_body=text_body,
            html_body=html_body,
            attachments=self._materialize_attachments(attachment_paths or []),
            from_address=from_address or self.config.default_from_address,
            from_name=self._resolve_from_name(from_name, profile=profile),
            in_reply_to=in_reply_to,
            references=references or [],
            greeting_template_id=greeting.id if greeting else None,
            closing_template_id=closing.id if closing else None,
            signature_id=signature.id if signature else None,
            signature_profile_id=profile.id if profile else None,
            status="draft",
        )
        draft.validate()
        return self.repository.upsert(draft)

    def create_reply_draft_from_message(
        self,
        *,
        original_message: dict[str, Any],
        reply_all: bool,
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
    ) -> MessageDraft:
        from_address_value = from_address or self.config.default_from_address
        recipients = _build_reply_recipients(
            original_message=original_message,
            self_address=from_address_value,
            reply_all=reply_all,
        )
        subject = _reply_subject(str(original_message.get("subject", "")))
        quoted_text = _build_reply_quote_text(original_message)
        quoted_html = _build_reply_quote_html(original_message)
        combined_text = _append_reply_quote(text_body, quoted_text)
        combined_html = _append_reply_quote_html(html_body, quoted_html)
        references = _build_references(original_message)
        return self.create_draft(
            subject=subject,
            to=recipients["to"],
            cc=recipients["cc"],
            bcc=[],
            reply_to=[],
            text_body=combined_text,
            html_body=combined_html,
            attachment_paths=attachment_paths,
            from_address=from_address_value,
            from_name=from_name,
            in_reply_to=str(original_message.get("message_id", "") or ""),
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

    def update_draft(self, draft_id: str, **updates: object) -> MessageDraft:
        draft = self.require_draft(draft_id)
        if draft.status == "sent":
            raise ValueError("sent draft cannot be modified")
        greeting_template_id = updates.pop("greeting_template_id", _UNSET)
        apply_default_greeting_template = bool(updates.pop("apply_default_greeting_template", False))
        clear_greeting_template = bool(updates.pop("clear_greeting_template", False))
        greeting_flags = (
            int(greeting_template_id is not _UNSET)
            + int(apply_default_greeting_template)
            + int(clear_greeting_template)
        )
        if greeting_flags > 1:
            raise ValueError("greeting options are mutually exclusive")
        if clear_greeting_template:
            draft.greeting_template_id = None
        elif greeting_template_id is not _UNSET:
            if greeting_template_id in (None, ""):
                draft.greeting_template_id = None
            else:
                resolved_greeting_id = str(greeting_template_id)
                self.require_greeting_template(resolved_greeting_id)
                draft.greeting_template_id = resolved_greeting_id
        elif apply_default_greeting_template:
            template = self.repository.get_default_greeting_template()
            draft.greeting_template_id = template.id if template else None

        closing_template_id = updates.pop("closing_template_id", _UNSET)
        apply_default_closing_template = bool(updates.pop("apply_default_closing_template", False))
        clear_closing_template = bool(updates.pop("clear_closing_template", False))
        closing_flags = (
            int(closing_template_id is not _UNSET)
            + int(apply_default_closing_template)
            + int(clear_closing_template)
        )
        if closing_flags > 1:
            raise ValueError("closing options are mutually exclusive")
        if clear_closing_template:
            draft.closing_template_id = None
        elif closing_template_id is not _UNSET:
            if closing_template_id in (None, ""):
                draft.closing_template_id = None
            else:
                resolved_closing_id = str(closing_template_id)
                self.require_closing_template(resolved_closing_id)
                draft.closing_template_id = resolved_closing_id
        elif apply_default_closing_template:
            template = self.repository.get_default_closing_template()
            draft.closing_template_id = template.id if template else None

        signature_id = updates.pop("signature_id", _UNSET)
        apply_default_signature = bool(updates.pop("apply_default_signature", False))
        clear_signature = bool(updates.pop("clear_signature", False))
        signature_flags = int(signature_id is not _UNSET) + int(apply_default_signature) + int(clear_signature)
        if signature_flags > 1:
            raise ValueError("signature options are mutually exclusive")
        if clear_signature:
            draft.signature_id = None
        elif signature_id is not _UNSET:
            if signature_id in (None, ""):
                draft.signature_id = None
            else:
                resolved_signature_id = str(signature_id)
                self.require_signature(resolved_signature_id)
                draft.signature_id = resolved_signature_id
        elif apply_default_signature:
            signature = self.repository.get_default_signature()
            draft.signature_id = signature.id if signature else None

        signature_profile_id = updates.pop("signature_profile_id", _UNSET)
        apply_default_signature_profile = bool(updates.pop("apply_default_signature_profile", False))
        clear_signature_profile = bool(updates.pop("clear_signature_profile", False))
        profile_flags = (
            int(signature_profile_id is not _UNSET)
            + int(apply_default_signature_profile)
            + int(clear_signature_profile)
        )
        if profile_flags > 1:
            raise ValueError("signature profile options are mutually exclusive")
        if clear_signature_profile:
            draft.signature_profile_id = None
        elif signature_profile_id is not _UNSET:
            if signature_profile_id in (None, ""):
                draft.signature_profile_id = None
            else:
                resolved_profile_id = str(signature_profile_id)
                self.require_signature_profile(resolved_profile_id)
                draft.signature_profile_id = resolved_profile_id
        elif apply_default_signature_profile:
            profile = self.repository.get_default_signature_profile()
            draft.signature_profile_id = profile.id if profile else None

        attachment_paths = updates.pop("attachment_paths", _UNSET)
        if attachment_paths is not _UNSET and attachment_paths is not None:
            draft.attachments = self._materialize_attachments(list(attachment_paths))
        for field_name, value in updates.items():
            if value is not None and hasattr(draft, field_name):
                setattr(draft, field_name, value)
        if "from_name" in updates and updates["from_name"] is None:
            draft.from_name = ""
        draft.validate()
        return self.repository.upsert(draft)

    def preview_signature(
        self,
        *,
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
        if not (text_body or html_body):
            raise ValueError("text_body or html_body is required")
        greeting = self._resolve_greeting_template(
            greeting_template_id,
            apply_default_greeting_template=apply_default_greeting_template,
        )
        closing = self._resolve_closing_template(
            closing_template_id,
            apply_default_closing_template=apply_default_closing_template,
        )
        signature = self._resolve_signature(signature_id, apply_default_signature=apply_default_signature)
        profile = self._resolve_signature_profile(
            signature_profile_id,
            apply_default_signature_profile=apply_default_signature_profile,
        )
        preview_draft = MessageDraft(
            id="preview",
            subject="preview",
            to=["preview@example.com"],
            text_body=text_body,
            html_body=html_body,
            greeting_template_id=greeting.id if greeting else None,
            closing_template_id=closing.id if closing else None,
            signature_id=signature.id if signature else None,
            signature_profile_id=profile.id if profile else None,
        )
        rendered_preview = preview_draft.rendered_copy(
            signature,
            greeting=greeting,
            closing=closing,
            profile=profile,
        )
        return {
            "text_body": text_body,
            "html_body": html_body,
            "rendered_text_body": rendered_preview.text_body,
            "rendered_html_body": rendered_preview.html_body,
            "inline_attachments": [attachment.to_dict() for attachment in rendered_preview.inline_attachments],
            "greeting_template": greeting.to_dict() if greeting else None,
            "closing_template": closing.to_dict() if closing else None,
            "signature": signature.to_dict() if signature else None,
            "signature_profile": profile.to_dict() if profile else None,
        }

    def preview_closing_signature(
        self,
        *,
        signature_id: str | None = None,
        signature_profile_id: str | None = None,
        apply_default_signature: bool = True,
        apply_default_signature_profile: bool = True,
        export_dir: str | None = None,
    ) -> dict[str, Any]:
        signature = self._resolve_signature(signature_id, apply_default_signature=apply_default_signature)
        if signature is None:
            raise ValueError("closing signature preview requires a signature template")
        if signature.mode != "closing_only":
            raise ValueError("closing signature preview requires a closing_only signature template")
        profile = self._resolve_signature_profile(
            signature_profile_id,
            apply_default_signature_profile=apply_default_signature_profile,
        )
        preview_draft = MessageDraft(
            id="closing-preview",
            subject="closing-preview",
            to=["preview@example.com"],
            text_body="",
            html_body="",
            signature_id=signature.id,
            signature_profile_id=profile.id if profile else None,
        )
        rendered_preview = preview_draft.rendered_copy(signature, profile=profile)
        result = {
            "rendered_text_body": rendered_preview.text_body,
            "rendered_html_body": rendered_preview.html_body,
            "inline_attachments": [attachment.to_dict() for attachment in rendered_preview.inline_attachments],
            "signature": signature.to_dict(),
            "signature_profile": profile.to_dict() if profile else None,
        }
        if export_dir:
            result["export"] = self._export_signature_preview(
                html_body=rendered_preview.html_body,
                inline_attachments=rendered_preview.inline_attachments,
                export_dir=export_dir,
            )
        return result

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

    def render_draft(self, draft_id: str) -> MessageDraft:
        draft = self.require_draft(draft_id)
        rendered = draft.rendered_copy(
            self.signature_for_draft(draft),
            greeting=self.greeting_for_draft(draft),
            closing=self.closing_for_draft(draft),
            profile=self.signature_profile_for_draft(draft),
        )
        rendered.validate()
        return rendered

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
        if not (self.config.smtp_use_tls or self.config.smtp_use_starttls):
            raise ValueError("SMTP transport must use TLS or STARTTLS")
        sending_draft = self.render_draft(draft.id)
        draft.status = "sending"
        draft.last_error = None
        self.repository.upsert(draft)
        try:
            self.sender.send(sending_draft)
        except Exception as exc:
            draft.status = "failed"
            draft.last_error = str(exc)
            self.repository.upsert(draft)
            raise
        draft.status = "sent"
        draft.sent_at = datetime.now(timezone.utc)
        draft.scheduled_for = None
        draft.last_error = None
        saved = self.repository.upsert(draft)
        self._record_sent_copy(sending_draft, saved)
        return saved

    def _record_sent_copy(self, sending_draft: MessageDraft, saved_draft: MessageDraft) -> None:
        # Best-effort: the mail is already sent. If copying it into the IMAP
        # Sent mailbox fails, keep the send successful and record a warning.
        if self.sent_recorder is None:
            return
        sending_draft.sent_at = saved_draft.sent_at
        try:
            self.sent_recorder.upload_to_sent(draft=sending_draft)
        except Exception as exc:
            saved_draft.last_error = f"sent-copy-failed: {exc}"
            self.repository.upsert(saved_draft)

    def _resolve_signature(
        self,
        signature_id: str | None,
        *,
        apply_default_signature: bool,
    ) -> SignatureTemplate | None:
        if signature_id:
            return self.require_signature(signature_id)
        if not apply_default_signature:
            return None
        return self.repository.get_default_signature()

    def _resolve_greeting_template(
        self,
        template_id: str | None,
        *,
        apply_default_greeting_template: bool,
    ) -> GreetingTemplate | None:
        if template_id:
            return self.require_greeting_template(template_id)
        if not apply_default_greeting_template:
            return None
        return self.repository.get_default_greeting_template()

    def _resolve_signature_profile(
        self,
        profile_id: str | None,
        *,
        apply_default_signature_profile: bool,
    ) -> SignatureProfile | None:
        if profile_id:
            return self.require_signature_profile(profile_id)
        if not apply_default_signature_profile:
            return None
        return self.repository.get_default_signature_profile()

    def _resolve_closing_template(
        self,
        template_id: str | None,
        *,
        apply_default_closing_template: bool,
    ) -> ClosingTemplate | None:
        if template_id:
            return self.require_closing_template(template_id)
        if not apply_default_closing_template:
            return None
        return self.repository.get_default_closing_template()

    def _materialize_attachments(self, attachment_paths: list[str]) -> list[DraftAttachment]:
        attachments: list[DraftAttachment] = []
        for raw_path in attachment_paths:
            path = Path(raw_path).expanduser()
            if not path.is_file():
                raise ValueError(f"attachment file not found: {path}")
            _ensure_safe_attachment_source(path)
            content_type, _encoding = mimetypes.guess_type(path.name)
            attachments.append(
                DraftAttachment(
                    id=str(uuid.uuid4()),
                    file_path=str(path.resolve()),
                    filename=path.name,
                    content_type=content_type or "application/octet-stream",
                    size_bytes=path.stat().st_size,
                    created_at=datetime.now(timezone.utc),
                )
            )
        return attachments

    def _normalize_logo_path(self, logo_image_path: str) -> str:
        if not logo_image_path.strip():
            return ""
        path = Path(logo_image_path).expanduser()
        if not path.is_file():
            raise ValueError(f"logo image file not found: {path}")
        _ensure_safe_attachment_source(path)
        return str(path.resolve())

    def _resolve_from_name(self, from_name: str | None, *, profile: SignatureProfile | None) -> str:
        if from_name is not None:
            return from_name.strip()
        if profile is not None:
            display_name = profile.fields.get("display_name", "").strip()
            if display_name:
                return display_name
        if self.config.default_from_name.strip():
            return self.config.default_from_name.strip()
        contacts = self.config.load_contacts()
        return contacts.get(self.config.default_from_address.strip().lower(), "")

    def _export_signature_preview(
        self,
        *,
        html_body: str,
        inline_attachments: list,
        export_dir: str,
    ) -> dict[str, str]:
        base_dir = Path(export_dir).expanduser().resolve()
        assets_dir = base_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        exported_html = html_body
        for attachment in inline_attachments:
            source = attachment.path.expanduser()
            target = assets_dir / attachment.filename
            shutil.copyfile(source, target)
            exported_html = exported_html.replace(
                f'cid:{attachment.cid}',
                f'assets/{html.escape(attachment.filename)}',
            )
        document = (
            "<!DOCTYPE html>\n"
            '<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            "<title>Signature Preview</title>\n"
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<style>body{font-family:"Malgun Gothic",sans-serif;margin:24px;color:#222;}'
            'img{max-width:320px;height:auto;}hr{border:none;border-top:1px solid #cfcfcf;margin:16px 0;}'
            "</style>\n</head>\n<body>\n"
            f"{exported_html}\n"
            "</body>\n</html>\n"
        )
        html_path = base_dir / "signature-preview.html"
        html_path.write_text(document, encoding="utf-8")
        return {
            "html_path": str(html_path),
            "assets_dir": str(assets_dir),
        }


_UNSET = object()


def _reply_subject(subject: str) -> str:
    normalized = subject.strip() or "(no subject)"
    if normalized.lower().startswith("re:"):
        return normalized
    return f"Re: {normalized}"


def _build_reply_recipients(
    *,
    original_message: dict[str, Any],
    self_address: str,
    reply_all: bool,
) -> dict[str, list[str]]:
    primary_source = original_message.get("reply_to") or original_message.get("from") or []
    primary = _dedupe_addresses(primary_source, exclude={self_address.lower()})
    if not primary:
        raise ValueError("original message has no reply recipient")
    if not reply_all:
        return {"to": primary, "cc": []}
    exclude = {self_address.lower(), *(address.lower() for address in primary)}
    cc = _dedupe_addresses(
        [*(original_message.get("to") or []), *(original_message.get("cc") or [])],
        exclude=exclude,
    )
    return {"to": primary, "cc": cc}


def _dedupe_addresses(addresses: list[str], *, exclude: set[str] | None = None) -> list[str]:
    seen: set[str] = set()
    skipped = exclude or set()
    result: list[str] = []
    for address in addresses:
        normalized = address.strip().lower()
        if not normalized or normalized in skipped or normalized in seen:
            continue
        seen.add(normalized)
        result.append(address.strip())
    return result


def _build_reply_quote_text(original_message: dict[str, Any]) -> str:
    date_value = str(original_message.get("date", "") or "")
    sender = ", ".join(original_message.get("from") or [])
    body = str(original_message.get("text_body", "") or "")
    quoted_lines = "\n".join(f"> {line}" if line else ">" for line in body.splitlines())
    return f"On {date_value}, {sender} wrote:\n{quoted_lines}".strip()


def _build_reply_quote_html(original_message: dict[str, Any]) -> str:
    date_value = html.escape(str(original_message.get("date", "") or ""))
    sender = html.escape(", ".join(original_message.get("from") or []))
    original_html = str(original_message.get("html_body", "") or "").strip()
    if not original_html:
        original_html = (
            '<div style="white-space:pre-line;">'
            + html.escape(str(original_message.get("text_body", "") or ""))
            + "</div>"
        )
    return (
        f'<div style="margin-top:12px;color:#666;font-size:13px;">On {date_value}, {sender} wrote:</div>'
        f'<blockquote style="margin:8px 0 0 0;padding-left:12px;border-left:2px solid #d0d0d0;">{original_html}</blockquote>'
    )


def _append_reply_quote(text_body: str, quoted_text: str) -> str:
    head = text_body.strip()
    if head:
        return f"{head}\n\n{quoted_text}"
    return quoted_text


def _append_reply_quote_html(html_body: str, quoted_html: str) -> str:
    head = html_body.strip()
    if head:
        return f"{head}{quoted_html}"
    return ""


def _build_references(original_message: dict[str, Any]) -> list[str]:
    references = [str(item).strip() for item in original_message.get("references") or [] if str(item).strip()]
    message_id = str(original_message.get("message_id", "") or "").strip()
    if message_id and message_id not in references:
        references.append(message_id)
    return references
