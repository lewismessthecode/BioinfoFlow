from __future__ import annotations

from typing import Any


def text_part(text: str) -> dict[str, str]:
    return {"type": "text", "text": text}


def tool_calls_part(tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "tool_calls", "tool_calls": tool_calls}


def parts_to_text(parts: list[dict[str, Any]] | None) -> str:
    text_parts: list[str] = []
    for part in parts or []:
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            text_parts.append(part["text"])
    return "\n".join(text_parts).strip()


def provider_message_from_parts(
    role: str,
    parts: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = parts_to_text(parts)
    if role == "assistant":
        tool_calls: list[dict[str, Any]] = []
        for part in parts:
            if part.get("type") == "tool_calls" and isinstance(part.get("tool_calls"), list):
                tool_calls.extend(part["tool_calls"])
        message: dict[str, Any] = {"role": role, "content": text}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return message
    if role == "tool":
        message = {"role": role, "content": text}
        tool_call_id = (metadata or {}).get("tool_call_id")
        if tool_call_id:
            message["tool_call_id"] = str(tool_call_id)
        return message
    return {"role": role, "content": text}
