from __future__ import annotations

from datetime import date, timezone

import pytest

from ubisam_mail_mcp import server


# --- datetime/date helpers -------------------------------------------------

def test_parse_datetime_requires_timezone():
    with pytest.raises(ValueError):
        server._parse_datetime("2026-06-09T10:00:00")


def test_parse_datetime_accepts_z_and_converts_to_utc():
    parsed = server._parse_datetime("2026-06-09T19:00:00+09:00")
    assert parsed.tzinfo == timezone.utc
    assert parsed.hour == 10


def test_parse_date_handles_none_and_iso():
    assert server._parse_date(None) is None
    assert server._parse_date("2026-06-09") == date(2026, 6, 9)


# --- input validation guards ----------------------------------------------

@pytest.mark.parametrize("limit", [0, 51])
def test_list_messages_rejects_out_of_range_limit(limit):
    with pytest.raises(ValueError):
        server.list_messages(limit=limit)


@pytest.mark.parametrize("sample_limit", [-1, 21])
def test_get_unread_status_rejects_out_of_range_sample_limit(sample_limit):
    with pytest.raises(ValueError):
        server.get_unread_status(sample_limit=sample_limit)


@pytest.mark.parametrize("chars", [99, 20001])
def test_get_message_rejects_out_of_range_preview(chars):
    with pytest.raises(ValueError):
        server.get_message(uid="1", body_preview_chars=chars)


def test_download_attachment_rejects_negative_index():
    with pytest.raises(ValueError):
        server.download_message_attachment(uid="1", attachment_index=-1)


def test_create_mailbox_requires_name():
    with pytest.raises(ValueError):
        server.create_mailbox(mailbox="   ")


def test_move_and_copy_require_target_mailbox():
    with pytest.raises(ValueError):
        server.move_messages(uids=["1"], to_mailbox="  ")
    with pytest.raises(ValueError):
        server.copy_messages(uids=["1"], to_mailbox="")


# --- delegation -------------------------------------------------------------

class _FakeImap:
    def __init__(self):
        self.calls = {}

    def search_messages(self, **kwargs):
        self.calls["search_messages"] = kwargs
        return ["m1"]

    def set_message_read_status(self, **kwargs):
        self.calls["set_message_read_status"] = kwargs
        return {"updated": len(kwargs["uids"])}


def test_search_messages_parses_dates_and_delegates(monkeypatch):
    fake = _FakeImap()
    monkeypatch.setattr(server, "_imap", lambda: fake)

    result = server.search_messages(
        subject_contains="hello",
        date_from="2026-06-01",
        date_to="2026-06-02",
        limit=5,
    )

    assert result == {"messages": ["m1"]}
    captured = fake.calls["search_messages"]
    assert captured["subject_contains"] == "hello"
    assert captured["date_from"] == date(2026, 6, 1)
    assert captured["date_to"] == date(2026, 6, 2)
    assert captured["limit"] == 5


def test_set_message_read_status_delegates(monkeypatch):
    fake = _FakeImap()
    monkeypatch.setattr(server, "_imap", lambda: fake)

    result = server.set_message_read_status(uids=["1", "2"], is_unread=True, mailbox="INBOX")

    assert result == {"result": {"updated": 2}}
    captured = fake.calls["set_message_read_status"]
    assert captured["uids"] == ["1", "2"]
    assert captured["is_unread"] is True
    assert captured["mailbox"] == "INBOX"
