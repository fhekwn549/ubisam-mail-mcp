from __future__ import annotations

import argparse
import getpass
import html
import http.server
import os
import re
import shlex
import shutil
import smtplib
import ssl
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import uuid
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
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
_PLACEHOLDER_RE = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")


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
        if args.web_setup:
            return _run_web_setup(args)
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
    parser.add_argument("--from-name", help="그룹웨어 내 본인 이름")
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
    parser.add_argument("--signature-gui", action="store_true", help="팝업 창에서 서식 값을 입력하고 실시간 미리보기")
    parser.add_argument("--web-setup", action="store_true", help="로컬 웹페이지에서 계정/서식 설정")
    parser.add_argument("--web-host", default="127.0.0.1", help="web setup bind host. 기본: 127.0.0.1")
    parser.add_argument("--web-port", type=int, default=8765, help="web setup port. 기본: 8765")
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
        "그룹웨어 내 본인 이름",
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


def _run_web_setup(args: argparse.Namespace) -> int:
    server = http.server.ThreadingHTTPServer(
        (args.web_host, args.web_port),
        _make_setup_request_handler(args),
    )
    server.pending_sessions = {}  # type: ignore[attr-defined]
    url = f"http://{args.web_host}:{server.server_port}/"
    print(f"setup 웹페이지: {url}")
    print("브라우저가 자동으로 열리지 않으면 위 주소를 직접 여세요.")
    if args.web_host in {"127.0.0.1", "localhost"}:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return int(getattr(server, "exit_code", 0))


def _make_setup_request_handler(args: argparse.Namespace) -> type[http.server.BaseHTTPRequestHandler]:
    class SetupRequestHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path not in {"/", "/index.html"}:
                self.send_error(404)
                return
            self._send_html(_web_form_html(args))

        def do_POST(self) -> None:
            if self.path not in {"/verify", "/setup"}:
                self.send_error(404)
                return
            try:
                payload = self._read_form_payload()
                if self.path == "/verify":
                    values = _values_from_web_account_payload(payload, args=args)
                    if not args.skip_connection_check:
                        _check_connections(_build_config(values))
                    token = uuid.uuid4().hex
                    self.server.pending_sessions[token] = values  # type: ignore[attr-defined]
                    self._send_html(_web_signature_form_html(token=token, values=values, args=args))
                    return

                token = _required_payload(payload, "setup_token", "setup token")
                values = self.server.pending_sessions.pop(token, None)  # type: ignore[attr-defined]
                if values is None:
                    raise ValueError("setup session expired. Start again.")
                result = _run_setup_from_web_payload(payload, args=args, values=values)
                self.server.exit_code = 0  # type: ignore[attr-defined]
                self._send_html(_web_success_html(result))
            except Exception as exc:
                self.server.exit_code = 1  # type: ignore[attr-defined]
                self._send_html(_web_error_html(exc), status=400)
                if self.path == "/setup":
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                if self.path == "/setup":
                    threading.Thread(target=self.server.shutdown, daemon=True).start()

        def _read_form_payload(self) -> dict[str, str]:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            return {
                key: values[-1]
                for key, values in urllib.parse.parse_qs(raw_body, keep_blank_values=True).items()
            }

        def log_message(self, format: str, *args) -> None:
            return

        def _send_html(self, body: str, *, status: int = 200) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return SetupRequestHandler


def _values_from_web_account_payload(payload: dict[str, str], *, args: argparse.Namespace) -> SetupValues:
    return SetupValues(
        env_file=Path(payload.get("env_file") or args.env_file).expanduser().resolve(),
        email=_required_payload(payload, "email", "메일 주소"),
        password=_required_payload(payload, "password", "메일 비밀번호"),
        from_name=_required_payload(payload, "from_name", "그룹웨어 내 본인 이름"),
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


def _run_setup_from_web_payload(
    payload: dict[str, str],
    *,
    args: argparse.Namespace,
    values: SetupValues | None = None,
) -> dict[str, str]:
    already_verified = values is not None
    if values is None:
        values = _values_from_web_account_payload(payload, args=args)
    fields = {
        "display_name": payload.get("display_name") or values.from_name,
        "english_name": payload.get("english_name", ""),
        "hanja_name": payload.get("hanja_name", ""),
        "department": payload.get("department", ""),
        "division_english": payload.get("division_english", ""),
        "team": payload.get("team", ""),
        "position": payload.get("position", ""),
        "job_title_english": payload.get("job_title_english", ""),
        "office_phone": payload.get("office_phone", ""),
        "mobile": payload.get("mobile", ""),
        "email": values.email,
    }
    setup_args = SimpleNamespace(
        display_name=fields["display_name"],
        english_name=fields["english_name"],
        hanja_name=fields["hanja_name"],
        department=fields["department"],
        division_english=fields["division_english"],
        team=fields["team"],
        position=fields["position"],
        job_title_english=fields["job_title_english"],
        office_phone=fields["office_phone"],
        mobile=fields["mobile"],
        logo_image_path=payload.get("logo_image_path", ""),
        greeting_text=payload.get("greeting_text") or DEFAULT_GREETING_TEXT,
        closing_text=payload.get("closing_text") or DEFAULT_CLOSING_TEXT,
        preview_dir=payload.get("preview_dir") or args.preview_dir,
        signature_gui=False,
        edit_templates=False,
        non_interactive=True,
    )
    _write_env_file(values, force=args.force or payload.get("force") == "on")
    config = _build_config(values)
    if (
        not already_verified
        and not args.skip_connection_check
        and payload.get("skip_connection_check") != "on"
    ):
        _check_connections(config)
    if payload.get("skip_signature_setup") != "on":
        _setup_default_signature(config, values=values, args=setup_args)
    return {
        "env_file": str(values.env_file),
        "command_path": str((Path.cwd() / ".venv" / "bin" / "ubisam-mail-mcp").resolve()),
        "codex_config": _codex_config_snippet(values.env_file),
        "claude_command": _claude_command_snippet(values.env_file),
    }


def _required_payload(payload: dict[str, str], key: str, label: str) -> str:
    value = payload.get(key, "").strip()
    if not value:
        raise ValueError(f"{label} 필요")
    return value


def _web_form_html(args: argparse.Namespace) -> str:
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ubisam-mail-mcp setup</title>
<style>
body{{font-family:"Malgun Gothic",system-ui,sans-serif;margin:0;background:#f5f7f9;color:#1b1f24;}}
main{{max-width:720px;margin:0 auto;padding:24px;}}
h1{{font-size:24px;margin:0 0 16px;}}
.panel{{background:white;border:1px solid #d7dde3;border-radius:8px;padding:16px;}}
.grid{{display:grid;grid-template-columns:180px 1fr;gap:10px;align-items:center;}}
label{{font-size:14px;color:#30363d;}}
input{{width:100%;box-sizing:border-box;border:1px solid #c7d0d9;border-radius:6px;padding:8px;font:14px "Malgun Gothic",system-ui,sans-serif;}}
.password-row{{display:flex;gap:8px;align-items:center;}}
.password-row input{{flex:1;}}
.secondary{{border:1px solid #aeb8c2;background:white;color:#1b1f24;border-radius:6px;padding:8px 10px;font-weight:600;cursor:pointer;white-space:nowrap;}}
.actions{{display:flex;justify-content:flex-end;margin-top:16px;gap:8px;}}
button{{border:1px solid #0069c2;background:#0078d4;color:white;border-radius:6px;padding:10px 16px;font-weight:700;cursor:pointer;}}
.hint{{font-size:13px;color:#59636e;margin:8px 0 0;}}
code{{background:#eef2f5;border-radius:4px;padding:2px 4px;}}
@media(max-width:700px){{.grid{{grid-template-columns:1fr;}}}}
</style>
</head>
<body>
<main>
<h1>1단계. 그룹웨어 계정 확인</h1>
<form method="post" action="/verify">
<section class="panel">
<div class="grid">
<label>메일 주소</label><input name="email" type="email" required>
<label>메일 비밀번호</label><div class="password-row"><input id="password" name="password" type="password" required><button class="secondary" type="button" id="togglePassword">보기</button></div>
<label>그룹웨어 내 본인 이름</label><input name="from_name" required>
</div>
<div class="actions"><button type="submit">계정 확인</button></div>
<p class="hint">먼저 IMAP/SMTP 로그인을 검증한다. 성공하면 서명 설정 화면으로 넘어간다.</p>
<p class="hint">경로, DB, SMTP/IMAP host/port는 기본값을 사용한다. 비밀번호는 이 PC의 로컬 setup 프로세스로만 전송된다.</p>
</section>
</form>
</main>
<script>
const password = document.querySelector("#password");
const togglePassword = document.querySelector("#togglePassword");
togglePassword.addEventListener("click", () => {{
  const visible = password.type === "text";
  password.type = visible ? "password" : "text";
  togglePassword.textContent = visible ? "보기" : "숨기기";
}});
</script>
</body>
</html>"""


def _web_signature_form_html(*, token: str, values: SetupValues, args: argparse.Namespace) -> str:
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ubisam-mail-mcp signature setup</title>
<style>
body{{font-family:"Malgun Gothic",system-ui,sans-serif;margin:0;background:#f5f7f9;color:#1b1f24;}}
main{{max-width:1180px;margin:0 auto;padding:24px;}}
h1{{font-size:24px;margin:0 0 16px;}}
.layout{{display:grid;grid-template-columns:minmax(420px,1fr) minmax(420px,1fr);gap:18px;align-items:start;}}
.panel{{background:white;border:1px solid #d7dde3;border-radius:8px;padding:16px;}}
.grid{{display:grid;grid-template-columns:150px 1fr;gap:10px;align-items:center;}}
label{{font-size:14px;color:#30363d;}}
input,textarea{{width:100%;box-sizing:border-box;border:1px solid #c7d0d9;border-radius:6px;padding:8px;font:14px "Malgun Gothic",system-ui,sans-serif;}}
textarea{{min-height:92px;resize:vertical;line-height:1.5;}}
.inline-check{{display:flex;align-items:center;gap:8px;}}
.inline-check input[type="checkbox"]{{width:auto;}}
.inline-check input[type="text"]{{flex:1;}}
.section{{margin-top:18px;padding-top:14px;border-top:1px solid #e5e9ee;}}
.preview{{white-space:pre-wrap;min-height:520px;background:#fff;border:1px solid #c7d0d9;border-radius:8px;padding:16px;line-height:1.55;font-size:15px;}}
.actions{{display:flex;justify-content:flex-end;margin-top:16px;gap:8px;}}
button{{border:1px solid #0069c2;background:#0078d4;color:white;border-radius:6px;padding:10px 16px;font-weight:700;cursor:pointer;}}
.hint{{font-size:13px;color:#59636e;margin:8px 0 0;}}
@media(max-width:900px){{.layout{{grid-template-columns:1fr;}}.grid{{grid-template-columns:1fr;}}}}
</style>
</head>
<body>
<main>
<h1>2단계. 기본 서식 설정</h1>
<p class="hint">계정 확인 완료: {_esc(values.email)}</p>
<form method="post" action="/setup">
<input type="hidden" name="setup_token" value="{_esc(token)}">
<input type="hidden" name="email" value="{_esc(values.email)}">
<input type="hidden" name="preview_dir" value="{_esc(args.preview_dir)}">
<div class="layout">
<section class="panel">
<div class="grid">
<label>서명 이름</label><input data-preview name="display_name" value="{_esc(values.from_name)}">
<label>영문 이름</label><input data-preview name="english_name">
<label>한자 이름</label><div class="inline-check"><input id="useHanja" type="checkbox"><input id="hanjaName" data-preview name="hanja_name" disabled></div>
<label>부서</label><input data-preview name="department">
<label>영문 부서</label><input data-preview name="division_english">
<label>팀</label><input data-preview name="team">
<label>직급</label><input data-preview name="position">
<label>영문 직함</label><input data-preview name="job_title_english">
<label>대표전화</label><input data-preview name="office_phone">
<label>휴대폰</label><input data-preview name="mobile">
</div>
<div class="section">
<label>기본 인삿말</label>
<textarea data-preview name="greeting_text">{_esc(DEFAULT_GREETING_TEXT)}</textarea>
<label>기본 맺음말</label>
<textarea data-preview name="closing_text">{_esc(DEFAULT_CLOSING_TEXT)}</textarea>
</div>
<div class="actions"><button type="submit">저장하고 완료</button></div>
<p class="hint">빈 영문 이름, 한자 이름, 전화번호는 저장되는 footer 서명에서 자동으로 빠진다.</p>
</section>
<section class="panel">
<h2>실시간 미리보기</h2>
<div id="preview" class="preview"></div>
</section>
</div>
</form>
</main>
<script>
const form = document.querySelector("form");
const preview = document.querySelector("#preview");
const useHanja = document.querySelector("#useHanja");
const hanjaName = document.querySelector("#hanjaName");
function value(name) {{ return (form.elements[name]?.value || "").trim(); }}
function parts(items, sep=" / ") {{ return items.filter(Boolean).join(sep); }}
function renderTemplate(text) {{
  return text.replace(/{{{{\\s*([a-zA-Z0-9_]+)\\s*}}}}/g, (_m, key) => value(key));
}}
function refresh() {{
  const nameHead = parts([parts([value("display_name"), value("position")], " "), value("english_name"), value("hanja_name")]);
  const dept = parts([value("department"), value("division_english"), value("job_title_english")]);
  const contact = parts([
    value("office_phone") ? "t " + value("office_phone") : "",
    value("mobile") ? "m " + value("mobile") : "",
    value("email") ? "e " + value("email") : ""
  ], "  ");
  const lines = [
    renderTemplate(value("greeting_text")),
    "본문 테스트입니다.",
    renderTemplate(value("closing_text")),
    [nameHead, dept, contact].filter(Boolean).join("\\n")
  ].filter(Boolean);
  preview.textContent = lines.join("\\n\\n");
}}
form.addEventListener("input", refresh);
useHanja.addEventListener("change", () => {{
  hanjaName.disabled = !useHanja.checked;
  if (!useHanja.checked) hanjaName.value = "";
  refresh();
}});
refresh();
</script>
</body>
</html>"""


def _web_success_html(result: dict[str, str]) -> str:
    env_file = _esc(result["env_file"])
    command_path = _esc(result["command_path"])
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>setup complete</title>
<style>body{{font-family:"Malgun Gothic",system-ui,sans-serif;margin:24px;line-height:1.55;max-width:920px;}}pre{{background:#f3f5f7;padding:12px;border-radius:8px;overflow:auto;}}</style></head>
<body>
<h1>설정 완료</h1>
<p><code>.env</code> 저장 위치: <code>{env_file}</code></p>
<p>아래 중 사용하는 client 설정에 넣으세요.</p>
<h2>Claude Code</h2>
<pre>{_esc(result["claude_command"])}</pre>
<h2>Codex</h2>
<pre>{_esc(result["codex_config"])}</pre>
<p>설정 후 Claude/Codex를 재시작하고 <code>내 메일 설정 상태 확인해줘.</code>라고 입력하세요.</p>
<p>command 절대경로: <code>{command_path}</code></p>
</body></html>"""


def _web_error_html(exc: Exception) -> str:
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>setup failed</title>
<style>body{{font-family:"Malgun Gothic",system-ui,sans-serif;margin:24px;line-height:1.55;}}</style></head>
<body><h1>설정 실패</h1><p>{_esc(str(exc))}</p><p>터미널에서 다시 <code>ubisam-mail-mcp-setup --web-setup</code>를 실행하세요.</p></body></html>"""


def _claude_command_snippet(env_file: Path) -> str:
    command_path = (Path.cwd() / ".venv" / "bin" / "ubisam-mail-mcp").resolve()
    return (
        "claude mcp add ubisam-mail \\\n"
        f"  --env UBISAM_ENV_FILE={env_file} \\\n"
        f"  -- {command_path}"
    )


def _codex_config_snippet(env_file: Path) -> str:
    command_path = (Path.cwd() / ".venv" / "bin" / "ubisam-mail-mcp").resolve()
    return (
        "[mcp_servers.ubisam_mail]\n"
        f'command = "{command_path}"\n'
        f'env = {{ UBISAM_ENV_FILE = "{env_file}" }}'
    )


def _esc(value: str) -> str:
    return html.escape(str(value), quote=True)


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
    greeting_text = args.greeting_text
    closing_text = args.closing_text
    logo_image_path = args.logo_image_path
    if args.signature_gui and not args.non_interactive:
        fields, greeting_text, closing_text, logo_image_path = _run_signature_gui(
            fields=fields,
            greeting_text=greeting_text,
            closing_text=closing_text,
            logo_image_path=logo_image_path,
        )
    elif not args.non_interactive:
        fields = _prompt_signature_fields(fields)
        if args.edit_templates:
            greeting_text = _edit_multiline_text("기본 인삿말", greeting_text)
            closing_text = _edit_multiline_text("기본 맺음말", closing_text)

    display_name = fields["display_name"].strip() or display_name
    template_fields = dict(fields)
    template_fields["logo_image_path"] = logo_image_path
    signature_text, signature_html = _build_signature_templates(template_fields)
    service.create_signature_profile(
        name=f"{display_name} 기본 프로필",
        fields=fields,
        logo_image_path=logo_image_path,
        is_default=True,
    )
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
        text_template=signature_text,
        html_template=signature_html,
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


def _build_signature_templates(fields: dict[str, str]) -> tuple[str, str]:
    name_head = _join_template_parts(
        [
            _join_template_parts(["{{display_name}}", "{{position}}"], separator=" "),
            _optional_placeholder("english_name", fields),
            _optional_placeholder("hanja_name", fields),
        ]
    )
    department_line = _join_template_parts(
        [
            _optional_placeholder("department", fields),
            _optional_placeholder("division_english", fields),
            _optional_placeholder("job_title_english", fields),
        ]
    )
    contact_line = _join_template_parts(
        [
            _prefixed_placeholder("t", "office_phone", fields),
            _prefixed_placeholder("m", "mobile", fields),
            _prefixed_placeholder("e", "email", fields),
        ],
        separator="  ",
    )
    text_lines = [line for line in (name_head, department_line, contact_line) if line]
    text_template = "\n".join(text_lines) or "{{display_name}}\ne {{email}}"

    logo_html = (
        '<span style="display:inline-flex;align-items:flex-end;line-height:1;">'
        "{{company_logo_img}}</span>"
        if fields.get("logo_image_path", "").strip()
        else ""
    )
    html_parts = [
        '<hr style="border:none;border-top:1px solid #cfcfcf;margin:0 0 14px 0;">',
        '<div style="font-family:\'Malgun Gothic\',sans-serif;color:#7c7c7c;">',
    ]
    html_parts.append(
        '  <div style="font-size:24px;font-weight:700;line-height:1.25;color:#8a8a8a;'
        'display:flex;align-items:flex-end;gap:14px;">'
        f"{logo_html}"
        '    <span style="display:inline-block;line-height:1;transform:translateY(-4px);">'
        f"{name_head}</span>"
        "  </div>"
    )
    if department_line:
        html_parts.append(
            '  <div style="margin-top:10px;font-size:19px;font-weight:700;line-height:1.3;color:#8a8a8a;">'
            f"{department_line}</div>"
        )
    if contact_line:
        html_parts.append(
            '  <div style="margin-top:14px;font-size:18px;line-height:1.45;color:#6f6f6f;">'
            f"{_html_contact_line(fields)}"
            "  </div>"
        )
    html_parts.append("</div>")
    return text_template, "".join(html_parts)


def _join_template_parts(parts: list[str], *, separator: str = " / ") -> str:
    return separator.join(part for part in parts if part)


def _optional_placeholder(name: str, fields: dict[str, str]) -> str:
    if not fields.get(name, "").strip():
        return ""
    return "{{" + name + "}}"


def _prefixed_placeholder(prefix: str, name: str, fields: dict[str, str]) -> str:
    if not fields.get(name, "").strip():
        return ""
    return f"{prefix} {{{{{name}}}}}"


def _html_contact_line(fields: dict[str, str]) -> str:
    parts: list[str] = []
    for prefix, name in (("t", "office_phone"), ("m", "mobile"), ("e", "email")):
        if fields.get(name, "").strip():
            parts.append(f'<strong style="color:#222;">{prefix}</strong> {{{{{name}}}}}')
    return " &nbsp;&nbsp; ".join(parts)


def _run_signature_gui(
    *,
    fields: dict[str, str],
    greeting_text: str,
    closing_text: str,
    logo_image_path: str,
) -> tuple[dict[str, str], str, str, str]:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        from tkinter.scrolledtext import ScrolledText
    except Exception as exc:
        raise ValueError("GUI setup requires tkinter. Use --edit-templates or terminal input.") from exc

    result: dict[str, object] = {"saved": False}
    root = tk.Tk()
    root.title("ubisam-mail-mcp 기본 서식 설정")
    root.geometry("1120x760")
    root.minsize(960, 680)

    field_labels = [
        ("display_name", "서명 이름"),
        ("english_name", "영문 이름"),
        ("hanja_name", "한자 이름"),
        ("department", "부서"),
        ("division_english", "영문 부서"),
        ("team", "팀"),
        ("position", "직급"),
        ("job_title_english", "영문 직함"),
        ("office_phone", "대표전화"),
        ("mobile", "휴대폰"),
        ("email", "이메일"),
    ]
    vars_by_key = {key: tk.StringVar(value=fields.get(key, "")) for key, _label in field_labels}
    logo_var = tk.StringVar(value=logo_image_path)

    outer = ttk.Frame(root, padding=12)
    outer.pack(fill="both", expand=True)
    outer.columnconfigure(0, weight=1)
    outer.columnconfigure(1, weight=1)
    outer.rowconfigure(0, weight=1)

    left = ttk.Frame(outer)
    left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
    left.columnconfigure(1, weight=1)
    right = ttk.Frame(outer)
    right.grid(row=0, column=1, sticky="nsew")
    right.rowconfigure(1, weight=1)
    right.columnconfigure(0, weight=1)

    ttk.Label(left, text="프로필", font=("", 12, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
    for row_index, (key, label) in enumerate(field_labels, start=1):
        ttk.Label(left, text=label).grid(row=row_index, column=0, sticky="w", pady=3)
        entry = ttk.Entry(left, textvariable=vars_by_key[key])
        entry.grid(row=row_index, column=1, columnspan=2, sticky="ew", pady=3)

    logo_row = len(field_labels) + 1
    ttk.Label(left, text="로고 이미지").grid(row=logo_row, column=0, sticky="w", pady=3)
    ttk.Entry(left, textvariable=logo_var).grid(row=logo_row, column=1, sticky="ew", pady=3)

    def choose_logo() -> None:
        selected = filedialog.askopenfilename(
            title="로고 이미지 선택",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.webp"),
                ("All files", "*.*"),
            ],
        )
        if selected:
            logo_var.set(selected)

    ttk.Button(left, text="찾기", command=choose_logo).grid(row=logo_row, column=2, sticky="ew", padx=(6, 0))

    text_row = logo_row + 1
    ttk.Label(left, text="기본 인삿말").grid(row=text_row, column=0, columnspan=3, sticky="w", pady=(12, 3))
    greeting_box = ScrolledText(left, height=5, wrap="word")
    greeting_box.grid(row=text_row + 1, column=0, columnspan=3, sticky="nsew")
    greeting_box.insert("1.0", greeting_text)

    ttk.Label(left, text="기본 맺음말").grid(row=text_row + 2, column=0, columnspan=3, sticky="w", pady=(12, 3))
    closing_box = ScrolledText(left, height=5, wrap="word")
    closing_box.grid(row=text_row + 3, column=0, columnspan=3, sticky="nsew")
    closing_box.insert("1.0", closing_text)
    left.rowconfigure(text_row + 1, weight=1)
    left.rowconfigure(text_row + 3, weight=1)

    ttk.Label(right, text="실시간 미리보기", font=("", 12, "bold")).grid(row=0, column=0, sticky="w")
    preview = ScrolledText(right, wrap="word", state="disabled")
    preview.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

    buttons = ttk.Frame(right)
    buttons.grid(row=2, column=0, sticky="e", pady=(12, 0))

    def current_fields() -> dict[str, str]:
        data = {key: variable.get().strip() for key, variable in vars_by_key.items()}
        data["logo_image_path"] = logo_var.get().strip()
        return data

    def current_greeting() -> str:
        return greeting_box.get("1.0", "end").strip()

    def current_closing() -> str:
        return closing_box.get("1.0", "end").strip()

    def refresh_preview(*_args) -> None:
        data = current_fields()
        text_template, _html_template = _build_signature_templates(data)
        rendered = "\n\n".join(
            part
            for part in [
                _render_setup_template(current_greeting(), data),
                "본문 테스트입니다.",
                _render_setup_template(current_closing(), data),
                _render_setup_template(text_template, data),
            ]
            if part
        )
        if data.get("logo_image_path"):
            rendered += f"\n\n[로고] {Path(data['logo_image_path']).name}"
        preview.configure(state="normal")
        preview.delete("1.0", "end")
        preview.insert("1.0", rendered)
        preview.configure(state="disabled")

    for variable in [*vars_by_key.values(), logo_var]:
        variable.trace_add("write", refresh_preview)
    greeting_box.bind("<KeyRelease>", refresh_preview)
    closing_box.bind("<KeyRelease>", refresh_preview)

    def save() -> None:
        data = current_fields()
        if not data.get("display_name"):
            messagebox.showerror("입력 필요", "서명 이름은 필수입니다.")
            return
        if not data.get("email"):
            messagebox.showerror("입력 필요", "이메일은 필수입니다.")
            return
        result["saved"] = True
        result["fields"] = data
        result["greeting_text"] = current_greeting() or DEFAULT_GREETING_TEXT
        result["closing_text"] = current_closing() or DEFAULT_CLOSING_TEXT
        result["logo_image_path"] = data.pop("logo_image_path", "")
        root.destroy()

    def cancel() -> None:
        root.destroy()

    ttk.Button(buttons, text="취소", command=cancel).pack(side="right", padx=(8, 0))
    ttk.Button(buttons, text="저장", command=save).pack(side="right")
    root.protocol("WM_DELETE_WINDOW", cancel)
    refresh_preview()
    root.mainloop()

    if not result["saved"]:
        raise KeyboardInterrupt
    return (
        result["fields"],  # type: ignore[return-value]
        str(result["greeting_text"]),
        str(result["closing_text"]),
        str(result["logo_image_path"]),
    )


def _render_setup_template(template: str, fields: dict[str, str]) -> str:
    return _PLACEHOLDER_RE.sub(lambda match: fields.get(match.group(1), ""), template).strip()


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
