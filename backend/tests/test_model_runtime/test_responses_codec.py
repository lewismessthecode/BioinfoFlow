from __future__ import annotations

from collections.abc import AsyncIterator
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.model_runtime.codecs.responses import ResponsesCodec
from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ModelInvocation,
    ModelTarget,
    ModelWarning,
    ReasoningDelta,
    ResponsesContinuation,
    TextDelta,
    TextPart,
    ToolCallDelta,
    ToolCallPart,
    ToolDefinition,
    ToolResultPart,
    UsageReport,
)
from app.services.model_runtime.errors import ModelError
from app.services.model_runtime.gateway import ModelGateway


FIXTURES = Path(__file__).parent / "fixtures/responses"


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def _invocation(
    *,
    stream: bool = False,
    continuation: ResponsesContinuation | None = None,
) -> ModelInvocation:
    return ModelInvocation(
        target=ModelTarget(
            endpoint_id="endpoint-responses",
            provider_kind="openai",
            model_name="gpt-test",
            wire_protocol="responses",
            base_url="https://relay.example/v1",
            api_key="secret",
        ),
        instructions="Be precise.",
        input_items=(
            TextPart(text="List projects."),
            ToolCallPart(
                call_id="call-old",
                name="projects__list",
                arguments={"limit": 1},
            ),
            ToolResultPart(
                call_id="call-old",
                output='{"projects":[]}',
            ),
            TextPart(text="No projects found.", phase="commentary"),
        ),
        tools=(
            ToolDefinition(
                name="projects__list",
                description="List projects.",
                parameters={"type": "object", "properties": {}},
            ),
        ),
        stream=stream,
        max_output_tokens=512,
        allow_reasoning=True,
        continuation=continuation,
    )


def test_encode_request_uses_stateless_encrypted_reasoning_continuation() -> None:
    opaque_items = (
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "List projects."}],
        },
        {
            "id": "reasoning-old",
            "type": "reasoning",
            "encrypted_content": "opaque-old-reasoning",
            "summary": [],
        },
        {
            "id": "function-old",
            "type": "function_call",
            "call_id": "call-continuation",
            "name": "projects__list",
            "arguments": "{}",
        },
    )
    invocation = _invocation(
        stream=True,
        continuation=ResponsesContinuation(
            response_id="resp-old",
            output_items=opaque_items,
            canonical_input_count=2,
            target=_invocation().target.continuation_target(),
        ),
    )

    request = ResponsesCodec().encode_request(invocation)

    assert request == {
        "model": "openai/gpt-test",
        "instructions": "Be precise.",
        "input": [
            *opaque_items,
            {
                "type": "function_call_output",
                "call_id": "call-old",
                "output": '{"projects":[]}',
            },
            {
                "role": "assistant",
                "content": "No projects found.",
            },
        ],
        "tools": [
            {
                "type": "function",
                "name": "projects__list",
                "description": "List projects.",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
        "stream": True,
        "max_output_tokens": 512,
        "store": False,
        "include": ["reasoning.encrypted_content"],
    }
    assert "previous_response_id" not in request


def test_encode_request_discards_continuation_bound_to_another_target() -> None:
    invocation = _invocation(
        continuation=ResponsesContinuation(
            response_id="resp-other",
            output_items=(
                {
                    "type": "reasoning",
                    "encrypted_content": "must-not-cross-targets",
                },
            ),
            canonical_input_count=4,
            target=ModelTarget(
                endpoint_id="fallback-endpoint",
                provider_kind="openai",
                model_name="fallback-model",
                wire_protocol="responses",
                base_url="https://fallback.example/v1",
            ).continuation_target(),
        )
    )

    request = ResponsesCodec().encode_request(invocation)

    assert request["input"][0] == {
        "role": "user",
        "content": [{"type": "input_text", "text": "List projects."}],
    }
    assert "must-not-cross-targets" not in repr(request)


@pytest.mark.asyncio
async def test_responses_codec_builds_complete_ordered_stateless_replay_across_tool_rounds() -> (
    None
):
    user = TextPart(text="Start.")
    first_message = TextPart(text="First call.", phase="commentary")
    first_call = ToolCallPart(call_id="call-1", name="step", arguments={"n": 1})
    first_result = ToolResultPart(call_id="call-1", output="one")
    second_message = TextPart(text="Second call.", phase="commentary")
    second_call = ToolCallPart(call_id="call-2", name="step", arguments={"n": 2})
    second_result = ToolResultPart(call_id="call-2", output="two")
    first_output = [
        {
            "id": "reasoning-1",
            "type": "reasoning",
            "encrypted_content": "encrypted-1",
            "summary": [],
        },
        {
            "id": "message-1",
            "type": "message",
            "role": "assistant",
            "phase": "commentary",
            "content": [{"type": "output_text", "text": "First call."}],
        },
        {
            "id": "function-1",
            "type": "function_call",
            "call_id": "call-1",
            "name": "step",
            "arguments": '{"n":1}',
        },
    ]
    second_output = [
        {
            "id": "reasoning-2",
            "type": "reasoning",
            "encrypted_content": "encrypted-2",
            "summary": [],
        },
        {
            "id": "message-2",
            "type": "message",
            "role": "assistant",
            "phase": "commentary",
            "content": [{"type": "output_text", "text": "Second call."}],
        },
        {
            "id": "function-2",
            "type": "function_call",
            "call_id": "call-2",
            "name": "step",
            "arguments": '{"n":2}',
        },
    ]

    class QueueBackend:
        def __init__(self) -> None:
            self.responses = [
                {"id": "resp-1", "status": "completed", "output": first_output},
                {"id": "resp-2", "status": "completed", "output": second_output},
            ]
            self.requests: list[dict[str, Any]] = []

        async def invoke(self, wire_protocol: str, request: dict[str, Any]) -> Any:
            assert wire_protocol == "responses"
            self.requests.append(request)
            return self.responses.pop(0)

    target = ModelTarget(
        endpoint_id="endpoint-responses",
        provider_kind="openai",
        model_name="gpt-test",
        wire_protocol="responses",
    )
    backend = QueueBackend()
    gateway = ModelGateway(backend=backend, codecs=[ResponsesCodec()])

    first_events = [
        event
        async for event in gateway.invoke(
            ModelInvocation(
                target=target,
                instructions="Continue.",
                input_items=(user,),
                tools=(),
                stream=False,
                max_output_tokens=128,
            )
        )
    ]
    first_continuation = first_events[-1].continuation
    assert first_continuation is not None
    assert first_continuation.canonical_input_count == 1
    assert first_continuation.matches_target(target)

    second_events = [
        event
        async for event in gateway.invoke(
            ModelInvocation(
                target=target,
                instructions="Continue.",
                input_items=(user, first_message, first_call, first_result),
                tools=(),
                stream=False,
                max_output_tokens=128,
                continuation=ResponsesContinuation(
                    response_id=first_continuation.response_id,
                    output_items=first_continuation.opaque_output_items(),
                    canonical_input_count=3,
                    target=first_continuation.target,
                ),
            )
        )
    ]
    second_continuation = second_events[-1].continuation
    assert second_continuation is not None
    assert second_continuation.canonical_input_count == 4
    assert second_continuation.matches_target(target)

    final_request = ResponsesCodec().encode_request(
        ModelInvocation(
            target=target,
            instructions="Continue.",
            input_items=(
                user,
                first_message,
                first_call,
                first_result,
                second_message,
                second_call,
                second_result,
            ),
            tools=(),
            stream=False,
            max_output_tokens=128,
            continuation=ResponsesContinuation(
                response_id=second_continuation.response_id,
                output_items=second_continuation.opaque_output_items(),
                canonical_input_count=6,
                target=second_continuation.target,
            ),
        )
    )

    assert final_request["input"] == [
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "Start."}],
        },
        *first_output,
        {"type": "function_call_output", "call_id": "call-1", "output": "one"},
        *second_output,
        {"type": "function_call_output", "call_id": "call-2", "output": "two"},
    ]
    assert [
        item.get("encrypted_content")
        for item in final_request["input"]
        if item.get("type") == "reasoning"
    ] == ["encrypted-1", "encrypted-2"]
    assert [
        item.get("id")
        for item in final_request["input"]
        if item.get("type") == "function_call"
    ] == ["function-1", "function-2"]


@pytest.mark.asyncio
async def test_response_failed_before_output_raises_safe_replayable_model_error() -> (
    None
):
    events = ResponsesCodec().decode_response(
        _stream(
            {
                "type": "response.failed",
                "response": {
                    "id": "resp-failed",
                    "status": "failed",
                    "error": {
                        "code": "server_error",
                        "message": "raw api_key=sentinel-secret",
                    },
                },
            }
        )
    )

    with pytest.raises(ModelError) as caught:
        await anext(events)

    error = caught.value
    assert error.category == "service_unavailable"
    assert error.http_status == 503
    assert error.provider_code == "server_error"
    assert error.retryable is True
    assert error.replay_safe is True
    assert "sentinel-secret" not in str(error)
    assert "sentinel-secret" not in repr(error)


@pytest.mark.asyncio
async def test_error_after_output_raises_safe_nonreplayable_model_error() -> None:
    events = ResponsesCodec().decode_response(
        _stream(
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {
                    "id": "message-1",
                    "type": "message",
                    "phase": "commentary",
                    "content": [],
                },
            },
            {
                "type": "response.output_text.delta",
                "output_index": 0,
                "item_id": "message-1",
                "delta": "Visible output.",
            },
            {
                "type": "error",
                "code": "rate_limit_exceeded",
                "message": "raw token=sentinel-secret",
            },
        )
    )

    assert await anext(events) == TextDelta(text="Visible output.", phase="commentary")
    with pytest.raises(ModelError) as caught:
        await anext(events)

    error = caught.value
    assert error.category == "rate_limit"
    assert error.http_status == 429
    assert error.provider_code == "rate_limit_exceeded"
    assert error.retryable is True
    assert error.replay_safe is False
    assert "sentinel-secret" not in repr(error.to_public_dict())


@pytest.mark.asyncio
async def test_response_incomplete_is_a_terminal_nonretryable_model_error() -> None:
    events = ResponsesCodec().decode_response(
        _stream(
            {
                "type": "response.incomplete",
                "response": {
                    "id": "resp-incomplete",
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                },
            }
        )
    )

    with pytest.raises(ModelError) as caught:
        await anext(events)

    error = caught.value
    assert error.category == "provider"
    assert error.http_status is None
    assert error.provider_code == "max_output_tokens"
    assert error.retryable is False
    assert error.replay_safe is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "category", "provider_code", "retryable"),
    [
        (
            {
                "id": "resp-failed-non-stream",
                "status": "failed",
                "error": {
                    "code": "server_error",
                    "message": "raw api_key=sentinel-secret",
                },
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "must not be decoded"}
                        ],
                    }
                ],
            },
            "service_unavailable",
            "server_error",
            True,
        ),
        (
            {
                "id": "resp-incomplete-non-stream",
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "output": [],
            },
            "provider",
            "max_output_tokens",
            False,
        ),
    ],
)
async def test_non_stream_terminal_status_raises_before_decoding_output(
    response: dict[str, Any],
    category: str,
    provider_code: str,
    retryable: bool,
) -> None:
    events = ResponsesCodec().decode_response(response)

    with pytest.raises(ModelError) as caught:
        await anext(events)

    error = caught.value
    assert error.category == category
    assert error.provider_code == provider_code
    assert error.retryable is retryable
    assert error.replay_safe is True
    assert "sentinel-secret" not in repr(error)


@pytest.mark.asyncio
async def test_stream_eof_before_output_raises_replayable_connection_error() -> None:
    events = ResponsesCodec().decode_response(
        _stream(
            {
                "type": "response.created",
                "response": {"id": "resp-truncated"},
            }
        )
    )

    with pytest.raises(ModelError) as caught:
        await anext(events)

    error = caught.value
    assert error.category == "connection"
    assert error.provider_code == "stream_terminated"
    assert error.retryable is True
    assert error.replay_safe is True


@pytest.mark.asyncio
@pytest.mark.parametrize("output_kind", ["text", "tool", "reasoning"])
async def test_stream_eof_after_canonical_output_is_not_replayable(
    output_kind: str,
) -> None:
    if output_kind == "text":
        chunks = (
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {
                    "id": "message-1",
                    "type": "message",
                    "phase": "commentary",
                    "content": [],
                },
            },
            {
                "type": "response.output_text.delta",
                "output_index": 0,
                "item_id": "message-1",
                "delta": "Partial text.",
            },
        )
    elif output_kind == "tool":
        chunks = (
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {
                    "id": "function-1",
                    "type": "function_call",
                    "call_id": "call-1",
                    "name": "step",
                    "arguments": "",
                },
            },
        )
    else:
        chunks = (
            {
                "type": "response.reasoning_summary_text.delta",
                "output_index": 0,
                "delta": "Partial reasoning.",
            },
        )
    events = ResponsesCodec().decode_response(_stream(*chunks))

    await anext(events)
    with pytest.raises(ModelError) as caught:
        await anext(events)

    error = caught.value
    assert error.category == "connection"
    assert error.provider_code == "stream_terminated"
    assert error.retryable is True
    assert error.replay_safe is False


@pytest.mark.asyncio
async def test_stream_refusal_deltas_emit_one_complete_warning_on_done() -> None:
    events = [
        event
        async for event in ResponsesCodec().decode_response(
            _stream(
                {"type": "response.refusal.delta", "delta": "I cannot "},
                {"type": "response.refusal.delta", "delta": "help."},
                {"type": "response.refusal.done", "refusal": "I cannot help."},
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp-refusal",
                        "status": "completed",
                        "output": [],
                    },
                },
            )
        )
    ]

    warnings = [event for event in events if isinstance(event, ModelWarning)]
    assert warnings == [ModelWarning(code="response_refusal", message="I cannot help.")]
    assert isinstance(events[-1], CompletionMetadata)


@pytest.mark.asyncio
async def test_stream_refusal_without_done_emits_one_complete_warning_on_completion() -> (
    None
):
    events = [
        event
        async for event in ResponsesCodec().decode_response(
            _stream(
                {"type": "response.refusal.delta", "delta": "I cannot "},
                {"type": "response.refusal.delta", "delta": "help."},
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp-refusal",
                        "status": "completed",
                        "output": [],
                    },
                },
            )
        )
    ]

    warnings = [event for event in events if isinstance(event, ModelWarning)]
    assert warnings == [ModelWarning(code="response_refusal", message="I cannot help.")]
    assert isinstance(events[-1], CompletionMetadata)


@pytest.mark.asyncio
async def test_decode_non_stream_response_preserves_all_output_items() -> None:
    response = _fixture("non_stream.json")

    events = [event async for event in ResponsesCodec().decode_response(response)]

    assert events[:-1] == [
        TextDelta(text="Analysis complete.", phase="final_answer"),
        ToolCallDelta(
            index=2,
            call_id="call-1",
            name="projects__list",
            arguments_delta='{"limit":5}',
        ),
        ToolCallDelta(
            index=3,
            call_id="call-2",
            name="runs__list",
            arguments_delta='{"status":"running"}',
        ),
        ModelWarning(
            code="response_refusal",
            message="I cannot perform that request.",
        ),
        ModelWarning(
            code="unsupported_response_item",
            message="Unsupported Responses output item type: future_output_item",
        ),
        UsageReport(
            input_tokens=21,
            output_tokens=13,
            total_tokens=34,
            cached_input_tokens=4,
            reasoning_tokens=6,
        ),
    ]
    completion = events[-1]
    assert isinstance(completion, CompletionMetadata)
    assert completion.response_id == "resp-non-stream"
    assert completion.finish_reason == "completed"
    assert completion.continuation is not None
    assert completion.continuation.response_id == "resp-non-stream"
    assert completion.continuation.opaque_output_items() == tuple(response["output"])


@pytest.mark.asyncio
async def test_decode_stream_preserves_phase_reasoning_calls_and_arbitrary_chunks() -> (
    None
):
    chunks = _fixture("stream.json")
    chunks[2] = SimpleNamespace(**chunks[2])

    events = [
        event async for event in ResponsesCodec().decode_response(_stream(*chunks))
    ]

    assert events == [
        TextDelta(text="Checking ", phase="commentary"),
        TextDelta(text="inputs.", phase="commentary"),
        ReasoningDelta(text="Reasoning chunk."),
        ToolCallDelta(
            index=2,
            call_id="call-stream",
            name="projects__list",
            arguments_delta="",
        ),
        ToolCallDelta(
            index=2,
            call_id=None,
            name=None,
            arguments_delta='{"limit":',
        ),
        ToolCallDelta(
            index=2,
            call_id=None,
            name=None,
            arguments_delta="5}",
        ),
        TextDelta(text="Done.", phase="final_answer"),
        ModelWarning(
            code="unsupported_response_event",
            message="Unsupported Responses stream event type: response.future_event",
        ),
        UsageReport(
            input_tokens=30,
            output_tokens=12,
            total_tokens=42,
            cached_input_tokens=8,
            reasoning_tokens=7,
        ),
        CompletionMetadata(
            response_id="resp-stream",
            finish_reason="completed",
            continuation=ResponsesContinuation(
                response_id="resp-stream",
                output_items=tuple(chunks[-1]["response"]["output"]),
            ),
        ),
    ]


def _stream(*chunks: Any) -> AsyncIterator[Any]:
    async def iterate() -> AsyncIterator[Any]:
        for chunk in chunks:
            yield chunk

    return iterate()
