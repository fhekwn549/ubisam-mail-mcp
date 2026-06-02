# ubisam-mail-mcp

## 사전 준비 (필수)

1. **Python 3.10 이상 + pip** — 확인: `python3 --version`. 3.10 미만이면 동작하지 않으니 먼저 3.10+를 설치한다. (가상환경 venv는 선택 사항이며 파이썬 버전을 바꿔주지 않는다.)
2. **유비샘 그룹웨어에서 외부 메일 연동 활성화**:
   > **유비샘 그룹웨어 → 메일 → 환경설정 → SMTP-POP3-IMAP → SMTP/IMAP** 페이지에서 사용을 활성화한다.

   활성화하지 않으면 아래 설정이 맞아도 IMAP/SMTP 로그인이 거부된다.

## 소개

유비샘 그룹웨어 메일 계정의 IMAP/SMTP를 사용해 agent가 메일 조회, 초안 작성, 임시보관, 예약 발송, 사용자 확인 후 발송을 수행하는 MCP 서버다.

## 범위

- `list_mailboxes`: IMAP 메일함 목록 조회
- `list_messages`: 메일함 최근 메일 요약 조회
- `get_message`: 특정 UID 메일 본문 미리보기 조회
- `create_signature`, `update_signature`, `get_signature`, `list_signatures`, `delete_signature`: 로컬 서명 템플릿 관리
- `create_draft`: 메일 초안 생성
- `update_draft`: 초안 수정
- `get_draft`, `list_drafts`: 임시보관/발송 상태 조회
- `schedule_draft`: 예약 발송 등록
- `send_draft_now`: 사용자 확인 뒤 즉시 발송
- `dispatch_due_messages`: 예약 시간이 지난 메일 발송

## 운영 제약

- 메일 조회는 IMAP, 실제 발송은 SMTP로 처리한다.
- 예약 발송은 SQLite에 저장된다.
- 보안상 SMTP 발송은 `TLS(465)` 또는 `STARTTLS(587)` 중 하나가 반드시 켜져 있어야 한다. 둘 다 꺼져 있으면 MCP가 발송을 거부한다.
- 그룹웨어 웹의 **메일 → 환경설정 → 서명** 값을 직접 읽어오지는 않는다. 필요하면 기존 서명을 1회 복사해 MCP 로컬 템플릿으로 저장한다.
- 서명 템플릿은 `{{body}}` placeholder를 기준으로 본문을 중간에 삽입한다.
- 회사 연락처처럼 글씨색/크기/폰트가 다른 서명은 `html_template`에 inline style로 저장한다.
- 서버가 실행 중이어야 예약 시간이 도래했을 때 자동 발송할 수 있다.
- 서버가 꺼져 있으면 `dispatch_due_messages`를 다시 호출해야 밀린 예약 메일을 보낸다.
- 1차 버전은 첨부파일 다운로드, 유비샘 웹 임시보관함 동기화, IMAP 발송함 업로드를 구현하지 않는다.

## 환경 변수

`.env.example`를 복사해 `.env`를 만들고 각자 계정값을 넣는다:

```bash
unzip ubisam-mail-mcp.zip      # 그룹웨어에서 받은 압축 파일 해제
cd ubisam-mail-mcp
cp .env.example .env
```

사용자별 값:
- `UBISAM_SMTP_USERNAME`
- `UBISAM_SMTP_PASSWORD`
- `UBISAM_IMAP_USERNAME`
- `UBISAM_IMAP_PASSWORD`
- `UBISAM_DEFAULT_FROM`

보통 `UBISAM_DEFAULT_FROM`은 자기 메일 주소와 동일하게 둔다.

공통 권장값은 `.env.example`에 포함돼 있다:
- `UBISAM_SMTP_HOST="ubisam.hanbiro.net"`
- `UBISAM_SMTP_PORT="587"`
- `UBISAM_SMTP_USE_TLS="false"`
- `UBISAM_SMTP_USE_STARTTLS="true"`
- `UBISAM_SMTP_DEBUG="false"`
- `UBISAM_IMAP_HOST="ubisam.hanbiro.net"`
- `UBISAM_IMAP_PORT="993"`
- `UBISAM_IMAP_USE_TLS="true"`

참고:
- `2026-06-01` 기준 `ubisam.hanbiro.net`에서 `IMAP 993 SSL`, `IMAP 143`, `SMTP 465 SSL`, `SMTP 587 STARTTLS` 응답을 확인했다.
- `2026-06-01` 기준 한 Ubisam 계정으로 `IMAP 993 SSL`, `SMTP 465 SSL`, `SMTP 587 STARTTLS` 로그인 성공을 확인했다.
- Hanbiro 계열 서버 인증서는 `*.hanbiro.net`로 응답할 수 있다.
- 한비로 공식 문서와 사내 댓글 예시는 `IMAP 143`, `SMTP 587`, 연결방식 `자동`을 사용한다. 현재 Ubisam 계정은 `IMAP 993 SSL` 구성이 확인됐고, SMTP는 `587 STARTTLS`를 우선 권장한다.
- SMTP는 `587 STARTTLS`를 권장한다. `465 SSL`(implicit TLS)로 보내면 한비로 서버 앞단에서 TLS가 종단되고 본체 qmail은 `127.0.0.1` 평문으로 수신해(`Received: ... with SMTP`) 웹메일에 "암호화되지 않음" 자물쇠가 표시된다. `587 STARTTLS`는 qmail이 직접 TLS를 협상해(`Received: ... encrypted SMTP`) 정상적으로 암호화 표시된다.
- `UBISAM_SMTP_USE_TLS`와 `UBISAM_SMTP_USE_STARTTLS`를 둘 다 `false`로 두면 평문 SMTP가 되어 보안상 허용되지 않는다.
- SMTP 연결 문제를 추적할 때는 `UBISAM_SMTP_DEBUG="true"`로 켜고 MCP 서버 stderr 로그에서 `smtp-debug ...` 줄을 확인한다.

## 설치 및 실행

공식 MCP Python SDK(`mcp`) 기반의 표준 stdio MCP 서버다. 의존성을 설치하면 `ubisam-mail-mcp` 진입점이 생긴다(가상환경 권장):

```bash
cd ubisam-mail-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
ubisam-mail-mcp          # stdio MCP 서버 시작
```

가상환경 없이 소스에서 직접 실행:

```bash
pip install -e .
PYTHONPATH=src python3 -m ubisam_mail_mcp.server
```

## MCP 클라이언트 설정

표준 stdio transport라 MCP를 지원하는 모든 agent(Claude Code, Claude Desktop, Codex 등)에서 같은 방식으로 붙는다. 클라이언트는 임의 디렉토리에서 서버를 실행하므로 `UBISAM_ENV_FILE`로 `.env` 절대경로를 지정한다. `command`는 PATH에 진입점이 없으면 절대경로로 적는다(가상환경이면 `/absolute/path/to/ubisam-mail-mcp/.venv/bin/ubisam-mail-mcp`).

### Claude Code

`claude mcp add` 명령이 설정을 자동 기록한다(user scope `~/.claude.json`, 또는 프로젝트 루트 `.mcp.json`). 등록 확인은 `claude mcp list`.

```bash
claude mcp add ubisam-mail \
  --env UBISAM_ENV_FILE=/absolute/path/to/ubisam-mail-mcp/.env \
  -- ubisam-mail-mcp
```

### Claude Desktop

설정 파일(앱 메뉴 **Settings → Developer → Edit Config**로도 열린다):
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

수정 후 앱을 재시작한다.

```json
{
  "mcpServers": {
    "ubisam-mail": {
      "command": "ubisam-mail-mcp",
      "env": { "UBISAM_ENV_FILE": "/absolute/path/to/ubisam-mail-mcp/.env" }
    }
  }
}
```

### Codex

설정 파일:
- macOS/Linux: `~/.codex/config.toml`
- Windows: `%USERPROFILE%\.codex\config.toml`

```toml
[mcp_servers.ubisam_mail]
command = "ubisam-mail-mcp"
env = { UBISAM_ENV_FILE = "/absolute/path/to/ubisam-mail-mcp/.env" }
```

진입점을 설치하지 않고 소스에서 직접 띄우려면 `command = "python3"`, `args = ["-m", "ubisam_mail_mcp.server"]`로 두고 `env`에 `PYTHONPATH = "/absolute/path/to/ubisam-mail-mcp/src"`를 추가한다.

설명:
- 설정은 MCP 실행 경로만 잡는다. 실제 계정값은 `.env`에서 자동 로드한다.
- 프로세스 환경변수와 `.env`가 동시에 있으면 환경변수가 우선한다.

## 권장 agent 흐름 / 튜토리얼

1. `create_signature`로 서명 템플릿 저장
2. `list_signatures` 또는 `get_signature`로 기본 서명 확인
3. `create_draft`로 초안 생성
4. `get_draft` 또는 `list_drafts`로 사용자에게 미리보기
5. 사용자 승인 후 `send_draft_now`
6. 예약이면 `schedule_draft`
7. 장기 운영이면 외부 cron/systemd timer로 MCP 서버 또는 보조 dispatcher 실행

서명 템플릿 예시:

```text
안녕하세요.

{{body}}

감사합니다.
홍길동 드림
OO팀 / 02-123-4567
```

HTML 서명 예시:

```html
<p>안녕하세요.</p>
<div>{{body}}</div>
<p>
  감사합니다.<br>
  홍길동 드림<br>
  <span style="color:#666;font-size:12px;font-family:'Malgun Gothic';">
    OO팀 / 02-123-4567
  </span>
</p>
```

메모:
- `create_draft`에서 `signature_id`를 주면 해당 서명을 사용한다.
- `apply_default_signature=true`면 기본 서명이 자동 적용된다.
- 초안 조회 응답에는 원본 `text_body`/`html_body`와 함께 서명까지 합쳐진 `rendered_text_body`/`rendered_html_body`가 포함된다.

## 테스트

```bash
cd ubisam-mail-mcp
PYTHONPATH=src pytest
```

## SMTP 디버그

연결이 갑자기 끊기거나 TLS 협상 여부를 확인해야 하면:

```bash
export UBISAM_SMTP_DEBUG="true"
ubisam-mail-mcp
```

로그 예시:

```text
smtp-debug connect mode=ssl host=ubisam.hanbiro.net port=465
smtp-debug auth method=plain username=your-email@ubisam.com
smtp-debug send_message recipients=1 subject=[MCP Test] self-send ...
```

실패하면 예외도 같이 찍힌다:

```text
smtp-debug error type=SMTPServerDisconnected detail=Connection unexpectedly closed
```

## 연결 확인 스크립트

SMTP:

```bash
cd ubisam-mail-mcp
python3 scripts/check_smtp.py --host ubisam.hanbiro.net --mode ssl --username your-email@ubisam.com
```

비밀번호는 프롬프트로 입력한다. 셸 히스토리에 남기고 싶지 않으면 `--password` 대신 프롬프트 입력을 권장한다.

IMAP:

```bash
cd ubisam-mail-mcp
python3 scripts/check_imap.py --host ubisam.hanbiro.net --mode ssl --username your-email@ubisam.com
```

브랜드 도메인과 인증서 이름이 다르면:

```bash
python3 scripts/check_imap.py --host yourdomain.hanbiro.net --tls-servername actual-cert-name.hanbiro.net --username you@company.com
python3 scripts/check_smtp.py --host yourdomain.hanbiro.net --tls-servername actual-cert-name.hanbiro.net --username you@company.com
```
