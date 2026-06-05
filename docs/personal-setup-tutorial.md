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

## 큰 그림 (5단계)

1. 프로그램 설치 (Python + 이 레포)
2. setup wizard 실행 (외부 메일 활성화 안내, 계정 검증, 기본 서명 설정)
3. AI 앱(MCP 클라이언트)에 연결
4. 연결 확인
5. 사용 시작 (메일 조회 → 초안 → 발송 → 메일 정리)

각 단계를 아래에서 하나씩 따라가면 된다. **순서대로** 하는 게 중요하다.

---

## 1단계. 프로그램 설치

### 1-0. 원클릭 설치 (권장)

레포를 clone 한 뒤, **자기 환경에 맞는 스크립트 하나만** 실행하면 Python 탐색·`.venv` 생성·설치·setup wizard(`--web-setup`)까지 한 번에 끝난다. (즉 아래 1-1~1-2와 2단계를 자동 처리)

Claude Desktop·Codex Desktop 같은 **Windows 데스크톱 앱**:

```powershell
git clone https://github.com/fhekwn549/ubisam-mail-mcp.git
cd ubisam-mail-mcp
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

Claude Code·Codex CLI 같은 **Ubuntu/WSL 터미널**:

```bash
git clone https://github.com/fhekwn549/ubisam-mail-mcp.git
cd ubisam-mail-mcp
bash scripts/setup.sh
```

- 스크립트는 Python 3.10+를 자동으로 찾고, 없으면 설치 명령을 안내한다.
- Git이 없으면 먼저 설치한다: Windows `winget install Git.Git` / Ubuntu `sudo apt install -y git`.
- 스크립트가 막히거나 단계를 직접 보고 싶으면 아래 수동 절차(1-1~2단계)를 따른다.

### 1-1. Python 3.10 이상 확인

터미널(Windows는 PowerShell, Mac은 터미널 앱)을 열고:

```bash
python3 --version
```

- `Python 3.10.x` 이상이 나오면 통과.
- 안 나오거나 3.10 미만이면 [python.org](https://www.python.org/downloads/)에서 Python 3.10 이상을 먼저 설치한다.
- Python이 아예 없는 PC는 Python 3.12 또는 3.13 설치를 권장한다. 너무 최신 버전이 부담되면 3.12가 보수적 선택이다.
- Windows에서 여러 버전이 설치돼 있으면 PowerShell에서 `py --list`로 확인한다.

### 1-2. 레포 clone / 설치

Claude Desktop이나 Codex Desktop 같은 **Windows 데스크톱 앱**에 붙일 PC라면 PowerShell에서 설치한다:

```powershell
git clone https://github.com/fhekwn549/ubisam-mail-mcp.git
cd ubisam-mail-mcp
py --list
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
python -m pip install -e .
```

Git이나 Python이 없으면 먼저 설치한다:

```powershell
winget install Git.Git
winget install Python.Python.3.12
```

Claude Code나 Codex CLI처럼 **Ubuntu/WSL 터미널**에서 쓸 PC라면 Ubuntu 안에 설치한다:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
git clone https://github.com/fhekwn549/ubisam-mail-mcp.git
cd ubisam-mail-mcp
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

`pip install -e .`가 끝나면 `ubisam-mail-mcp`라는 실행 명령이 생긴다. 이게 AI와 메일을 잇는 서버다.

> 필요한 Python은 3.10 이상이다(3.11, 3.12 등 모두 가능). `py -3`는 설치된 최신 3.x를 잡는다.
> `python --version`으로 3.10 이상인지 확인하고, 최신이 3.10 미만이면 `py -3.12`처럼 버전을 명시해서 만든다.
> 가상환경 활성화는 `source .venv/bin/activate` 대신 `.venv\Scripts\Activate.ps1`.
> `.venv`는 Python 버전을 올려주지 않는다. 기존 `.venv`를 3.9 이하로 만들었다면 삭제 후 새 Python으로 다시 만든다.

Windows PowerShell 예시:

```powershell
py --list
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
python -m pip install -e .
```

기존 `.venv`를 다시 만들 때:

```powershell
Remove-Item -Recurse -Force .venv
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

---

## 2단계. setup wizard 실행

setup wizard가 외부 메일 활성화 안내, 계정 입력, IMAP/SMTP 검증, `.env` 생성, 기본 인삿말/맺음말/footer 서명 설정까지 처리한다. 화면 안내대로 진행하면 된다.

> 1-0의 원클릭 스크립트를 실행했다면 wizard가 이미 떠 있으니 이 단계는 건너뛴다. 수동으로 따로 실행할 때만 아래를 쓴다.

Windows PowerShell:

```powershell
python -m ubisam_mail_mcp.setup_wizard --web-setup
```

Ubuntu/WSL:

```bash
source .venv/bin/activate
ubisam-mail-mcp-setup --web-setup
```

완료 화면에 Claude/Codex에 붙여 넣을 설정 예시가 나온다. 여기서 `command`와 `UBISAM_ENV_FILE` 경로를 다음 단계에 사용한다.

> `.env`에는 비밀번호가 들어간다. 다른 사람과 공유하거나 외부에 올리지 않는다.
> 인삿말·맺음말·서명·초안 같은 데이터는 프로젝트 폴더 안 `data/mail.db`(로컬 SQLite)에 저장된다. `.env`와 함께 백업하면 설정이 보존된다.

---

## 3단계. AI 앱(MCP 클라이언트)에 연결

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

### Codex Desktop/CLI를 쓰는 경우

Codex Desktop과 Codex CLI는 같은 `~/.codex/config.toml`을 공유한다. Codex Desktop은 **Settings → Configuration → Open config.toml**로 열고, Codex CLI는 `~/.codex/config.toml`을 직접 편집해 아래를 넣는다(둘 다 내용 동일):

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

완료 화면의 설정 예시를 우선 사용하고, 전체 프로젝트 정보는 [README.md](../README.md)를 참고한다.

---

## 4단계. 연결 확인

AI 앱을 새로 켠 뒤, 채팅창에 이렇게 말한다:

> **"내 메일 설정 상태 확인해줘."**

AI가 내부적으로 `config_status`를 호출하고, 다음을 보여준다:
- `smtp_ready: true` (보내기 준비됨)
- `imap_ready: true` (읽기 준비됨)
- `default_from_address`가 내 주소인지

둘 중 하나라도 `false`면 setup wizard를 다시 실행해 외부 메일 활성화, 계정/비밀번호, `UBISAM_ENV_FILE` 절대경로를 확인한다.

<details>
<summary>참고: AI가 내부적으로 부르는 형태</summary>

```text
config_status()
```
</details>

---

## 5단계. 사용 시작

setup wizard에서 계정과 기본 서명 설정을 마쳤으면, 이후에는 AI에게 평소 말하듯 요청하면 된다. wizard가 기본 프로필·인삿말·맺음말·footer 서명까지 자동으로 만들어 두므로, 바로 초안 작성부터 시작할 수 있다.

실제로 어떤 말이 어떤 tool 호출로 이어지는지는 짝꿍 문서에 예문으로 정리해 두었다.

➡ **[personal-setup-tool-call-examples.md](personal-setup-tool-call-examples.md)** — 자연어 요청 ↔ tool 호출 예문 모음

이 문서에 기본값 확인, 미리보기, 첫 초안 작성·발송·예약, 메일 조회·검색, 메일 정리, 기본값 수정까지 단계별 예문이 들어 있다.

---

## 자주 생기는 문제

**연결이 안 됨 / `imap_ready`나 `smtp_ready`가 false**
- setup wizard에서 안내한 그룹웨어 SMTP/IMAP 활성화를 완료했는지 확인한다
- wizard를 다시 실행해 계정/비밀번호를 재입력한다
- AI 앱 설정의 `UBISAM_ENV_FILE` 절대경로가 setup 완료 화면의 값과 같은지 확인한다

**도구가 안 보임**
- AI 앱을 완전히 종료한 뒤 다시 켠다
- `command` 경로가 setup 완료 화면의 값과 같은지 확인한다

---

## 빠른 시작 체크리스트

1. Python 3.10+ 확인
2. `git clone` 후 `pip install -e .`
3. setup wizard 실행
4. wizard 완료 화면의 Claude/Codex 설정을 AI 앱에 붙여넣기
5. AI 앱 재시작
6. "내 메일 설정 상태 확인해줘" → ready 확인
7. "초안 만들어줘" → 확인 → "보내줘"

한 번 세팅하면 이후엔 말로만 시키면 된다.
