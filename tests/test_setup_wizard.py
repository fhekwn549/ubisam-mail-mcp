from __future__ import annotations

from pathlib import Path

from ubisam_mail_mcp.repository import DraftRepository
from ubisam_mail_mcp.setup_wizard import main


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
