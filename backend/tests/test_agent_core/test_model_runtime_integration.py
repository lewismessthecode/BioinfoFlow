from __future__ import annotations

from collections.abc import AsyncIterator
import json
import sys

import pytest

from app.models.llm import LlmModel, LlmModelProfile, LlmProvider
from app.models.workspace import Workspace
from app.config import settings
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentEventRepository,
    AgentMessageRepository,
)
from app.services.agent_core import AgentCoreService
from app.services.agent_core.core.loop import AgentLoopController
from app.services.agent_core.core.runtime_strategy import RuntimeCapabilities, RuntimeStrategy
from app.services.agent_core.runtime import AgentCoreRuntime
from app.services.agent_core.tools.executor import ToolExecutionResult
from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ModelEvent,
    ModelInvocation,
    ModelTarget,
    ReasoningDelta,
    ResponseStarted,
    TextDelta,
    TextPart,
    ToolCallDelta,
    ToolCallPart,
    ToolResultPart,
    UsageReport,
)
from app.services.model_runtime.errors import ModelError
from app.workspace import DEFAULT_WORKSPACE_ID


class FakeModelGateway:
    def __init__(self, *responses: tuple[ModelEvent, ...] | Exception) -> None:
        self.responses = list(responses)
        self.invocations: list[ModelInvocation] = []

    async def invoke(self, invocation: ModelInvocation) -> AsyncIterator[ModelEvent]:
        self.invocations.append(invocation)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        for event in response:
            yield event


async def _turn(db_session, *, input_text: str = "Summarize this workflow."):
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    await db_session.commit()
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text=input_text,
    )
    return session, turn


def _target() -> ModelTarget:
    return ModelTarget(
        endpoint_id="endpoint-1",
        provider_kind="openai_compatible",
        model_name="gpt-test",
        wire_protocol="chat_completions",
        base_url="https://models.example/v1",
        api_key="secret",
    )


@pytest.mark.asyncio
async def test_normal_turn_runs_through_injected_model_gateway(db_session) -> None:
    session, turn = await _turn(db_session)
    gateway = FakeModelGateway(
        (
            TextDelta(text="The workflow is valid."),
            UsageReport(input_tokens=12, output_tokens=5, total_tokens=17),
            CompletionMetadata(response_id="chatcmpl-1", finish_reason="stop"),
        )
    )
    controller = AgentLoopController(db_session, model_gateway=gateway)

    result = await controller.run_turn(
        turn_id=str(turn.id),
        target=_target(),
        capabilities=RuntimeCapabilities(supports_tools=False),
        strategy=RuntimeStrategy(allow_tools=False),
        max_tokens=256,
    )

    assert result.termination_reason == "assistant_final"
    assert result.final_text == "The workflow is valid."
    assert result.token_usage == {
        "prompt_tokens": 12,
        "completion_tokens": 5,
        "total_tokens": 17,
    }
    assert len(gateway.invocations) == 1
    invocation = gateway.invocations[0]
    assert invocation.target == _target()
    assert invocation.stream is True
    assert invocation.max_output_tokens == 256
    assert invocation.instructions
    assert invocation.input_items == (TextPart(text="Summarize this workflow."),)

    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    assert [message.role for message in messages] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_non_stream_turn_emits_completed_event_without_text_delta(db_session) -> None:
    _session, turn = await _turn(db_session, input_text="Reply without streaming.")
    gateway = FakeModelGateway(
        (
            ResponseStarted(streaming=False),
            ReasoningDelta(text="Checked the request."),
            TextDelta(text="One complete response."),
            CompletionMetadata(response_id="chatcmpl-non-stream", finish_reason="stop"),
        )
    )

    result = await AgentLoopController(db_session, model_gateway=gateway).run_turn(
        turn_id=str(turn.id),
        target=_target(),
        capabilities=RuntimeCapabilities(supports_streaming=True, supports_tools=False),
        strategy=RuntimeStrategy(use_streaming=True, allow_tools=False, allow_thinking=True),
    )

    assert result.termination_reason == "assistant_final"
    events = await AgentEventRepository(db_session).list_for_turn(turn_id=str(turn.id))
    event_types = [event.type for event in events]
    assert "assistant.text.completed" in event_types
    assert "assistant.text.delta" not in event_types
    assert "assistant.thinking.completed" in event_types
    assert "assistant.thinking.delta" not in event_types


@pytest.mark.asyncio
async def test_tool_call_result_continues_through_gateway(db_session) -> None:
    _session, turn = await _turn(db_session, input_text="List projects, then summarize.")
    gateway = FakeModelGateway(
        (
            ToolCallDelta(
                index=0,
                call_id="call-projects",
                name="projects__list",
                arguments_delta="{}",
            ),
            CompletionMetadata(response_id="chatcmpl-tool", finish_reason="tool_calls"),
        ),
        (
            TextDelta(text="There are no projects yet."),
            CompletionMetadata(response_id="chatcmpl-final", finish_reason="stop"),
        ),
    )
    controller = AgentLoopController(db_session, model_gateway=gateway)

    result = await controller.run_turn(
        turn_id=str(turn.id),
        target=_target(),
        capabilities=RuntimeCapabilities(supports_tools=True),
        strategy=RuntimeStrategy(allow_tools=True),
    )

    assert result.termination_reason == "assistant_final"
    assert result.final_text == "There are no projects yet."
    assert len(gateway.invocations) == 2
    assert any(
        isinstance(item, ToolCallPart) and item.call_id == "call-projects"
        for item in gateway.invocations[1].input_items
    )
    assert any(
        isinstance(item, ToolResultPart) and item.call_id == "call-projects"
        for item in gateway.invocations[1].input_items
    )


@pytest.mark.asyncio
async def test_failed_tool_result_round_trips_with_error_flag(db_session, monkeypatch) -> None:
    _session, turn = await _turn(db_session, input_text="Run a command and report failure.")
    gateway = FakeModelGateway(
        (
            ToolCallDelta(
                index=0,
                call_id="call-failed",
                name="bash",
                arguments_delta="{}",
            ),
            CompletionMetadata(response_id="chatcmpl-failed", finish_reason="tool_calls"),
        ),
        (
            TextDelta(text="The command failed."),
            CompletionMetadata(response_id="chatcmpl-after-failure", finish_reason="stop"),
        ),
    )
    controller = AgentLoopController(db_session, model_gateway=gateway)

    async def failed_execution(*args, **kwargs):
        del args, kwargs
        return ToolExecutionResult(
            action_id="failed-action",
            status="failed",
            error={"type": "CommandFailed", "message": "failed"},
        )

    monkeypatch.setattr(controller.executor, "execute", failed_execution)

    result = await controller.run_turn(turn_id=str(turn.id), target=_target())

    assert result.termination_reason == "assistant_final"
    tool_result = next(
        item
        for item in gateway.invocations[1].input_items
        if isinstance(item, ToolResultPart)
    )
    assert tool_result.call_id == "call-failed"
    assert tool_result.is_error is True


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["approve", "reject"])
async def test_approval_resume_survives_controller_restart(
    db_session,
    monkeypatch,
    decision: str,
) -> None:
    session, turn = await _turn(db_session, input_text="Run the approved command.")
    gateway = FakeModelGateway(
        (
            ToolCallDelta(
                index=0,
                call_id="call-bash",
                name="bash",
                arguments_delta=json.dumps(
                    {
                        "command": f"{sys.executable} -c 'print(\"approved\")'",
                        "cwd": str(settings.bioinfoflow_home),
                    }
                ),
            ),
            CompletionMetadata(response_id="chatcmpl-approval", finish_reason="tool_calls"),
        ),
        (
            TextDelta(text=f"Continued after {decision}."),
            CompletionMetadata(response_id="chatcmpl-resumed", finish_reason="stop"),
        ),
    )
    first_controller = AgentLoopController(db_session, model_gateway=gateway)

    waiting = await first_controller.run_turn(
        turn_id=str(turn.id),
        target=_target(),
    )

    assert waiting.termination_reason == "waiting_approval"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    assert len(actions) == 1
    service = AgentCoreService(db_session)
    monkeypatch.setattr("app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None)
    await service.decide_action(
        action_id=str(actions[0].id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision=decision,
    )

    restarted_controller = AgentLoopController(db_session, model_gateway=gateway)
    result = await restarted_controller.resume_turn_from_action(
        action_id=str(actions[0].id),
        target=_target(),
    )

    assert result.termination_reason == "assistant_final"
    assert result.final_text == f"Continued after {decision}."
    tool_result = next(
        item
        for item in gateway.invocations[1].input_items
        if isinstance(item, ToolResultPart)
    )
    assert tool_result.call_id == "call-bash"
    if decision == "reject":
        assert "UserRejected" in tool_result.output
        assert tool_result.is_error is True
    else:
        assert "approved" in tool_result.output
        assert tool_result.is_error is False
    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    assert [message.role for message in messages] == ["user", "assistant", "tool", "assistant"]


@pytest.mark.asyncio
async def test_empty_response_retries_once_then_fails(db_session) -> None:
    _session, turn = await _turn(db_session, input_text="Do not answer.")
    empty = (CompletionMetadata(response_id="chatcmpl-empty", finish_reason="stop"),)
    gateway = FakeModelGateway(empty, empty)

    result = await AgentLoopController(db_session, model_gateway=gateway).run_turn(
        turn_id=str(turn.id),
        target=_target(),
    )

    assert result.termination_reason == "model_failed"
    assert result.error_code == "empty_model_response"
    assert len(gateway.invocations) == 2


@pytest.mark.asyncio
async def test_repeated_gateway_tool_calls_stop_without_progress(db_session) -> None:
    _session, turn = await _turn(db_session, input_text="Keep listing projects.")
    repeated = (
        ToolCallDelta(
            index=0,
            call_id="call-projects",
            name="projects__list",
            arguments_delta="{}",
        ),
        CompletionMetadata(response_id="chatcmpl-loop", finish_reason="tool_calls"),
    )
    gateway = FakeModelGateway(repeated, repeated, repeated)

    result = await AgentLoopController(db_session, model_gateway=gateway).run_turn(
        turn_id=str(turn.id),
        target=_target(),
    )

    assert result.termination_reason == "no_progress"
    assert result.error_code == "no_progress_detected"
    assert len(gateway.invocations) == 3


@pytest.mark.asyncio
async def test_cancelled_turn_never_invokes_gateway(db_session) -> None:
    _session, turn = await _turn(db_session, input_text="Cancel this.")
    service = AgentCoreService(db_session)
    turn = await service.turn_repo.update_all(turn, status="cancelled")
    gateway = FakeModelGateway()

    result = await AgentLoopController(db_session, model_gateway=gateway).run_turn(
        turn_id=str(turn.id),
        target=_target(),
    )

    assert result.termination_reason == "cancelled"
    assert gateway.invocations == []


@pytest.mark.asyncio
async def test_runtime_uses_semantic_fallback_through_same_gateway(db_session) -> None:
    session, turn = await _turn(db_session, input_text="Use fallback if needed.")
    provider = LlmProvider(
        name="Gateway provider",
        kind="openai_compatible",
        base_url="https://models.example/v1",
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "openai-compatible"},
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    primary = LlmModel(
        provider_id=str(provider.id),
        model_id="primary-model",
        display_name="Primary",
        supports_tools=False,
    )
    fallback = LlmModel(
        provider_id=str(provider.id),
        model_id="fallback-model",
        display_name="Fallback",
        supports_tools=False,
    )
    db_session.add_all([primary, fallback])
    await db_session.commit()
    await db_session.refresh(primary)
    await db_session.refresh(fallback)
    profile = LlmModelProfile(
        name="Fallback profile",
        task_type="agent",
        primary_model_id=str(primary.id),
        fallback_model_ids=[str(fallback.id)],
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    service = AgentCoreService(db_session)
    await service.session_repo.update_all(session, default_model_profile_id=str(profile.id))
    gateway = FakeModelGateway(
        ModelError(
            category="invalid_request",
            message="Primary model rejected the request.",
            retryable=False,
        ),
        (
            TextDelta(text="Fallback completed."),
            CompletionMetadata(response_id="chatcmpl-fallback", finish_reason="stop"),
        ),
    )

    completed = await AgentCoreRuntime(db_session, model_gateway=gateway).run_turn(str(turn.id))

    assert completed.status == "completed"
    assert completed.final_text == "Fallback completed."
    assert [item.target.model_name for item in gateway.invocations] == [
        "primary-model",
        "fallback-model",
    ]


@pytest.mark.asyncio
async def test_fallback_approval_resume_uses_exact_resolved_fallback_target(
    db_session,
    monkeypatch,
) -> None:
    session, turn = await _turn(db_session, input_text="Fallback, then request approval.")
    provider = LlmProvider(
        name="Approval fallback provider",
        kind="openai_compatible",
        base_url="https://models.example/v1",
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "openai-compatible"},
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    primary = LlmModel(
        provider_id=str(provider.id),
        model_id="approval-primary",
        display_name="Approval primary",
        supports_tools=True,
    )
    fallback = LlmModel(
        provider_id=str(provider.id),
        model_id="approval-fallback",
        display_name="Approval fallback",
        supports_tools=True,
    )
    db_session.add_all([primary, fallback])
    await db_session.commit()
    await db_session.refresh(primary)
    await db_session.refresh(fallback)
    profile = LlmModelProfile(
        name="Approval fallback profile",
        task_type="agent",
        primary_model_id=str(primary.id),
        fallback_model_ids=[str(fallback.id)],
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    service = AgentCoreService(db_session)
    await service.session_repo.update_all(session, default_model_profile_id=str(profile.id))
    gateway = FakeModelGateway(
        ModelError(
            category="invalid_request",
            message="Primary rejected the request.",
            retryable=False,
        ),
        (
            ToolCallDelta(
                index=0,
                call_id="call-fallback-bash",
                name="bash",
                arguments_delta=json.dumps(
                    {
                        "command": f"{sys.executable} -c 'print(\"fallback-approved\")'",
                        "cwd": str(settings.bioinfoflow_home),
                    }
                ),
            ),
            CompletionMetadata(
                response_id="chatcmpl-fallback-approval",
                finish_reason="tool_calls",
            ),
        ),
        (
            TextDelta(text="Fallback resumed."),
            CompletionMetadata(response_id="chatcmpl-fallback-resume", finish_reason="stop"),
        ),
    )

    waiting = await AgentCoreRuntime(db_session, model_gateway=gateway).run_turn(str(turn.id))

    assert waiting.status == "waiting_approval"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    monkeypatch.setattr("app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None)
    await service.decide_action(
        action_id=str(actions[0].id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )

    resumed = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).resume_turn_after_action(str(actions[0].id))

    assert resumed.status == "completed"
    assert resumed.final_text == "Fallback resumed."
    assert [item.target.model_name for item in gateway.invocations] == [
        "approval-primary",
        "approval-fallback",
        "approval-fallback",
    ]
    assert resumed.model_profile_snapshot["resolved_model_target"] == {
        "endpoint_id": str(provider.id),
        "provider_kind": "openai_compatible",
        "model_name": "approval-fallback",
        "wire_protocol": "chat_completions",
        "base_url": "https://models.example/v1",
    }
