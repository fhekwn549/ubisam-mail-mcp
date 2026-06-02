from __future__ import annotations

from email.message import EmailMessage

from ubisam_mail_mcp.imap_client import (
    _decode_header_value,
    _extract_html_body,
    _extract_text_body,
    _parse_flags,
    _parse_mailbox_line,
    _parse_size,
)


def test_parse_mailbox_line_handles_common_list_response():
    parsed = _parse_mailbox_line(b'(\\HasNoChildren) "/" "INBOX"')

    assert parsed["name"] == "INBOX"
    assert parsed["attributes"] == ["\\HasNoChildren"]
    assert parsed["delimiter"] == "/"


def test_decode_header_value_decodes_mime_words():
    decoded = _decode_header_value("=?utf-8?b?7ZWc67mE66GcIO2FjOyKpO2KuA==?=")

    assert decoded == "한비로 테스트"


def test_parse_flags_and_size_from_fetch_metadata():
    metadata = "1 (UID 99 FLAGS (\\Seen \\Answered) RFC822.SIZE 1234 BODY[] {100}"

    assert _parse_flags(metadata) == ["\\Seen", "\\Answered"]
    assert _parse_size(metadata) == 1234


def test_extract_text_and_html_body():
    message = EmailMessage()
    message["Subject"] = "demo"
    message.set_content("plain body")
    message.add_alternative("<p>html body</p>", subtype="html")

    assert _extract_text_body(message) == "plain body"
    assert _extract_html_body(message) == "<p>html body</p>"
