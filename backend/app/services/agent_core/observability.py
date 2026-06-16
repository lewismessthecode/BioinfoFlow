from __future__ import annotations

from typing import Any


_MAX_LOG_MESSAGE_CHARS = 200


def agent_event_log_fields(
    *,
    session_id: str,
    turn_id: str | None,
    seq: int,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "session_id": session_id,
        "turn_id": turn_id,
        "seq": seq,
        "event_type": event_type,
    }
    payload = payload or {}
    for key in ("status", "termination_reason", "error_code"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            fields[key] = value
    error_message = payload.get("error_message")
    if isinstance(error_message, str) and error_message:
        fields["error_message"] = truncate_log_value(error_message)
    return fields


def truncate_log_value(value: str, limit: int = _MAX_LOG_MESSAGE_CHARS) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."


__all__ = ["agent_event_log_fields", "truncate_log_value"]
