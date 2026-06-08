from __future__ import annotations

from typing import Any


DEFAULT_TOOL_RESULT_LIMIT = 12000


def normalize_tool_result(result: dict[str, Any], limit: int = DEFAULT_TOOL_RESULT_LIMIT) -> tuple[dict[str, Any], str | None]:
    normalized = dict(result)
    summary: str | None = None
    for key, value in list(normalized.items()):
        if isinstance(value, str) and len(value) > limit:
            normalized[key] = value[:limit] + "\n[truncated]"
            summary = "Large text output was truncated to the tool result budget."
    return normalized, summary
