from __future__ import annotations

from collections.abc import AsyncIterator
import json
import sys

import pytest

from app.models.llm import (
    LlmCredentialSource,
    LlmModel,
    LlmModelProfile,
    LlmProvider,
    LlmProviderCredential,
)
from app.models.workspace import Workspace, WorkspaceMembership
from app.config import settings
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentEventRepository,
    AgentMessageRepository,
)
from app.services.agent_core import AgentCoreService
from app.services.agent_core.core.loop import AgentLoopController
from app.services.agent_core.core.runtime_strategy import RuntimeCapabilities, RuntimeStrategy
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.runtime import AgentCoreRuntime
from app.services.agent_core.tools.executor import ToolExecutionResult
from app.services.llm.credentials import encrypt_secret
from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ModelEvent,
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
    ToolResultPart,
    UsageReport,
)
from app.services.model_runtime.errors import ModelError
from app.services.agent_core.transcript import provider_message_from_parts
from app.services.agent_core.transcript.messages import (
    metadata_with_responses_continuation,
)
from app.services.agent_core.transcript.store import AgentTranscriptStore
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


class PartialFailureGateway:
    def __init__(self) -> None:
        self.invocations: list[ModelInvocation] = []

    async def invoke(self, invocation: ModelInvocation) -> AsyncIterator[ModelEvent]:
        self.invocations.append(invocation)
        yield TextDelta(text="Partial output.")
        raise ModelError(
            category="service_unavailable",
            message="Stream failed after output started.",
            retryable=True,
            replay_safe=False,
        )


async def _turn(
    db_session,
    *,
    input_text: str = "Summarize this workflow.",
    user_id: str = "dev",
):
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    await db_session.commit()
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id=user_id,
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id=user_id,
        input_text=input_text,
    )
    return session, turn


async def _select_catalog_model(
    db_session,
    *,
    session,
    name: str,
    user_id: str,
    scope: str = "user",
    base_url: str,
    credential_source: str = LlmCredentialSource.NONE,
    env_var_name: str | None = None,
):
    provider = LlmProvider(
        name=name,
        kind="openai_compatible",
        base_url=base_url,
        scope=scope,
        workspace_id=(DEFAULT_WORKSPACE_ID if scope != "global" else None),
        user_id=(user_id if scope == "user" else None),
        enabled=True,
        provider_metadata={"providerTemplate": "openai-compatible"},
    )
    db_session.add(provider)
    await db_session.flush()
    if credential_source != LlmCredentialSource.NONE:
        db_session.add(
            LlmProviderCredential(
                provider_id=str(provider.id),
                source=credential_source,
                env_var_name=env_var_name,
                masked_hint=(f"env:{env_var_name}" if env_var_name else None),
                updated_by=user_id,
            )
        )
    model = LlmModel(
        provider_id=str(provider.id),
        model_id=f"{name}-model",
        display_name=f"{name} model",
        supports_tools=False,
        supports_streaming=True,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    await AgentCoreService(db_session).session_repo.update_all(
        session,
        session_metadata={"model_selection": {"model_id": str(model.id)}},
    )
    return provider, model


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
async def test_team_member_agent_invocation_rejects_hostname_resolving_private(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    session, turn = await _turn(db_session, user_id="member-1")
    db_session.add(
        WorkspaceMembership(
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="member-1",
            role="member",
        )
    )
    await db_session.commit()
    await _select_catalog_model(
        db_session,
        session=session,
        name="member-rebinding-provider",
        user_id="member-1",
        base_url="https://relay.example.com/v1",
    )
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 0))],
    )
    gateway = FakeModelGateway(
        (
            TextDelta(text="must not be reached"),
            CompletionMetadata(response_id="forbidden", finish_reason="stop"),
        )
    )

    failed = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).run_turn(str(turn.id))

    assert failed.status == "failed"
    assert failed.error_code == "model_selection_missing"
    assert gateway.invocations == []


@pytest.mark.asyncio
async def test_team_member_agent_invocation_rejects_legacy_user_env_credential(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setenv("DATABASE_URL", "legacy-server-secret")
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("1.1.1.1", 0))],
    )
    session, turn = await _turn(db_session, user_id="member-1")
    db_session.add(
        WorkspaceMembership(
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="member-1",
            role="member",
        )
    )
    await db_session.commit()
    await _select_catalog_model(
        db_session,
        session=session,
        name="legacy-member-env-provider",
        user_id="member-1",
        base_url="https://1.1.1.1/v1",
        credential_source=LlmCredentialSource.ENV,
        env_var_name="DATABASE_URL",
    )
    gateway = FakeModelGateway(
        (
            TextDelta(text="must not receive the environment secret"),
            CompletionMetadata(response_id="forbidden-env", finish_reason="stop"),
        )
    )

    failed = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).run_turn(str(turn.id))

    assert failed.status == "failed"
    assert failed.error_code == "model_selection_missing"
    assert gateway.invocations == []


@pytest.mark.asyncio
async def test_team_member_public_provider_carries_public_only_network_policy(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("1.1.1.1", 0))],
    )
    session, turn = await _turn(db_session, user_id="member-1")
    db_session.add(
        WorkspaceMembership(
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="member-1",
            role="member",
        )
    )
    await db_session.commit()
    await _select_catalog_model(
        db_session,
        session=session,
        name="member-public-provider",
        user_id="member-1",
        base_url="https://relay.example.com/v1",
    )
    gateway = FakeModelGateway(
        (
            TextDelta(text="public provider completed"),
            CompletionMetadata(response_id="public-ok", finish_reason="stop"),
        )
    )

    completed = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).run_turn(str(turn.id))

    assert completed.status == "completed"
    assert gateway.invocations[0].target.network_access == "public_only"


@pytest.mark.asyncio
async def test_team_admin_agent_invocation_preserves_private_env_provider_access(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setenv("ADMIN_RELAY_API_KEY", "admin-relay-secret")
    session, turn = await _turn(db_session, user_id="admin-1")
    db_session.add(
        WorkspaceMembership(
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="admin-1",
            role="admin",
        )
    )
    await db_session.commit()
    await _select_catalog_model(
        db_session,
        session=session,
        name="admin-private-provider",
        user_id="admin-1",
        base_url="http://127.0.0.1:8000/v1",
        credential_source=LlmCredentialSource.ENV,
        env_var_name="ADMIN_RELAY_API_KEY",
    )
    gateway = FakeModelGateway(
        (
            TextDelta(text="admin provider completed"),
            CompletionMetadata(response_id="admin-ok", finish_reason="stop"),
        )
    )

    completed = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).run_turn(str(turn.id))

    assert completed.status == "completed"
    target = gateway.invocations[0].target
    assert target.network_access == "unrestricted"
    assert target.resolved_api_key() == "admin-relay-secret"


@pytest.mark.asyncio
async def test_team_member_can_invoke_admin_managed_workspace_env_provider(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setenv("WORKSPACE_RELAY_API_KEY", "workspace-relay-secret")
    session, turn = await _turn(db_session, user_id="member-1")
    db_session.add(
        WorkspaceMembership(
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="member-1",
            role="member",
        )
    )
    await db_session.commit()
    await _select_catalog_model(
        db_session,
        session=session,
        name="workspace-private-provider",
        user_id="admin-1",
        scope="workspace",
        base_url="http://127.0.0.1:8000/v1",
        credential_source=LlmCredentialSource.ENV,
        env_var_name="WORKSPACE_RELAY_API_KEY",
    )
    gateway = FakeModelGateway(
        (
            TextDelta(text="workspace provider completed"),
            CompletionMetadata(response_id="workspace-ok", finish_reason="stop"),
        )
    )

    completed = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).run_turn(str(turn.id))

    assert completed.status == "completed"
    target = gateway.invocations[0].target
    assert target.network_access == "unrestricted"
    assert target.resolved_api_key() == "workspace-relay-secret"


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
async def test_partial_model_failure_is_marked_unsafe_for_fallback(db_session) -> None:
    _session, turn = await _turn(db_session, input_text="Stream a response.")
    gateway = PartialFailureGateway()

    result = await AgentLoopController(
        db_session,
        model_gateway=gateway,
    ).run_turn(
        turn_id=str(turn.id),
        target=_target(),
        capabilities=RuntimeCapabilities(supports_tools=False),
        strategy=RuntimeStrategy(allow_tools=False),
    )

    assert result.termination_reason == "model_failed"
    assert result.error_code == "model_request_failed"
    assert result.model_replay_safe is False


@pytest.mark.asyncio
async def test_responses_commentary_does_not_complete_without_final_answer(
    db_session,
) -> None:
    session, turn = await _turn(db_session, input_text="Work in two visible phases.")
    target = ModelTarget(
        endpoint_id="endpoint-responses",
        provider_kind="openai_compatible",
        model_name="gpt-responses-test",
        wire_protocol="responses",
    )
    continuation = ResponsesContinuation(
        response_id="resp-commentary",
        canonical_input_count=1,
        output_items=(
            {
                "type": "message",
                "id": "msg-commentary",
                "role": "assistant",
                "phase": "commentary",
                "content": [{"type": "output_text", "text": "Still checking."}],
            },
        ),
        target=target.continuation_target(),
    )
    gateway = FakeModelGateway(
        (
            TextDelta(text="Still checking.", phase="commentary"),
            CompletionMetadata(
                response_id="resp-commentary",
                finish_reason="incomplete",
                continuation=continuation,
            ),
        ),
        (
            TextDelta(text="The final result is ready.", phase="final_answer"),
            CompletionMetadata(response_id="resp-final", finish_reason="stop"),
        ),
    )
    result = await AgentLoopController(db_session, model_gateway=gateway).run_turn(
        turn_id=str(turn.id),
        target=target,
        capabilities=RuntimeCapabilities(supports_tools=False),
        strategy=RuntimeStrategy(allow_tools=False),
    )

    assert result.termination_reason == "assistant_final"
    assert result.final_text == "The final result is ready."
    assert len(gateway.invocations) == 2
    assert gateway.invocations[1].continuation is not None
    assert gateway.invocations[1].continuation.response_id == "resp-commentary"
    assert gateway.invocations[1].continuation.canonical_input_count == 2
    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    assert [message.role for message in messages] == ["user", "assistant", "assistant"]
    assert messages[1].content_parts == [
        {"type": "text", "text": "Still checking.", "phase": "commentary"}
    ]


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


@pytest.mark.asyncio
@pytest.mark.parametrize("rotation", ["none", "endpoint", "credential"])
async def test_responses_approval_resume_survives_service_restart(
    db_session,
    monkeypatch,
    caplog,
    rotation,
) -> None:
    session, turn = await _turn(
        db_session,
        input_text="Explain the command, run it with approval, then report the result.",
    )
    provider = LlmProvider(
        name="Responses continuation provider",
        kind="openai_compatible",
        base_url="https://responses.example/v1",
        wire_protocol="responses",
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "openai-compatible"},
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    credential = LlmProviderCredential(
        provider_id=str(provider.id),
        source=LlmCredentialSource.STORED,
        encrypted_secret=encrypt_secret("initial-responses-key"),
        fingerprint="initial-responses-fingerprint",
        masked_hint="init...-key",
        updated_by="dev",
    )
    db_session.add(credential)
    await db_session.commit()
    model = LlmModel(
        provider_id=str(provider.id),
        model_id="gpt-responses-test",
        display_name="Responses test model",
        supports_tools=True,
        supports_streaming=True,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    service = AgentCoreService(db_session)
    session = await service.session_repo.update_all(
        session,
        session_metadata={"model_selection": {"model_id": str(model.id)}},
        compression_state={
            "enabled": True,
            "threshold_chars": 1,
            "preserve_recent_messages": 0,
        },
    )

    opaque_secret = "encrypted-reasoning-must-stay-private"
    continuation_target = ModelTarget(
        endpoint_id=str(provider.id),
        provider_kind="openai_compatible",
        model_name="gpt-responses-test",
        wire_protocol="responses",
        base_url="https://responses.example/v1",
    ).continuation_target()
    first_continuation = ResponsesContinuation(
        response_id="resp-approval",
        canonical_input_count=1,
        output_items=(
            {
                "type": "reasoning",
                "id": "rs_approval",
                "encrypted_content": opaque_secret,
            },
            {
                "type": "message",
                "id": "msg_commentary",
                "role": "assistant",
                "phase": "commentary",
                "content": [{"type": "output_text", "text": "I will run it."}],
            },
            {
                "type": "function_call",
                "id": "fc_approval",
                "call_id": "call-responses-bash",
                "name": "bash",
                "arguments": json.dumps(
                    {
                        "command": f"{sys.executable} -c 'print(\"responses-approved\")'",
                        "cwd": str(settings.bioinfoflow_home),
                    }
                ),
            },
        ),
        target=continuation_target,
    )
    gateway = FakeModelGateway(
        (
            TextDelta(text="I will run it.", phase="commentary"),
            ToolCallDelta(
                index=0,
                call_id="call-responses-bash",
                name="bash",
                arguments_delta=json.dumps(
                    {
                        "command": f"{sys.executable} -c 'print(\"responses-approved\")'",
                        "cwd": str(settings.bioinfoflow_home),
                    }
                ),
            ),
            CompletionMetadata(
                response_id="resp-approval",
                finish_reason="tool_calls",
                continuation=first_continuation,
            ),
        ),
        (
            TextDelta(text="The approved command finished. ", phase="commentary"),
            TextDelta(text="Responses continuation completed.", phase="final_answer"),
            CompletionMetadata(
                response_id="resp-final",
                finish_reason="stop",
                continuation=ResponsesContinuation(
                    response_id="resp-final",
                    canonical_input_count=4,
                    output_items=(
                        {
                            "type": "message",
                            "id": "msg_final",
                            "role": "assistant",
                            "phase": "final_answer",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "Responses continuation completed.",
                                }
                            ],
                        },
                    ),
                    target=continuation_target,
                ),
            ),
        ),
    )

    waiting = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).run_turn(str(turn.id))

    assert waiting.status == "waiting_approval"
    assert waiting.final_text is None
    assert waiting.model_profile_snapshot["resolved_model_target"] == {
        "endpoint_id": str(provider.id),
        "provider_kind": "openai_compatible",
        "model_name": "gpt-responses-test",
        "wire_protocol": "responses",
        "base_url": "https://responses.example/v1",
    }
    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    assistant = next(message for message in messages if message.role == "assistant")
    assert sum(
        "_responses_continuation" in (message.message_metadata or {})
        for message in messages
    ) == 1
    assert all(
        "_responses_continuation" not in (message.message_metadata or {})
        for message in messages
        if message.role == "tool"
    )
    assert opaque_secret in json.dumps(assistant.message_metadata)
    assert opaque_secret not in json.dumps(
        provider_message_from_parts(
            assistant.role,
            assistant.content_parts,
            assistant.message_metadata,
        )
    )
    events = await AgentEventRepository(db_session).list_for_turn(turn_id=str(turn.id))
    assert opaque_secret not in json.dumps([event.payload for event in events])
    assert opaque_secret not in caplog.text

    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    assert len(actions) == 1
    monkeypatch.setattr("app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None)
    await service.decide_action(
        action_id=str(actions[0].id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )

    if rotation == "endpoint":
        provider.base_url = "https://changed.example/v1"
        provider.wire_protocol = "chat_completions"
        await db_session.commit()
    elif rotation == "credential":
        credential.encrypted_secret = encrypt_secret("rotated-responses-key")
        credential.fingerprint = "rotated-responses-fingerprint"
        await db_session.commit()

    resumed = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).resume_turn_after_action(str(actions[0].id))

    if rotation != "none":
        assert resumed.status == "failed"
        assert resumed.error_code == "model_selection_missing"
        assert len(gateway.invocations) == 1

        failed_action = await AgentActionRepository(db_session).get(str(actions[0].id))
        assert failed_action is not None
        assert failed_action.status == "failed"
        assert failed_action.error == {
            "type": "ModelConfigurationChanged",
            "message": (
                "The model configuration changed while approval was pending; "
                "the tool was not executed."
            ),
        }
        assert failed_action.completed_at is not None

        messages = await AgentMessageRepository(db_session).list_for_session(
            str(session.id)
        )
        matching_tool_results = [
            message
            for message in messages
            if message.role == "tool"
            and (message.message_metadata or {}).get("tool_call_id")
            == "call-responses-bash"
        ]
        assert len(matching_tool_results) == 1
        tool_message = provider_message_from_parts(
            matching_tool_results[0].role,
            matching_tool_results[0].content_parts,
            matching_tool_results[0].message_metadata,
        )
        assert tool_message["is_error"] is True
        assert json.loads(tool_message["content"])["error"] == failed_action.error
        assert all(
            "_responses_continuation" not in (message.message_metadata or {})
            for message in messages
        )

        follow_up_gateway = FakeModelGateway(
            (
                TextDelta(text="The follow-up turn completed.", phase="final_answer"),
                CompletionMetadata(response_id="resp-follow-up", finish_reason="stop"),
            )
        )
        follow_up_turn = await AgentCoreService(db_session).create_turn_record(
            session_id=str(session.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text="Continue after the cancelled tool call.",
        )
        follow_up = await AgentCoreRuntime(
            db_session,
            model_gateway=follow_up_gateway,
        ).run_turn(str(follow_up_turn.id))

        assert follow_up.status == "completed"
        assert follow_up.final_text == "The follow-up turn completed."
        assert len(follow_up_gateway.invocations) == 1
        assert follow_up_gateway.invocations[0].continuation is None
        return

    assert resumed.status == "completed"
    assert resumed.final_text == "Responses continuation completed."
    assert len(gateway.invocations) == 2
    resumed_invocation = gateway.invocations[1]
    assert resumed_invocation.target.wire_protocol == "responses"
    assert resumed_invocation.target.base_url == "https://responses.example/v1"
    assert resumed_invocation.continuation is not None
    assert resumed_invocation.continuation.response_id == "resp-approval"
    assert resumed_invocation.continuation.canonical_input_count == 3
    assert resumed_invocation.continuation.opaque_output_items() == (
        first_continuation.opaque_output_items()
    )
    tool_result = next(
        item
        for item in resumed_invocation.input_items
        if isinstance(item, ToolResultPart)
    )
    assert tool_result.call_id == "call-responses-bash"
    assert "responses-approved" in tool_result.output
    assert tool_result.is_error is False
    assert resumed_invocation.input_items[
        resumed_invocation.continuation.canonical_input_count :
    ] == (tool_result,)
    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    assert all(message.status == "committed" for message in messages)
    assert all(
        opaque_secret
        not in json.dumps(
            provider_message_from_parts(
                message.role,
                message.content_parts,
                message.message_metadata,
            )
        )
        for message in messages
    )
    events = await AgentEventRepository(db_session).list_for_turn(turn_id=str(turn.id))
    assert opaque_secret not in json.dumps([event.payload for event in events])
    assert opaque_secret not in caplog.text


@pytest.mark.asyncio
async def test_responses_two_tool_rounds_advance_canonical_suffix_without_duplicates(
    db_session,
    monkeypatch,
) -> None:
    _session, turn = await _turn(db_session, input_text="Run two commands, then finish.")
    target = ModelTarget(
        endpoint_id="endpoint-responses",
        provider_kind="openai_compatible",
        model_name="gpt-responses-test",
        wire_protocol="responses",
    )
    gateway = FakeModelGateway(
        (
            ToolCallDelta(
                index=0,
                call_id="call-one",
                name="bash",
                arguments_delta='{"command":"first"}',
            ),
            CompletionMetadata(
                response_id="resp-one",
                finish_reason="tool_calls",
                continuation=ResponsesContinuation(
                    response_id="resp-one",
                    canonical_input_count=1,
                    output_items=(
                        {
                            "type": "function_call",
                            "call_id": "call-one",
                            "name": "bash",
                            "arguments": '{"command":"first"}',
                        },
                    ),
                    target=target.continuation_target(),
                ),
            ),
        ),
        (
            ToolCallDelta(
                index=0,
                call_id="call-two",
                name="bash",
                arguments_delta='{"command":"second"}',
            ),
            CompletionMetadata(
                response_id="resp-two",
                finish_reason="tool_calls",
                continuation=ResponsesContinuation(
                    response_id="resp-two",
                    canonical_input_count=3,
                    output_items=(
                        {
                            "type": "function_call",
                            "call_id": "call-two",
                            "name": "bash",
                            "arguments": '{"command":"second"}',
                        },
                    ),
                    target=target.continuation_target(),
                ),
            ),
        ),
        (
            TextDelta(text="Both commands completed.", phase="final_answer"),
            CompletionMetadata(response_id="resp-final", finish_reason="stop"),
        ),
    )
    controller = AgentLoopController(db_session, model_gateway=gateway)

    async def completed_execution(*args, **kwargs):
        del args, kwargs
        return ToolExecutionResult(
            action_id="completed-action",
            status="completed",
            result={"ok": True},
        )

    monkeypatch.setattr(controller.executor, "execute", completed_execution)
    result = await controller.run_turn(turn_id=str(turn.id), target=target)

    assert result.termination_reason == "assistant_final"
    assert len(gateway.invocations) == 3
    first_resume = gateway.invocations[1]
    assert first_resume.continuation is not None
    assert first_resume.continuation.canonical_input_count == 2
    assert [
        item.call_id
        for item in first_resume.input_items[
            first_resume.continuation.canonical_input_count :
        ]
        if isinstance(item, ToolResultPart)
    ] == ["call-one"]
    second_resume = gateway.invocations[2]
    assert second_resume.continuation is not None
    assert second_resume.continuation.canonical_input_count == 4
    assert [
        item.call_id
        for item in second_resume.input_items[
            second_resume.continuation.canonical_input_count :
        ]
        if isinstance(item, ToolResultPart)
    ] == ["call-two"]

    messages = await AgentMessageRepository(db_session).list_for_session(
        str(turn.session_id)
    )
    continuation_messages = [
        message
        for message in messages
        if "_responses_continuation" in (message.message_metadata or {})
    ]
    assert continuation_messages == []
    assert all(
        "_responses_continuation" not in (message.message_metadata or {})
        for message in messages
        if message.role == "tool"
    )


@pytest.mark.asyncio
async def test_fallback_target_change_discards_durable_responses_continuation(
    db_session,
) -> None:
    session, turn = await _turn(db_session, input_text="Use a fallback if needed.")
    responses_target = ModelTarget(
        endpoint_id="responses-endpoint",
        provider_kind="openai_compatible",
        model_name="responses-model",
        wire_protocol="responses",
        base_url="https://responses.example/v1",
    )
    await AgentTranscriptStore(db_session).append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        parts=[{"type": "text", "text": "Trying another model."}],
        metadata=metadata_with_responses_continuation(
            {"kind": "commentary"},
            ResponsesContinuation(
                response_id="resp-primary",
                output_items=(
                    {
                        "type": "reasoning",
                        "encrypted_content": "discard-on-fallback",
                    },
                ),
                canonical_input_count=2,
                target=responses_target.continuation_target(),
            ),
        ),
    )
    gateway = FakeModelGateway(
        (
            TextDelta(text="Fallback completed."),
            CompletionMetadata(response_id="chat-fallback", finish_reason="stop"),
        )
    )
    fallback_target = ModelTarget(
        endpoint_id="chat-endpoint",
        provider_kind="anthropic",
        model_name="fallback-model",
        wire_protocol="chat_completions",
        base_url="https://fallback.example/v1",
    )

    result = await AgentLoopController(db_session, model_gateway=gateway).run_turn(
        turn_id=str(turn.id),
        target=fallback_target,
    )

    assert result.termination_reason == "assistant_final"
    assert gateway.invocations[0].continuation is None
    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    assert all(
        "_responses_continuation" not in (message.message_metadata or {})
        for message in messages
    )
    assert "discard-on-fallback" not in repr(
        [message.message_metadata for message in messages]
    )


@pytest.mark.asyncio
async def test_responses_refusal_only_returns_specific_error_without_empty_retry(
    db_session,
) -> None:
    _session, turn = await _turn(db_session, input_text="Request something refused.")
    gateway = FakeModelGateway(
        (
            ModelWarning(
                code="response_refusal",
                message="The model refused this request.",
            ),
            CompletionMetadata(response_id="resp-refusal", finish_reason="completed"),
        )
    )

    result = await AgentLoopController(db_session, model_gateway=gateway).run_turn(
        turn_id=str(turn.id),
        target=ModelTarget(
            endpoint_id="endpoint-responses",
            provider_kind="openai_compatible",
            model_name="gpt-responses-test",
            wire_protocol="responses",
        ),
    )

    assert result.termination_reason == "model_failed"
    assert result.error_code == "model_refusal"
    assert result.error_message == "The model refused this request."
    assert len(gateway.invocations) == 1
    events = await AgentEventRepository(db_session).list_for_turn(turn_id=str(turn.id))
    warning = next(event for event in events if event.type == AgentEventType.MODEL_WARNING)
    assert warning.payload == {
        "code": "response_refusal",
        "message": "The model refused this request.",
    }


@pytest.mark.asyncio
async def test_responses_unknown_item_with_final_answer_emits_warning_and_succeeds(
    db_session,
) -> None:
    _session, turn = await _turn(db_session, input_text="Return a final answer.")
    gateway = FakeModelGateway(
        (
            ModelWarning(
                code="unsupported_response_item",
                message="Unsupported Responses output item type: future_item",
            ),
            TextDelta(text="Safe final answer.", phase="final_answer"),
            CompletionMetadata(response_id="resp-warning", finish_reason="completed"),
        )
    )

    result = await AgentLoopController(db_session, model_gateway=gateway).run_turn(
        turn_id=str(turn.id),
        target=ModelTarget(
            endpoint_id="endpoint-responses",
            provider_kind="openai_compatible",
            model_name="gpt-responses-test",
            wire_protocol="responses",
        ),
    )

    assert result.termination_reason == "assistant_final"
    assert result.final_text == "Safe final answer."
    events = await AgentEventRepository(db_session).list_for_turn(turn_id=str(turn.id))
    assert any(event.type == AgentEventType.MODEL_WARNING for event in events)


@pytest.mark.asyncio
async def test_completed_responses_turn_continues_into_next_turn_with_one_session_anchor(
    db_session,
) -> None:
    session, first_turn = await _turn(
        db_session,
        input_text="Inspect the workflow and remember the result.",
    )
    target = ModelTarget(
        endpoint_id="endpoint-responses-session",
        provider_kind="openai_compatible",
        model_name="gpt-responses-session",
        wire_protocol="responses",
    )
    first_continuation = ResponsesContinuation(
        response_id="resp-first-turn",
        canonical_input_count=1,
        output_items=(
            {
                "type": "reasoning",
                "id": "reasoning-first-turn",
                "encrypted_content": "encrypted-first-turn",
            },
            {
                "type": "message",
                "id": "message-first-turn",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": "First result."}],
            },
        ),
        target=target.continuation_target(),
    )
    second_continuation = ResponsesContinuation(
        response_id="resp-second-turn",
        canonical_input_count=3,
        output_items=(
            {
                "type": "message",
                "id": "message-second-turn",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": "Second result."}],
            },
        ),
        target=target.continuation_target(),
    )
    gateway = FakeModelGateway(
        (
            TextDelta(text="First result.", phase="final_answer"),
            CompletionMetadata(
                response_id="resp-first-turn",
                finish_reason="completed",
                continuation=first_continuation,
            ),
        ),
        (
            TextDelta(text="Second result.", phase="final_answer"),
            CompletionMetadata(
                response_id="resp-second-turn",
                finish_reason="completed",
                continuation=second_continuation,
            ),
        ),
    )
    controller = AgentLoopController(db_session, model_gateway=gateway)

    first_result = await controller.run_turn(
        turn_id=str(first_turn.id),
        target=target,
    )
    assert first_result.termination_reason == "assistant_final"

    second_turn = await AgentCoreService(db_session).create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Use that result for a follow-up.",
    )
    second_result = await controller.run_turn(
        turn_id=str(second_turn.id),
        target=target,
    )

    assert second_result.termination_reason == "assistant_final"
    continuation = gateway.invocations[1].continuation
    assert continuation is not None
    assert continuation.response_id == "resp-first-turn"
    assert continuation.canonical_input_count == 2
    assert gateway.invocations[1].input_items[2:] == (
        TextPart(text="Use that result for a follow-up."),
    )
    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    anchors = [
        message
        for message in messages
        if "_responses_continuation" in (message.message_metadata or {})
    ]
    assert len(anchors) == 1
    assert anchors[0].turn_id == second_turn.id


@pytest.mark.asyncio
async def test_cross_turn_responses_continuation_is_invalidated_when_context_compacts(
    db_session,
) -> None:
    session, first_turn = await _turn(db_session, input_text="A" * 80)
    session = await AgentCoreService(db_session).session_repo.update_all(
        session,
        compression_state={
            "enabled": True,
            "threshold_chars": 1,
            "preserve_recent_messages": 1,
        },
    )
    target = ModelTarget(
        endpoint_id="endpoint-responses-compaction",
        provider_kind="openai_compatible",
        model_name="gpt-responses-compaction",
        wire_protocol="responses",
    )
    gateway = FakeModelGateway(
        (
            TextDelta(text="First result.", phase="final_answer"),
            CompletionMetadata(
                response_id="resp-before-compaction",
                finish_reason="completed",
                continuation=ResponsesContinuation(
                    response_id="resp-before-compaction",
                    canonical_input_count=1,
                    output_items=(
                        {
                            "type": "reasoning",
                            "id": "reasoning-before-compaction",
                            "encrypted_content": "discard-after-compaction",
                        },
                    ),
                    target=target.continuation_target(),
                ),
            ),
        ),
        (
            TextDelta(text="Fresh result.", phase="final_answer"),
            CompletionMetadata(response_id="resp-after-compaction", finish_reason="completed"),
        ),
    )
    controller = AgentLoopController(db_session, model_gateway=gateway)
    await controller.run_turn(turn_id=str(first_turn.id), target=target)
    before_compaction = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    assert sum(
        "_responses_continuation" in (message.message_metadata or {})
        for message in before_compaction
    ) == 1
    assert "discard-after-compaction" in repr(
        [message.message_metadata for message in before_compaction]
    )
    second_turn = await AgentCoreService(db_session).create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Continue after compaction.",
    )

    result = await controller.run_turn(turn_id=str(second_turn.id), target=target)

    assert result.termination_reason == "assistant_final"
    assert gateway.invocations[1].continuation is None
    assert any(
        isinstance(item, TextPart) and "Conversation summary for continuity" in item.text
        for item in gateway.invocations[1].input_items
    )
    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    assert "discard-after-compaction" not in repr(
        [message.message_metadata for message in messages]
    )
