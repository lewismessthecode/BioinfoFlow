from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class StreamToolCall:
    call_id: str
    name: str
    provider_call_id: str | None = None
    arguments_text: str = ""
    index: int = 0

    def arguments(self) -> dict[str, Any]:
        raw = self.arguments_text.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


@dataclass
class StreamCompletionResult:
    text: str
    thinking: str
    tool_calls: list[StreamToolCall]
    token_usage: dict[str, Any] | None
    streamed: bool


@dataclass
class ToolCallDelta:
    index: int
    call_id: str | None = None
    name: str | None = None
    arguments_delta: str = ""


async def collect_stream_result(response: Any) -> StreamCompletionResult:
    if not hasattr(response, "__aiter__"):
        return StreamCompletionResult(
            text="",
            thinking="",
            tool_calls=[],
            token_usage=_extract_usage(response),
            streamed=False,
        )

    text_parts: list[str] = []
    thinking_parts: list[str] = []
    tool_calls: dict[int, StreamToolCall] = {}
    token_usage: dict[str, Any] | None = None

    async for chunk in response:
        token_usage = _merge_usage(token_usage, _extract_usage(chunk))
        thinking_delta = extract_reasoning_delta(chunk)
        if thinking_delta:
            thinking_parts.append(thinking_delta)
        text_delta = extract_text_delta(chunk)
        if text_delta:
            text_parts.append(text_delta)
        for delta in extract_tool_call_deltas(chunk):
            state = tool_calls.setdefault(
                delta.index,
                StreamToolCall(
                    call_id=delta.call_id or f"tool_call_{delta.index + 1}",
                    name=delta.name or "",
                    provider_call_id=delta.call_id,
                    index=delta.index,
                ),
            )
            if delta.call_id:
                state.call_id = delta.call_id
                state.provider_call_id = delta.call_id
            if delta.name:
                state.name = delta.name
            if delta.arguments_delta:
                state.arguments_text += delta.arguments_delta

    return StreamCompletionResult(
        text="".join(text_parts).strip(),
        thinking="".join(thinking_parts).strip(),
        tool_calls=[tool_calls[index] for index in sorted(tool_calls)],
        token_usage=token_usage,
        streamed=True,
    )


def extract_text_delta(chunk: Any) -> str:
    delta = _choice_delta(chunk)
    return _extract_content_value(delta, ("content", "text", "content_text"))


def extract_reasoning_delta(chunk: Any) -> str:
    delta = _choice_delta(chunk)
    return _extract_content_value(
        delta,
        (
            "reasoning_content",
            "reasoning",
            "reasoning_text",
            "thinking",
            "thinking_content",
        ),
    )


def extract_tool_call_deltas(chunk: Any) -> list[ToolCallDelta]:
    delta = _choice_delta(chunk)
    raw_tool_calls = _get(delta, "tool_calls")
    if not isinstance(raw_tool_calls, list):
        return []
    result: list[ToolCallDelta] = []
    for raw in raw_tool_calls:
        if not isinstance(raw, dict) and not hasattr(raw, "__dict__"):
            continue
        function = _get(raw, "function") or {}
        index_value = _get(raw, "index")
        try:
            index = int(index_value or 0)
        except (TypeError, ValueError):
            index = 0
        result.append(
            ToolCallDelta(
                index=index,
                call_id=_string_or_none(_get(raw, "id")),
                name=_string_or_none(_get(function, "name")),
                arguments_delta=_string_or_none(_get(function, "arguments")) or "",
            )
        )
    return result


def extract_response_thinking(response: Any) -> str:
    message = _response_message(response)
    return _extract_content_value(
        message,
        (
            "reasoning_content",
            "reasoning",
            "reasoning_text",
            "thinking",
            "thinking_content",
        ),
    )


def _choice_delta(chunk: Any) -> Any:
    choices = _get(chunk, "choices") or []
    if not choices:
        return {}
    first = choices[0]
    return _get(first, "delta") or {}


def _response_message(response: Any) -> Any:
    choices = _get(response, "choices") or []
    if not choices:
        return {}
    return _get(choices[0], "message") or {}


def _extract_content_value(source: Any, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _get(source, key)
        text = _normalize_text_value(value)
        if text:
            return text
    return ""


def _normalize_text_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
            else:
                text = getattr(item, "text", None) or getattr(item, "content", None)
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)
    return ""


def _extract_usage(payload: Any) -> dict[str, Any] | None:
    usage = _get(payload, "usage")
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if isinstance(usage, dict):
        return usage
    return {key: value for key, value in vars(usage).items() if not key.startswith("_")}


def _merge_usage(
    current: dict[str, Any] | None,
    next_usage: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not next_usage:
        return current
    if not current:
        return dict(next_usage)
    merged = dict(current)
    for key, value in next_usage.items():
        if isinstance(value, int) and isinstance(merged.get(key), int):
            merged[key] += value
        else:
            merged[key] = value
    return merged


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)
