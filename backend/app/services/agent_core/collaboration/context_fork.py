from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any


class InvalidForkTurnsError(ValueError):
    code = "invalid_fork_turns"

    def __init__(self) -> None:
        super().__init__(self.code)


_NON_SEMANTIC_KINDS = {
    "agent_lifecycle",
    "approval",
    "inter_agent_message",
    "lifecycle",
    "mailbox",
    "steer",
    "tool_calls",
}


def fork_agent_context(
    items: Sequence[Any],
    *,
    fork_turns: str,
) -> list[dict[str, Any]]:
    """Return a provider-neutral, model-visible snapshot of parent history."""

    turn_limit = _parse_fork_turns(fork_turns)
    if turn_limit == 0:
        return []

    semantic = [
        normalized
        for item in items
        if (normalized := _semantic_message(item)) is not None
    ]
    if turn_limit is None:
        return semantic

    stable_prefix: list[dict[str, Any]] = []
    conversation: list[dict[str, Any]] = []
    for item in semantic:
        if (
            item["role"] in {"system", "developer"}
            or _metadata(item).get("kind") == "compaction_summary"
        ):
            stable_prefix.append(item)
        else:
            conversation.append(item)
    user_indices = [
        index for index, item in enumerate(conversation) if item["role"] == "user"
    ]
    if not user_indices:
        return stable_prefix
    start = user_indices[-turn_limit] if len(user_indices) >= turn_limit else user_indices[0]
    return [*stable_prefix, *conversation[start:]]


def _parse_fork_turns(value: object) -> int | None:
    if value == "none":
        return 0
    if value == "all":
        return None
    if isinstance(value, str) and value.isdecimal() and int(value) > 0:
        return int(value)
    raise InvalidForkTurnsError()


def _semantic_message(item: Any) -> dict[str, Any] | None:
    status = _field(item, "status", "committed")
    if status != "committed":
        return None
    role = _field(item, "role")
    if role not in {"system", "developer", "user", "assistant"}:
        return None
    if role == "assistant" and _contains_tool_call_structure(item):
        return None
    metadata = _field(item, "message_metadata") or _field(item, "metadata") or {}
    if not isinstance(metadata, Mapping):
        metadata = {}
    kind = metadata.get("kind")
    if kind in _NON_SEMANTIC_KINDS:
        return None

    raw_parts = _field(item, "content_parts")
    if raw_parts is None:
        content = _field(item, "content")
        raw_parts = [{"type": "text", "text": content}] if isinstance(content, str) else []
    if not isinstance(raw_parts, Sequence) or isinstance(raw_parts, (str, bytes)):
        return None

    parts: list[dict[str, Any]] = []
    for raw_part in raw_parts:
        if not isinstance(raw_part, Mapping) or raw_part.get("type") != "text":
            continue
        text = raw_part.get("text")
        if not isinstance(text, str) or not text:
            continue
        if role == "assistant" and kind != "compaction_summary":
            phase = raw_part.get("phase")
            if phase not in {None, "final_answer"}:
                continue
        parts.append(deepcopy(dict(raw_part)))
    if not parts:
        return None
    safe_metadata = _semantic_metadata(metadata)
    return {
        "role": role,
        "content_parts": parts,
        "message_metadata": safe_metadata or None,
    }


def _field(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _metadata(item: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = item.get("message_metadata")
    return metadata if isinstance(metadata, Mapping) else {}


def _semantic_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(metadata[key])
        for key in ("kind", "_temporal_context", "continuity_state")
        if key in metadata
    }


_TOOL_CALL_TYPES = frozenset(
    {
        "function_call",
        "function_calls",
        "tool_call",
        "tool_calls",
        "tool_use",
    }
)


def _contains_tool_call_structure(value: Any) -> bool:
    if isinstance(value, Mapping):
        if any(key in value for key in _TOOL_CALL_TYPES):
            return True
        item_type = value.get("type")
        if isinstance(item_type, str) and item_type.lower() in _TOOL_CALL_TYPES:
            return True
        return any(
            _contains_tool_call_structure(value[field])
            for field in ("content", "content_parts", "parts", "output")
            if field in value
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_tool_call_structure(item) for item in value)
    class_name = type(value).__name__.lower()
    if class_name in {"functioncallpart", "toolcallpart", "toolusepart"}:
        return True
    for attribute in (
        "content",
        "content_parts",
        "parts",
        "output",
        "function_call",
        "tool_call",
        "tool_calls",
        "tool_use",
    ):
        nested = getattr(value, attribute, None)
        if nested is not None and _contains_tool_call_structure(nested):
            return True
    return False
