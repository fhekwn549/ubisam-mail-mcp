# ubisam-mail-mcp 배포 전 체크리스트

목표: 배포물에 개인 정보가 섞이지 않고, 새 노트북에서 Claude/Codex MCP 연결까지 재현되는지 확인한다.

## 1. 배포 전 로컬 품질 확인

- [ ] 작업트리 확인: 의도한 변경만 남아 있는지 확인

  ```bash
  git status --short
  ```

- [ ] 개인/민감 파일 제외 확인

  ```bash
  git status --ignored --short .env data downloads .venv .pytest_cache
  ```

  통과 기준:
  - `.env`는 추적되지 않는다.
  - `data/*.local.json`은 추적되지 않는다.
  - `downloads/`는 추적되지 않는다.
  - `.venv/`, `.pytest_cache/`, `*.egg-info/`는 추적되지 않는다.

- [ ] 전체 테스트 통과

  ```bash
  python3 -m pip install -e . pytest
  python3 -m pytest
  ```

- [ ] 실행 진입점 확인

  ```bash
  python3 -c "import ubisam_mail_mcp.server; print('server import ok')"
  command -v ubisam-mail-mcp
  command -v ubisam-mail-mcp-setup
  ```

  통과 기준:
  - `server import ok` 출력
  - `ubisam-mail-mcp` 경로 출력
  - `ubisam-mail-mcp-setup` 경로 출력

- [ ] README 설치 절차가 현재 코드와 맞는지 확인

  확인 위치:
  - [README.md](../README.md)
  - [docs/personal-setup-tutorial.md](personal-setup-tutorial.md)
  - [docs/personal-setup-tool-call-examples.md](personal-setup-tool-call-examples.md)

## 2. 배포물 구성 확인

- [ ] 포함 파일
  - `README.md`
  - `pyproject.toml`
  - `src/`
  - `scripts/`
  - `tests/`
  - `docs/`
  - `.env.example`
  - `.gitignore`

- [ ] 제외 파일
  - `.env`
  - `.venv/`
  - `.pytest_cache/`
  - `*.egg-info/`
  - `data/*.local.json`
  - `downloads/`
  - 실제 메일 첨부
  - 실제 주소록
  - 개인 DB 파일(`UBISAM_MAIL_MCP_DB`)

- [ ] zip 배포물 생성 시 커밋 후 `git archive` 사용

  ```bash
  git archive --format=zip --output ../ubisam-mail-mcp.zip HEAD
  unzip -l ../ubisam-mail-mcp.zip | grep -E '(^|/)(\.env|\.venv|downloads|contacts\.local|mail\.db|egg-info)'
  ```

  통과 기준: 두 번째 명령 출력 없음. `grep` 종료코드 `1`은 매칭 없음이므로 이 항목에서는 정상이다.

## 3. 새 노트북 제로베이스 설치 테스트

테스트 대상: 배포물을 처음 받는 사용자 PC. 기존 repo, venv, MCP 설정 없다고 가정.

- [ ] Python 3.10+ 확인

  ```bash
  python3 --version
  ```

- [ ] 배포물 해제 후 설치

  ```bash
  unzip ubisam-mail-mcp.zip
  cd ubisam-mail-mcp
  python3 -m venv .venv
  source .venv/bin/activate
  python3 -m pip install --upgrade pip
  python3 -m pip install -e .
  ```

  Windows PowerShell:

  ```powershell
  py -3 --version
  py -3 -m venv .venv
  .venv\Scripts\Activate.ps1
  python -m pip install --upgrade pip
  python -m pip install -e .
  ```

- [ ] setup wizard로 `.env` 생성

  ```bash
  ubisam-mail-mcp-setup --web-setup
  ```

  브라우저가 자동으로 열리지 않으면 터미널에 나온 로컬 URL을 직접 연다.

  통과 기준:
  - 사전 준비 화면에는 그룹웨어 SMTP/IMAP 활성화 안내 이미지가 표시됨
  - 확인 체크박스를 켜야 다음 버튼 활성화
  - 계정 화면에는 메일 주소/비밀번호/그룹웨어 내 본인 이름만 표시
  - 비밀번호 보기/숨기기 토글 동작
  - IMAP/SMTP 검증 성공 후 서식 화면으로 이동
  - 한자 이름은 체크박스를 켠 경우에만 입력 가능
  - SMTP/IMAP host/port, DB 경로, 다운로드 폴더는 기본 화면에 노출되지 않음

  GUI 팝업에서 서식을 실시간 확인하며 입력하려면:

  ```bash
  ubisam-mail-mcp-setup --signature-gui
  ```

  여러 줄 인삿말/맺음말을 에디터에서 편집하려면:

  ```bash
  ubisam-mail-mcp-setup --edit-templates
  ```

  wizard 입력값:
  - `UBISAM_SMTP_USERNAME`
  - `UBISAM_SMTP_PASSWORD`
  - `UBISAM_IMAP_USERNAME`
  - `UBISAM_IMAP_PASSWORD`
  - `UBISAM_DEFAULT_FROM`
  - `UBISAM_DEFAULT_FROM_NAME`
  - 기본 서식 프로필 값(선택, 건너뛰기 가능)

  수동 생성이 필요하면:

  ```bash
  cp .env.example .env
  ```

- [ ] 그룹웨어 설정 확인
  - 그룹웨어 웹 로그인
  - `메일 -> 환경설정 -> SMTP-POP3-IMAP -> SMTP/IMAP`
  - SMTP/IMAP 사용 활성화

- [ ] IMAP/SMTP 계정 로그인 probe

  ```bash
  python3 scripts/check_imap.py \
    --host ubisam.hanbiro.net \
    --username "user@ubisam.com" \
    --mode ssl
  ```

  ```bash
  python3 scripts/check_smtp.py \
    --host ubisam.hanbiro.net \
    --username "user@ubisam.com" \
    --mode starttls
  ```

  통과 기준:
  - IMAP `993/SSL login succeeded`
  - SMTP `587/STARTTLS login succeeded`

## 4. Claude Code 연결 테스트

- [ ] 가상환경 진입점 절대경로 확인

  ```bash
  pwd
  which ubisam-mail-mcp
  ```

- [ ] Claude Code MCP 등록

  ```bash
  claude mcp add ubisam-mail \
    --env UBISAM_ENV_FILE=/absolute/path/to/ubisam-mail-mcp/.env \
    -- /absolute/path/to/ubisam-mail-mcp/.venv/bin/ubisam-mail-mcp
  ```

- [ ] 등록 확인

  ```bash
  claude mcp list
  ```

- [ ] Claude Code 재시작 후 채팅에서 확인

  ```text
  내 메일 설정 상태 확인해줘.
  ```

  통과 기준:
  - `config_status` 호출됨
  - `smtp_ready: true`
  - `imap_ready: true`
  - `default_from_address`가 본인 메일

## 5. Codex 연결 테스트

- [ ] `~/.codex/config.toml`에 서버 추가

  ```toml
  [mcp_servers.ubisam_mail]
  command = "/absolute/path/to/ubisam-mail-mcp/.venv/bin/ubisam-mail-mcp"
  env = { UBISAM_ENV_FILE = "/absolute/path/to/ubisam-mail-mcp/.env" }
  ```

- [ ] Codex 재시작 후 MCP tool 노출 확인

  채팅 요청:

  ```text
  내 메일 설정 상태 확인해줘.
  ```

  통과 기준:
  - `config_status` 호출 가능
  - `smtp_ready: true`
  - `imap_ready: true`

## 6. 실제 기능 smoke test

테스트 계정에서 진행. 실사용 메일함을 망가뜨리지 않도록 처음에는 조회/초안/미리보기 위주로 확인한다.

- [ ] 메일함 목록 조회

  ```text
  내 메일함 목록 보여줘.
  ```

  통과 기준: `list_mailboxes` 결과가 보임.

- [ ] 안 읽은 메일 상태 조회

  ```text
  안 읽은 메일 있어?
  ```

  통과 기준: `get_unread_status` 결과가 보임.

- [ ] 최근 메일 조회

  ```text
  받은편지함 최근 메일 3개만 보여줘.
  ```

  통과 기준: `list_messages(limit=3)` 결과가 보임.

- [ ] 서명 프로필/템플릿 생성

  [docs/personal-setup-tutorial.md](personal-setup-tutorial.md)의 `6-1` 순서대로 진행.

- [ ] 전체 서명 미리보기

  ```text
  기본 서명 적용해서 미리보기 보여줘.
  ```

  통과 기준:
  - 인삿말 표시
  - 본문 표시
  - 맺음말 표시
  - footer 서명 placeholder 치환
  - 로고 이미지 경로가 있으면 inline 이미지 처리

- [ ] 초안 생성

  ```text
  내 메일 주소로 'MCP 테스트 초안' 제목의 초안을 만들어줘. 본문은 '제로베이스 설치 테스트입니다.' 기본 서명 적용해줘. 아직 보내지 마.
  ```

  통과 기준:
  - `create_draft` 성공
  - `get_draft`에서 렌더링된 본문 확인 가능

- [ ] IMAP 임시보관 업로드

  ```text
  방금 만든 초안을 임시보관함에 업로드해줘.
  ```

  통과 기준:
  - `upload_draft_to_imap` 성공
  - 웹메일 임시보관함에서 확인 가능

- [ ] 실제 발송 테스트

  ```text
  방금 초안을 내 메일 주소로 보내줘.
  ```

  통과 기준:
  - agent가 사용자 확인을 받고 `send_draft_now` 호출
  - 본인 수신함에서 메일 수신 확인
  - 첨부 없는 기본 메일 정상 표시

- [ ] 예약 발송 테스트

  ```text
  새 테스트 초안을 만들고 2분 뒤로 예약해줘.
  ```

  통과 기준:
  - `schedule_draft` 성공
  - 서버가 켜진 상태에서 예약 시간이 지나면 발송
  - 서버가 꺼졌던 경우 재시작 후 `밀린 예약 메일 보내줘`로 `dispatch_due_messages` 성공

## 7. 실패 시 확인 순서

- [ ] `config_status`가 `false`
  - `.env` 절대경로가 맞는지 확인
  - Claude/Codex 설정의 `UBISAM_ENV_FILE` 확인
  - 프로세스 환경변수가 `.env`보다 우선하는 점 확인

- [ ] IMAP/SMTP 로그인 실패
  - 그룹웨어 SMTP/IMAP 활성화 확인
  - 비밀번호 확인
  - 회사망/VPN/방화벽 확인
  - `scripts/check_imap.py`, `scripts/check_smtp.py`로 직접 probe

- [ ] MCP 서버 실행 실패
  - `command`를 절대경로로 지정
  - `python3 -m pip install -e .` 재실행
  - `which ubisam-mail-mcp` 결과 확인

- [ ] 첨부/로고 실패
  - 파일 경로를 절대경로로 지정
  - MCP 서버가 실행되는 PC에서 접근 가능한 경로인지 확인

## 8. 배포 승인 기준

배포 가능 조건:

- [ ] 로컬 테스트 전체 통과
- [ ] 새 노트북 설치 테스트 통과
- [ ] Claude Code 연결 통과
- [ ] Codex 연결 통과
- [ ] 조회/초안/미리보기 smoke test 통과
- [ ] 실제 발송 테스트 통과
- [ ] zip 안에 `.env`, `downloads/`, `data/*.local.json`, DB 없음
- [ ] README와 튜토리얼 기준으로 초보자가 따라 할 수 있음
