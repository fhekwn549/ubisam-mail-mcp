from __future__ import annotations

import html
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any


BODY_PLACEHOLDER = "{{body}}"
VALID_STATUSES = {"draft", "scheduled", "sending", "sent", "failed"}
VALID_SIGNATURE_MODES = {"wrap_body", "closing_only"}
_PLACEHOLDER_RE = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")
DEFAULT_TEXT_FONT_SIZE_PX = 16
DEFAULT_TEXT_LINE_HEIGHT = 1.5
DEFAULT_BLANK_LINE_HEIGHT_EM = DEFAULT_TEXT_LINE_HEIGHT


@dataclass(slots=True)
class DraftAttachment:
    id: str
    file_path: str
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime | None = None

    def validate(self) -> None:
        if not self.file_path.strip():
            raise ValueError("attachment file_path is required")
        if not self.filename.strip():
            raise ValueError("attachment filename is required")
        if self.size_bytes < 0:
            raise ValueError("attachment size_bytes must be non-negative")

    @property
    def path(self) -> Path:
        return Path(self.file_path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file_path": self.file_path,
            "filename": self.filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "created_at": _datetime_to_iso(self.created_at),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DraftAttachment":
        return cls(
            id=str(value["id"]),
            file_path=str(value["file_path"]),
            filename=str(value["filename"]),
            content_type=str(value.get("content_type", "application/octet-stream")),
            size_bytes=int(value.get("size_bytes", 0)),
            created_at=_parse_datetime(value.get("created_at")),
        )


@dataclass(slots=True)
class InlineAttachment:
    cid: str
    file_path: str
    filename: str
    content_type: str

    def validate(self) -> None:
        if not self.cid.strip():
            raise ValueError("inline attachment cid is required")
        if not self.file_path.strip():
            raise ValueError("inline attachment file_path is required")
        if not self.filename.strip():
            raise ValueError("inline attachment filename is required")

    @property
    def path(self) -> Path:
        return Path(self.file_path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cid": self.cid,
            "file_path": self.file_path,
            "filename": self.filename,
            "content_type": self.content_type,
        }


@dataclass(slots=True)
class SignatureProfile:
    id: str
    name: str
    fields: dict[str, str] = field(default_factory=dict)
    logo_image_path: str = ""
    is_default: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("signature profile name is required")
        self.fields = {str(key): str(value) for key, value in self.fields.items()}

    @property
    def logo_path(self) -> Path | None:
        if not self.logo_image_path.strip():
            return None
        return Path(self.logo_image_path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "fields": self.fields,
            "logo_image_path": self.logo_image_path,
            "is_default": self.is_default,
            "created_at": _datetime_to_iso(self.created_at),
            "updated_at": _datetime_to_iso(self.updated_at),
        }


@dataclass(slots=True)
class GreetingTemplate:
    id: str
    name: str
    text_template: str = ""
    html_template: str = ""
    is_default: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("greeting template name is required")
        if not (self.text_template or self.html_template):
            raise ValueError("text_template or html_template is required")

    def render_text(self, context: dict[str, str]) -> str:
        return _render_template(self.text_template, context)

    def render_html(self, context: dict[str, str]) -> str:
        if self.html_template:
            return _render_template(self.html_template, context)
        return _text_to_html(self.render_text(context))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "text_template": self.text_template,
            "html_template": self.html_template,
            "is_default": self.is_default,
            "created_at": _datetime_to_iso(self.created_at),
            "updated_at": _datetime_to_iso(self.updated_at),
        }


@dataclass(slots=True)
class ClosingTemplate:
    id: str
    name: str
    text_template: str = ""
    html_template: str = ""
    is_default: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("closing template name is required")
        if not (self.text_template or self.html_template):
            raise ValueError("text_template or html_template is required")

    def render_text(self, context: dict[str, str]) -> str:
        return _render_template(self.text_template, context)

    def render_html(self, context: dict[str, str]) -> str:
        if self.html_template:
            return _render_template(self.html_template, context)
        return _text_to_html(self.render_text(context))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "text_template": self.text_template,
            "html_template": self.html_template,
            "is_default": self.is_default,
            "created_at": _datetime_to_iso(self.created_at),
            "updated_at": _datetime_to_iso(self.updated_at),
        }


@dataclass(slots=True)
class SignatureTemplate:
    id: str
    name: str
    text_template: str = ""
    html_template: str = ""
    mode: str = "wrap_body"
    is_default: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("signature name is required")
        if not (self.text_template or self.html_template):
            raise ValueError("text_template or html_template is required")
        if self.mode not in VALID_SIGNATURE_MODES:
            raise ValueError(f"invalid signature mode: {self.mode}")
        if self.mode == "wrap_body":
            if self.text_template and BODY_PLACEHOLDER not in self.text_template:
                raise ValueError("text_template must include {{body}}")
            if self.html_template and BODY_PLACEHOLDER not in self.html_template:
                raise ValueError("html_template must include {{body}}")

    def render_text(self, body: str, context: dict[str, str] | None = None) -> str:
        if not self.text_template:
            return body
        template_context = dict(context or {})
        template_context["body"] = body
        return _render_template(self.text_template, template_context)

    def render_html(self, body: str, context: dict[str, str] | None = None) -> str:
        if not self.html_template:
            return body
        template_context = dict(context or {})
        template_context["body"] = body
        return _render_template(self.html_template, template_context)

    def render_closing_text(self, context: dict[str, str]) -> str:
        return _render_template(self.text_template, context)

    def render_closing_html(self, context: dict[str, str]) -> str:
        if self.html_template:
            return _render_template(self.html_template, context)
        return _text_to_html(self.render_closing_text(context))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "text_template": self.text_template,
            "html_template": self.html_template,
            "mode": self.mode,
            "is_default": self.is_default,
            "created_at": _datetime_to_iso(self.created_at),
            "updated_at": _datetime_to_iso(self.updated_at),
        }


@dataclass(slots=True)
class MessageDraft:
    id: str
    subject: str
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    reply_to: list[str] = field(default_factory=list)
    text_body: str = ""
    html_body: str = ""
    attachments: list[DraftAttachment] = field(default_factory=list)
    inline_attachments: list[InlineAttachment] = field(default_factory=list)
    from_address: str = ""
    from_name: str = ""
    in_reply_to: str = ""
    references: list[str] = field(default_factory=list)
    greeting_template_id: str | None = None
    closing_template_id: str | None = None
    signature_id: str | None = None
    signature_profile_id: str | None = None
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
        for attachment in self.attachments:
            attachment.validate()
        for inline_attachment in self.inline_attachments:
            inline_attachment.validate()

    def rendered_text_body(
        self,
        signature: SignatureTemplate | None = None,
        *,
        greeting: GreetingTemplate | None = None,
        closing: ClosingTemplate | None = None,
        profile: SignatureProfile | None = None,
    ) -> str:
        context, _inline_attachments = build_profile_context(profile)
        sections: list[str] = []
        if greeting:
            greeting_text = greeting.render_text(context)
            if greeting_text.strip():
                sections.append(greeting_text.strip())
        body_text = self.text_body
        if signature and signature.mode == "wrap_body":
            body_text = signature.render_text(self.text_body, context) if self.text_body else ""
        if body_text.strip():
            sections.append(body_text.strip())
        if closing:
            closing_text = closing.render_text(context)
            if closing_text.strip():
                sections.append(closing_text.strip())
        if signature and signature.mode == "closing_only":
            closing_text = signature.render_closing_text(context)
            if closing_text.strip():
                sections.append(closing_text.strip())
        return "\n\n".join(sections)

    def rendered_html_body(
        self,
        signature: SignatureTemplate | None = None,
        *,
        greeting: GreetingTemplate | None = None,
        closing: ClosingTemplate | None = None,
        profile: SignatureProfile | None = None,
    ) -> str:
        context, _inline_attachments = build_profile_context(profile)
        sections: list[tuple[str, str]] = []
        if greeting:
            if greeting.html_template:
                greeting_html = greeting.render_html(context)
                if greeting_html.strip():
                    sections.append(("html", greeting_html.strip()))
            else:
                greeting_text = greeting.render_text(context)
                if greeting_text.strip():
                    sections.append(("text", greeting_text.strip()))
        body_html = self.html_body
        if signature and signature.mode == "wrap_body":
            body_html = signature.render_html(self.html_body, context) if self.html_body else ""
        if body_html.strip():
            sections.append(("html", body_html.strip()))
        elif self.text_body.strip():
            body_text = self.text_body
            if signature and signature.mode == "wrap_body":
                body_text = signature.render_text(self.text_body, context) if self.text_body else ""
            if body_text.strip():
                sections.append(("text", body_text.strip()))
        if closing:
            if closing.html_template:
                closing_html = closing.render_html(context)
                if closing_html.strip():
                    sections.append(("html", closing_html.strip()))
            else:
                closing_text = closing.render_text(context)
                if closing_text.strip():
                    sections.append(("text", closing_text.strip()))
        if signature and signature.mode == "closing_only":
            if signature.html_template:
                footer_html = signature.render_closing_html(context)
                if footer_html.strip():
                    sections.append(("html", footer_html.strip()))
            else:
                footer_text = signature.render_closing_text(context)
                if footer_text.strip():
                    sections.append(("text", footer_text.strip()))
        return _join_rendered_sections(sections)

    def rendered_copy(
        self,
        signature: SignatureTemplate | None = None,
        *,
        greeting: GreetingTemplate | None = None,
        closing: ClosingTemplate | None = None,
        profile: SignatureProfile | None = None,
    ) -> MessageDraft:
        _context, inline_attachments = build_profile_context(profile)
        return replace(
            self,
            text_body=self.rendered_text_body(signature, greeting=greeting, closing=closing, profile=profile),
            html_body=self.rendered_html_body(signature, greeting=greeting, closing=closing, profile=profile),
            inline_attachments=inline_attachments,
        )

    def to_dict(
        self,
        signature: SignatureTemplate | None = None,
        *,
        greeting: GreetingTemplate | None = None,
        closing: ClosingTemplate | None = None,
        profile: SignatureProfile | None = None,
    ) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "to": self.to,
            "cc": self.cc,
            "bcc": self.bcc,
            "reply_to": self.reply_to,
            "text_body": self.text_body,
            "html_body": self.html_body,
            "attachments": [attachment.to_dict() for attachment in self.attachments],
            "inline_attachments": [attachment.to_dict() for attachment in self.inline_attachments],
            "rendered_text_body": self.rendered_text_body(signature, greeting=greeting, closing=closing, profile=profile),
            "rendered_html_body": self.rendered_html_body(signature, greeting=greeting, closing=closing, profile=profile),
            "from_address": self.from_address,
            "from_name": self.from_name,
            "in_reply_to": self.in_reply_to,
            "references": self.references,
            "greeting_template_id": self.greeting_template_id,
            "closing_template_id": self.closing_template_id,
            "signature_id": self.signature_id,
            "signature_profile_id": self.signature_profile_id,
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


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def build_profile_context(profile: SignatureProfile | None) -> tuple[dict[str, str], list[InlineAttachment]]:
    if profile is None:
        return {}, []
    context = dict(profile.fields)
    inline_attachments: list[InlineAttachment] = []
    logo_path = profile.logo_path
    if logo_path is not None:
        cid = f"profile-logo-{profile.id}"
        inline_attachments.append(
            InlineAttachment(
                cid=cid,
                file_path=str(logo_path.expanduser()),
                filename=logo_path.name,
                content_type=_guess_content_type(logo_path.name),
            )
        )
        context["company_logo_img"] = (
            f'<img src="cid:{cid}" alt="company logo" '
            'style="height:28px;width:auto;display:block;">'
        )
    else:
        context["company_logo_img"] = ""
    return context, inline_attachments


def _render_template(template: str, context: dict[str, str]) -> str:
    if not template:
        return ""

    def replace_placeholder(match: re.Match[str]) -> str:
        return context.get(match.group(1), "")

    return _PLACEHOLDER_RE.sub(replace_placeholder, template)


def _text_to_html(text: str) -> str:
    if not text:
        return ""
    return (
        f'<div style="white-space:pre-line; line-height:{DEFAULT_TEXT_LINE_HEIGHT}; '
        f'font-size:{DEFAULT_TEXT_FONT_SIZE_PX}px; color:#222;">'
        + html.escape(text)
        + "</div>"
    )


def _join_html_sections(sections: list[str]) -> str:
    non_empty = [section for section in sections if section.strip()]
    if not non_empty:
        return ""
    spacer = f'<div style="height:{DEFAULT_BLANK_LINE_HEIGHT_EM}em;"></div>'
    return spacer.join(non_empty)


def _join_rendered_sections(sections: list[tuple[str, str]]) -> str:
    rendered_parts: list[str] = []
    text_buffer: list[str] = []

    def flush_text_buffer() -> None:
        if not text_buffer:
            return
        rendered_parts.append(_text_to_html("\n\n".join(text_buffer)))
        text_buffer.clear()

    for section_type, content in sections:
        if not content.strip():
            continue
        if section_type == "text":
            text_buffer.append(content)
            continue
        flush_text_buffer()
        rendered_parts.append(content)

    flush_text_buffer()
    return _join_html_sections(rendered_parts)


def _guess_content_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".png"}:
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".gif":
        return "image/gif"
    if suffix == ".svg":
        return "image/svg+xml"
    return "application/octet-stream"
