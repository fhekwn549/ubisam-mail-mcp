# ubisam-mail-mcp 자연어 요청 ↔ Tool 호출 예문

이 문서는 [personal-setup-tutorial.md](personal-setup-tutorial.md)의 짝꿍 문서다.

- **왼쪽("이렇게 말하세요")**: AI 채팅창에 평소처럼 한국어로 부탁하는 문장.
- **오른쪽(코드 블록)**: 그 부탁을 받은 AI가 내부적으로 호출하는 실제 tool 형태.

당신은 보통 **왼쪽만** 쓰면 된다. 코드 블록은 "AI가 뭘 하는지" 확인하거나, 값을 정확히 지정하고 싶을 때 참고한다.

> **중요(wizard 패치 반영):** setup wizard(`--web-setup`)가 이미 **기본 프로필 / 기본 인삿말 / 기본 맺음말 / 기본 footer 서명**을 `is_default=true`로 자동 생성한다. 그래서 아래 예문은 "처음부터 만들기"가 아니라 **wizard가 만든 기본값을 확인하고 → 미리보기·초안·발송에 쓰고 → 필요하면 수정**하는 흐름이다. 직접 새로 만드는 호출은 맨 끝 "기본값 직접 손보기"에 모았다.

검증 상태:
- 문서 갱신: `2026-06-05` — wizard 자동 생성 반영
- tool 호출 형태(파라미터)는 현재 `server.py` 시그니처와 일치 확인
- 스모크 검증 범위(`2026-06-02`, 임시 DB/임시 다운로드 경로): `config_status`, `create_signature_profile`, `create_greeting_template`, `create_closing_template`, `create_signature`, `preview_signature`, `preview_closing_signature`, `create_draft`, `get_draft` — wizard도 이 service 메서드를 그대로 호출
- 제외: 실제 SMTP 발송, 실제 IMAP 업로드, 실계정 수신 확인

전제:
- 예시 값은 익명화 샘플 `홍길동 / John Doe / 洪吉童` 기준
- 프로필의 `logo_image_path`는 본인 PC의 **절대경로**로 바꿔서 말한다

---

## 0. 연결 확인

> 이렇게 말하세요: **"내 메일 설정 상태 확인해줘."**

```text
config_status()
```

응답에서 `smtp_ready`, `imap_ready`, `default_from_address` 확인.

---

## 1. wizard가 만든 기본값 확인

setup wizard가 자동으로 만들어 둔 기본 구성(모두 `is_default=true`)을 먼저 본다.

> 이렇게 말하세요: **"내 기본 서명 구성 보여줘. 프로필·인삿말·맺음말·footer 다."**

AI가 순서대로 호출한다:

```text
list_signature_profiles()    # "홍길동 기본 프로필"
list_greeting_templates()    # "기본 인삿말"
list_closing_templates()     # "기본 맺음말"
list_signatures()            # "기본 footer html" (mode=closing_only)
```

> wizard가 입력받은 값(이름/부서/연락처/로고 경로 등)으로 위 4개를 만든다.
> 만약 setup 때 `--skip-signature-setup`으로 건너뛰었다면 이 목록이 비어 있다. 그때는 맨 끝 "기본값 직접 손보기"로 새로 만든다.

각 항목의 `id`는 뒤에서 특정 조합을 강제 지정할 때 쓴다.

---

## 2. 전체 서명 미리보기

> 이렇게 말하세요: **"기본 서명 다 적용해서 미리보기 보여줘."**

```text
preview_signature(
  text_body="본문 테스트입니다.",
  html_body="<p>본문 테스트입니다.</p>",
  apply_default_greeting_template=true,
  apply_default_closing_template=true,
  apply_default_signature=true,
  apply_default_signature_profile=true
)
```

확인: 인삿말 위치 / 맺음말 위치 / footer 치환 / HTML 줄간격·색상·폰트.

---

## 3. footer만 HTML로 뽑아 브라우저 확인

> 이렇게 말하세요: **"footer 서명만 HTML로 뽑아서 /절대경로/downloads/sig-preview 폴더에 저장해줘."**

```text
preview_closing_signature(
  apply_default_signature=true,
  apply_default_signature_profile=true,
  export_dir="/absolute/path/to/downloads/signature-preview-hong-gildong"
)
```

> `export_dir`는 서버의 현재 작업 디렉토리 기준으로 풀린다. 위치를 확실히 하려면 절대경로(`/home/<user>/...`)를 쓴다.

결과(절대경로 기준):
- `<export_dir>/signature-preview.html`
- `<export_dir>/assets/logo-color.png`

---

## 4. 첫 초안 만들기

`create_draft`는 기본값이 모두 자동 적용(`apply_default_*=true`)이라, wizard가 만든 기본 서명이 그대로 붙는다.

> 이렇게 말하세요: **"someone@example.com 한테 'MCP 테스트 메일' 제목으로 초안 만들어줘. 본문은 '본문 초안입니다.'"**

```text
create_draft(
  subject="MCP 테스트 메일",
  to=["someone@example.com"],
  text_body="본문 초안입니다.",
  html_body="<p>본문 초안입니다.</p>"
)
```

> `apply_default_*`는 기본이 `true`라 굳이 적지 않아도 기본 인삿말·맺음말·프로필·footer가 적용된다.

확인:

```text
get_draft(draft_id="생성된 draft id")
```

응답에서 `rendered_text_body`, `rendered_html_body` 확인.

---

## 5. 초안 발송 / 예약

> 이렇게 말하세요: **"좋아, 지금 보내줘."**

```text
send_draft_now(draft_id="draft-id")
```

> 이렇게 말하세요: **"내일 오전 9시에 예약 발송해줘."**

```text
schedule_draft(draft_id="draft-id", scheduled_for="2026-06-05T09:00:00+09:00")
```

> 서버가 켜져 있어야 예약 시간에 자동 발송된다. 밀린 예약은 "밀린 예약 메일 보내줘" → `dispatch_due_messages()`.

---

## 6. 메일 조회 / 검색

> **"안 읽은 메일 있어?"**

```text
get_unread_status(mailbox="INBOX")
```

> **"받은편지함 최근 메일 보여줘."**

```text
list_messages(mailbox="INBOX", limit=10)
```

> **"제목에 '주간보고' 들어간 메일 찾아줘."** (보낸메일함 기준)

```text
search_messages(mailbox="Sent", subject_contains="주간보고", limit=50)
```

---

## 7. 메일 정리 — 주간보고 모으기 (복사, 원본 유지)

> 이렇게 말하세요: **"'주간보고' 메일함 만들고, 보낸메일함에서 제목에 '주간보고' 들어간 메일을 거기로 복사해줘."**

AI가 순서대로 호출한다:

```text
list_mailboxes()                                  # 보낸메일함 정확한 이름 확인
create_mailbox(mailbox="주간보고")                  # 새 메일함 생성
search_messages(mailbox="Sent", subject_contains="주간보고", limit=50)   # 대상 UID 수집
copy_messages(
  from_mailbox="Sent",
  to_mailbox="주간보고",
  uids=["101", "102", "103"]                       # 위 검색 결과의 UID
)
```

> `copy_messages`는 원본을 보낸메일함에 그대로 둔 채 사본만 만든다(발송 기록 보존).

원본까지 옮기고 싶을 때(보낸메일함에서 사라짐):

> **"복사 말고 이동해줘."**

```text
move_messages(from_mailbox="Sent", to_mailbox="주간보고", uids=["101", "102", "103"])
```

---

## 8. 특정 템플릿 ID를 직접 지정해 초안 만들기

기본값 대신 특정 조합을 강제로 쓸 때(섹션 1의 `list_*`로 얻은 id 사용):

> 이렇게 말하세요: **"이번 건 외부용 정중한 인삿말이랑 영문 프로필로 초안 만들어줘."**

```text
create_draft(
  subject="외부 발송 테스트",
  to=["partner@example.com"],
  text_body="본문입니다.",
  html_body="<p>본문입니다.</p>",
  greeting_template_id="greeting-template-id",
  closing_template_id="closing-template-id",
  signature_profile_id="signature-profile-id",
  signature_id="signature-id",
  apply_default_greeting_template=false,
  apply_default_closing_template=false,
  apply_default_signature=false,
  apply_default_signature_profile=false
)
```

ID 조회:

```text
list_greeting_templates()
list_closing_templates()
list_signature_profiles()
list_signatures()
```

---

## 9. 기본값 다시 적용하거나 해제

> **"이 초안에 기본 서명 다시 붙여줘."**

```text
update_draft(draft_id="draft-id", apply_default_signature=true)
```

> **"인삿말·맺음말·프로필·서명 다 떼줘."**

```text
update_draft(
  draft_id="draft-id",
  clear_greeting_template=true,
  clear_closing_template=true,
  clear_signature_profile=true,
  clear_signature=true
)
```

---

## 10. 기본값 직접 손보기 (wizard 결과 수정 / 처음부터 다시 만들기)

wizard가 만든 기본값이 마음에 안 들거나, `--skip-signature-setup`으로 건너뛰어서 비어 있을 때 쓴다.

### 10-1. wizard가 만든 값 수정 (id는 섹션 1에서 확인)

> **"기본 프로필 휴대폰 번호 010-9999-0000으로 바꿔줘."**

```text
update_signature_profile(profile_id="signature-profile-id", fields={"mobile": "010-9999-0000"})
```

> **"기본 인삿말 문구 바꿔줘."**

```text
update_greeting_template(template_id="greeting-template-id", text_template="안녕하세요.\n{{department}} {{display_name}}입니다.")
```

> **"기본 맺음말 바꿔줘."**

```text
update_closing_template(template_id="closing-template-id", text_template="검토 부탁드립니다.\n\n감사합니다.")
```

### 10-2. 처음부터 다시 만들기 (skip 했거나 새로 짜고 싶을 때)

참조 파일: [signature-profile.example.json](examples/personal-setup/signature-profile.example.json), [greeting-template.example.json](examples/personal-setup/greeting-template.example.json), [closing-template.example.json](examples/personal-setup/closing-template.example.json), [signature-template.example.json](examples/personal-setup/signature-template.example.json)

> 이렇게 말하세요: **"이 정보로 기본 서명 프로필 만들어줘. 이름 홍길동, 영문 John Doe, 한자 洪吉童, 부서 로봇자동화사업부, 팀 로봇팀, 직급 사원, 영문부서 Robot Automation, 영문직함 Software Engineer, 대표전화 02-1234-5678, 휴대폰 010-1234-5678, 이메일 hong.gildong@ubisam.com, 로고는 /절대경로/logo-color.png. 기본값으로 해줘."**

```text
create_signature_profile(
  name="홍길동 기본 프로필",
  fields={
    "display_name": "홍길동",
    "english_name": "John Doe",
    "hanja_name": "洪吉童",
    "department": "로봇자동화사업부",
    "team": "로봇팀",
    "position": "사원",
    "division_english": "Robot Automation",
    "job_title_english": "Software Engineer",
    "office_phone": "02-1234-5678",
    "mobile": "010-1234-5678",
    "email": "hong.gildong@ubisam.com"
  },
  logo_image_path="/absolute/path/to/ubisam-mail-mcp/docs/examples/personal-setup/assets/logo-color.png",
  is_default=true
)
```

> `hanja_name`, `division_english`, `job_title_english`는 기본 footer가 사용한다. 비우면 footer에 빈칸이 생긴다.

```text
create_greeting_template(
  name="기본 인삿말",
  text_template="안녕하십니까.\n{{department}} {{team}} {{display_name}} {{position}}입니다.",
  is_default=true
)
```

```text
create_closing_template(
  name="기본 맺음말",
  text_template="확인 부탁드립니다.\n\n감사합니다.",
  is_default=true
)
```

footer 서명은 `mode="closing_only"`, `html_template`이 핵심이다. 한글 폰트는 `Malgun Gothic`을 쓰고, `{{company_logo_img}}`는 프로필에 `logo_image_path`가 있을 때만 렌더링된다.

```text
create_signature(
  name="기본 footer html",
  text_template="{{display_name}} {{position}} / {{english_name}} / {{hanja_name}}\n{{department}} / {{division_english}} / {{job_title_english}}\nt {{office_phone}}  m {{mobile}}  e {{email}}",
  html_template="<hr style=\"border:none;border-top:1px solid #cfcfcf;margin:0 0 14px 0;\"><div style=\"font-family:'Malgun Gothic',sans-serif;color:#7c7c7c;\">  <div style=\"font-size:24px;font-weight:700;line-height:1.25;color:#8a8a8a;display:flex;align-items:flex-end;gap:14px;\">    <span style=\"display:inline-flex;align-items:flex-end;line-height:1;\">{{company_logo_img}}</span>    <span style=\"display:inline-block;line-height:1;transform:translateY(-4px);\">{{display_name}} {{position}} / {{english_name}} / {{hanja_name}}</span>  </div>  <div style=\"margin-top:10px;font-size:19px;font-weight:700;line-height:1.3;color:#8a8a8a;\">{{department}} / {{division_english}} / {{job_title_english}}</div>  <div style=\"margin-top:14px;font-size:18px;line-height:1.45;color:#6f6f6f;\">    <strong style=\"color:#222;\">t</strong> {{office_phone}} &nbsp;&nbsp;    <strong style=\"color:#222;\">m</strong> {{mobile}} &nbsp;&nbsp;    <strong style=\"color:#222;\">e</strong> {{email}}  </div></div>",
  mode="closing_only",
  is_default=true
)
```

새로 만든 뒤에는 섹션 2의 `preview_signature`로 결과를 확인한다.
