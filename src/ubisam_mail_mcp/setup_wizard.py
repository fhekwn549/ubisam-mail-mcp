from __future__ import annotations

import argparse
import getpass
import os
import shlex
import shutil
import smtplib
import ssl
import subprocess
import sys
import tempfile
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .config import AppConfig
from .imap_client import ImapMailClient
from .repository import DraftRepository
from .service import MailService
from .smtp_client import _SmtpSslWithServername, _close_smtp_session, _smtp_login


DEFAULT_HOST = "ubisam.hanbiro.net"
DEFAULT_SMTP_PORT = 587
DEFAULT_IMAP_PORT = 993
DEFAULT_DB_PATH = "$HOME/.local/share/ubisam-mail-mcp/mail.db"
DEFAULT_DOWNLOAD_DIR = "downloads"
DEFAULT_CONTACTS_PATH = "data/contacts.local.json"

DEFAULT_GREETING_TEXT = "안녕하십니까.\n{{department}} {{team}} {{display_name}} {{position}}입니다."
DEFAULT_CLOSING_TEXT = "확인 부탁드립니다.\n\n감사합니다."
DEFAULT_SIGNATURE_TEXT = (
    "{{display_name}} {{position}} / {{english_name}} / {{hanja_name}}\n"
    "{{department}} / {{division_english}} / {{job_title_english}}\n"
    "t {{office_phone}}  m {{mobile}}  e {{email}}"
)
DEFAULT_SIGNATURE_HTML = (
    '<hr style="border:none;border-top:1px solid #cfcfcf;margin:0 0 14px 0;">'
    '<div style="font-family:\'Malgun Gothic\',sans-serif;color:#7c7c7c;">'
    '  <div style="font-size:24px;font-weight:700;line-height:1.25;color:#8a8a8a;'
    'display:flex;align-items:flex-end;gap:14px;">'
    '    <span style="display:inline-flex;align-items:flex-end;line-height:1;">{{company_logo_img}}</span>'
    '    <span style="display:inline-block;line-height:1;transform:translateY(-4px);">'
    "{{display_name}} {{position}} / {{english_name}} / {{hanja_name}}</span>"
    "  </div>"
    '  <div style="margin-top:10px;font-size:19px;font-weight:700;line-height:1.3;color:#8a8a8a;">'
    "{{department}} / {{division_english}} / {{job_title_english}}</div>"
    '  <div style="margin-top:14px;font-size:18px;line-height:1.45;color:#6f6f6f;">'
    '    <strong style="color:#222;">t</strong> {{office_phone}} &nbsp;&nbsp;'
    '    <strong style="color:#222;">m</strong> {{mobile}} &nbsp;&nbsp;'
    '    <strong style="color:#222;">e</strong> {{email}}'
    "  </div></div>"
)


@dataclass(slots=True)
class SetupValues:
    env_file: Path
    email: str
    password: str
    from_name: str
    smtp_host: str = DEFAULT_HOST
    smtp_port: int = DEFAULT_SMTP_PORT
    smtp_use_starttls: bool = True
    smtp_use_tls: bool = False
    imap_host: str = DEFAULT_HOST
    imap_port: int = DEFAULT_IMAP_PORT
    imap_use_tls: bool = True
    db_path: str = DEFAULT_DB_PATH
    download_dir: str = DEFAULT_DOWNLOAD_DIR
    contacts_path: str = DEFAULT_CONTACTS_PATH


class _NoopSender:
    def send(self, _draft) -> None:
        raise RuntimeError("setup wizard does not send mail")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        values = _collect_values(args)
        _write_env_file(values, force=args.force)
        config = _build_config(values)
        print(f".env 저장: {values.env_file}")

        if not args.skip_connection_check:
            _check_connections(config)

        if args.skip_signature_setup:
            print("기본 서식 설정 건너뜀.")
        else:
            preview = _setup_default_signature(
                config,
                values=values,
                args=args,
            )
            print("기본 서식 저장 완료.")
            print("미리보기 텍스트:")
            print(preview["rendered_text_body"])
            export = preview.get("export")
            if export:
                html_path = export["html_path"]
                print(f"HTML 미리보기: {html_path}")
                if args.open_preview:
                    webbrowser.open(Path(html_path).as_uri())

        print("")
        print("다음 단계:")
        print(f'Claude/Codex MCP env에 UBISAM_ENV_FILE="{values.env_file}" 지정')
        print("agent에서 '내 메일 설정 상태 확인해줘.' 실행")
        return 0
    except KeyboardInterrupt:
        print("\n중단됨.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"setup failed: {exc}", file=sys.stderr)
        return 1


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ubisam-mail-mcp first-run setup wizard")
    parser.add_argument("--env-file", default=".env", help="생성할 .env 경로. 기본: .env")
    parser.add_argument("--email", help="유비샘 메일 주소")
    parser.add_argument("--password", help="메일 비밀번호. 미지정 시 숨김 입력")
    parser.add_argument("--from-name", help="보내는 사람 표시 이름")
    parser.add_argument("--smtp-host", default=DEFAULT_HOST)
    parser.add_argument("--smtp-port", type=int, default=DEFAULT_SMTP_PORT)
    parser.add_argument("--smtp-use-tls", action="store_true", help="SMTP 465 implicit TLS 사용")
    parser.add_argument("--smtp-no-starttls", action="store_true", help="SMTP STARTTLS 비활성화")
    parser.add_argument("--imap-host", default=DEFAULT_HOST)
    parser.add_argument("--imap-port", type=int, default=DEFAULT_IMAP_PORT)
    parser.add_argument("--imap-no-tls", action="store_true", help="IMAP TLS 비활성화")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--download-dir", default=DEFAULT_DOWNLOAD_DIR)
    parser.add_argument("--contacts-path", default=DEFAULT_CONTACTS_PATH)
    parser.add_argument("--force", action="store_true", help="기존 .env 덮어쓰기")
    parser.add_argument("--skip-connection-check", action="store_true", help="IMAP/SMTP 로그인 검증 생략")
    parser.add_argument("--skip-signature-setup", action="store_true", help="기본 서식 설정 생략")
    parser.add_argument("--non-interactive", action="store_true", help="프롬프트 없이 인자로만 실행")
    parser.add_argument("--edit-templates", action="store_true", help="인삿말/맺음말을 에디터에서 여러 줄 편집")
    parser.add_argument("--greeting-text", default=DEFAULT_GREETING_TEXT)
    parser.add_argument("--closing-text", default=DEFAULT_CLOSING_TEXT)
    parser.add_argument("--display-name", help="서명 이름")
    parser.add_argument("--english-name", default="")
    parser.add_argument("--hanja-name", default="")
    parser.add_argument("--department", default="")
    parser.add_argument("--division-english", default="")
    parser.add_argument("--team", default="")
    parser.add_argument("--position", default="")
    parser.add_argument("--job-title-english", default="")
    parser.add_argument("--office-phone", default="")
    parser.add_argument("--mobile", default="")
    parser.add_argument("--logo-image-path", default="")
    parser.add_argument("--preview-dir", default="downloads/setup-preview")
    parser.add_argument("--open-preview", action="store_true", help="HTML 미리보기를 기본 브라우저로 열기")
    return parser.parse_args(argv)


def _collect_values(args: argparse.Namespace) -> SetupValues:
    env_file = Path(args.env_file).expanduser().resolve()
    email = args.email or _prompt("메일 주소", required=True, non_interactive=args.non_interactive)
    password = args.password or _prompt_password(non_interactive=args.non_interactive)
    from_name = args.from_name or _prompt(
        "보내는 사람 표시 이름",
        default=args.display_name or "",
        required=True,
        non_interactive=args.non_interactive,
    )
    return SetupValues(
        env_file=env_file,
        email=email,
        password=password,
        from_name=from_name,
        smtp_host=args.smtp_host,
        smtp_port=args.smtp_port,
        smtp_use_starttls=not args.smtp_no_starttls,
        smtp_use_tls=args.smtp_use_tls,
        imap_host=args.imap_host,
        imap_port=args.imap_port,
        imap_use_tls=not args.imap_no_tls,
        db_path=args.db_path,
        download_dir=args.download_dir,
        contacts_path=args.contacts_path,
    )


def _prompt(
    label: str,
    *,
    default: str = "",
    required: bool = False,
    non_interactive: bool = False,
) -> str:
    if non_interactive:
        if required and not default:
            raise ValueError(f"{label} is required in non-interactive mode")
        return default
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{label}{suffix}: ").strip() or default
        if value or not required:
            return value
        print("필수 입력.")


def _prompt_password(*, non_interactive: bool) -> str:
    if non_interactive:
        raise ValueError("password is required in non-interactive mode")
    password = getpass.getpass("메일 비밀번호: ")
    if not password:
        raise ValueError("메일 비밀번호 필요")
    return password


def _write_env_file(values: SetupValues, *, force: bool) -> None:
    if values.env_file.exists() and not force:
        raise ValueError(f"{values.env_file} already exists. Use --force to overwrite.")
    values.env_file.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        [
            "# Hanbiro mail MCP per-user settings",
            f'UBISAM_SMTP_HOST="{values.smtp_host}"',
            f'UBISAM_SMTP_PORT="{values.smtp_port}"',
            f'UBISAM_SMTP_USERNAME="{values.email}"',
            f'UBISAM_SMTP_PASSWORD="{_escape_env_value(values.password)}"',
            f'UBISAM_DEFAULT_FROM="{values.email}"',
            f'UBISAM_DEFAULT_FROM_NAME="{values.from_name}"',
            f'UBISAM_SMTP_USE_STARTTLS="{_bool_text(values.smtp_use_starttls)}"',
            f'UBISAM_SMTP_USE_TLS="{_bool_text(values.smtp_use_tls)}"',
            f'UBISAM_SMTP_TLS_SERVERNAME="{values.smtp_host}"',
            "",
            f'UBISAM_IMAP_HOST="{values.imap_host}"',
            f'UBISAM_IMAP_PORT="{values.imap_port}"',
            f'UBISAM_IMAP_USERNAME="{values.email}"',
            f'UBISAM_IMAP_PASSWORD="{_escape_env_value(values.password)}"',
            f'UBISAM_IMAP_USE_TLS="{_bool_text(values.imap_use_tls)}"',
            f'UBISAM_IMAP_TLS_SERVERNAME="{values.imap_host}"',
            "",
            f'UBISAM_MAIL_MCP_DB="{values.db_path}"',
            f'UBISAM_ATTACHMENT_DOWNLOAD_DIR="{values.download_dir}"',
            f'UBISAM_CONTACTS_PATH="{values.contacts_path}"',
            "",
        ]
    )
    values.env_file.write_text(content, encoding="utf-8")
    try:
        values.env_file.chmod(0o600)
    except OSError:
        pass


def _build_config(values: SetupValues) -> AppConfig:
    return AppConfig(
        smtp_host=values.smtp_host,
        smtp_port=values.smtp_port,
        smtp_username=values.email,
        smtp_password=values.password,
        smtp_use_tls=values.smtp_use_tls,
        smtp_use_starttls=values.smtp_use_starttls,
        smtp_debug=False,
        smtp_tls_servername=values.smtp_host,
        imap_host=values.imap_host,
        imap_port=values.imap_port,
        imap_username=values.email,
        imap_password=values.password,
        imap_use_tls=values.imap_use_tls,
        imap_tls_servername=values.imap_host,
        default_from_address=values.email,
        default_from_name=values.from_name,
        sqlite_path=Path(os.path.expandvars(values.db_path)).expanduser(),
        attachment_download_dir=Path(os.path.expandvars(values.download_dir)).expanduser(),
        contacts_path=Path(os.path.expandvars(values.contacts_path)).expanduser(),
    )


def _check_connections(config: AppConfig) -> None:
    print("IMAP 로그인 검증...")
    ImapMailClient(config).list_mailboxes()
    print("IMAP OK")
    print("SMTP 로그인 검증...")
    _probe_smtp(config)
    print("SMTP OK")


def _probe_smtp(config: AppConfig) -> None:
    if not (config.smtp_use_tls or config.smtp_use_starttls):
        raise ValueError("SMTP transport must use TLS or STARTTLS")
    if config.smtp_use_tls:
        smtp = _SmtpSslWithServername(
            config.smtp_tls_servername,
            config.smtp_host,
            config.smtp_port,
            timeout=15,
            context=ssl.create_default_context(),
        )
    else:
        smtp = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=15)
    try:
        if config.smtp_use_starttls and not config.smtp_use_tls:
            smtp._host = config.smtp_tls_servername
            smtp.starttls(context=ssl.create_default_context())
        _smtp_login(smtp, config.smtp_username, config.smtp_password, config=config)
    finally:
        _close_smtp_session(smtp)


def _setup_default_signature(
    config: AppConfig,
    *,
    values: SetupValues,
    args: argparse.Namespace,
) -> dict:
    service = MailService(
        repository=DraftRepository(config.sqlite_path),
        sender=_NoopSender(),
        config=config,
    )
    display_name = args.display_name or values.from_name
    fields = {
        "display_name": display_name,
        "english_name": args.english_name,
        "hanja_name": args.hanja_name,
        "department": args.department,
        "division_english": args.division_english,
        "team": args.team,
        "position": args.position,
        "job_title_english": args.job_title_english,
        "office_phone": args.office_phone,
        "mobile": args.mobile,
        "email": values.email,
    }
    if not args.non_interactive:
        fields = _prompt_signature_fields(fields)
    service.create_signature_profile(
        name=f"{display_name} 기본 프로필",
        fields=fields,
        logo_image_path=args.logo_image_path,
        is_default=True,
    )
    greeting_text = args.greeting_text
    closing_text = args.closing_text
    if args.edit_templates and not args.non_interactive:
        greeting_text = _edit_multiline_text("기본 인삿말", greeting_text)
        closing_text = _edit_multiline_text("기본 맺음말", closing_text)

    service.create_greeting_template(
        name="기본 인삿말",
        text_template=greeting_text,
        is_default=True,
    )
    service.create_closing_template(
        name="기본 맺음말",
        text_template=closing_text,
        is_default=True,
    )
    service.create_signature(
        name="기본 footer html",
        text_template=DEFAULT_SIGNATURE_TEXT,
        html_template=DEFAULT_SIGNATURE_HTML,
        mode="closing_only",
        is_default=True,
    )
    preview = service.preview_signature(
        text_body="본문 테스트입니다.",
        html_body="<p>본문 테스트입니다.</p>",
        apply_default_greeting_template=True,
        apply_default_closing_template=True,
        apply_default_signature=True,
        apply_default_signature_profile=True,
    )
    closing_preview = service.preview_closing_signature(
        apply_default_signature=True,
        apply_default_signature_profile=True,
        export_dir=args.preview_dir,
    )
    preview["export"] = closing_preview.get("export")
    return preview


def _prompt_signature_fields(defaults: dict[str, str]) -> dict[str, str]:
    labels = {
        "display_name": "서명 이름",
        "english_name": "영문 이름",
        "hanja_name": "한자 이름",
        "department": "부서",
        "division_english": "영문 부서",
        "team": "팀",
        "position": "직급",
        "job_title_english": "영문 직함",
        "office_phone": "대표전화",
        "mobile": "휴대폰",
        "email": "이메일",
    }
    result: dict[str, str] = {}
    print("")
    print("기본 서식 값 입력. 빈 값은 Enter로 건너뜀.")
    for key, label in labels.items():
        result[key] = _prompt(label, default=defaults.get(key, ""))
    return result


def _edit_multiline_text(title: str, default: str) -> str:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or _default_editor()
    if editor:
        return _edit_with_editor(title, default, editor)
    return _read_multiline_from_stdin(title, default)


def _default_editor() -> str:
    for candidate in ("nano", "vim", "vi"):
        if shutil.which(candidate):
            return candidate
    if os.name == "nt":
        return "notepad"
    return ""


def _edit_with_editor(title: str, default: str, editor: str) -> str:
    with tempfile.NamedTemporaryFile(
        "w+",
        encoding="utf-8",
        suffix=".txt",
        prefix="ubisam-mail-template-",
        delete=False,
    ) as handle:
        path = Path(handle.name)
        handle.write(default)
        handle.write(
            "\n\n# 위 내용을 수정하세요. # 으로 시작하는 줄은 저장 시 제거됩니다.\n"
            f"# 템플릿: {title}\n"
        )
    try:
        subprocess.run([*shlex.split(editor), str(path)], check=True)
        lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if not line.startswith("#")
        ]
        value = "\n".join(lines).strip()
        if not value:
            raise ValueError(f"{title} cannot be empty")
        return value
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def _read_multiline_from_stdin(title: str, default: str) -> str:
    print("")
    print(f"{title} 입력. 빈 줄 포함 가능. 한 줄에 . 만 입력하면 종료.")
    print("기본값:")
    print(default)
    lines: list[str] = []
    while True:
        line = input()
        if line == ".":
            break
        lines.append(line)
    value = "\n".join(lines).strip()
    return value or default


def _escape_env_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


if __name__ == "__main__":
    raise SystemExit(main())
