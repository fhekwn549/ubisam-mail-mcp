# ubisam-mail-mcp 개인 설정 튜토리얼

이 문서는 동료가 처음 `ubisam-mail-mcp`를 붙인 뒤 자기 계정과 개인 메일 템플릿을 세팅하는 순서를 설명한다.

목표:
- 계정 연결 확인
- 개인 인삿말 템플릿 저장
- 개인 맺음말 템플릿 저장
- 개인 footer 서명 저장
- 이름/부서/연락처/로고 프로필 저장
- 기본값 지정 후 초안 작성 시 자동 적용

복붙용 예시 파일:
- [greeting-template.example.json](/home/yourname/ubisam-mail-mcp/docs/examples/personal-setup/greeting-template.example.json)
- [closing-template.example.json](/home/yourname/ubisam-mail-mcp/docs/examples/personal-setup/closing-template.example.json)
- [signature-profile.example.json](/home/yourname/ubisam-mail-mcp/docs/examples/personal-setup/signature-profile.example.json)
- [signature-template.example.json](/home/yourname/ubisam-mail-mcp/docs/examples/personal-setup/signature-template.example.json)
- logo asset: [logo-color.png](/home/yourname/ubisam-mail-mcp/docs/examples/personal-setup/assets/logo-color.png)
- tool 호출 예문: [personal-setup-tool-call-examples.md](/home/yourname/ubisam-mail-mcp/docs/personal-setup-tool-call-examples.md)

이 예시 파일들은 현재 사용 중인 서명 레이아웃을 기준으로 익명화한 샘플이다.
- 한글 이름: `홍길동`
- 영문 이름: `John Doe`
- 한자 이름: `洪吉童`

## 1. 먼저 해야 할 것

사전 조건:
- 그룹웨어에서 `메일 -> 환경설정 -> SMTP-POP3-IMAP -> SMTP/IMAP` 사용 활성화
- 로컬에 이 레포 설치
- MCP 클라이언트에 `UBISAM_ENV_FILE` 설정 완료

`.env` 파일 예시:

```bash
cp .env.example .env
```

최소 수정 항목:
- `UBISAM_SMTP_USERNAME`
- `UBISAM_SMTP_PASSWORD`
- `UBISAM_IMAP_USERNAME`
- `UBISAM_IMAP_PASSWORD`
- `UBISAM_DEFAULT_FROM`
- `UBISAM_DEFAULT_FROM_NAME`

권장:
- `UBISAM_ATTACHMENT_DOWNLOAD_DIR`
- `UBISAM_CONTACTS_PATH`

확인 방법:
- MCP 연결 후 `config_status` 호출
- `smtp_ready=true`
- `imap_ready=true`
- `default_from_address`가 본인 주소인지 확인

## 2. 템플릿 구조 이해

이 MCP는 메일 끝부분을 4개 조각으로 나눈다.

1. `greeting template`
본문 위 인삿말.

2. `closing template`
본문 아래 맺음말 문구.

3. `signature profile`
이름, 부서, 직급, 연락처, 로고 같은 placeholder 값 모음.

4. `signature`
footer 서명 템플릿. 보통 `mode="closing_only"` 사용.

권장 조합:
- 인삿말: `create_greeting_template`
- 맺음말: `create_closing_template`
- 프로필: `create_signature_profile`
- footer: `create_signature(mode="closing_only")`

추천 작업 순서:
1. 예시 JSON 파일 4개를 열어 본인 정보로 수정
2. `signature-profile.example.json`의 `logo_image_path`를 실제 로컬 경로로 수정
3. 수정한 JSON 내용을 MCP tool 인자로 사용
4. `preview_signature`, `preview_closing_signature`로 검증
5. 이상 없으면 기본값으로 사용

## 3. 제일 먼저 프로필 만들기

프로필은 템플릿이 참조할 실제 값 저장소다. 보통 이것부터 만든다.

사용 파일:
- [signature-profile.example.json](/home/yourname/ubisam-mail-mcp/docs/examples/personal-setup/signature-profile.example.json)

호출:

```text
create_signature_profile(...)
```

메모:
- `fields` 키 이름은 자유다.
- 템플릿에서 `{{display_name}}`, `{{department}}`처럼 그대로 참조한다.
- `logo_image_path`는 선택이다.
- `is_default=true`면 초안 작성 시 기본 프로필로 자동 적용된다.
- 최소 수정 권장 항목은 `display_name`, `english_name`, `department`, `team`, `position`, `office_phone`, `mobile`, `email`, `logo_image_path`다.

## 4. 인삿말 템플릿 만들기

사용 파일:
- [greeting-template.example.json](/home/yourname/ubisam-mail-mcp/docs/examples/personal-setup/greeting-template.example.json)

호출:

```text
create_greeting_template(...)
```

메모:
- `text_template`, `html_template` 둘 중 하나는 필수다.
- HTML을 직접 넣지 않으면 text 기반으로 렌더링된다.
- 기본 인삿말 하나만 둘 거면 `is_default=true` 권장.
- 현재 예시는 `{{department}} {{team}} {{display_name}} {{position}}` 형식이다.
- 팀명을 빼고 싶으면 `{{team}}` 부분만 지우면 된다.

## 5. 맺음말 템플릿 만들기

사용 파일:
- [closing-template.example.json](/home/yourname/ubisam-mail-mcp/docs/examples/personal-setup/closing-template.example.json)

호출:

```text
create_closing_template(...)
```

메모:
- 이 블록은 본문 뒤, footer 위에 들어간다.
- `{{display_name}}` 같은 프로필 placeholder도 사용 가능하다.

## 6. footer 서명 만들기

일반 권장값은 `mode="closing_only"`다.

사용 파일:
- [signature-template.example.json](/home/yourname/ubisam-mail-mcp/docs/examples/personal-setup/signature-template.example.json)
- logo asset 예시: [logo-color.png](/home/yourname/ubisam-mail-mcp/docs/examples/personal-setup/assets/logo-color.png)

호출:

```text
create_signature(...)
```

메모:
- `{{company_logo_img}}`는 프로필의 `logo_image_path`가 있을 때만 렌더링된다.
- 회사 메일 서명처럼 스타일이 중요하면 `html_template`에 inline style 권장.
- 한글 폰트는 `Malgun Gothic` 사용.
- `wrap_body` 모드는 예전 전체 감싸기 방식이다. 이 튜토리얼은 `closing_only` 기준이다.
- 현재 예시는 `이름 / 영문명 / 한자명`, `부서 / 영문 부서명 / 영문 직함`, `대표전화 / 휴대전화 / 이메일`을 한 줄씩 노출한다.

## 7. 미리보기로 검증

메일 보내기 전 반드시 `preview_signature`로 확인한다.

예시:

```json
{
  "text_body": "본문 테스트입니다.",
  "html_body": "<p>본문 테스트입니다.</p>",
  "apply_default_greeting_template": true,
  "apply_default_closing_template": true,
  "apply_default_signature": true,
  "apply_default_signature_profile": true
}
```

호출:

```text
preview_signature(...)
```

확인 포인트:
- 인삿말이 본문 위에 붙는지
- 맺음말이 본문 아래에 붙는지
- footer에 이름/부서/연락처가 치환되는지
- HTML에서 줄바꿈/폰트/색상 깨짐 없는지

footer만 따로 보고 싶으면:

```json
{
  "export_dir": "downloads/signature-preview-kim-minjun",
  "apply_default_signature": true,
  "apply_default_signature_profile": true
}
```

호출:

```text
preview_closing_signature(...)
```

결과:
- `signature-preview.html`
- 로고 asset 복사본

브라우저로 열어서 회사 서명처럼 보이는지 확인한다.

권장:
- 예시 파일 4개를 저장한 직후 바로 `preview_signature`
- logo 경로 수정 후 `preview_closing_signature(export_dir="...")`
- 줄간격, 폰트, 로고 높이까지 확인

## 8. 첫 초안 만들기

기본 템플릿들을 모두 `is_default=true`로 저장했다면 초안 작성 때 별도 ID를 안 넣어도 된다.

예시:

```json
{
  "subject": "MCP 테스트 메일",
  "to": ["someone@example.com"],
  "text_body": "본문 초안입니다.",
  "html_body": "<p>본문 초안입니다.</p>",
  "apply_default_greeting_template": true,
  "apply_default_closing_template": true,
  "apply_default_signature": true,
  "apply_default_signature_profile": true
}
```

호출:

```text
create_draft(...)
```

이후 확인:
- `get_draft(draft_id=...)`
- 응답의 `rendered_text_body`, `rendered_html_body` 확인

## 9. 특정 메일만 다른 톤 쓰기

기본값은 유지하고 특정 메일에서만 다른 템플릿을 쓰면 된다.

방법:
- `list_greeting_templates`, `list_closing_templates`, `list_signature_profiles`, `list_signatures`로 ID 조회
- `create_draft` 또는 `update_draft`에 원하는 `*_id` 직접 지정

예시:
- 대외 메일: 정중한 인삿말 템플릿 사용
- 내부 메일: 짧은 인삿말 템플릿 사용
- 영문 메일: 영문 프로필 + 영문 footer 사용

기본값 해제/재적용:
- `update_draft(clear_greeting_template=true)`
- `update_draft(clear_closing_template=true)`
- `update_draft(clear_signature=true)`
- `update_draft(clear_signature_profile=true)`
- `update_draft(apply_default_signature=true)`

## 10. 자주 생기는 실수

`placeholder`가 빈칸으로 나옴:
- 프로필 `fields` 키와 템플릿 변수명이 다름
- 예: 프로필은 `name`, 템플릿은 `{{display_name}}`

로고가 안 나옴:
- `logo_image_path` 오타
- MCP 서버가 그 파일 경로에 접근 못 함
- HTML 템플릿에 `{{company_logo_img}}` 없음

초안에 서명이 안 붙음:
- 기본값으로 저장 안 했거나 `apply_default_*`를 껐음
- `signature`를 `closing_only`로 만들지 않았음

`wrap_body` 생성 오류:
- `mode="wrap_body"`에서는 `{{body}}` placeholder 필수

발신자 이름이 예상과 다름:
- 우선순위는 `create_draft/from_name` 직접값 -> 프로필의 `display_name` -> `.env`의 `UBISAM_DEFAULT_FROM_NAME`

## 11. 팀 권장 운영 방식

개인별로 최소 4개 기본 리소스 보유 권장:
- 기본 인삿말 1개
- 기본 맺음말 1개
- 기본 프로필 1개
- 기본 footer 1개

추가로 있으면 좋은 것:
- 외부 발송용 정중 버전
- 내부 공유용 짧은 버전
- 영문 버전

팀 공통 룰 권장:
- 프로필 key 이름 통일
- HTML 서명 폰트 통일
- 로고 파일 경로 저장 위치 통일
- `preview_signature` 확인 후 발송

## 12. 빠른 시작 체크리스트

1. `.env` 작성
2. MCP 클라이언트에 `UBISAM_ENV_FILE` 연결
3. `config_status`로 연결 확인
4. `create_signature_profile(is_default=true)`
5. `create_greeting_template(is_default=true)`
6. `create_closing_template(is_default=true)`
7. `create_signature(mode=\"closing_only\", is_default=true)`
8. `preview_signature`
9. `preview_closing_signature(export_dir=\"...\")`
10. `create_draft`
11. `get_draft`로 최종 확인

이 순서로 한 번만 세팅하면 이후 초안 작성에서 기본값 자동 적용된다.
