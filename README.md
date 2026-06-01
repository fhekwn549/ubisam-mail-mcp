# hanbiro-mail-mcp

한비로 메일 계정의 IMAP/SMTP를 사용해 agent가 메일 조회, 초안 작성, 임시보관, 예약 발송, 사용자 확인 후 발송을 수행하는 MCP 서버다.

## 범위

- `list_mailboxes`: IMAP 메일함 목록 조회
- `list_messages`: 메일함 최근 메일 요약 조회
- `get_message`: 특정 UID 메일 본문 미리보기 조회
- `create_draft`: 메일 초안 생성
- `update_draft`: 초안 수정
- `get_draft`, `list_drafts`: 임시보관/발송 상태 조회
- `schedule_draft`: 예약 발송 등록
- `send_draft_now`: 사용자 확인 뒤 즉시 발송
- `dispatch_due_messages`: 예약 시간이 지난 메일 발송

## 운영 제약

- 메일 조회는 IMAP, 실제 발송은 SMTP로 처리한다.
- 예약 발송은 SQLite에 저장된다.
- 서버가 실행 중이어야 예약 시간이 도래했을 때 자동 발송할 수 있다.
- 서버가 꺼져 있으면 `dispatch_due_messages`를 다시 호출해야 밀린 예약 메일을 보낸다.
- 1차 버전은 첨부파일 다운로드, Hanbiro 웹 임시보관함 동기화, IMAP 발송함 업로드를 구현하지 않는다.

## 환경 변수

`.env.example`를 복사해 `.env`를 만들고 각자 계정값을 넣는다:

```bash
cd /home/fhekwn549/hanbiro-mail-mcp
cp .env.example .env
```

사용자별 값:
- `HANBIRO_SMTP_USERNAME`
- `HANBIRO_SMTP_PASSWORD`
- `HANBIRO_IMAP_USERNAME`
- `HANBIRO_IMAP_PASSWORD`
- `HANBIRO_DEFAULT_FROM`

보통 `HANBIRO_DEFAULT_FROM`은 자기 메일 주소와 동일하게 둔다.

공통 권장값은 `.env.example`에 포함돼 있다:
- `HANBIRO_SMTP_HOST="ubisam.hanbiro.net"`
- `HANBIRO_SMTP_PORT="465"`
- `HANBIRO_SMTP_USE_TLS="true"`
- `HANBIRO_SMTP_USE_STARTTLS="false"`
- `HANBIRO_IMAP_HOST="ubisam.hanbiro.net"`
- `HANBIRO_IMAP_PORT="993"`
- `HANBIRO_IMAP_USE_TLS="true"`

참고:
- `2026-06-01` 기준 `ubisam.hanbiro.net`에서 `IMAP 993 SSL`, `IMAP 143`, `SMTP 465 SSL`, `SMTP 587 STARTTLS` 응답을 확인했다.
- `2026-06-01` 기준 `your-email@ubisam.com` 계정으로 `IMAP 993 SSL`, `SMTP 465 SSL` 로그인 성공을 확인했다.
- Hanbiro 계열 서버 인증서는 `*.hanbiro.net`로 응답할 수 있다.
- 한비로 공식 문서와 사내 댓글 예시는 `IMAP 143`, `SMTP 587`, 연결방식 `자동`을 사용한다. 현재 Ubisam 계정은 `IMAP 993 SSL`, `SMTP 465 SSL` 구성이 확인됐으므로 이 값을 우선 권장한다.

## 실행

```bash
cd /home/fhekwn549/hanbiro-mail-mcp
PYTHONPATH=src python3 -m hanbiro_mail_mcp.server
```

또는:

```bash
cd /home/fhekwn549/hanbiro-mail-mcp
python3 -m pip install -e .
hanbiro-mail-mcp
```

## Codex MCP 설정 예시

`~/.codex/config.toml`:

```toml
[mcp_servers.hanbiro_mail]
command = "python3"
args = ["-m", "hanbiro_mail_mcp.server"]
cwd = "/home/fhekwn549/hanbiro-mail-mcp"
env = { PYTHONPATH = "/home/fhekwn549/hanbiro-mail-mcp/src", HANBIRO_ENV_FILE = "/home/fhekwn549/hanbiro-mail-mcp/.env" }
```

설명:
- `config.toml`은 MCP 실행 경로만 잡는다.
- 실제 계정값은 `.env`에서 자동 로드한다.
- 프로세스 환경변수와 `.env`가 동시에 있으면 환경변수가 우선한다.

## 권장 agent 흐름

1. `create_draft`로 초안 생성
2. `get_draft` 또는 `list_drafts`로 사용자에게 미리보기
3. 사용자 승인 후 `send_draft_now`
4. 예약이면 `schedule_draft`
5. 장기 운영이면 외부 cron/systemd timer로 MCP 서버 또는 보조 dispatcher 실행

## 테스트

```bash
cd /home/fhekwn549/hanbiro-mail-mcp
PYTHONPATH=src pytest
```

## 연결 확인 스크립트

SMTP:

```bash
cd /home/fhekwn549/hanbiro-mail-mcp
python3 scripts/check_smtp.py --host ubisam.hanbiro.net --mode ssl --username your-email@ubisam.com
```

비밀번호는 프롬프트로 입력한다. 셸 히스토리에 남기고 싶지 않으면 `--password` 대신 프롬프트 입력을 권장한다.

IMAP:

```bash
cd /home/fhekwn549/hanbiro-mail-mcp
python3 scripts/check_imap.py --host ubisam.hanbiro.net --mode ssl --username your-email@ubisam.com
```

브랜드 도메인과 인증서 이름이 다르면:

```bash
python3 scripts/check_imap.py --host yourdomain.hanbiro.net --tls-servername actual-cert-name.hanbiro.net --username you@company.com
python3 scripts/check_smtp.py --host yourdomain.hanbiro.net --tls-servername actual-cert-name.hanbiro.net --username you@company.com
```
