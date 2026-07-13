from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict

import pytest

from app.services.model_runtime import contracts as runtime_contracts
from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ModelInvocation,
    ModelTarget,
    ModelWarning,
    ReasoningDelta,
    ResponseStarted,
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


def test_model_runtime_exposes_its_stable_public_surface() -> None:
    from app.services import model_runtime

    assert model_runtime.ModelGateway.__name__ == "ModelGateway"
    assert model_runtime.ModelInvocation is ModelInvocation
    assert model_runtime.ModelError is ModelError


def test_canonical_input_contracts_are_immutable_and_typed() -> None:
    text = TextPart(text="Inspect the workflow")
    call = ToolCallPart(
        call_id="call-1",
        name="workflows.get",
        arguments={"workflow_id": "wf-1"},
    )
    result = ToolResultPart(call_id="call-1", output='{"name":"demo"}')
    tool = ToolDefinition(
        name="workflows.get",
        description="Read one workflow",
        parameters={"type": "object"},
    )

    assert text.phase is None
    assert call.arguments == {"workflow_id": "wf-1"}
    assert result.is_error is False
    assert tool.parameters == {"type": "object"}
    with pytest.raises(FrozenInstanceError):
        text.text = "mutated"  # type: ignore[misc]


def test_model_target_and_invocation_hide_credentials_from_public_surfaces() -> None:
    secret = "sk-test-never-log"
    target = ModelTarget(
        endpoint_id="endpoint-1",
        provider_kind="openai",
        model_name="gpt-5.4-mini",
        wire_protocol="responses",
        base_url="https://relay.example/v1",
        api_key=secret,
    )
    continuation = ResponsesContinuation(
        response_id="resp-1",
        output_items=({"encrypted_content": secret},),
    )
    invocation = ModelInvocation(
        target=target,
        instructions="Be precise.",
        input_items=(TextPart(text="ping"),),
        tools=(),
        stream=True,
        max_output_tokens=256,
        continuation=continuation,
    )

    assert target.resolved_api_key() == secret
    assert continuation.opaque_output_items() == ({"encrypted_content": secret},)
    assert continuation.canonical_input_count == 0
    assert secret not in repr(target)
    assert secret not in repr(continuation)
    assert secret not in repr(invocation)
    assert target.to_public_dict() == {
        "endpoint_id": "endpoint-1",
        "provider_kind": "openai",
        "model_name": "gpt-5.4-mini",
        "wire_protocol": "responses",
        "base_url": "https://relay.example/v1",
    }


def test_dataclass_serialization_structurally_excludes_transport_secrets() -> None:
    secret = "sk-asdict-sentinel"
    opaque_item = {"encrypted_content": "opaque-asdict-sentinel"}
    target = ModelTarget(
        endpoint_id="endpoint-1",
        provider_kind="openai",
        model_name="gpt-5.4-mini",
        wire_protocol="responses",
        api_key=secret,
    )
    continuation = ResponsesContinuation(
        response_id="resp-1",
        output_items=(opaque_item,),
    )
    invocation = ModelInvocation(
        target=target,
        instructions="Continue.",
        input_items=(),
        tools=(),
        stream=True,
        max_output_tokens=128,
        continuation=continuation,
    )

    for serialized in (asdict(target), asdict(continuation), asdict(invocation)):
        rendered = repr(serialized)
        assert secret not in rendered
        assert opaque_item["encrypted_content"] not in rendered


def test_model_events_have_stable_tags_and_safe_defaults() -> None:
    events = (
        ResponseStarted(streaming=False),
        TextDelta(text="done"),
        ReasoningDelta(text="checking"),
        ToolCallDelta(
            index=0,
            call_id="call-1",
            name="workflows.get",
            arguments_delta='{"workflow_id":',
        ),
        UsageReport(input_tokens=10, output_tokens=4, total_tokens=14),
        ModelWarning(code="unknown_item", message="Skipped an unknown item."),
        CompletionMetadata(response_id="resp-1", finish_reason="stop"),
    )

    assert [event.kind for event in events] == [
        "response_started",
        "text_delta",
        "reasoning_delta",
        "tool_call_delta",
        "usage",
        "warning",
        "completion",
    ]
    assert events[1].phase == "final_answer"
    assert events[4].cached_input_tokens is None
    assert events[4].reasoning_tokens is None


def test_model_error_is_structured_immutable_and_never_serializes_its_cause() -> None:
    secret = "sk-upstream-secret"
    error = ModelError(
        category="rate_limit",
        message="The provider rate limit was exceeded.",
        http_status=429,
        provider_code="rate_limit_exceeded",
        retryable=True,
        replay_safe=True,
        retry_after_seconds=1.5,
        request_id="req-1",
        cause=RuntimeError(f"Authorization: Bearer {secret}"),
    )

    assert str(error) == "The provider rate limit was exceeded."
    assert error.args == ("The provider rate limit was exceeded.",)
    assert secret not in repr(error)
    assert secret not in str(error)
    assert secret not in repr(error.to_public_dict())
    assert error.to_public_dict() == {
        "category": "rate_limit",
        "message": "The provider rate limit was exceeded.",
        "http_status": 429,
        "provider_code": "rate_limit_exceeded",
        "retryable": True,
        "replay_safe": True,
        "retry_after_seconds": 1.5,
        "request_id": "req-1",
    }
    with pytest.raises(FrozenInstanceError):
        error.retryable = False  # type: ignore[misc]


def test_responses_continuation_private_round_trip_and_count_advance() -> None:
    secret = "opaque-private-reasoning"
    target = ModelTarget(
        endpoint_id="endpoint-1",
        provider_kind="openai_compatible",
        model_name="gpt-test",
        wire_protocol="responses",
        base_url="https://relay.example/v1",
        target_revision="opaque-revision-1",
    )
    canonical_prefix = (
        TextPart(text="Start."),
        TextPart(text="Working.", phase="commentary"),
        ToolCallPart(call_id="call-1", name="step", arguments={"n": 1}),
    )
    continuation = ResponsesContinuation(
        response_id="resp-1",
        output_items=({"type": "reasoning", "encrypted_content": secret},),
        canonical_input_count=3,
        canonical_input_digest=runtime_contracts.canonical_input_prefix_digest(
            canonical_prefix
        ),
        target=target.continuation_target(),
    )

    private_payload = continuation.to_private_dict()
    restored = ResponsesContinuation.from_private_dict(private_payload)

    assert restored is not None
    assert restored.response_id == "resp-1"
    assert restored.canonical_input_count == 3
    assert restored.opaque_output_items() == continuation.opaque_output_items()
    appended = (
        ToolResultPart(call_id="call-1", output="done"),
        TextPart(text="Finished.", phase="final_answer"),
    )
    advanced = restored.advance_canonical_input(appended)
    assert advanced.canonical_input_count == 5
    assert advanced.canonical_input_digest == runtime_contracts.canonical_input_prefix_digest(
        canonical_prefix + appended
    )
    assert advanced.opaque_output_items() == restored.opaque_output_items()
    assert advanced.matches_target(target)
    assert secret not in repr(continuation)
    assert secret not in repr(asdict(continuation))


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"output_items": "not-a-list"},
        {"output_items": ["not-an-object"]},
    ],
)
def test_responses_continuation_rejects_invalid_private_payload(payload: object) -> None:
    assert ResponsesContinuation.from_private_dict(payload) is None


def test_responses_continuation_target_revision_prevents_cross_credential_replay() -> None:
    first_target = ModelTarget(
        endpoint_id="endpoint-1",
        provider_kind="openai_compatible",
        model_name="gpt-test",
        routed_model_name="openai/gpt-test",
        wire_protocol="responses",
        target_revision="credential-revision-a",
    )
    rotated_target = ModelTarget(
        endpoint_id="endpoint-1",
        provider_kind="openai_compatible",
        model_name="gpt-test",
        routed_model_name="openai/gpt-test",
        wire_protocol="responses",
        target_revision="credential-revision-b",
    )
    prefix = (TextPart(text="Start."),)
    continuation = ResponsesContinuation(
        response_id="resp-1",
        output_items=({"type": "reasoning", "encrypted_content": "opaque"},),
        canonical_input_count=1,
        canonical_input_digest=runtime_contracts.canonical_input_prefix_digest(prefix),
        target=first_target.continuation_target(),
    )

    assert continuation.matches_target(first_target)
    assert not continuation.matches_target(rotated_target)


def test_legacy_responses_continuation_without_revision_or_prefix_digest_fails_closed() -> None:
    legacy_payload = {
        "response_id": "resp-legacy",
        "canonical_input_count": 1,
        "output_items": [{"type": "reasoning", "encrypted_content": "opaque"}],
        "target": {
            "endpoint_id": "endpoint-1",
            "provider_kind": "openai_compatible",
            "model_name": "gpt-test",
            "wire_protocol": "responses",
            "base_url": None,
        },
    }

    assert ResponsesContinuation.from_private_dict(legacy_payload) is None
