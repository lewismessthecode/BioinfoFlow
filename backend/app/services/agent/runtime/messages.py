"""Plain-dict message helpers matching the OpenAI Chat Completions API format.

Drops LangChain message types from the hot path. All messages are plain dicts:
    {"role": "user", "content": str}
    {"role": "assistant", "content": str, "tool_calls": [ToolCall]}
    {"role": "tool", "tool_call_id": str, "content": str}

ToolCall format:
    {"id": str, "type": "function", "function": {"name": str, "arguments": str}}
"""

from __future__ import annotations

import json
from typing import Any


def make_user_message(text: str) -> dict[str, Any]:
    """Create a user message dict."""
    return {"role": "user", "content": text}


def make_tool_results(
    tool_calls: list[dict[str, Any]],
    results: list[str],
) -> list[dict[str, Any]]:
    """Create tool-role messages from tool call results.

    Args:
        tool_calls: List of tool call dicts (each with "id" key).
        results: Corresponding result strings, one per tool call.

    Returns:
        A list of tool-role messages, one per tool call.
    """
    return [
        {"role": "tool", "tool_call_id": call["id"], "content": result}
        for call, result in zip(tool_calls, results)
    ]


def extract_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract tool calls from an assistant message.

    Returns:
        List of dicts with keys: id, name, input.
    """
    return [
        {
            "id": tc["id"],
            "name": tc["function"]["name"],
            "input": json.loads(tc["function"]["arguments"]),
        }
        for tc in message.get("tool_calls", [])
    ]


def extract_text(message: dict[str, Any]) -> str:
    """Extract text content from an assistant message."""
    return message.get("content", "") or ""


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate token count using a rough heuristic: len(json) // 4.

    This is provider-agnostic and avoids importing tiktoken or similar.
    """
    try:
        raw = json.dumps(messages, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        raw = str(messages)
    return len(raw) // 4
