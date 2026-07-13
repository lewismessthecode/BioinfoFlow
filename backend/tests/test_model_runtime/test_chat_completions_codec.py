from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.model_runtime.codecs.chat_completions import ChatCompletionsCodec
from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ModelInvocation,
    ModelTarget,
    ReasoningDelta,
    TextDelta,
    TextPart,
    ToolCallDelta,
    ToolCallPart,
    ToolDefinition,
    ToolResultPart,
    UsageReport,
)


def _invocation(*, stream: bool = False) -> ModelInvocation:
    return ModelInvocation(
        target=ModelTarget(
            endpoint_id="endpoint-1",
            provider_kind="openai",
            model_name="gpt-test",
            wire_protocol="chat_completions",
            base_url="https://relay.example/v1",
            api_key="secret",
        ),
        instructions="You are concise.",
        input_items=(
            TextPart(text="Run the workflow."),
            ToolCallPart(
                call_id="call-1",
                name="run_workflow",
                arguments={"name": "demo"},
            ),
            ToolResultPart(call_id="call-1", output='{"status":"ok"}'),
            TextPart(text="The workflow completed.", phase="final_answer"),
        ),
        tools=(
            ToolDefinition(
                name="run_workflow",
                description="Run a workflow.",
                parameters={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            ),
        ),
        stream=stream,
        max_output_tokens=321,
    )


def test_encode_request_preserves_chat_message_and_tool_order() -> None:
    request = ChatCompletionsCodec().encode_request(_invocation(stream=True))

    assert request == {
        "model": "gpt-test",
        "messages": [
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": "Run the workflow."},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "run_workflow",
                            "arguments": '{"name":"demo"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "content": '{"status":"ok"}',
            },
            {"role": "assistant", "content": "The workflow completed."},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "run_workflow",
                    "description": "Run a workflow.",
                    "parameters": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                    },
                },
            }
        ],
        "stream": True,
        "max_tokens": 321,
    }


def test_encode_request_keeps_assistant_text_and_tool_calls_in_one_message() -> None:
    invocation = _invocation()

    request = ChatCompletionsCodec().encode_request(
        ModelInvocation(
            target=invocation.target,
            instructions=invocation.instructions,
            input_items=(
                TextPart(text="I will inspect the workflow.", phase="commentary"),
                ToolCallPart(
                    call_id="call-a",
                    name="run_workflow",
                    arguments={"name": "alpha"},
                ),
                ToolCallPart(
                    call_id="call-b",
                    name="run_workflow",
                    arguments={"name": "beta"},
                ),
            ),
            tools=invocation.tools,
            stream=False,
            max_output_tokens=invocation.max_output_tokens,
        )
    )

    assert request["messages"][1] == {
        "role": "assistant",
        "content": "I will inspect the workflow.",
        "tool_calls": [
            {
                "id": "call-a",
                "type": "function",
                "function": {
                    "name": "run_workflow",
                    "arguments": '{"name":"alpha"}',
                },
            },
            {
                "id": "call-b",
                "type": "function",
                "function": {
                    "name": "run_workflow",
                    "arguments": '{"name":"beta"}',
                },
            },
        ],
    }
    assert len(request["messages"]) == 2


def test_encode_request_uses_catalog_litellm_provider_prefix() -> None:
    invocation = _invocation()
    target = ModelTarget(
        endpoint_id=invocation.target.endpoint_id,
        provider_kind="ollama",
        model_name="qwen3:8b",
        wire_protocol="chat_completions",
        base_url="http://127.0.0.1:11434",
    )

    request = ChatCompletionsCodec().encode_request(
        ModelInvocation(
            target=target,
            instructions=invocation.instructions,
            input_items=invocation.input_items,
            tools=invocation.tools,
            stream=invocation.stream,
            max_output_tokens=invocation.max_output_tokens,
        )
    )

    assert request["model"] == "ollama_chat/qwen3:8b"


@pytest.mark.asyncio
async def test_parallel_tool_calls_share_one_assistant_message_and_round_trip() -> None:
    invocation = _invocation()
    request = ChatCompletionsCodec().encode_request(
        ModelInvocation(
            target=invocation.target,
            instructions=invocation.instructions,
            input_items=(
                TextPart(text="Run both workflows."),
                ToolCallPart(
                    call_id="call-a",
                    name="run_workflow",
                    arguments={"name": "alpha"},
                ),
                ToolCallPart(
                    call_id="call-b",
                    name="run_workflow",
                    arguments={"name": "beta"},
                ),
                ToolResultPart(call_id="call-a", output="alpha ok"),
                ToolResultPart(call_id="call-b", output="beta ok"),
                TextPart(text="Both completed.", phase="final_answer"),
            ),
            tools=invocation.tools,
            stream=False,
            max_output_tokens=invocation.max_output_tokens,
        )
    )

    assert request["messages"] == [
        {"role": "system", "content": "You are concise."},
        {"role": "user", "content": "Run both workflows."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-a",
                    "type": "function",
                    "function": {
                        "name": "run_workflow",
                        "arguments": '{"name":"alpha"}',
                    },
                },
                {
                    "id": "call-b",
                    "type": "function",
                    "function": {
                        "name": "run_workflow",
                        "arguments": '{"name":"beta"}',
                    },
                },
            ],
        },
        {"role": "tool", "tool_call_id": "call-a", "content": "alpha ok"},
        {"role": "tool", "tool_call_id": "call-b", "content": "beta ok"},
        {"role": "assistant", "content": "Both completed."},
    ]

    assistant_message = request["messages"][2]
    response = {
        "id": "chatcmpl-parallel",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": assistant_message,
            }
        ],
    }
    events = [event async for event in ChatCompletionsCodec().decode_response(response)]

    assert events[:2] == [
        ToolCallDelta(
            index=0,
            call_id="call-a",
            name="run_workflow",
            arguments_delta='{"name":"alpha"}',
        ),
        ToolCallDelta(
            index=1,
            call_id="call-b",
            name="run_workflow",
            arguments_delta='{"name":"beta"}',
        ),
    ]


@pytest.mark.asyncio
async def test_decode_non_stream_response_emits_text_tools_usage_and_completion() -> None:
    response = SimpleNamespace(
        id="chatcmpl-1",
        model="gpt-test",
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    content=[{"text": "I will run it."}],
                    reasoning_content="Checking inputs.",
                    tool_calls=[
                        SimpleNamespace(
                            id="call-1",
                            function=SimpleNamespace(
                                name="run_workflow",
                                arguments='{"name":"demo"}',
                            ),
                        )
                    ],
                ),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=11,
            completion_tokens=7,
            total_tokens=18,
        ),
    )

    events = [event async for event in ChatCompletionsCodec().decode_response(response)]

    assert events == [
        ReasoningDelta(text="Checking inputs."),
        TextDelta(text="I will run it.", phase="final_answer"),
        ToolCallDelta(
            index=0,
            call_id="call-1",
            name="run_workflow",
            arguments_delta='{"name":"demo"}',
        ),
        UsageReport(input_tokens=11, output_tokens=7, total_tokens=18),
        CompletionMetadata(
            response_id="chatcmpl-1",
            finish_reason="tool_calls",
        ),
    ]


@pytest.mark.asyncio
async def test_decode_non_stream_serializes_dict_tool_arguments() -> None:
    response = SimpleNamespace(
        id="chatcmpl-dict",
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message={
                    "tool_calls": [
                        {
                            "id": "call-dict",
                            "function": {
                                "name": "run_workflow",
                                "arguments": {"name": "demo", "retries": 2},
                            },
                        }
                    ]
                },
            )
        ],
        usage=None,
    )

    events = [event async for event in ChatCompletionsCodec().decode_response(response)]

    assert events[0] == ToolCallDelta(
        index=0,
        call_id="call-dict",
        name="run_workflow",
        arguments_delta='{"name":"demo","retries":2}',
    )


@pytest.mark.asyncio
async def test_decode_usage_from_model_dump_only_object() -> None:
    class DumpOnlyUsage:
        def model_dump(self) -> dict[str, Any]:
            return {
                "prompt_tokens": 17,
                "completion_tokens": 9,
                "total_tokens": 26,
                "prompt_tokens_details": {"cached_tokens": 5},
                "completion_tokens_details": {"reasoning_tokens": 3},
            }

    response = SimpleNamespace(
        id="chatcmpl-usage-dump",
        choices=[SimpleNamespace(finish_reason="stop", message={"content": "done"})],
        usage=DumpOnlyUsage(),
    )

    events = [event async for event in ChatCompletionsCodec().decode_response(response)]

    assert UsageReport(
        input_tokens=17,
        output_tokens=9,
        total_tokens=26,
        cached_input_tokens=5,
        reasoning_tokens=3,
    ) in events


@pytest.mark.asyncio
async def test_decode_usage_preserves_missing_optional_token_details() -> None:
    response = SimpleNamespace(
        id="chatcmpl-usage-basic",
        choices=[SimpleNamespace(finish_reason="stop", message={"content": "done"})],
        usage={
            "prompt_tokens": 17,
            "completion_tokens": 9,
            "total_tokens": 26,
        },
    )

    events = [event async for event in ChatCompletionsCodec().decode_response(response)]

    assert UsageReport(
        input_tokens=17,
        output_tokens=9,
        total_tokens=26,
        cached_input_tokens=None,
        reasoning_tokens=None,
    ) in events


@pytest.mark.asyncio
async def test_decode_stream_response_emits_deltas_and_final_usage() -> None:
    response = _stream(
        SimpleNamespace(
            id="chatcmpl-2",
            model="gpt-test",
            choices=[
                SimpleNamespace(
                    finish_reason=None,
                    delta={
                        "reasoning_content": "Think ",
                        "content": "Run ",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-2",
                                "function": {
                                    "name": "run_workflow",
                                    "arguments": '{"name":',
                                },
                            }
                        ],
                    },
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            id="chatcmpl-2",
            model="gpt-test",
            choices=[
                SimpleNamespace(
                    finish_reason="tool_calls",
                    delta={
                        "content": "done",
                        "tool_calls": [
                            {
                                "index": 0,
                                "function": {"arguments": '"demo"}'},
                            }
                        ],
                    },
                )
            ],
            usage={"prompt_tokens": 13, "completion_tokens": 8, "total_tokens": 21},
        ),
    )

    events = [event async for event in ChatCompletionsCodec().decode_response(response)]

    assert events == [
        ReasoningDelta(text="Think "),
        TextDelta(text="Run ", phase="final_answer"),
        ToolCallDelta(
            index=0,
            call_id="call-2",
            name="run_workflow",
            arguments_delta='{"name":',
        ),
        TextDelta(text="done", phase="final_answer"),
        ToolCallDelta(
            index=0,
            call_id=None,
            name=None,
            arguments_delta='"demo"}',
        ),
        UsageReport(input_tokens=13, output_tokens=8, total_tokens=21),
        CompletionMetadata(
            response_id="chatcmpl-2",
            finish_reason="tool_calls",
        ),
    ]


@pytest.mark.asyncio
async def test_decode_stream_merges_detailed_usage_across_chunks() -> None:
    response = _stream(
        {
            "id": "chatcmpl-usage",
            "choices": [],
            "usage": {
                "prompt_tokens": 2,
                "completion_tokens": 1,
                "total_tokens": 3,
                "prompt_tokens_details": {"cached_tokens": 1},
                "completion_tokens_details": {"reasoning_tokens": 1},
            },
        },
        {
            "id": "chatcmpl-usage",
            "choices": [{"finish_reason": "stop", "delta": {}}],
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 4,
                "total_tokens": 7,
                "prompt_tokens_details": {"cached_tokens": 2},
                "completion_tokens_details": {"reasoning_tokens": 2},
            },
        },
    )

    events = [event async for event in ChatCompletionsCodec().decode_response(response)]

    assert events == [
        UsageReport(
            input_tokens=5,
            output_tokens=5,
            total_tokens=10,
            cached_input_tokens=3,
            reasoning_tokens=3,
        ),
        CompletionMetadata(response_id="chatcmpl-usage", finish_reason="stop"),
    ]


def _stream(*chunks: Any) -> AsyncIterator[Any]:
    async def iterate() -> AsyncIterator[Any]:
        for chunk in chunks:
            yield chunk

    return iterate()
