from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from email.message import EmailMessage
from pathlib import Path

from ubisam_mail_mcp.config import AppConfig
from ubisam_mail_mcp.imap_client import (
    ImapMailClient,
    _bodystructure_has_attachments,
    _build_search_terms,
    _decode_header_value,
    _extract_attachments,
    _extract_html_body,
    _extract_text_body,
    _format_imap_date,
    _is_unread,
    _join_uid_set,
    _parse_flags,
    _parse_mailbox_line,
    _parse_size,
)
from ubisam_mail_mcp.models import MessageDraft


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


def test_is_unread_depends_on_seen_flag():
    assert _is_unread([]) is True
    assert _is_unread(["\\Flagged"]) is True
    assert _is_unread(["\\Seen"]) is False


def test_search_helpers_build_expected_values():
    assert _format_imap_date(date(2026, 6, 2)) == "02-Jun-2026"
    assert _join_uid_set(["10", "11"]) == "10,11"
    assert _bodystructure_has_attachments('BODYSTRUCTURE (("TEXT" "PLAIN")("IMAGE" "PNG" NIL NIL NIL "BASE64" 123 NIL ("ATTACHMENT" ("FILENAME" "a.png"))))') is True
    assert _bodystructure_has_attachments('BODYSTRUCTURE ("TEXT" "PLAIN" NIL NIL NIL "7BIT" 10 1)') is False
    assert _build_search_terms(
        subject_contains="test",
        from_contains="alice",
        to_contains="bob",
        body_contains="hello",
        is_unread=True,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 2),
    ) == [
        "ALL",
        "SUBJECT",
        '"test"',
        "FROM",
        '"alice"',
        "TO",
        '"bob"',
        "TEXT",
        '"hello"',
        "UNSEEN",
        "SINCE",
        "01-Jun-2026",
        "BEFORE",
        "03-Jun-2026",
    ]


def test_extract_text_and_html_body():
    message = EmailMessage()
    message["Subject"] = "demo"
    message.set_content("plain body")
    message.add_alternative("<p>html body</p>", subtype="html")

    assert _extract_text_body(message) == "plain body"
    assert _extract_html_body(message) == "<p>html body</p>"


def test_extract_attachments():
    message = EmailMessage()
    message["Subject"] = "demo"
    message.set_content("plain body")
    message.add_attachment("hello".encode("utf-8"), maintype="text", subtype="plain", filename="hello.txt")

    attachments = _extract_attachments(message)

    assert len(attachments) == 1
    assert attachments[0].filename == "hello.txt"
    assert attachments[0].content_type == "text/plain"
    assert attachments[0].size_bytes == len("hello".encode("utf-8"))


class FakeImapFetchClient:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def uid(self, command: str, uid: str, query: str):
        assert command == "fetch"
        return "OK", [(b"1 (BODY[] {1}", self.payload), b")"]


class FakeImapUnreadClient:
    def uid(self, command: str, uid: str | None, query: str):
        if command == "search":
            assert query == "UNSEEN"
            return "OK", [b"10 11"]
        assert command == "fetch"
        if uid == "11":
            metadata = b"1 (UID 11 FLAGS () RFC822.SIZE 200 BODY[HEADER.FIELDS (SUBJECT FROM TO DATE)] {1}"
            payload = (
                b"Subject: unread latest\r\n"
                b"From: latest@example.com\r\n"
                b"To: user@example.com\r\n"
                b"Date: Mon, 01 Jun 2026 10:00:00 +0900\r\n\r\n"
            )
            return "OK", [(metadata, payload), b")"]
        if uid == "10":
            metadata = b"1 (UID 10 FLAGS () RFC822.SIZE 180 BODY[HEADER.FIELDS (SUBJECT FROM TO DATE)] {1}"
            payload = (
                b"Subject: unread older\r\n"
                b"From: older@example.com\r\n"
                b"To: user@example.com\r\n"
                b"Date: Sun, 31 May 2026 18:00:00 +0900\r\n\r\n"
            )
            return "OK", [(metadata, payload), b")"]
        raise AssertionError(f"unexpected uid: {uid}")


class FakeImapAppendClient:
    def __init__(self) -> None:
        self.append_calls: list[tuple[str, str, object, bytes]] = []

    def list(self):
        return "OK", [b'(\\HasNoChildren \\Drafts) "/" "&x4TC3Lz0rQDVaA-"']

    def append(self, mailbox: str, flags: str, internaldate: object, message_bytes: bytes):
        self.append_calls.append((mailbox, flags, internaldate, message_bytes))
        return "OK", [b"[APPENDUID 12345 678] APPEND completed"]


class FakeImapSearchClient:
    def __init__(self) -> None:
        self.search_calls: list[tuple[object, ...]] = []

    def uid(self, command: str, *args):
        if command == "search":
            self.search_calls.append(args)
            return "OK", [b"21 22"]
        assert command == "fetch"
        uid = args[0]
        query = args[1]
        if query == "(FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO DATE)])":
            metadata = f'1 (UID {uid} FLAGS () RFC822.SIZE 180 BODY[HEADER.FIELDS (SUBJECT FROM TO DATE)] {{1}}'.encode()
            payload = (
                f"Subject: message {uid}\r\n".encode()
                + b"From: sender@example.com\r\n"
                + b"To: user@example.com\r\n"
                + b"Date: Mon, 01 Jun 2026 10:00:00 +0900\r\n\r\n"
            )
            return "OK", [(metadata, payload), b")"]
        if query == "(BODYSTRUCTURE FLAGS RFC822.SIZE)":
            if uid == "22":
                return "OK", [b'1 (UID 22 FLAGS () RFC822.SIZE 200 BODYSTRUCTURE (("TEXT" "PLAIN")("IMAGE" "PNG" NIL NIL NIL "BASE64" 123 NIL ("ATTACHMENT" ("FILENAME" "a.png")))))']
            return "OK", [b'1 (UID 21 FLAGS () RFC822.SIZE 180 BODYSTRUCTURE ("TEXT" "PLAIN" NIL NIL NIL "7BIT" 10 1))']
        raise AssertionError(f"unexpected fetch args: {args}")


class FakeImapWriteClient:
    def __init__(self, *, move_status: str = "OK") -> None:
        self.created_mailboxes: list[str] = []
        self.store_calls: list[tuple[object, ...]] = []
        self.move_calls: list[tuple[object, ...]] = []
        self.copy_calls: list[tuple[object, ...]] = []
        self.expunge_called = False
        self.move_status = move_status

    def create(self, mailbox: str):
        self.created_mailboxes.append(mailbox)
        return "OK", [b"created"]

    def list(self):
        return "OK", [b'(\\HasNoChildren \\Trash) "/" "&1zTJwNG1-"']

    def select(self, mailbox: str, readonly: bool = True):
        self.selected = (mailbox, readonly)
        return "OK", [b"1"]

    def uid(self, command: str, *args):
        if command == "store":
            self.store_calls.append(args)
            return "OK", [b"stored"]
        if command == "MOVE":
            self.move_calls.append(args)
            return self.move_status, [b"move unsupported" if self.move_status != "OK" else b"moved"]
        if command == "COPY":
            self.copy_calls.append(args)
            return "OK", [b"copied"]
        raise AssertionError(f"unexpected uid command: {command}")

    def expunge(self):
        self.expunge_called = True
        return "OK", [b"expunged"]

    def close(self):
        return None


def make_client(tmp_path: Path) -> ImapMailClient:
    config = AppConfig(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="user",
        smtp_password="pass",
        smtp_use_tls=False,
        smtp_use_starttls=True,
        smtp_debug=False,
        smtp_tls_servername="smtp.example.com",
        imap_host="imap.example.com",
        imap_port=993,
        imap_username="user",
        imap_password="pass",
        imap_use_tls=True,
        imap_tls_servername="imap.example.com",
        default_from_address="bot@example.com",
        default_from_name="",
        sqlite_path=tmp_path / "mail.db",
        attachment_download_dir=tmp_path / "downloads",
        contacts_path=tmp_path / "contacts.local.json",
    )
    return ImapMailClient(config)


def make_draft() -> MessageDraft:
    return MessageDraft(
        id="draft-1",
        subject="subject",
        from_address="user@example.com",
        to=["to@example.com"],
        cc=[],
        bcc=[],
        text_body="body",
        html_body="<p>body</p>",
        status="draft",
    )


def test_download_attachment_saves_file(monkeypatch, tmp_path):
    message = EmailMessage()
    message["Subject"] = "demo"
    message.set_content("plain body")
    message.add_attachment("hello".encode("utf-8"), maintype="text", subtype="plain", filename="hello.txt")
    client = make_client(tmp_path)
    fake_client = FakeImapFetchClient(message.as_bytes())

    @contextmanager
    def fake_connect():
        yield fake_client

    @contextmanager
    def fake_select(_client, _mailbox: str):
        yield

    monkeypatch.setattr(client, "_connect", fake_connect)
    monkeypatch.setattr(client, "_select_mailbox", fake_select)

    result = client.download_attachment(
        mailbox="INBOX",
        uid="1",
        attachment_index=0,
        target_path=str(tmp_path / "downloads" / "hello.txt"),
    )

    saved_path = Path(result["saved_to"])
    assert saved_path.read_text(encoding="utf-8") == "hello"
    assert result["attachment"]["filename"] == "hello.txt"


def test_download_attachment_uses_default_dir_when_target_path_missing(monkeypatch, tmp_path):
    message = EmailMessage()
    message["Subject"] = "demo"
    message.set_content("plain body")
    message.add_attachment("hello".encode("utf-8"), maintype="text", subtype="plain", filename="hello.txt")
    client = make_client(tmp_path)
    fake_client = FakeImapFetchClient(message.as_bytes())

    @contextmanager
    def fake_connect():
        yield fake_client

    @contextmanager
    def fake_select(_client, _mailbox: str):
        yield

    monkeypatch.setattr(client, "_connect", fake_connect)
    monkeypatch.setattr(client, "_select_mailbox", fake_select)

    result = client.download_attachment(mailbox="INBOX", uid="42", attachment_index=0)

    saved_path = Path(result["saved_to"])
    assert saved_path == tmp_path / "downloads" / "uid_42" / "hello.txt"
    assert saved_path.read_text(encoding="utf-8") == "hello"


def test_get_unread_status_returns_count_and_latest_messages(monkeypatch, tmp_path):
    client = make_client(tmp_path)
    fake_client = FakeImapUnreadClient()

    @contextmanager
    def fake_connect():
        yield fake_client

    @contextmanager
    def fake_select(_client, _mailbox: str):
        yield

    monkeypatch.setattr(client, "_connect", fake_connect)
    monkeypatch.setattr(client, "_select_mailbox", fake_select)

    result = client.get_unread_status(mailbox="INBOX", sample_limit=1)

    assert result["mailbox"] == "INBOX"
    assert result["has_unread"] is True
    assert result["unread_count"] == 2
    assert [item["uid"] for item in result["latest_unread_messages"]] == ["11"]
    assert result["latest_unread_messages"][0]["is_unread"] is True


def test_list_messages_includes_is_unread(monkeypatch, tmp_path):
    client = make_client(tmp_path)
    fake_client = FakeImapUnreadClient()

    @contextmanager
    def fake_connect():
        yield fake_client

    @contextmanager
    def fake_select(_client, _mailbox: str):
        yield

    monkeypatch.setattr(client, "_connect", fake_connect)
    monkeypatch.setattr(client, "_select_mailbox", fake_select)

    messages = client.list_messages(mailbox="INBOX", limit=2, criteria="UNSEEN")

    assert [item["uid"] for item in messages] == ["11", "10"]
    assert all(item["is_unread"] is True for item in messages)


def test_upload_draft_uses_drafts_mailbox_and_returns_append_uid(monkeypatch, tmp_path):
    client = make_client(tmp_path)
    fake_client = FakeImapAppendClient()

    @contextmanager
    def fake_connect():
        yield fake_client

    monkeypatch.setattr(client, "_connect", fake_connect)

    result = client.upload_draft(draft=make_draft())

    assert result["mailbox"] == "&x4TC3Lz0rQDVaA-"
    assert result["append_uid"] == "678"
    assert result["subject"] == "subject"
    mailbox, flags, _internaldate, message_bytes = fake_client.append_calls[0]
    assert mailbox == "&x4TC3Lz0rQDVaA-"
    assert flags == "(\\Draft)"
    assert b"Subject: subject" in message_bytes


def test_search_messages_supports_filters_and_attachment_check(monkeypatch, tmp_path):
    client = make_client(tmp_path)
    fake_client = FakeImapSearchClient()

    @contextmanager
    def fake_connect():
        yield fake_client

    @contextmanager
    def fake_select(_client, _mailbox: str, readonly: bool = True):
        yield

    monkeypatch.setattr(client, "_connect", fake_connect)
    monkeypatch.setattr(client, "_select_mailbox", fake_select)

    messages = client.search_messages(
        mailbox="INBOX",
        limit=5,
        subject_contains="message",
        is_unread=True,
        has_attachments=True,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 2),
    )

    assert [item["uid"] for item in messages] == ["22"]
    assert messages[0]["has_attachments"] is True
    assert fake_client.search_calls[0] == (
        None,
        "ALL",
        "SUBJECT",
        '"message"',
        "UNSEEN",
        "SINCE",
        "01-Jun-2026",
        "BEFORE",
        "03-Jun-2026",
    )


def test_create_mailbox_calls_imap_create(monkeypatch, tmp_path):
    client = make_client(tmp_path)
    fake_client = FakeImapWriteClient()

    @contextmanager
    def fake_connect():
        yield fake_client

    monkeypatch.setattr(client, "_connect", fake_connect)

    result = client.create_mailbox(mailbox="Projects/Test")

    assert result == {"mailbox": "Projects/Test", "created": True}
    assert fake_client.created_mailboxes == ["Projects/Test"]


def test_set_message_read_status_updates_seen_flag(monkeypatch, tmp_path):
    client = make_client(tmp_path)
    fake_client = FakeImapWriteClient()

    @contextmanager
    def fake_connect():
        yield fake_client

    monkeypatch.setattr(client, "_connect", fake_connect)

    result = client.set_message_read_status(mailbox="INBOX", uids=["10", "11"], is_unread=False)

    assert result["updated"] == 2
    assert fake_client.selected == ("INBOX", False)
    assert fake_client.store_calls == [("10,11", "+FLAGS.SILENT", "(\\Seen)")]


def test_move_messages_falls_back_to_copy_delete_expunge(monkeypatch, tmp_path):
    client = make_client(tmp_path)
    fake_client = FakeImapWriteClient(move_status="NO")

    @contextmanager
    def fake_connect():
        yield fake_client

    monkeypatch.setattr(client, "_connect", fake_connect)

    result = client.move_messages(from_mailbox="INBOX", to_mailbox="Archive", uids=["15"])

    assert result["moved"] == 1
    assert fake_client.selected == ("INBOX", False)
    assert fake_client.move_calls == [("15", "Archive")]
    assert fake_client.copy_calls == [("15", "Archive")]
    assert fake_client.store_calls == [("15", "+FLAGS.SILENT", "(\\Deleted)")]
    assert fake_client.expunge_called is True


def test_copy_messages_copies_without_expunge(monkeypatch, tmp_path):
    client = make_client(tmp_path)
    fake_client = FakeImapWriteClient(move_status="OK")

    @contextmanager
    def fake_connect():
        yield fake_client

    monkeypatch.setattr(client, "_connect", fake_connect)

    result = client.copy_messages(from_mailbox="Sent", to_mailbox="주간보고", uids=["15", "16"])

    assert result["copied"] == 2
    assert result["from_mailbox"] == "Sent"
    assert result["to_mailbox"] == "주간보고"
    assert fake_client.selected == ("Sent", True)
    assert fake_client.copy_calls == [("15,16", "주간보고")]
    assert fake_client.store_calls == []
    assert fake_client.expunge_called is False


def test_delete_messages_prefers_trash_mailbox(monkeypatch, tmp_path):
    client = make_client(tmp_path)
    fake_client = FakeImapWriteClient(move_status="OK")

    @contextmanager
    def fake_connect():
        yield fake_client

    monkeypatch.setattr(client, "_connect", fake_connect)

    result = client.delete_messages(mailbox="INBOX", uids=["17"])

    assert result["deleted"] == 1
    assert result["method"] == "move-to-trash"
    assert result["trash_mailbox"] == "&1zTJwNG1-"
    assert fake_client.move_calls == [("17", "&1zTJwNG1-")]
