from __future__ import annotations

from pathlib import Path

from app.services.agent_core.context.assembler import model_context_from_messages
from app.services.agent_core.tools.specs import AgentToolSpec
from app.services.agent_core.tools.toolsets import model_tool_definitions
from app.services.agent_core.transcript.messages import (
    metadata_with_responses_continuation,
    model_input_parts_from_message,
    provider_message_from_parts,
    responses_continuation_from_metadata,
    text_part,
    tool_calls_part,
)
from app.services.model_runtime.contracts import (
    ResponsesContinuation,
    TextPart,
    ToolCallPart,
    ToolDefinition,
    ToolResultPart,
)


def test_tool_calls_part_writes_canonical_shape_from_legacy_and_canonical_calls():
    secret = "sentinel-secret-must-not-persist"

    part = tool_calls_part(
        [
            {
                "id": "legacy-call",
                "type": "function",
                "function": {
                    "name": "projects__list",
                    "arguments": '{"limit":5}',
                    "api_key": secret,
                },
            },
            {
                "id": "canonical-call",
                "name": "runs__list",
                "arguments": {"status": "running"},
                "api_key": secret,
            },
        ]
    )

    assert part == {
        "type": "tool_calls",
        "tool_calls": [
            {
                "id": "legacy-call",
                "name": "projects__list",
                "arguments": {"limit": 5},
            },
            {
                "id": "canonical-call",
                "name": "runs__list",
                "arguments": {"status": "running"},
            },
        ],
    }
    assert secret not in repr(part)


def test_legacy_and_canonical_tool_calls_convert_to_identical_model_parts():
    legacy = [
        {
            "type": "text",
            "text": "Checking projects.",
        },
        {
            "type": "tool_calls",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "projects__list",
                        "arguments": '{"limit":5}',
                    },
                }
            ],
        },
    ]
    canonical = [
        {"type": "text", "text": "Checking projects."},
        {
            "type": "tool_calls",
            "tool_calls": [
                {
                    "id": "call-1",
                    "name": "projects__list",
                    "arguments": {"limit": 5},
                }
            ],
        },
    ]

    expected = (
        TextPart(text="Checking projects.", phase="final_answer"),
        ToolCallPart(
            call_id="call-1",
            name="projects__list",
            arguments={"limit": 5},
        ),
    )
    assert model_input_parts_from_message("assistant", legacy) == expected
    assert model_input_parts_from_message("assistant", canonical) == expected


def test_canonical_parts_still_render_legacy_chat_request_for_compatibility():
    canonical = tool_calls_part(
        [{"id": "call-1", "name": "projects__list", "arguments": {"limit": 5}}]
    )

    message = provider_message_from_parts("assistant", [canonical])

    assert message == {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "projects__list",
                    "arguments": '{"limit":5}',
                },
            }
        ],
    }


def test_tool_result_uses_metadata_call_id_and_error_flag():
    parts = model_input_parts_from_message(
        "tool",
        [{"type": "text", "text": '{"status":"failed"}'}],
        {"tool_call_id": "call-1", "is_error": True},
    )

    assert parts == (
        ToolResultPart(
            call_id="call-1",
            output='{"status":"failed"}',
            is_error=True,
        ),
    )


def test_responses_phase_and_private_continuation_round_trip_without_public_leak():
    secret = "encrypted-private-reasoning"
    continuation = ResponsesContinuation(
        response_id="resp-1",
        canonical_input_count=3,
        output_items=({"type": "reasoning", "encrypted_content": secret},),
    )
    metadata = metadata_with_responses_continuation(
        {"provider": "openai_compatible"},
        continuation,
    )

    restored = responses_continuation_from_metadata(metadata)
    assert restored is not None
    assert restored.to_private_dict() == continuation.to_private_dict()
    parts = [
        text_part("Working.", phase="commentary"),
        text_part("Done.", phase="final_answer"),
    ]
    assert model_input_parts_from_message("assistant", parts, metadata) == (
        TextPart(text="Working.", phase="commentary"),
        TextPart(text="Done.", phase="final_answer"),
    )
    assert secret not in repr(provider_message_from_parts("assistant", parts, metadata))

def test_context_messages_shape_model_instructions_and_inputs_without_secrets():
    secret = "sentinel-context-secret"
    context = model_context_from_messages(
        [
            {"role": "system", "content": "Stable instructions."},
            {"role": "system", "content": "Turn context.", "api_key": secret},
            {"role": "user", "content": "List projects.", "api_key": secret},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "projects__list",
                            "arguments": "{}",
                        },
                    }
                ],
                "api_key": secret,
            },
        ]
    )

    assert context.instructions == "Stable instructions.\n\nTurn context."
    assert context.input_items == (
        TextPart(text="List projects."),
        ToolCallPart(call_id="call-1", name="projects__list", arguments={}),
    )
    assert secret not in repr(context)


def test_agent_tool_specs_map_to_protocol_neutral_tool_definitions():
    spec = AgentToolSpec(
        name="projects.list",
        description="List projects.",
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object"},
        risk_level="read",
    )

    assert model_tool_definitions([spec]) == (
        ToolDefinition(
            name="projects__list",
            description="List projects.",
            parameters={"type": "object", "properties": {}},
        ),
    )


def test_agent_core_no_longer_contains_provider_stream_parser():
    backend_root = Path(__file__).resolve().parents[2]

    assert not (backend_root / "app/services/agent_core/core/stream_adapter.py").exists()
