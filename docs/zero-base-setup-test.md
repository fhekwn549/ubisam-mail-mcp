# ubisam-mail-mcp 제로베이스 설치 테스트

목표: 새 폴더나 다른 노트북에서 처음 받는 사용자 기준으로 setup wizard, Claude/Codex MCP 연결, 기본 메일 기능을 확인한다.

## 1. 깨끗한 폴더에서 설치

```bash
git clone https://github.com/fhekwn549/ubisam-mail-mcp.git ubisam-mail-mcp-fresh
cd ubisam-mail-mcp-fresh
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

통과 기준:
- Python `3.10` 이상
- `command -v ubisam-mail-mcp` 경로 출력
- `command -v ubisam-mail-mcp-setup` 경로 출력

## 2. setup wizard 실행

로컬 웹페이지에서 계정/서식 설정:

```bash
ubisam-mail-mcp-setup --web-setup
```

브라우저가 자동으로 열리지 않으면 터미널에 나온 `http://127.0.0.1:8765/` 주소를 직접 연다.

웹 setup 흐름:
1. 그룹웨어 SMTP/IMAP 활성화 안내 이미지 확인
2. `그룹웨어에서 SMTP/IMAP 사용을 활성화하고 저장했습니다.` 체크 후 다음
3. 메일 주소, 메일 비밀번호, 그룹웨어 내 본인 이름 입력
4. IMAP/SMTP 계정 검증
5. 검증 성공 후 서식 입력 화면으로 이동
6. 실제 HTML 메일 양식에 가까운 서식 미리보기 확인 후 저장

GUI 팝업에서 기본 서식까지 설정:

```bash
ubisam-mail-mcp-setup --signature-gui
```

터미널 에디터에서 여러 줄 인삿말/맺음말을 편집:

```bash
ubisam-mail-mcp-setup --edit-templates
```

서식 없이 계정 연결만 확인:

```bash
ubisam-mail-mcp-setup --skip-signature-setup
```

입력값:
- 메일 주소
- 메일 비밀번호
- 그룹웨어 내 본인 이름
- 서명 프로필 값
- 인삿말/맺음말 여러 줄 텍스트

화면 동작:
- 비밀번호는 `보기/숨기기` 토글로 확인 가능
- 한자 이름은 체크박스를 켠 경우에만 입력
- SMTP/IMAP host/port, DB 경로, 다운로드 폴더는 기본값으로 숨김 처리
- footer에는 기본 회사 로고가 자동으로 들어감
- setup을 다시 실행하면 기존 메일 주소/이름/서식 값은 채워지고 비밀번호만 다시 입력

통과 기준:
- `.env` 생성
- IMAP 로그인 `OK`
- SMTP 로그인 `OK`
- 기본 서식 저장 완료
- `downloads/setup-preview/signature-preview.html` 생성
- 완료 페이지에 Claude/Codex 설정 예시 출력
- 설정 예시에 `UBISAM_ENV_FILE` 절대경로 포함

## 3. Claude Code 연결

```bash
claude mcp add ubisam-mail \
  --env UBISAM_ENV_FILE=/absolute/path/to/ubisam-mail-mcp-fresh/.env \
  -- /absolute/path/to/ubisam-mail-mcp-fresh/.venv/bin/ubisam-mail-mcp
claude mcp list
```

Claude Code 재시작 후 요청:

```text
내 메일 설정 상태 확인해줘.
```

통과 기준:
- `config_status` 호출
- `smtp_ready: true`
- `imap_ready: true`
- `default_from_address`가 본인 메일

## 4. Codex 연결

`~/.codex/config.toml`:

```toml
[mcp_servers.ubisam_mail]
command = "/absolute/path/to/ubisam-mail-mcp-fresh/.venv/bin/ubisam-mail-mcp"
env = { UBISAM_ENV_FILE = "/absolute/path/to/ubisam-mail-mcp-fresh/.env" }
```

Codex 재시작 후 요청:

```text
내 메일 설정 상태 확인해줘.
```

통과 기준:
- `config_status` 호출
- `smtp_ready: true`
- `imap_ready: true`

## 5. 기능 smoke test

조회:

```text
내 메일함 목록 보여줘.
안 읽은 메일 있어?
받은편지함 최근 메일 3개만 보여줘.
```

초안:

```text
내 메일 주소로 'MCP 테스트 초안' 제목의 초안을 만들어줘. 본문은 '제로베이스 설치 테스트입니다.' 기본 서명 적용해줘. 아직 보내지 마.
```

미리보기:

```text
기본 서명 적용해서 미리보기 보여줘.
```

발송:

```text
방금 초안을 내 메일 주소로 보내줘.
```

통과 기준:
- 메일함 목록 조회 성공
- 안 읽은 메일 상태 조회 성공
- 최근 메일 조회 성공
- 초안 생성 성공
- 기본 인삿말/맺음말/footer 표시
- 사용자 승인 후 실제 발송 성공
- 본인 수신함에서 테스트 메일 확인

## 6. 실패 시 확인

- `ubisam-mail-mcp-setup` 없음: `python3 -m pip install -e .` 재실행
- IMAP/SMTP 실패: 그룹웨어 `SMTP/IMAP 사용` 활성화 확인
- Claude/Codex에서 tool 없음: 앱 재시작, command 절대경로 확인
- `smtp_ready`/`imap_ready` false: `UBISAM_ENV_FILE` 절대경로 확인
- 서명 이미지 실패: `logo_image_path`를 절대경로로 입력
