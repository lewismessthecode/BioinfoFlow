from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from typing import Any

from app.services.model_runtime.backend.naming import litellm_model_name
from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ModelEvent,
    ModelInvocation,
    ModelWarning,
    Phase,
    ReasoningDelta,
    ResponsesContinuation,
    TextDelta,
    TextPart,
    ToolCallDelta,
    ToolCallPart,
    ToolResultPart,
    UsageReport,
)
from app.services.model_runtime.errors import ModelError


_IGNORED_STREAM_EVENTS = {
    "response.created",
    "response.in_progress",
    "response.output_item.done",
    "response.content_part.added",
    "response.content_part.done",
    "response.output_text.done",
    "response.function_call_arguments.done",
    "response.reasoning_summary_part.added",
    "response.reasoning_summary_part.done",
    "response.reasoning_summary_text.done",
}


class ResponsesCodec:
    wire_protocol = "responses"

    def encode_request(self, invocation: ModelInvocation) -> dict[str, Any]:
        input_items: list[dict[str, Any]] = []
        continuation = invocation.continuation
        if continuation is not None and not continuation.matches_target(
            invocation.target
        ):
            continuation = None
        if continuation is not None:
            input_items.extend(
                _jsonable(item)
                for item in continuation.opaque_output_items()
            )
        canonical_input_count = (
            continuation.canonical_input_count
            if continuation is not None
            else 0
        )
        for item in invocation.input_items[canonical_input_count:]:
            if isinstance(item, TextPart):
                if item.phase is None:
                    input_items.append(
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": item.text}],
                        }
                    )
                else:
                    input_items.append(
                        {
                            "role": "assistant",
                            "content": item.text,
                        }
                    )
            elif isinstance(item, ToolCallPart):
                input_items.append(
                    {
                        "type": "function_call",
                        "call_id": item.call_id,
                        "name": item.name,
                        "arguments": json.dumps(
                            item.arguments,
                            separators=(",", ":"),
                            default=str,
                        ),
                    }
                )
            elif isinstance(item, ToolResultPart):
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": item.output,
                    }
                )

        request: dict[str, Any] = {
            "model": _responses_model_name(
                invocation.target.provider_kind,
                invocation.target.model_name,
            ),
            "instructions": invocation.instructions,
            "input": input_items,
            "stream": invocation.stream,
            "max_output_tokens": invocation.max_output_tokens,
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }
        if invocation.tools:
            request["tools"] = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
                for tool in invocation.tools
            ]
        return request

    def finalize_event(
        self,
        invocation: ModelInvocation,
        request: dict[str, Any],
        event: ModelEvent,
    ) -> ModelEvent:
        if not isinstance(event, CompletionMetadata) or event.continuation is None:
            return event
        replay_input = _merge_replay_input(
            request.get("input"),
            event.continuation.opaque_output_items(),
        )
        return CompletionMetadata(
            response_id=event.response_id,
            finish_reason=event.finish_reason,
            continuation=ResponsesContinuation(
                response_id=event.response_id,
                output_items=replay_input,
                canonical_input_count=len(invocation.input_items),
                target=invocation.target.continuation_target(),
            ),
        )

    async def decode_response(self, response: Any) -> AsyncIterator[ModelEvent]:
        if hasattr(response, "__aiter__"):
            async for event in self._decode_stream(response):
                yield event
            return

        response_id = _string_or_none(_get(response, "id"))
        status = _string_or_none(_get(response, "status"))
        if status in {"failed", "incomplete"}:
            raise _terminal_error(
                {"response": response},
                event_type=f"response.{status}",
                replay_safe=True,
            )
        output = _sequence(_get(response, "output"))
        for index, item in enumerate(output):
            for event in _decode_output_item(item, index=index):
                yield event
        usage = _usage_report(response)
        if usage is not None:
            yield usage
        yield CompletionMetadata(
            response_id=response_id,
            finish_reason=_string_or_none(_get(response, "status")),
            continuation=_continuation(response_id, output),
        )

    async def _decode_stream(self, response: Any) -> AsyncIterator[ModelEvent]:
        response_id: str | None = None
        finish_reason: str | None = None
        phases_by_index: dict[int, Phase] = {}
        phases_by_item_id: dict[str, Phase] = {}
        output_items: dict[int, dict[str, Any]] = {}
        completed = False
        output_yielded = False
        refusal_parts: list[str] = []
        refusal_emitted = False

        async for chunk in response:
            event_type = _string_or_none(_get(chunk, "type"))
            if event_type == "response.created" or event_type == "response.in_progress":
                payload = _get(chunk, "response") or {}
                response_id = _string_or_none(_get(payload, "id")) or response_id
                continue
            if event_type == "response.output_item.added":
                index = _event_index(chunk)
                item = _get(chunk, "item") or {}
                output_items[index] = _jsonable(item)
                item_id = _string_or_none(_get(item, "id"))
                item_type = _string_or_none(_get(item, "type"))
                if item_type == "message":
                    phase = _phase(_get(item, "phase"))
                    phases_by_index[index] = phase
                    if item_id is not None:
                        phases_by_item_id[item_id] = phase
                elif item_type == "function_call":
                    output_yielded = True
                    yield ToolCallDelta(
                        index=index,
                        call_id=_string_or_none(_get(item, "call_id")),
                        name=_string_or_none(_get(item, "name")),
                        arguments_delta=_argument_text(_get(item, "arguments")),
                    )
                elif item_type not in {"reasoning"}:
                    yield _unsupported_item_warning(item_type)
                continue
            if event_type == "response.output_item.done":
                output_items[_event_index(chunk)] = _jsonable(_get(chunk, "item") or {})
                continue
            if event_type == "response.output_text.delta":
                index = _event_index(chunk)
                item_id = _string_or_none(_get(chunk, "item_id"))
                phase = _phase(
                    _get(chunk, "phase")
                    or phases_by_item_id.get(item_id or "")
                    or phases_by_index.get(index)
                )
                delta = _text(_get(chunk, "delta"))
                if delta:
                    output_yielded = True
                    yield TextDelta(text=delta, phase=phase)
                continue
            if event_type == "response.function_call_arguments.delta":
                output_yielded = True
                yield ToolCallDelta(
                    index=_event_index(chunk),
                    call_id=None,
                    name=None,
                    arguments_delta=_text(_get(chunk, "delta")),
                )
                continue
            if event_type in {
                "response.reasoning_summary_text.delta",
                "response.reasoning_text.delta",
            }:
                delta = _text(_get(chunk, "delta"))
                if delta:
                    output_yielded = True
                    yield ReasoningDelta(text=delta)
                continue
            if event_type == "response.refusal.delta":
                refusal = _text(_get(chunk, "delta"))
                if refusal:
                    refusal_parts.append(refusal)
                continue
            if event_type == "response.refusal.done":
                refusal = _text(_get(chunk, "refusal")) or "".join(refusal_parts)
                yield ModelWarning(
                    code="response_refusal",
                    message=refusal or "The model refused the request.",
                )
                refusal_emitted = True
                continue
            if event_type in {"response.failed", "response.incomplete", "error"}:
                raise _terminal_error(
                    chunk,
                    event_type=event_type,
                    replay_safe=not output_yielded,
                )
            if event_type == "response.completed":
                completed = True
                payload = _get(chunk, "response") or {}
                response_id = _string_or_none(_get(payload, "id")) or response_id
                finish_reason = _string_or_none(_get(payload, "status"))
                if refusal_parts and not refusal_emitted:
                    yield ModelWarning(
                        code="response_refusal",
                        message="".join(refusal_parts),
                    )
                    refusal_emitted = True
                final_output = _sequence(_get(payload, "output"))
                if final_output:
                    output_items = {
                        index: _jsonable(item)
                        for index, item in enumerate(final_output)
                    }
                usage = _usage_report(payload)
                if usage is not None:
                    yield usage
                yield CompletionMetadata(
                    response_id=response_id,
                    finish_reason=finish_reason,
                    continuation=_continuation(
                        response_id,
                        [output_items[index] for index in sorted(output_items)],
                    ),
                )
                continue
            if event_type in _IGNORED_STREAM_EVENTS:
                continue
            yield ModelWarning(
                code="unsupported_response_event",
                message=(
                    "Unsupported Responses stream event type: "
                    f"{event_type or '<missing>'}"
                ),
            )

        if not completed:
            raise _terminal_error(
                {"code": "stream_terminated"},
                event_type="error",
                replay_safe=not output_yielded,
            )


def _decode_output_item(item: Any, *, index: int) -> list[ModelEvent]:
    item_type = _string_or_none(_get(item, "type"))
    if item_type == "reasoning":
        events: list[ModelEvent] = []
        for summary in _sequence(_get(item, "summary")):
            text = _text(_get(summary, "text"))
            if text:
                events.append(ReasoningDelta(text=text))
        return events
    if item_type == "message":
        phase = _phase(_get(item, "phase"))
        events = []
        for content in _sequence(_get(item, "content")):
            content_type = _string_or_none(_get(content, "type"))
            if content_type == "output_text":
                text = _text(_get(content, "text"))
                if text:
                    events.append(TextDelta(text=text, phase=phase))
            elif content_type == "refusal":
                events.append(
                    ModelWarning(
                        code="response_refusal",
                        message=(
                            _text(_get(content, "refusal") or _get(content, "text"))
                            or "The model refused the request."
                        ),
                    )
                )
            else:
                events.append(
                    ModelWarning(
                        code="unsupported_response_content",
                        message=(
                            "Unsupported Responses message content type: "
                            f"{content_type or '<missing>'}"
                        ),
                    )
                )
        return events
    if item_type == "function_call":
        return [
            ToolCallDelta(
                index=index,
                call_id=_string_or_none(_get(item, "call_id")),
                name=_string_or_none(_get(item, "name")),
                arguments_delta=_argument_text(_get(item, "arguments")),
            )
        ]
    return [_unsupported_item_warning(item_type)]


def _unsupported_item_warning(item_type: str | None) -> ModelWarning:
    return ModelWarning(
        code="unsupported_response_item",
        message=f"Unsupported Responses output item type: {item_type or '<missing>'}",
    )


def _usage_report(payload: Any) -> UsageReport | None:
    usage = _get(payload, "usage")
    if usage is None:
        return None
    input_details = _get(usage, "input_tokens_details") or {}
    output_details = _get(usage, "output_tokens_details") or {}
    return UsageReport(
        input_tokens=_int_or_zero(_get(usage, "input_tokens")),
        output_tokens=_int_or_zero(_get(usage, "output_tokens")),
        total_tokens=_int_or_zero(_get(usage, "total_tokens")),
        cached_input_tokens=_optional_int(_get(input_details, "cached_tokens")),
        reasoning_tokens=_optional_int(_get(output_details, "reasoning_tokens")),
    )


def _continuation(
    response_id: str | None,
    output: list[Any],
) -> ResponsesContinuation | None:
    if response_id is None and not output:
        return None
    return ResponsesContinuation(
        response_id=response_id,
        output_items=tuple(_jsonable(item) for item in output),
    )


def _merge_replay_input(
    request_input: Any,
    current_output: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    candidates = [
        *(
            item
            for item in request_input
            if isinstance(request_input, (list, tuple)) and isinstance(item, dict)
        ),
        *current_output,
    ]
    for item in candidates:
        key = _stable_replay_key(item)
        if key is not None and key in seen:
            continue
        if key is not None:
            seen.add(key)
        merged.append(item)
    return tuple(merged)


def _stable_replay_key(item: dict[str, Any]) -> tuple[str, str] | None:
    item_id = item.get("id")
    if isinstance(item_id, str) and item_id:
        return "id", item_id
    if item.get("type") == "function_call":
        call_id = item.get("call_id")
        if isinstance(call_id, str) and call_id:
            return "function_call", call_id
    return None


def _terminal_error(
    event: Any,
    *,
    event_type: str,
    replay_safe: bool,
) -> ModelError:
    payload = _get(event, "response") or event
    error = _get(payload, "error") or _get(event, "error") or {}
    if event_type == "response.incomplete":
        details = _get(payload, "incomplete_details") or {}
        code = _safe_identifier(_get(details, "reason"))
    else:
        code = _safe_identifier(_get(error, "code") or _get(event, "code"))

    category, http_status, retryable, message = _terminal_error_classification(code)
    return ModelError(
        category=category,
        message=message,
        http_status=http_status,
        provider_code=code,
        retryable=retryable,
        replay_safe=replay_safe,
    )


def _terminal_error_classification(
    code: str | None,
) -> tuple[str, int | None, bool, str]:
    if code in {"rate_limit_exceeded", "rate_limit_error"}:
        return (
            "rate_limit",
            429,
            True,
            "The model provider rate limit was exceeded.",
        )
    if code in {"server_error", "internal_error", "overloaded"}:
        return (
            "service_unavailable",
            503,
            True,
            "The model provider is temporarily unavailable.",
        )
    if code in {"timeout", "request_timeout"}:
        return "timeout", 408, True, "The model provider request timed out."
    if code == "stream_terminated":
        return "connection", None, True, "The model provider connection failed."
    if code in {"invalid_request", "invalid_prompt", "invalid_tool_schema"}:
        return "invalid_request", 400, False, "The model provider rejected the request."
    if code in {"invalid_api_key", "authentication_error"}:
        return "authentication", 401, False, "Model provider authentication failed."
    if code in {"permission_denied", "authorization_error"}:
        return "authorization", 403, False, "Model provider authorization failed."
    return "provider", None, False, "Model provider request failed."


def _safe_identifier(value: Any) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 256:
        return None
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:/-")
    return (
        value if value[0].isalnum() and all(char in allowed for char in value) else None
    )


def _responses_model_name(provider_kind: str, model_name: str) -> str:
    name = litellm_model_name(provider_kind, model_name)
    if provider_kind == "openai" and not name.startswith("openai/"):
        return f"openai/{name}"
    return name


def _phase(value: Any) -> Phase:
    return value if value in {"commentary", "final_answer"} else "final_answer"


def _event_index(event: Any) -> int:
    value = _get(event, "output_index")
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _argument_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return json.dumps(value, separators=(",", ":"), default=str)
    return ""


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump(exclude_none=False)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _get(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _int_or_zero(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
