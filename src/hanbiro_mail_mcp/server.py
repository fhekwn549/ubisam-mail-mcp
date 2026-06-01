from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any

from .config import AppConfig
from .imap_client import ImapMailClient
from .repository import DraftRepository
from .service import MailService
from .smtp_client import SmtpMailSender

SERVER_INFO = {"name": "hanbiro-mail-mcp", "version": "0.1.0"}
PROTOCOL_VERSION = "2024-11-05"


class McpServer:
    def __init__(self) -> None:
        self._config = AppConfig.from_env()
        self._imap_client = ImapMailClient(self._config)
        self._service = MailService(
            repository=DraftRepository(self._config.sqlite_path),
            sender=SmtpMailSender(self._config),
            config=self._config,
        )

    def serve_forever(self) -> None:
        while True:
            request = _read_message()
            if request is None:
                return
            response = self._handle_request(request)
            if response is not None:
                _write_message(response)

    def _handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")

        try:
            if method == "initialize":
                return self._result(
                    request_id,
                    {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": SERVER_INFO,
                    },
                )
            if method == "notifications/initialized":
                return None
            if method == "ping":
                return self._result(request_id, {})
            if method == "tools/list":
                return self._result(request_id, {"tools": _tool_definitions()})
            if method == "tools/call":
                params = request.get("params", {})
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                payload = self._call_tool(tool_name, arguments)
                return self._result(
                    request_id,
                    {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]},
                )
            raise ValueError(f"unsupported method: {method}")
        except Exception as exc:
            return self._error(request_id, str(exc))

    def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "config_status":
            return {
                "smtp_ready": self._config.smtp_ready(),
                "smtp_host": self._config.smtp_host,
                "smtp_port": self._config.smtp_port,
                "smtp_username": self._config.smtp_username,
                "smtp_use_tls": self._config.smtp_use_tls,
                "smtp_use_starttls": self._config.smtp_use_starttls,
                "imap_ready": self._config.imap_ready(),
                "imap_host": self._config.imap_host,
                "imap_port": self._config.imap_port,
                "imap_username": self._config.imap_username,
                "imap_use_tls": self._config.imap_use_tls,
                "default_from_address": self._config.default_from_address,
                "sqlite_path": str(self._config.sqlite_path),
            }
        if tool_name == "list_mailboxes":
            return {"mailboxes": self._imap_client.list_mailboxes()}
        if tool_name == "list_messages":
            return {
                "messages": self._imap_client.list_messages(
                    mailbox=str(arguments.get("mailbox", "INBOX")),
                    limit=_optional_int(arguments, "limit", default=10, minimum=1, maximum=50),
                    criteria=str(arguments.get("criteria", "ALL")),
                )
            }
        if tool_name == "get_message":
            return {
                "message": self._imap_client.get_message(
                    mailbox=str(arguments.get("mailbox", "INBOX")),
                    uid=_require_string(arguments, "uid"),
                    body_preview_chars=_optional_int(
                        arguments,
                        "body_preview_chars",
                        default=4000,
                        minimum=100,
                        maximum=20000,
                    ),
                )
            }
        if tool_name == "create_draft":
            draft = self._service.create_draft(
                subject=_require_string(arguments, "subject"),
                to=_require_string_list(arguments, "to"),
                cc=_optional_string_list(arguments, "cc"),
                bcc=_optional_string_list(arguments, "bcc"),
                text_body=str(arguments.get("text_body", "")),
                html_body=str(arguments.get("html_body", "")),
                from_address=arguments.get("from_address"),
            )
            return {"draft": draft.to_dict()}
        if tool_name == "update_draft":
            updates = {
                "subject": arguments.get("subject"),
                "to": _optional_string_list(arguments, "to"),
                "cc": _optional_string_list(arguments, "cc"),
                "bcc": _optional_string_list(arguments, "bcc"),
                "text_body": arguments.get("text_body"),
                "html_body": arguments.get("html_body"),
                "from_address": arguments.get("from_address"),
            }
            draft = self._service.update_draft(_require_string(arguments, "draft_id"), **updates)
            return {"draft": draft.to_dict()}
        if tool_name == "get_draft":
            draft = self._service.require_draft(_require_string(arguments, "draft_id"))
            return {"draft": draft.to_dict()}
        if tool_name == "list_drafts":
            return {"drafts": [draft.to_dict() for draft in self._service.repository.list_all()]}
        if tool_name == "schedule_draft":
            draft = self._service.schedule_draft(
                _require_string(arguments, "draft_id"),
                _parse_datetime(_require_string(arguments, "scheduled_for")),
            )
            return {"draft": draft.to_dict()}
        if tool_name == "send_draft_now":
            draft = self._service.send_draft_now(_require_string(arguments, "draft_id"))
            return {"draft": draft.to_dict()}
        if tool_name == "dispatch_due_messages":
            drafts = self._service.dispatch_due_messages()
            return {"sent": [draft.to_dict() for draft in drafts], "count": len(drafts)}
        raise ValueError(f"unknown tool: {tool_name}")

    @staticmethod
    def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32000, "message": message},
        }


def _tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "config_status",
            "description": "Return SMTP, IMAP, and SQLite configuration status.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "list_mailboxes",
            "description": "List IMAP mailboxes available to the configured account.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "list_messages",
            "description": "List recent IMAP messages from a mailbox.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "mailbox": {"type": "string"},
                    "limit": {"type": "integer"},
                    "criteria": {"type": "string"},
                },
            },
        },
        {
            "name": "get_message",
            "description": "Fetch one IMAP message by UID with a text/html body preview.",
            "inputSchema": {
                "type": "object",
                "required": ["uid"],
                "properties": {
                    "uid": {"type": "string"},
                    "mailbox": {"type": "string"},
                    "body_preview_chars": {"type": "integer"},
                },
            },
        },
        {
            "name": "create_draft",
            "description": "Create a new draft mail. This does not send mail.",
            "inputSchema": {
                "type": "object",
                "required": ["subject", "to"],
                "properties": {
                    "subject": {"type": "string"},
                    "to": {"type": "array", "items": {"type": "string"}},
                    "cc": {"type": "array", "items": {"type": "string"}},
                    "bcc": {"type": "array", "items": {"type": "string"}},
                    "text_body": {"type": "string"},
                    "html_body": {"type": "string"},
                    "from_address": {"type": "string"},
                },
            },
        },
        {
            "name": "update_draft",
            "description": "Update an existing unsent draft.",
            "inputSchema": {
                "type": "object",
                "required": ["draft_id"],
                "properties": {
                    "draft_id": {"type": "string"},
                    "subject": {"type": "string"},
                    "to": {"type": "array", "items": {"type": "string"}},
                    "cc": {"type": "array", "items": {"type": "string"}},
                    "bcc": {"type": "array", "items": {"type": "string"}},
                    "text_body": {"type": "string"},
                    "html_body": {"type": "string"},
                    "from_address": {"type": "string"},
                },
            },
        },
        {
            "name": "get_draft",
            "description": "Get one draft by id.",
            "inputSchema": {
                "type": "object",
                "required": ["draft_id"],
                "properties": {"draft_id": {"type": "string"}},
            },
        },
        {
            "name": "list_drafts",
            "description": "List all drafts and sent messages stored in SQLite.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "schedule_draft",
            "description": "Schedule a draft for later sending. Use ISO 8601 with timezone.",
            "inputSchema": {
                "type": "object",
                "required": ["draft_id", "scheduled_for"],
                "properties": {
                    "draft_id": {"type": "string"},
                    "scheduled_for": {"type": "string"},
                },
            },
        },
        {
            "name": "send_draft_now",
            "description": "Send a draft immediately after explicit confirmation by the user.",
            "inputSchema": {
                "type": "object",
                "required": ["draft_id"],
                "properties": {"draft_id": {"type": "string"}},
            },
        },
        {
            "name": "dispatch_due_messages",
            "description": "Send scheduled drafts whose time has arrived.",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]


def _require_string(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _require_string_list(arguments: dict[str, Any], key: str) -> list[str]:
    value = _optional_string_list(arguments, key)
    if not value:
        raise ValueError(f"{key} must contain at least one value")
    return value


def _optional_string_list(arguments: dict[str, Any], key: str) -> list[str] | None:
    if key not in arguments or arguments.get(key) is None:
        return None
    value = arguments.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{key} must be a list of non-empty strings")
    return [item.strip() for item in value]


def _optional_int(
    arguments: dict[str, Any],
    key: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if key not in arguments or arguments.get(key) is None:
        return default
    value = arguments.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}")
    return value


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("scheduled_for must include timezone information")
    return parsed.astimezone(timezone.utc)


def _read_message() -> dict[str, Any] | None:
    content_length = None
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        header = line.decode("utf-8").strip()
        if header.lower().startswith("content-length:"):
            content_length = int(header.split(":", 1)[1].strip())
    if content_length is None:
        raise ValueError("missing Content-Length header")
    body = sys.stdin.buffer.read(content_length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _write_message(payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def main() -> None:
    server = McpServer()
    server.serve_forever()


if __name__ == "__main__":
    main()
