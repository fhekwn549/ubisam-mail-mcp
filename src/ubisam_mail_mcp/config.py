from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class AppConfig:
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool
    smtp_use_starttls: bool
    smtp_tls_servername: str
    imap_host: str
    imap_port: int
    imap_username: str
    imap_password: str
    imap_use_tls: bool
    imap_tls_servername: str
    default_from_address: str
    sqlite_path: Path

    @classmethod
    def from_env(cls) -> "AppConfig":
        dotenv_values = _load_dotenv()
        home = Path(os.environ.get("HOME", "."))
        default_db = home / ".local" / "share" / "ubisam-mail-mcp" / "mail.db"
        smtp_host = _env_value("UBISAM_SMTP_HOST", dotenv_values=dotenv_values)
        smtp_username = _env_value("UBISAM_SMTP_USERNAME", dotenv_values=dotenv_values)
        smtp_password = _env_value("UBISAM_SMTP_PASSWORD", dotenv_values=dotenv_values)
        imap_use_tls = _env_flag("UBISAM_IMAP_USE_TLS", default=True, dotenv_values=dotenv_values)
        default_imap_port = "993" if imap_use_tls else "143"
        return cls(
            smtp_host=smtp_host,
            smtp_port=int(_env_value("UBISAM_SMTP_PORT", "587", dotenv_values=dotenv_values)),
            smtp_username=smtp_username,
            smtp_password=smtp_password,
            smtp_use_tls=_env_flag("UBISAM_SMTP_USE_TLS", default=False, dotenv_values=dotenv_values),
            smtp_use_starttls=_env_flag("UBISAM_SMTP_USE_STARTTLS", default=True, dotenv_values=dotenv_values),
            smtp_tls_servername=_env_value("UBISAM_SMTP_TLS_SERVERNAME", smtp_host, dotenv_values=dotenv_values),
            imap_host=_env_value("UBISAM_IMAP_HOST", smtp_host, dotenv_values=dotenv_values),
            imap_port=int(_env_value("UBISAM_IMAP_PORT", default_imap_port, dotenv_values=dotenv_values)),
            imap_username=_env_value("UBISAM_IMAP_USERNAME", smtp_username, dotenv_values=dotenv_values),
            imap_password=_env_value("UBISAM_IMAP_PASSWORD", smtp_password, dotenv_values=dotenv_values),
            imap_use_tls=imap_use_tls,
            imap_tls_servername=_env_value(
                "UBISAM_IMAP_TLS_SERVERNAME",
                _env_value("UBISAM_IMAP_HOST", smtp_host, dotenv_values=dotenv_values),
                dotenv_values=dotenv_values,
            ),
            default_from_address=_env_value("UBISAM_DEFAULT_FROM", smtp_username, dotenv_values=dotenv_values),
            sqlite_path=Path(_env_value("UBISAM_MAIL_MCP_DB", str(default_db), dotenv_values=dotenv_values)),
        )

    def smtp_ready(self) -> bool:
        return all(
            [
                self.smtp_host,
                self.smtp_port > 0,
                self.smtp_username,
                self.smtp_password,
                self.default_from_address,
            ]
        )

    def imap_ready(self) -> bool:
        return all(
            [
                self.imap_host,
                self.imap_port > 0,
                self.imap_username,
                self.imap_password,
            ]
        )


def _env_value(name: str, default: str = "", *, dotenv_values: dict[str, str]) -> str:
    return os.environ.get(name, dotenv_values.get(name, default))


def _env_flag(name: str, *, default: bool, dotenv_values: dict[str, str]) -> bool:
    raw = os.environ.get(name, dotenv_values.get(name))
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _load_dotenv() -> dict[str, str]:
    env_path = os.environ.get("UBISAM_ENV_FILE")
    dotenv_path = Path(env_path) if env_path else Path.cwd() / ".env"
    if not dotenv_path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        name, value = line.split("=", 1)
        key = name.strip()
        if not key:
            continue

        values[key] = _strip_matching_quotes(value.strip())
    return values


def _strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return os.path.expanduser(os.path.expandvars(value))
