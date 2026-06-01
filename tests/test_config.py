from __future__ import annotations

from pathlib import Path

from hanbiro_mail_mcp.config import AppConfig


def test_imap_defaults_follow_smtp_values(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HANBIRO_SMTP_HOST", "mail.ubisam.com")
    monkeypatch.setenv("HANBIRO_SMTP_USERNAME", "user@ubisam.com")
    monkeypatch.setenv("HANBIRO_SMTP_PASSWORD", "secret")

    config = AppConfig.from_env()

    assert config.imap_host == "mail.ubisam.com"
    assert config.imap_port == 993
    assert config.imap_username == "user@ubisam.com"
    assert config.imap_password == "secret"
    assert config.imap_use_tls is True
    assert config.smtp_tls_servername == "mail.ubisam.com"
    assert config.imap_tls_servername == "mail.ubisam.com"
    assert config.sqlite_path == Path(tmp_path) / ".local" / "share" / "hanbiro-mail-mcp" / "mail.db"


def test_imap_env_overrides(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HANBIRO_IMAP_HOST", "mail.example.com")
    monkeypatch.setenv("HANBIRO_IMAP_PORT", "143")
    monkeypatch.setenv("HANBIRO_IMAP_USERNAME", "imap-user@example.com")
    monkeypatch.setenv("HANBIRO_IMAP_PASSWORD", "imap-pass")
    monkeypatch.setenv("HANBIRO_IMAP_USE_TLS", "false")
    monkeypatch.setenv("HANBIRO_SMTP_TLS_SERVERNAME", "smtp-cert.example.com")
    monkeypatch.setenv("HANBIRO_IMAP_TLS_SERVERNAME", "imap-cert.example.com")

    config = AppConfig.from_env()

    assert config.imap_host == "mail.example.com"
    assert config.imap_port == 143
    assert config.imap_username == "imap-user@example.com"
    assert config.imap_password == "imap-pass"
    assert config.imap_use_tls is False
    assert config.smtp_tls_servername == "smtp-cert.example.com"
    assert config.imap_tls_servername == "imap-cert.example.com"


def test_dotenv_loads_when_process_env_is_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                'HANBIRO_SMTP_HOST="ubisam.hanbiro.net"',
                'HANBIRO_SMTP_PORT="465"',
                'HANBIRO_SMTP_USERNAME="user@ubisam.com"',
                'HANBIRO_SMTP_PASSWORD="secret"',
                'HANBIRO_DEFAULT_FROM="user@ubisam.com"',
                'HANBIRO_SMTP_USE_STARTTLS="false"',
                'HANBIRO_SMTP_USE_TLS="true"',
                'HANBIRO_IMAP_HOST="ubisam.hanbiro.net"',
                'HANBIRO_IMAP_PORT="993"',
                'HANBIRO_IMAP_USERNAME="user@ubisam.com"',
                'HANBIRO_IMAP_PASSWORD="secret"',
                'HANBIRO_IMAP_USE_TLS="true"',
            ]
        ),
        encoding="utf-8",
    )

    config = AppConfig.from_env()

    assert config.smtp_host == "ubisam.hanbiro.net"
    assert config.smtp_port == 465
    assert config.smtp_use_tls is True
    assert config.smtp_use_starttls is False
    assert config.imap_host == "ubisam.hanbiro.net"
    assert config.default_from_address == "user@ubisam.com"


def test_process_env_overrides_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text('HANBIRO_SMTP_USERNAME="dotenv@ubisam.com"\n', encoding="utf-8")
    monkeypatch.setenv("HANBIRO_SMTP_USERNAME", "env@ubisam.com")

    config = AppConfig.from_env()

    assert config.smtp_username == "env@ubisam.com"
