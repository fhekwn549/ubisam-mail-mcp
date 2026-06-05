# ubisam-mail-mcp 처음 사용 가이드 (완전 초보용)

이 문서는 **AI(Claude 등)를 처음 써 보는 동료**가 `ubisam-mail-mcp`를 자기 PC에 붙여서,
AI에게 한국어로 말만 하면 메일을 정리·작성·발송하도록 만드는 전체 과정을 순서대로 설명한다.

> 핵심 개념 먼저: 당신이 직접 명령어나 코드를 외울 필요는 없다.
> 설정만 한 번 끝내면, 이후에는 **AI에게 평소 말하듯 부탁**하면 된다.
> 예: "안 읽은 메일 있어?", "이 내용으로 초안 만들어줘", "보낸메일함에서 주간보고 메일 모아줘".
> AI가 알아서 뒤에 있는 메일 기능(tool)을 대신 호출한다. 아래 코드 블록은 "AI가 내부적으로 이렇게 부른다"는 참고용이다.

대상:
- 그룹웨어 메일 계정이 있는 회사 동료
- 터미널/코드 경험이 거의 없어도 됨 (복붙 위주)

다 끝내면 할 수 있는 것:
- AI에게 말로 메일 조회·검색
- 내 서명/인삿말 자동 적용된 메일 초안 작성
- 확인 후 발송 또는 예약 발송
- 보낸메일 등을 주제별 메일함으로 정리

---

## 큰 그림 (6단계)

1. 그룹웨어에서 외부 메일 연동 켜기
2. 프로그램 설치 (Python + 이 레포)
3. 내 계정 정보 입력 (`.env` 파일)
4. AI 앱(MCP 클라이언트)에 연결
5. 연결 확인
6. 사용 시작 (서명 세팅 → 초안 → 발송 → 메일 정리)

각 단계를 아래에서 하나씩 따라가면 된다. **순서대로** 하는 게 중요하다.

---

## 1단계. 그룹웨어에서 외부 메일 연동 켜기

이걸 먼저 안 켜면, 설정을 아무리 잘해도 로그인이 거부된다.

1. 유비샘 그룹웨어 웹에 로그인
2. **메일 → 환경설정 → SMTP-POP3-IMAP → SMTP/IMAP** 메뉴로 이동
3. **SMTP / IMAP 사용**을 활성화하고 저장

> IMAP = 메일을 읽어오는 통로, SMTP = 메일을 보내는 통로. 둘 다 켜야 한다.

---

## 2단계. 프로그램 설치

### 2-1. Python 3.10 이상 확인

터미널(Windows는 PowerShell, Mac은 터미널 앱)을 열고:

```bash
python3 --version
```

- `Python 3.10.x` 이상이 나오면 통과.
- 안 나오거나 3.10 미만이면 [python.org](https://www.python.org/downloads/)에서 Python 3.10 이상을 먼저 설치한다.
- Python이 아예 없는 PC는 Python 3.12 또는 3.13 설치를 권장한다. 너무 최신 버전이 부담되면 3.12가 보수적 선택이다.
- Windows에서 여러 버전이 설치돼 있으면 PowerShell에서 `py --list`로 확인한다.

### 2-2. 레포 받기 / 설치

그룹웨어에서 받은 압축 파일을 풀고 설치한다:

```bash
unzip ubisam-mail-mcp.zip      # 받은 압축 파일 풀기
cd ubisam-mail-mcp
python3 -m venv .venv && source .venv/bin/activate   # (선택) 가상환경
pip install -e .
```

`pip install -e .`가 끝나면 `ubisam-mail-mcp`라는 실행 명령이 생긴다. 이게 AI와 메일을 잇는 서버다.

> Windows에서 여러 Python 버전이 있으면 사용할 버전을 명시한다. 예: `py -3.12 -m venv .venv`.
> 가상환경 활성화는 `source .venv/bin/activate` 대신 `.venv\Scripts\Activate.ps1`.
> `.venv`는 Python 버전을 올려주지 않는다. 기존 `.venv`를 3.9 이하로 만들었다면 삭제 후 새 Python으로 다시 만든다.

Windows PowerShell 예시:

```powershell
py --list
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
python -m pip install -e .
```

기존 `.venv`를 다시 만들 때:

```powershell
Remove-Item -Recurse -Force .venv
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

---

## 3단계. 내 계정 정보 입력 (`.env`)

서버가 내 메일 계정으로 로그인하려면 계정값이 필요하다. 예시 파일을 복사해서 내 값으로 채운다:

```bash
cp .env.example .env
```

그다음 `.env` 파일을 메모장/편집기로 열어 **내 값으로 수정**한다.

반드시 채워야 하는 항목:
- `UBISAM_SMTP_USERNAME` — 내 메일 주소 (보내기용 로그인 아이디)
- `UBISAM_SMTP_PASSWORD` — 메일 비밀번호
- `UBISAM_IMAP_USERNAME` — 보통 메일 주소와 동일
- `UBISAM_IMAP_PASSWORD` — 메일 비밀번호
- `UBISAM_DEFAULT_FROM` — 내 메일 주소 (보내는 사람)
- `UBISAM_DEFAULT_FROM_NAME` — 받는 사람에게 보일 내 이름

채우면 좋은 항목(선택):
- `UBISAM_ATTACHMENT_DOWNLOAD_DIR` — 받은 첨부를 저장할 폴더
- `UBISAM_CONTACTS_PATH` — 이름↔메일 자동 변환용 주소록 파일

나머지 호스트/포트 값(`ubisam.hanbiro.net`, SMTP 587 STARTTLS, IMAP 993 SSL 등)은 `.env.example`에 이미 권장값이 들어 있으니 그대로 두면 된다.

> `.env`에는 비밀번호가 들어간다. 다른 사람과 공유하거나 외부에 올리지 않는다.

---

## 4단계. AI 앱(MCP 클라이언트)에 연결

쓰는 AI 앱에 맞는 항목 하나를 따라 한다. 공통 규칙: MCP 서버를 실행하는 `command`와 설정 파일 경로 `UBISAM_ENV_FILE`을 AI 앱 설정에 넣는다.

Claude Desktop과 Codex Desktop은 같은 `command`와 `UBISAM_ENV_FILE` 값을 쓴다. 차이는 Claude Desktop은 JSON, Codex Desktop은 TOML 형식이라는 점뿐이다.

### Claude Desktop을 쓰는 경우

앱 메뉴 **Settings → Developer → Edit Config**로 설정 파일을 열고 아래를 넣는다:

```json
{
  "mcpServers": {
    "ubisam-mail": {
      "command": "ubisam-mail-mcp",
      "env": { "UBISAM_ENV_FILE": "/절대경로/ubisam-mail-mcp/.env" }
    }
  }
}
```

Windows PowerShell에 설치한 MCP를 Claude Desktop에 이미 붙였다면, 그 `command`와 `UBISAM_ENV_FILE` 값을 그대로 Codex Desktop에도 쓴다.

저장 후 **앱을 완전히 종료했다 다시 켠다**.

### Claude Code(터미널)를 쓰는 경우

```bash
claude mcp add ubisam-mail \
  --env UBISAM_ENV_FILE=/절대경로/ubisam-mail-mcp/.env \
  -- ubisam-mail-mcp
```

> 등록 후에는 Claude Code를 한 번 재시작해야 메일 기능이 대화에 나타난다.

### Codex Desktop을 쓰는 경우

Codex Desktop → **Settings → Configuration → Open config.toml**을 열거나, `~/.codex/config.toml`에 아래를 넣는다:

```toml
[mcp_servers.ubisam_mail]
command = "ubisam-mail-mcp"
env = { UBISAM_ENV_FILE = "/절대경로/ubisam-mail-mcp/.env" }
```

Windows에서 Claude Desktop 설정이 이미 이렇게 되어 있다면:

```json
"command": "C:\\Users\\YOUR_NAME\\ubisam-mail-mcp\\.venv\\Scripts\\ubisam-mail-mcp.exe",
"UBISAM_ENV_FILE": "C:\\Users\\YOUR_NAME\\ubisam-mail-mcp\\.env"
```

Codex는 같은 값을 TOML로 적는다:

```toml
[mcp_servers.ubisam_mail]
command = "C:\\Users\\YOUR_NAME\\ubisam-mail-mcp\\.venv\\Scripts\\ubisam-mail-mcp.exe"
env = { UBISAM_ENV_FILE = "C:\\Users\\YOUR_NAME\\ubisam-mail-mcp\\.env" }
```

자세한 클라이언트별 설명은 [README.md](../README.md)의 "MCP 클라이언트 설정" 참고.

---

## 5단계. 연결 확인

AI 앱을 새로 켠 뒤, 채팅창에 이렇게 말한다:

> **"내 메일 설정 상태 확인해줘."**

AI가 내부적으로 `config_status`를 호출하고, 다음을 보여준다:
- `smtp_ready: true` (보내기 준비됨)
- `imap_ready: true` (읽기 준비됨)
- `default_from_address`가 내 주소인지

둘 중 하나라도 `false`면 1~3단계(그룹웨어 활성화 / `.env` 값)를 다시 확인한다.

<details>
<summary>참고: AI가 내부적으로 부르는 형태</summary>

```text
config_status()
```
</details>

---

## 6단계. 사용 시작

여기서부터가 실제 사용이다. **한 번만 서명을 세팅**해 두면, 이후 메일은 서명이 자동으로 붙는다.

### 6-1. 메일 서명/인삿말 세팅 (한 번만)

이 MCP는 메일 끝부분을 4개 조각으로 관리한다:

| 조각 | 역할 | 만드는 기능 |
|------|------|-------------|
| 프로필(profile) | 이름·부서·연락처·로고 같은 **값 모음** | `create_signature_profile` |
| 인삿말(greeting) | 본문 **위** 인사 문구 | `create_greeting_template` |
| 맺음말(closing) | 본문 **아래** 마무리 문구 | `create_closing_template` |
| footer 서명(signature) | 맨 아래 연락처/로고 블록 | `create_signature(mode="closing_only")` |

> 인삿말·맺음말은 글자만 있으면 되므로 **텍스트만** 넣으면 된다(HTML은 자동 생성). 반면 footer 서명은 색상·로고 같은 스타일이 핵심이라 **HTML과 텍스트를 함께** 둔다. 그래서 예시 파일도 인삿말/맺음말은 텍스트만, footer는 둘 다 들어 있다.

먼저 복붙용 예시 파일 4개를 열어 **본인 정보로 수정**한다(특히 프로필):
- [signature-profile.example.json](examples/personal-setup/signature-profile.example.json) ← 이름/부서/연락처/로고
- [greeting-template.example.json](examples/personal-setup/greeting-template.example.json)
- [closing-template.example.json](examples/personal-setup/closing-template.example.json)
- [signature-template.example.json](examples/personal-setup/signature-template.example.json)
- 로고 이미지: [logo-color.png](examples/personal-setup/assets/logo-color.png)

> 예시 값은 익명화 샘플 `홍길동 / John Doe / 洪吉童` 기준이다.

**프로필에 꼭 채울 항목** (기본 footer가 이 값들을 사용한다):
`display_name`, `english_name`, `hanja_name`, `department`, `division_english`, `team`, `position`, `job_title_english`, `office_phone`, `mobile`, `email`, `logo_image_path`

> `hanja_name`, `division_english`, `job_title_english`를 비워 두면 footer에 ` / ` 같은 빈칸이 남는다. 안 쓰면 해당 칸을 템플릿에서 지워야 한다.

이제 AI에게 순서대로 부탁한다. **수정한 JSON 파일을 업로드하는 게 아니라**, 그 안의 값을 AI에게 알려주면 AI가 대신 등록한다.

> **"이 정보로 내 기본 서명 프로필 만들어줘. 이름 홍길동, 영문 John Doe, 한자 洪吉童, 부서 로봇자동화사업부, 팀 로봇팀, 직급 사원, 영문부서 Robot Automation, 영문직함 Software Engineer, 대표전화 02-1234-5678, 휴대폰 010-1234-5678, 이메일 hong.gildong@ubisam.com, 로고는 /절대경로/logo-color.png. 이걸 기본값으로 해줘."**

이어서:
> **"기본 인삿말 템플릿도 만들어줘. '안녕하십니까. 로봇자동화사업부 로봇팀 홍길동 사원입니다.' 형식으로."**
> **"기본 맺음말도 만들어줘. '확인 부탁드립니다. 감사합니다.'로."**
> **"기본 footer 서명도 만들어줘. 이름/영문명/한자명, 부서/영문부서/영문직함, 전화/휴대폰/이메일이 한 줄씩 나오게."**

구체적인 tool 호출 형태(복붙 가능)는 [personal-setup-tool-call-examples.md](personal-setup-tool-call-examples.md)에 정리돼 있다.

### 6-2. 미리보기로 확인

발송 전에 서명이 제대로 붙는지 본다:

> **"기본 서명 적용해서 미리보기 보여줘."**

AI가 `preview_signature`를 호출해 인삿말+본문+맺음말+footer 조합을 보여준다.

footer만 브라우저로 확인하고 싶으면:

> **"footer 서명만 HTML로 뽑아줘. /절대경로/downloads/sig-preview 폴더에 저장해줘."**

> 저장 위치(`export_dir`)는 **절대경로**로 말하는 게 안전하다. 상대경로로 하면 서버가 실행된 위치 기준으로 풀려서 엉뚱한 곳에 생길 수 있다.

확인 포인트: 인삿말이 위, 맺음말이 아래, footer에 이름/부서/연락처가 제대로 채워지는지, HTML 줄바꿈/폰트/색상 깨짐 없는지.

### 6-3. 첫 초안 만들고 발송

> **"someone@example.com 한테 'MCP 테스트 메일' 제목으로 초안 하나 만들어줘. 본문은 '테스트입니다.' 기본 서명 다 적용해서."**

AI가 `create_draft`로 초안을 만들고, 렌더링된 결과(`rendered_text_body` / `rendered_html_body`)를 보여준다.

내용을 확인한 뒤:

> **"좋아, 지금 보내줘."** → AI가 `send_draft_now`로 발송 (발송 전 한 번 확인을 거친다)
> **"내일 오전 9시에 예약 발송해줘."** → AI가 `schedule_draft`로 예약

> 서버가 켜져 있어야 예약 시간에 자동 발송된다. 꺼져 있었다면 다시 "밀린 예약 메일 보내줘"라고 하면 된다(`dispatch_due_messages`).

### 6-4. 메일 조회·검색

> **"안 읽은 메일 있어?"** → `get_unread_status`
> **"받은편지함 최근 메일 보여줘."** → `list_messages`
> **"제목에 '계약' 들어간 메일 찾아줘."** → `search_messages`

### 6-5. 메일 정리 (예: 주간보고 모으기)

보낸메일함에 흩어진 같은 주제 메일을 한 메일함에 모을 수 있다. **복사 방식이라 보낸메일함 원본은 그대로 남는다.**

> **"'주간보고'라는 메일함 만들고, 보낸메일함에서 제목에 '주간보고' 들어간 메일을 거기로 복사해줘."**

AI가 순서대로 처리한다:
1. `list_mailboxes` — 보낸메일함의 정확한 이름 확인
2. `create_mailbox("주간보고")` — 새 메일함 생성
3. `search_messages(subject_contains="주간보고")` — 대상 메일 찾기
4. `copy_messages(...)` — 원본 유지하며 새 메일함으로 복사

> 원본까지 옮겨서 보낸메일함을 비우고 싶으면 "복사 말고 이동해줘"라고 하면 `move_messages`를 쓴다. 단 이동은 보낸메일함에서 원본이 사라진다(되돌리기 번거로움).

---

## 자주 생기는 문제

**연결이 안 됨 / `imap_ready`나 `smtp_ready`가 false**
- 1단계(그룹웨어 SMTP/IMAP 활성화)를 안 했다
- `.env`의 아이디/비밀번호 오타
- `UBISAM_ENV_FILE` 절대경로가 틀림

**서명의 빈칸이 ` / `로 나옴**
- 프로필에 `hanja_name` / `division_english` / `job_title_english`를 안 채웠다
- 또는 프로필 키 이름과 템플릿 변수명이 다르다 (예: 프로필 `name`, 템플릿 `{{display_name}}`)

**로고가 안 나옴**
- `logo_image_path` 경로 오타 또는 서버가 그 파일에 접근 못 함
- footer 템플릿에 `{{company_logo_img}}`가 없음

**초안에 서명이 안 붙음**
- 템플릿을 기본값(`is_default=true`)으로 저장 안 했거나 "기본 서명 적용"을 안 함

**미리보기 파일이 어디 생겼는지 모르겠음**
- `export_dir`를 절대경로로 다시 지정한다

---

## 빠른 시작 체크리스트

1. 그룹웨어 SMTP/IMAP 활성화
2. `python3 --version`으로 3.10+ 확인
3. 압축 풀고 `pip install -e .`
4. `cp .env.example .env` 후 내 계정값 입력
5. AI 앱에 `UBISAM_ENV_FILE` 절대경로로 연결
6. AI 앱 재시작
7. "내 메일 설정 상태 확인해줘" → ready 확인
8. 기본 프로필 / 인삿말 / 맺음말 / footer 서명 만들기
9. "기본 서명 미리보기 보여줘"로 확인
10. "초안 만들어줘" → 확인 → "보내줘"

한 번 세팅하면 이후엔 말로만 시키면 된다.
