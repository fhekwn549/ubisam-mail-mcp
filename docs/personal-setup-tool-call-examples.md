# ubisam-mail-mcp 개인 설정 Tool 호출 예문

이 문서는 [personal-setup-tutorial.md](/home/yourname/ubisam-mail-mcp/docs/personal-setup-tutorial.md) 과
[docs/examples/personal-setup](/home/yourname/ubisam-mail-mcp/docs/examples/personal-setup) 예시 파일을 기준으로,
실제로 MCP tool에 넣을 수 있는 호출 예문을 모아둔 문서다.

전제:
- 예시 JSON 4개를 먼저 본인 정보로 수정
- `signature-profile.example.json`의 `logo_image_path`를 실제 로컬 절대경로로 수정
- 아래 예문은 익명화 샘플 값 `홍길동 / John Doe / 洪吉童` 기준

## 1. 프로필 생성

참조 파일:
- [signature-profile.example.json](/home/yourname/ubisam-mail-mcp/docs/examples/personal-setup/signature-profile.example.json)

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

## 2. 인삿말 템플릿 생성

참조 파일:
- [greeting-template.example.json](/home/yourname/ubisam-mail-mcp/docs/examples/personal-setup/greeting-template.example.json)

```text
create_greeting_template(
  name="기본 인삿말",
  text_template="안녕하십니까.\n{{department}} {{team}} {{display_name}} {{position}}입니다.",
  html_template="<p>안녕하십니까.</p><p>{{department}} {{team}} {{display_name}} {{position}}입니다.</p>",
  is_default=true
)
```

## 3. 맺음말 템플릿 생성

참조 파일:
- [closing-template.example.json](/home/yourname/ubisam-mail-mcp/docs/examples/personal-setup/closing-template.example.json)

```text
create_closing_template(
  name="기본 맺음말",
  text_template="확인 부탁드립니다.\n\n감사합니다.",
  html_template="<p>확인 부탁드립니다.</p><p>감사합니다.</p>",
  is_default=true
)
```

## 4. footer 서명 템플릿 생성

참조 파일:
- [signature-template.example.json](/home/yourname/ubisam-mail-mcp/docs/examples/personal-setup/signature-template.example.json)

```text
create_signature(
  name="기본 footer html",
  text_template="{{display_name}} {{position}} / {{english_name}} / {{hanja_name}}\n{{department}} / {{division_english}} / {{job_title_english}}\nt {{office_phone}}  m {{mobile}}  e {{email}}",
  html_template="<hr style=\"border:none;border-top:1px solid #cfcfcf;margin:0 0 14px 0;\"><div style=\"font-family:'Malgun Gothic',sans-serif;color:#7c7c7c;\">  <div style=\"font-size:24px;font-weight:700;line-height:1.25;color:#8a8a8a;display:flex;align-items:flex-end;gap:14px;\">    <span style=\"display:inline-flex;align-items:flex-end;line-height:1;\">{{company_logo_img}}</span>    <span style=\"display:inline-block;line-height:1;transform:translateY(-4px);\">{{display_name}} {{position}} / {{english_name}} / {{hanja_name}}</span>  </div>  <div style=\"margin-top:10px;font-size:19px;font-weight:700;line-height:1.3;color:#8a8a8a;\">{{department}} / {{division_english}} / {{job_title_english}}</div>  <div style=\"margin-top:14px;font-size:18px;line-height:1.45;color:#6f6f6f;\">    <strong style=\"color:#222;\">t</strong> {{office_phone}} &nbsp;&nbsp;    <strong style=\"color:#222;\">m</strong> {{mobile}} &nbsp;&nbsp;    <strong style=\"color:#222;\">e</strong> {{email}}  </div></div>",
  mode="closing_only",
  is_default=true
)
```

## 5. 전체 서명 미리보기

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

확인 포인트:
- 인삿말 위치
- 맺음말 위치
- footer 이름/부서/연락처 치환
- HTML 줄간격/색상/폰트

## 6. footer만 미리보기

```text
preview_closing_signature(
  apply_default_signature=true,
  apply_default_signature_profile=true,
  export_dir="downloads/signature-preview-hong-gildong"
)
```

결과:
- `downloads/signature-preview-hong-gildong/signature-preview.html`
- `downloads/signature-preview-hong-gildong/assets/logo-color.png`

## 7. 첫 초안 생성

```text
create_draft(
  subject="MCP 테스트 메일",
  to=["someone@example.com"],
  text_body="본문 초안입니다.",
  html_body="<p>본문 초안입니다.</p>",
  apply_default_greeting_template=true,
  apply_default_closing_template=true,
  apply_default_signature=true,
  apply_default_signature_profile=true
)
```

이후 확인:

```text
get_draft(draft_id="생성된 draft id")
```

응답에서 확인:
- `rendered_text_body`
- `rendered_html_body`

## 8. 특정 템플릿 ID를 직접 지정해 초안 만들기

기본값 대신 특정 템플릿 조합을 강제로 쓰고 싶을 때:

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

## 9. 기본값 다시 적용하거나 해제

서명만 다시 기본값 붙이기:

```text
update_draft(
  draft_id="draft-id",
  apply_default_signature=true
)
```

인삿말/맺음말/프로필/서명 제거:

```text
update_draft(
  draft_id="draft-id",
  clear_greeting_template=true,
  clear_closing_template=true,
  clear_signature_profile=true,
  clear_signature=true
)
```

## 10. 동료에게 그대로 전달할 최소 세트

동료 온보딩 때는 아래 3개만 먼저 전달하면 된다.

1. [personal-setup-tutorial.md](/home/yourname/ubisam-mail-mcp/docs/personal-setup-tutorial.md)
2. [docs/examples/personal-setup](/home/yourname/ubisam-mail-mcp/docs/examples/personal-setup)
3. 이 문서 [personal-setup-tool-call-examples.md](/home/yourname/ubisam-mail-mcp/docs/personal-setup-tool-call-examples.md)
