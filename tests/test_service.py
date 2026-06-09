from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ubisam_mail_mcp.config import AppConfig
from ubisam_mail_mcp.repository import DraftRepository
from ubisam_mail_mcp.service import MailService, _ensure_safe_attachment_source


class FakeSender:
    def __init__(self) -> None:
        self.sent_ids: list[str] = []
        self.sent_drafts: list[object] = []

    def send(self, draft) -> None:
        self.sent_ids.append(draft.id)
        self.sent_drafts.append(draft)


def make_service(tmp_path):
    config = AppConfig(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="user",
        smtp_password="pass",
        smtp_use_tls=False,
        smtp_use_starttls=True,
        smtp_debug=False,
        smtp_tls_servername="smtp.example.com",
        imap_host="imap.example.com",
        imap_port=993,
        imap_username="user",
        imap_password="pass",
        imap_use_tls=True,
        imap_tls_servername="imap.example.com",
        default_from_address="bot@example.com",
        default_from_name="",
        sqlite_path=tmp_path / "mail.db",
        attachment_download_dir=tmp_path / "downloads",
        contacts_path=tmp_path / "contacts.local.json",
    )
    sender = FakeSender()
    service = MailService(
        repository=DraftRepository(config.sqlite_path),
        sender=sender,
        config=config,
    )
    return service, sender


def make_service_with_config(tmp_path, config: AppConfig):
    sender = FakeSender()
    service = MailService(
        repository=DraftRepository(config.sqlite_path),
        sender=sender,
        config=config,
    )
    return service, sender


def write_attachment(tmp_path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def write_logo(tmp_path) -> Path:
    path = tmp_path / "logo.png"
    path.write_bytes(
        bytes.fromhex(
            "89504E470D0A1A0A"
            "0000000D49484452000000010000000108060000001F15C489"
            "0000000D49444154789C6360000002000154A24F5D00000000"
            "49454E44AE426082"
        )
    )
    return path


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


def test_create_draft_persists_attachments(tmp_path):
    service, _sender = make_service(tmp_path)
    attachment = write_attachment(tmp_path, "hello.txt", "attachment body")

    draft = service.create_draft(
        subject="hello",
        to=["user@example.com"],
        text_body="body",
        attachment_paths=[str(attachment)],
    )

    loaded = service.require_draft(draft.id)
    assert len(loaded.attachments) == 1
    assert loaded.attachments[0].filename == "hello.txt"
    assert loaded.attachments[0].size_bytes == len("attachment body".encode("utf-8"))


def test_create_draft_applies_default_signature(tmp_path):
    service, _sender = make_service(tmp_path)
    signature = service.create_signature(
        name="default",
        text_template="안녕하세요.\n\n{{body}}\n\n감사합니다.\n회사",
        html_template=(
            "<p>안녕하세요.</p>"
            "<div>{{body}}</div>"
            "<p><strong>감사합니다.</strong><br>"
            '<span style="color:#666;font-size:12px;">회사</span></p>'
        ),
        is_default=True,
    )

    draft = service.create_draft(
        subject="hello",
        to=["user@example.com"],
        text_body="본문",
        html_body="<p>본문</p>",
    )

    loaded = service.require_draft(draft.id)
    rendered = loaded.to_dict(signature=signature)
    assert loaded.signature_id == signature.id
    assert rendered["rendered_text_body"] == "안녕하세요.\n\n본문\n\n감사합니다.\n회사"
    assert 'style="color:#666;font-size:12px;"' in rendered["rendered_html_body"]


def test_create_draft_applies_requested_signature_instead_of_default(tmp_path):
    service, _sender = make_service(tmp_path)
    default_signature = service.create_signature(
        name="default",
        text_template="기본\n{{body}}\n기본끝",
        is_default=True,
    )
    custom_signature = service.create_signature(
        name="custom",
        text_template="커스텀\n{{body}}\n커스텀끝",
    )

    draft = service.create_draft(
        subject="hello",
        to=["user@example.com"],
        text_body="본문",
        signature_id=custom_signature.id,
    )

    loaded = service.require_draft(draft.id)
    rendered = loaded.to_dict(signature=custom_signature)
    assert loaded.signature_id == custom_signature.id
    assert rendered["rendered_text_body"] == "커스텀\n본문\n커스텀끝"
    assert rendered["rendered_text_body"] != default_signature.render_text("본문")


def test_update_draft_reapplies_signature(tmp_path):
    service, _sender = make_service(tmp_path)
    signature = service.create_signature(
        name="default",
        text_template="머리말\n{{body}}\n꼬리말",
        is_default=True,
    )
    draft = service.create_draft(
        subject="hello",
        to=["user@example.com"],
        text_body="첫 본문",
    )

    updated = service.update_draft(draft.id, text_body="수정 본문")

    rendered = updated.to_dict(signature=signature)
    assert rendered["rendered_text_body"] == "머리말\n수정 본문\n꼬리말"


def test_update_draft_rendered_html_preserves_text_line_breaks(tmp_path):
    service, _sender = make_service(tmp_path)
    draft = service.create_draft(
        subject="hello",
        to=["user@example.com"],
        text_body="첫 줄\n둘째 줄",
        apply_default_signature=False,
        apply_default_greeting_template=False,
        apply_default_closing_template=False,
    )

    updated = service.update_draft(draft.id, text_body="수정 첫 줄\n수정 둘째 줄\n\n수정 셋째 줄")
    rendered = updated.to_dict()

    assert "수정 첫 줄<br>수정 둘째 줄<br><br>수정 셋째 줄" in rendered["rendered_html_body"]


def test_update_draft_can_clear_signature(tmp_path):
    service, _sender = make_service(tmp_path)
    signature = service.create_signature(
        name="default",
        text_template="머리말\n{{body}}\n꼬리말",
        is_default=True,
    )
    draft = service.create_draft(
        subject="hello",
        to=["user@example.com"],
        text_body="본문",
    )

    updated = service.update_draft(draft.id, clear_signature=True)

    assert updated.signature_id is None
    rendered = updated.to_dict(signature=service.signature_for_draft(updated))
    assert rendered["rendered_text_body"] == "본문"
    assert signature.render_text("본문") != rendered["rendered_text_body"]


def test_update_draft_can_apply_default_signature(tmp_path):
    service, _sender = make_service(tmp_path)
    signature = service.create_signature(
        name="default",
        text_template="머리말\n{{body}}\n꼬리말",
        is_default=True,
    )
    draft = service.create_draft(
        subject="hello",
        to=["user@example.com"],
        text_body="본문",
        apply_default_signature=False,
    )

    updated = service.update_draft(draft.id, apply_default_signature=True)

    assert updated.signature_id == signature.id
    rendered = updated.to_dict(signature=service.signature_for_draft(updated))
    assert rendered["rendered_text_body"] == "머리말\n본문\n꼬리말"


def test_render_draft_returns_applied_templates(tmp_path):
    service, _sender = make_service(tmp_path)
    greeting = service.create_greeting_template(
        name="greeting",
        text_template="안녕하세요.",
        is_default=True,
    )
    closing = service.create_closing_template(
        name="closing",
        text_template="감사합니다.",
        is_default=True,
    )
    signature = service.create_signature(
        name="footer",
        text_template="담당자 {{display_name}}",
        mode="closing_only",
        is_default=True,
    )
    profile = service.create_signature_profile(
        name="me",
        fields={"display_name": "홍길동"},
        is_default=True,
    )
    draft = service.create_draft(
        subject="hello",
        to=["user@example.com"],
        text_body="본문",
    )

    rendered = service.render_draft(draft.id)

    assert rendered.text_body == "안녕하세요.\n\n본문\n\n감사합니다.\n\n담당자 홍길동"
    assert "안녕하세요.<br><br>본문<br><br>감사합니다." in rendered.html_body
    assert '<div style="height:1.5em;"></div>' not in rendered.html_body
    assert rendered.greeting_template_id == greeting.id
    assert rendered.closing_template_id == closing.id
    assert rendered.signature_id == signature.id
    assert rendered.signature_profile_id == profile.id


def test_create_reply_draft_from_message_sets_headers_and_recipients(tmp_path):
    service, _sender = make_service(tmp_path)
    original = {
        "subject": "원본 제목",
        "from": ["sender@example.com"],
        "to": ["bot@example.com", "other@example.com"],
        "cc": ["cc1@example.com"],
        "reply_to": [],
        "message_id": "<msg-1@example.com>",
        "references": ["<msg-0@example.com>"],
        "date": "2026-06-02T10:00:00+09:00",
        "text_body": "원본 본문",
        "html_body": "<p>원본 본문</p>",
    }

    draft = service.create_reply_draft_from_message(
        original_message=original,
        reply_all=True,
        text_body="답장 본문",
        from_address="bot@example.com",
    )

    assert draft.subject == "Re: 원본 제목"
    assert draft.to == ["sender@example.com"]
    assert draft.cc == ["other@example.com", "cc1@example.com"]
    assert draft.in_reply_to == "<msg-1@example.com>"
    assert draft.references == ["<msg-0@example.com>", "<msg-1@example.com>"]
    assert "On 2026-06-02T10:00:00+09:00, sender@example.com wrote:" in draft.text_body
    assert "답장 본문" in draft.text_body


def test_create_draft_uses_profile_display_name_as_from_name(tmp_path):
    service, _sender = make_service(tmp_path)
    profile = service.create_signature_profile(
        name="me",
        fields={"display_name": "홍길동"},
        is_default=True,
    )

    draft = service.create_draft(
        subject="hello",
        to=["user@example.com"],
        text_body="본문",
        signature_profile_id=profile.id,
        apply_default_signature=False,
        apply_default_greeting_template=False,
        apply_default_closing_template=False,
        apply_default_signature_profile=False,
    )

    assert draft.from_name == "홍길동"


def test_update_draft_replaces_attachments(tmp_path):
    service, _sender = make_service(tmp_path)
    first = write_attachment(tmp_path, "first.txt", "first")
    second = write_attachment(tmp_path, "second.txt", "second-file")
    draft = service.create_draft(
        subject="hello",
        to=["user@example.com"],
        text_body="본문",
        attachment_paths=[str(first)],
    )

    updated = service.update_draft(draft.id, attachment_paths=[str(second)])

    assert [attachment.filename for attachment in updated.attachments] == ["second.txt"]
    assert updated.attachments[0].size_bytes == len("second-file".encode("utf-8"))


def test_create_draft_rejects_missing_attachment(tmp_path):
    service, _sender = make_service(tmp_path)

    try:
        service.create_draft(
            subject="hello",
            to=["user@example.com"],
            text_body="본문",
            attachment_paths=[str(tmp_path / "missing.txt")],
        )
    except ValueError as exc:
        assert "attachment file not found" in str(exc)
    else:
        raise AssertionError("expected missing attachment to be rejected")


def test_create_signature_profile_rejects_missing_logo(tmp_path):
    service, _sender = make_service(tmp_path)

    try:
        service.create_signature_profile(
            name="kim",
            fields={"display_name": "홍길동"},
            logo_image_path=str(tmp_path / "missing-logo.png"),
        )
    except ValueError as exc:
        assert "logo image file not found" in str(exc)
    else:
        raise AssertionError("expected missing logo to be rejected")


def test_update_draft_rejects_conflicting_signature_options(tmp_path):
    service, _sender = make_service(tmp_path)
    signature = service.create_signature(
        name="custom",
        text_template="머리말\n{{body}}\n꼬리말",
    )
    draft = service.create_draft(
        subject="hello",
        to=["user@example.com"],
        text_body="본문",
        apply_default_signature=False,
    )

    try:
        service.update_draft(
            draft.id,
            signature_id=signature.id,
            clear_signature=True,
        )
    except ValueError as exc:
        assert str(exc) == "signature options are mutually exclusive"
    else:
        raise AssertionError("expected conflicting signature options to be rejected")


def test_create_signature_keeps_only_one_default(tmp_path):
    service, _sender = make_service(tmp_path)
    first = service.create_signature(
        name="first",
        text_template="A\n{{body}}\nB",
        is_default=True,
    )
    second = service.create_signature(
        name="second",
        text_template="C\n{{body}}\nD",
        is_default=True,
    )

    signatures = {item.id: item for item in service.list_signatures()}
    assert signatures[first.id].is_default is False
    assert signatures[second.id].is_default is True


def test_preview_signature_renders_text_and_html(tmp_path):
    service, _sender = make_service(tmp_path)
    signature = service.create_signature(
        name="default",
        text_template="안녕하세요.\n\n{{body}}\n\n감사합니다.",
        html_template="<p>안녕하세요.</p><div>{{body}}</div><p>감사합니다.</p>",
        is_default=True,
    )

    preview = service.preview_signature(
        text_body="본문",
        html_body="<p>본문</p>",
    )

    assert preview["signature"] == signature.to_dict()
    assert preview["rendered_text_body"] == "안녕하세요.\n\n본문\n\n감사합니다."
    assert preview["rendered_html_body"] == "<p>안녕하세요.</p><div><p>본문</p></div><p>감사합니다.</p>"


def test_preview_signature_can_compose_greeting_profile_and_closing_logo(tmp_path):
    service, _sender = make_service(tmp_path)
    logo = write_logo(tmp_path)
    greeting = service.create_greeting_template(
        name="formal",
        text_template="안녕하십니까.\n{{department}} {{display_name}} {{position}}입니다.",
        html_template="<p>안녕하십니까.</p><p>{{department}} {{display_name}} {{position}}입니다.</p>",
        is_default=True,
    )
    profile = service.create_signature_profile(
        name="kim",
        fields={
            "display_name": "홍길동",
            "department": "로봇자동화사업부",
            "position": "사원",
            "english_name": "John Doe",
            "mobile": "010-1234-5678",
            "email": "hong.gildong@ubisam.com",
        },
        logo_image_path=str(logo),
        is_default=True,
    )
    closing = service.create_closing_template(
        name="closing-phrase",
        text_template="확인 부탁드립니다.\n\n감사합니다.",
        html_template="<div>확인 부탁드립니다.\n\n감사합니다.</div>",
        is_default=True,
    )
    signature = service.create_signature(
        name="closing",
        text_template="{{display_name}} 드림\nm {{mobile}} | e {{email}}",
        html_template=(
            "<hr>"
            "<div>{{company_logo_img}}<strong>{{display_name}}</strong> / {{english_name}}</div>"
            "<div>m {{mobile}} | e {{email}}</div>"
        ),
        mode="closing_only",
        is_default=True,
    )

    preview = service.preview_signature(
        text_body="확인 부탁드립니다.",
        html_body="<p>확인 부탁드립니다.</p>",
    )

    assert preview["closing_template"] == closing.to_dict()
    assert preview["greeting_template"] == greeting.to_dict()
    assert preview["signature_profile"] == profile.to_dict()
    assert preview["signature"] == signature.to_dict()
    assert "안녕하십니까." in preview["rendered_text_body"]
    assert "감사합니다." in preview["rendered_text_body"]
    assert 'src="cid:profile-logo-' in preview["rendered_html_body"]
    assert preview["inline_attachments"][0]["filename"] == "logo.png"


def test_create_draft_can_store_greeting_and_signature_profile(tmp_path):
    service, _sender = make_service(tmp_path)
    logo = write_logo(tmp_path)
    greeting = service.create_greeting_template(
        name="formal",
        text_template="안녕하십니까.\n{{department}} {{display_name}} {{position}}입니다.",
        is_default=True,
    )
    closing = service.create_closing_template(
        name="closing-phrase",
        text_template="확인 부탁드립니다.\n\n감사합니다.",
        is_default=True,
    )
    profile = service.create_signature_profile(
        name="kim",
        fields={
            "display_name": "홍길동",
            "department": "로봇자동화사업부",
            "position": "사원",
        },
        logo_image_path=str(logo),
        is_default=True,
    )
    signature = service.create_signature(
        name="closing",
        text_template="{{display_name}} 드림",
        mode="closing_only",
        is_default=True,
    )

    draft = service.create_draft(
        subject="hello",
        to=["user@example.com"],
        text_body="확인 부탁드립니다.",
    )

    loaded = service.require_draft(draft.id)
    rendered = loaded.to_dict(
        signature=service.signature_for_draft(loaded),
        greeting=service.greeting_for_draft(loaded),
        closing=service.closing_for_draft(loaded),
        profile=service.signature_profile_for_draft(loaded),
    )
    assert loaded.greeting_template_id == greeting.id
    assert loaded.closing_template_id == closing.id
    assert loaded.signature_profile_id == profile.id
    assert loaded.signature_id == signature.id
    assert rendered["rendered_text_body"].startswith("안녕하십니까.")
    assert "확인 부탁드립니다." in rendered["rendered_text_body"]
    assert rendered["rendered_text_body"].endswith("홍길동 드림")


def test_send_draft_now_renders_inline_logo_attachment(tmp_path):
    service, sender = make_service(tmp_path)
    logo = write_logo(tmp_path)
    service.create_greeting_template(
        name="formal",
        text_template="안녕하십니까.\n{{display_name}}입니다.",
        html_template="<p>안녕하십니까.</p><p>{{display_name}}입니다.</p>",
        is_default=True,
    )
    service.create_signature_profile(
        name="kim",
        fields={"display_name": "홍길동"},
        logo_image_path=str(logo),
        is_default=True,
    )
    service.create_signature(
        name="closing",
        text_template="감사합니다.\n{{display_name}} 드림",
        html_template="<p>감사합니다.</p><div>{{company_logo_img}}{{display_name}}</div>",
        mode="closing_only",
        is_default=True,
    )
    draft = service.create_draft(
        subject="send now",
        to=["user@example.com"],
        text_body="본문",
        html_body="<p>본문</p>",
    )

    service.send_draft_now(draft.id)

    sending_draft = sender.sent_drafts[0]
    assert sending_draft.inline_attachments[0].filename == "logo.png"
    assert 'cid:profile-logo-' in sending_draft.html_body


def test_preview_closing_signature_can_export_html(tmp_path):
    service, _sender = make_service(tmp_path)
    logo = write_logo(tmp_path)
    profile = service.create_signature_profile(
        name="kim",
        fields={
            "display_name": "홍길동",
            "english_name": "John Doe",
            "mobile": "010-1234-5678",
            "email": "hong.gildong@ubisam.com",
        },
        logo_image_path=str(logo),
        is_default=True,
    )
    signature = service.create_signature(
        name="closing",
        text_template="감사합니다.\n{{display_name}} 드림",
        html_template="<div>{{company_logo_img}}<strong>{{display_name}}</strong> / {{english_name}}</div>",
        mode="closing_only",
        is_default=True,
    )

    preview = service.preview_closing_signature(export_dir=str(tmp_path / "signature-preview"))

    assert preview["signature"] == signature.to_dict()
    assert preview["signature_profile"] == profile.to_dict()
    assert "홍길동" in preview["rendered_text_body"]
    assert 'cid:profile-logo-' in preview["rendered_html_body"]
    export = preview["export"]
    html_path = Path(export["html_path"])
    assert html_path.is_file()
    html_content = html_path.read_text(encoding="utf-8")
    assert "assets/logo.png" in html_content
    assert (Path(export["assets_dir"]) / "logo.png").is_file()


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


def test_send_draft_now_rejects_plain_smtp(tmp_path):
    insecure_config = AppConfig(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="user",
        smtp_password="pass",
        smtp_use_tls=False,
        smtp_use_starttls=False,
        smtp_debug=False,
        smtp_tls_servername="smtp.example.com",
        imap_host="imap.example.com",
        imap_port=993,
        imap_username="user",
        imap_password="pass",
        imap_use_tls=True,
        imap_tls_servername="imap.example.com",
        default_from_address="bot@example.com",
        default_from_name="",
        sqlite_path=tmp_path / "mail.db",
        attachment_download_dir=tmp_path / "downloads",
        contacts_path=tmp_path / "contacts.local.json",
    )
    service, sender = make_service_with_config(tmp_path, insecure_config)
    draft = service.create_draft(
        subject="send now",
        to=["user@example.com"],
        text_body="body",
        apply_default_signature=False,
    )

    try:
        service.send_draft_now(draft.id)
    except ValueError as exc:
        assert str(exc) == "SMTP transport must use TLS or STARTTLS"
    else:
        raise AssertionError("expected plain SMTP to be rejected")

    assert sender.sent_ids == []


def test_attachment_gate_rejects_sensitive_files(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("UBISAM_SMTP_PASSWORD=secret", encoding="utf-8")
    pem_file = tmp_path / "server.pem"
    pem_file.write_text("-----BEGIN PRIVATE KEY-----", encoding="utf-8")
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    ssh_file = ssh_dir / "config"
    ssh_file.write_text("Host *", encoding="utf-8")
    env_local = tmp_path / ".env.local"
    env_local.write_text("X=1", encoding="utf-8")

    for bad in (env_file, pem_file, ssh_file, env_local):
        with pytest.raises(ValueError, match="refusing to attach"):
            _ensure_safe_attachment_source(bad)


def test_attachment_gate_allows_normal_files(tmp_path):
    doc = tmp_path / "report.pdf"
    doc.write_text("content", encoding="utf-8")
    image = tmp_path / "logo.png"
    image.write_bytes(b"\x89PNG\r\n")

    _ensure_safe_attachment_source(doc)
    _ensure_safe_attachment_source(image)
