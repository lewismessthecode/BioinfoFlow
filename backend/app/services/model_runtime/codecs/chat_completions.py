from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from typing import Any

from app.services.model_runtime.backend.naming import litellm_model_name
from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ModelEvent,
    ModelInvocation,
    ReasoningDelta,
    TextDelta,
    TextPart,
    ToolCallDelta,
    ToolCallPart,
    ToolResultPart,
    UsageReport,
)


class ChatCompletionsCodec:
    wire_protocol = "chat_completions"

    def encode_request(self, invocation: ModelInvocation) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        if invocation.instructions:
            messages.append({"role": "system", "content": invocation.instructions})
        for item in invocation.input_items:
            if isinstance(item, TextPart):
                messages.append(
                    {
                        "role": "assistant" if item.phase is not None else "user",
                        "content": item.text,
                    }
                )
            elif isinstance(item, ToolCallPart):
                tool_call = _encode_tool_call(item)
                if messages and _is_assistant_message(messages[-1]):
                    messages[-1].setdefault("tool_calls", []).append(tool_call)
                else:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [tool_call],
                        }
                    )
            elif isinstance(item, ToolResultPart):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": item.call_id,
                        "content": item.output,
                    }
                )

        request: dict[str, Any] = {
            "model": litellm_model_name(
                invocation.target.provider_kind,
                invocation.target.model_name,
            ),
            "messages": messages,
            "stream": invocation.stream,
            "max_tokens": invocation.max_output_tokens,
        }
        if invocation.tools:
            request["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in invocation.tools
            ]
        return request

    async def decode_response(self, response: Any) -> AsyncIterator[ModelEvent]:
        if hasattr(response, "__aiter__"):
            async for event in self._decode_stream(response):
                yield event
            return

        choice = _first_choice(response)
        message = _get(choice, "message") or {}
        reasoning = _extract_content(
            message,
            ("reasoning_content", "reasoning", "reasoning_text", "thinking", "thinking_content"),
        )
        if reasoning:
            yield ReasoningDelta(text=reasoning)
        text = _extract_content(message, ("content", "text", "content_text"))
        if text:
            yield TextDelta(text=text, phase="final_answer")
        for index, raw_call in enumerate(_get(message, "tool_calls") or []):
            event = _tool_call_delta(raw_call, default_index=index)
            if event is not None:
                yield event
        usage = _usage_report(response)
        if usage is not None:
            yield usage
        yield _completion_metadata(response, choice)

    def finalize_event(
        self,
        invocation: ModelInvocation,
        request: dict[str, Any],
        event: ModelEvent,
    ) -> ModelEvent:
        del invocation, request
        return event

    async def _decode_stream(self, response: Any) -> AsyncIterator[ModelEvent]:
        response_id: str | None = None
        finish_reason: str | None = None
        usage: UsageReport | None = None
        async for chunk in response:
            response_id = _string_or_none(_get(chunk, "id")) or response_id
            choice = _first_choice(chunk)
            chunk_finish_reason = _string_or_none(_get(choice, "finish_reason"))
            finish_reason = chunk_finish_reason or finish_reason
            delta = _get(choice, "delta") or {}
            reasoning = _extract_content(
                delta,
                ("reasoning_content", "reasoning", "reasoning_text", "thinking", "thinking_content"),
            )
            if reasoning:
                yield ReasoningDelta(text=reasoning)
            text = _extract_content(delta, ("content", "text", "content_text"))
            if text:
                yield TextDelta(text=text, phase="final_answer")
            for raw_call in _get(delta, "tool_calls") or []:
                event = _tool_call_delta(raw_call)
                if event is not None:
                    yield event
            usage = _merge_usage_reports(usage, _usage_report(chunk))
        if usage is not None:
            yield usage
        yield CompletionMetadata(
            response_id=response_id,
            finish_reason=finish_reason,
        )


def _encode_tool_call(item: ToolCallPart) -> dict[str, Any]:
    return {
        "id": item.call_id,
        "type": "function",
        "function": {
            "name": item.name,
            "arguments": json.dumps(
                item.arguments,
                separators=(",", ":"),
                default=str,
            ),
        },
    }


def _is_assistant_message(message: dict[str, Any]) -> bool:
    return message.get("role") == "assistant" and (
        "tool_calls" not in message or isinstance(message.get("tool_calls"), list)
    )


def _first_choice(payload: Any) -> Any:
    choices = _get(payload, "choices") or []
    return choices[0] if choices else {}


def _tool_call_delta(raw: Any, *, default_index: int = 0) -> ToolCallDelta | None:
    function = _get(raw, "function") or {}
    name = _string_or_none(_get(function, "name"))
    arguments = _argument_text(_get(function, "arguments"))
    call_id = _string_or_none(_get(raw, "id"))
    raw_index = _get(raw, "index")
    try:
        index = int(raw_index) if raw_index is not None else default_index
    except (TypeError, ValueError):
        index = default_index
    if name is None and call_id is None and not arguments:
        return None
    return ToolCallDelta(
        index=index,
        call_id=call_id,
        name=name,
        arguments_delta=arguments,
    )


def _completion_metadata(response: Any, choice: Any) -> CompletionMetadata:
    return CompletionMetadata(
        response_id=_string_or_none(_get(response, "id")),
        finish_reason=_string_or_none(_get(choice, "finish_reason")),
    )


def _usage_report(payload: Any) -> UsageReport | None:
    usage = _get(payload, "usage")
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        dumped = usage.model_dump()
        if isinstance(dumped, Mapping):
            usage = dumped
    input_tokens = _int_or_zero(_get(usage, "prompt_tokens"))
    output_tokens = _int_or_zero(_get(usage, "completion_tokens"))
    total_tokens = _int_or_zero(_get(usage, "total_tokens"))
    prompt_details = _get(usage, "prompt_tokens_details") or {}
    completion_details = _get(usage, "completion_tokens_details") or {}
    return UsageReport(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=_optional_int(_get(prompt_details, "cached_tokens")),
        reasoning_tokens=_optional_int(_get(completion_details, "reasoning_tokens")),
    )


def _merge_usage_reports(
    current: UsageReport | None,
    next_usage: UsageReport | None,
) -> UsageReport | None:
    if next_usage is None:
        return current
    if current is None:
        return next_usage
    return UsageReport(
        input_tokens=current.input_tokens + next_usage.input_tokens,
        output_tokens=current.output_tokens + next_usage.output_tokens,
        total_tokens=current.total_tokens + next_usage.total_tokens,
        cached_input_tokens=_sum_optional_ints(
            current.cached_input_tokens,
            next_usage.cached_input_tokens,
        ),
        reasoning_tokens=_sum_optional_ints(
            current.reasoning_tokens,
            next_usage.reasoning_tokens,
        ),
    )


def _extract_content(source: Any, keys: tuple[str, ...]) -> str:
    for key in keys:
        text = _normalize_text(_get(source, key))
        if text:
            return text
    return ""


def _normalize_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            else:
                text = _get(item, "text") or _get(item, "content")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _argument_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return json.dumps(value, separators=(",", ":"), default=str)
    return ""


def _int_or_zero(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _sum_optional_ints(current: int | None, next_value: int | None) -> int | None:
    if current is None:
        return next_value
    if next_value is None:
        return current
    return current + next_value
