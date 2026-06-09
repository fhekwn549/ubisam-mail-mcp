from __future__ import annotations

from pathlib import Path

from ubisam_mail_mcp.repository import DraftRepository
from ubisam_mail_mcp.setup_wizard import (
    SetupValues,
    _build_signature_templates,
    _parse_args,
    _run_setup_from_web_payload,
    _setup_image_path,
    _web_account_form_html,
    _web_preflight_html,
    _web_signature_form_html,
    main,
)


def test_setup_wizard_writes_env_and_skips_signature_setup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / ".env"

    exit_code = main(
        [
            "--non-interactive",
            "--skip-connection-check",
            "--skip-signature-setup",
            "--force",
            "--env-file",
            str(env_file),
            "--email",
            "user@ubisam.com",
            "--password",
            "secret",
            "--from-name",
            "홍길동",
        ]
    )

    assert exit_code == 0
    env_text = env_file.read_text(encoding="utf-8")
    assert 'UBISAM_SMTP_USERNAME="user@ubisam.com"' in env_text
    assert 'UBISAM_SMTP_PASSWORD="secret"' in env_text
    assert 'UBISAM_DEFAULT_FROM_NAME="홍길동"' in env_text
    assert env_file.stat().st_mode & 0o777 == 0o600


def test_setup_wizard_creates_default_templates_and_preview(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / ".env"
    db_path = tmp_path / "mail.db"
    preview_dir = tmp_path / "preview"

    exit_code = main(
        [
            "--non-interactive",
            "--skip-connection-check",
            "--force",
            "--env-file",
            str(env_file),
            "--email",
            "user@ubisam.com",
            "--password",
            "secret",
            "--from-name",
            "홍길동",
            "--db-path",
            str(db_path),
            "--preview-dir",
            str(preview_dir),
            "--department",
            "로봇자동화사업부",
            "--team",
            "로봇팀",
            "--position",
            "사원",
            "--mobile",
            "010-1234-5678",
        ]
    )

    assert exit_code == 0
    repository = DraftRepository(Path(db_path))
    profile = repository.get_default_signature_profile()
    greeting = repository.get_default_greeting_template()
    closing = repository.get_default_closing_template()
    signature = repository.get_default_signature()

    assert profile is not None
    assert profile.fields["display_name"] == "홍길동"
    assert profile.fields["department"] == "로봇자동화사업부"
    assert greeting is not None
    assert closing is not None
    assert signature is not None
    assert signature.mode == "closing_only"
    assert (preview_dir / "signature-preview.html").is_file()


def test_setup_wizard_accepts_multiline_template_arguments(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "mail.db"

    exit_code = main(
        [
            "--non-interactive",
            "--skip-connection-check",
            "--force",
            "--env-file",
            str(tmp_path / ".env"),
            "--email",
            "user@ubisam.com",
            "--password",
            "secret",
            "--from-name",
            "홍길동",
            "--db-path",
            str(db_path),
            "--greeting-text",
            "안녕하십니까.\n홍길동입니다.",
            "--closing-text",
            "확인 부탁드립니다.\n\n감사합니다.",
        ]
    )

    assert exit_code == 0
    repository = DraftRepository(Path(db_path))
    greeting = repository.get_default_greeting_template()
    closing = repository.get_default_closing_template()

    assert greeting is not None
    assert greeting.text_template == "안녕하십니까.\n홍길동입니다."
    assert closing is not None
    assert closing.text_template == "확인 부탁드립니다.\n\n감사합니다."


def test_signature_template_omits_empty_optional_fields():
    text_template, html_template = _build_signature_templates(
        {
            "display_name": "홍길동",
            "english_name": "",
            "hanja_name": "",
            "department": "로봇자동화사업부",
            "division_english": "",
            "job_title_english": "",
            "position": "사원",
            "office_phone": "",
            "mobile": "",
            "email": "user@ubisam.com",
        }
    )

    assert text_template == "{{display_name}} {{position}}\n{{department}}\ne {{email}}"
    assert "hanja_name" not in text_template
    assert "english_name" not in text_template
    assert " / " not in html_template


def test_signature_template_uses_default_footer_scale_and_logo():
    _text_template, html_template = _build_signature_templates(
        {
            "display_name": "홍길동",
            "position": "사원",
            "department": "로봇자동화사업부",
            "office_phone": "02-1234-5678",
            "email": "user@ubisam.com",
            "logo_image_path": "/tmp/logo.png",
        }
    )

    assert "{{company_logo_img}}" in html_template
    assert "font-size:14px" in html_template
    assert "font-size:12px" in html_template
    assert "font-size:11px" in html_template


def test_web_setup_payload_creates_env_and_templates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = _parse_args(
        [
            "--web-setup",
            "--force",
            "--skip-connection-check",
            "--env-file",
            str(tmp_path / ".env"),
            "--db-path",
            str(tmp_path / "mail.db"),
            "--preview-dir",
            str(tmp_path / "preview"),
        ]
    )

    result = _run_setup_from_web_payload(
        {
            "email": "user@ubisam.com",
            "password": "secret",
            "from_name": "홍길동",
            "env_file": str(tmp_path / ".env"),
            "db_path": str(tmp_path / "mail.db"),
            "preview_dir": str(tmp_path / "preview"),
            "skip_connection_check": "on",
            "display_name": "홍길동",
            "department": "로봇자동화사업부",
            "position": "사원",
            "greeting_text": "안녕하십니까.\n{{display_name}}입니다.",
            "closing_text": "감사합니다.",
        },
        args=args,
    )

    assert result["env_file"] == str((tmp_path / ".env").resolve())
    assert "UBISAM_ENV_FILE" in result["codex_config"]
    assert result["claude_command"].startswith("claude mcp add ubisam-mail --env")
    assert "\\\n" not in result["claude_command"]
    repository = DraftRepository(tmp_path / "mail.db")
    profile = repository.get_default_signature_profile()
    assert profile is not None
    assert profile.logo_image_path.endswith("logo-color.png")
    assert repository.get_default_greeting_template() is not None
    assert repository.get_default_closing_template() is not None
    signature = repository.get_default_signature()
    assert signature is not None
    assert "{{company_logo_img}}" in signature.html_template


def test_web_setup_preflight_page_requires_confirmation():
    html = _web_preflight_html()

    assert "/assets/mcp-setting.png" in html
    assert "SMTP/IMAP 사용을 활성화하고 저장했습니다" in html
    assert 'id="next" type="button" disabled' in html
    assert "/account" in html


def test_setup_image_asset_exists():
    assert _setup_image_path().is_file()


def test_web_setup_account_page_hides_advanced_fields():
    html = _web_account_form_html(_parse_args(["--web-setup"]))

    assert 'action="/verify"' in html
    assert "togglePassword" in html
    assert "SMTP host" not in html
    assert "DB 경로" not in html
    assert "로고 이미지 경로" not in html
    assert "서명 이름" not in html


def test_web_signature_page_uses_hanja_toggle():
    html = _web_signature_form_html(
        token="token",
        values=SetupValues(
            env_file=Path(".env"),
            email="user@ubisam.com",
            password="secret",
            from_name="홍길동",
        ),
        args=_parse_args(["--web-setup"]),
    )

    assert 'action="/setup"' in html
    assert 'id="useHanja"' in html
    assert 'id="hanjaName"' in html
    assert "<iframe" in html
    assert "preview.srcdoc" in html
    assert "signatureHtml" in html
    assert "비밀번호" not in html


def test_web_success_page_explains_where_to_paste_client_settings():
    from ubisam_mail_mcp.setup_wizard import _web_success_html

    html = _web_success_html(
        {
            "env_file": "/example/project/config.env",
            "command_path": "/example/project/.venv/bin/ubisam-mail-mcp",
            "claude_command": "claude mcp add ubisam-mail --env UBISAM_ENV_FILE=/example/project/config.env -- /example/project/.venv/bin/ubisam-mail-mcp",
            "codex_config": '[mcp_servers.ubisam_mail]\ncommand = "/example/project/.venv/bin/ubisam-mail-mcp"',
            "claude_desktop_config": '{\n  "mcpServers": {\n    "ubisam-mail": {}\n  }\n}',
        }
    )

    assert "터미널에 한 줄로 입력" in html
    assert "command와 <code>UBISAM_ENV_FILE</code> 값은 Claude Desktop과 같고" in html
    assert "형식만 JSON 대신 TOML입니다" in html
    assert "Settings → Configuration → Open config.toml" in html
    assert "nano ~/.codex/config.toml" in html
    assert "아래 내용을 붙여넣고 저장" in html
    assert "<h2>Claude Desktop</h2>" in html
    assert "claude_desktop_config.json" in html


def test_web_setup_prefills_existing_env_and_signature_values(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "mail.db"
    env_file = tmp_path / ".env"
    exit_code = main(
        [
            "--non-interactive",
            "--skip-connection-check",
            "--force",
            "--env-file",
            str(env_file),
            "--email",
            "user@ubisam.com",
            "--password",
            "secret",
            "--from-name",
            "홍길동",
            "--db-path",
            str(db_path),
            "--department",
            "로봇자동화사업부",
            "--position",
            "사원",
            "--greeting-text",
            "안녕하십니까.\n{{display_name}}입니다.",
            "--closing-text",
            "감사합니다.",
        ]
    )
    assert exit_code == 0
    args = _parse_args(["--web-setup"])

    account_html = _web_account_form_html(args)
    signature_html = _web_signature_form_html(
        token="token",
        values=SetupValues(
            env_file=env_file,
            email="user@ubisam.com",
            password="secret",
            from_name="홍길동",
        ),
        args=args,
    )

    assert 'value="user@ubisam.com"' in account_html
    assert 'value="홍길동"' in account_html
    assert "secret" not in account_html
    assert 'value="로봇자동화사업부"' in signature_html
    assert 'value="사원"' in signature_html
    assert "안녕하십니까." in signature_html
    assert "감사합니다." in signature_html


def test_setup_wizard_refuses_existing_env_without_force(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("existing=true\n", encoding="utf-8")

    exit_code = main(
        [
            "--non-interactive",
            "--skip-connection-check",
            "--skip-signature-setup",
            "--env-file",
            str(env_file),
            "--email",
            "user@ubisam.com",
            "--password",
            "secret",
            "--from-name",
            "홍길동",
        ]
    )

    assert exit_code == 1
    assert env_file.read_text(encoding="utf-8") == "existing=true\n"
