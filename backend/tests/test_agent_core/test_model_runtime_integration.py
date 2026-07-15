from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
import json
import sys

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agent_core import AgentActionStatus, AgentTurnStatus
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
    AgentTurnRepository,
)
from app.services.agent_core import AgentCoreService
from app.services.agent_core.core.loop import AgentLoopController
from app.services.agent_core.core.runtime_strategy import (
    RuntimeCapabilities,
    RuntimeStrategy,
)
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.runtime import AgentCoreRuntime
from app.services.agent_core.tools.executor import ToolExecutionResult
from app.services.llm.credentials import (
    derive_model_target_revision,
    encrypt_secret,
    resolve_credential_material,
)
from app.services.llm.provider_templates import route_provider_model_name
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
    canonical_input_prefix_digest,
)
from app.services.model_runtime.errors import ModelError
from app.services.agent_core.transcript import provider_message_from_parts
from app.services.agent_core.transcript.messages import (
    metadata_with_responses_continuation,
    text_part,
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


class BlockingFinalGateway:
    def __init__(self, text: str = "Long model call completed.") -> None:
        self.text = text
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.invocations: list[ModelInvocation] = []

    async def invoke(self, invocation: ModelInvocation) -> AsyncIterator[ModelEvent]:
        self.invocations.append(invocation)
        self.started.set()
        await self.release.wait()
        yield TextDelta(text=self.text, phase="final_answer")
        yield CompletionMetadata(response_id="resp-blocking", finish_reason="stop")


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


class NeverCompletingGateway:
    def __init__(self) -> None:
        self.invocations: list[ModelInvocation] = []
        self.cancelled = asyncio.Event()

    async def invoke(self, invocation: ModelInvocation) -> AsyncIterator[ModelEvent]:
        self.invocations.append(invocation)
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled.set()
        if False:  # pragma: no cover - keeps this an async generator
            yield CompletionMetadata(response_id=None, finish_reason=None)


class PartialThenBlockingGateway:
    def __init__(self) -> None:
        self.invocations: list[ModelInvocation] = []
        self.cancelled = asyncio.Event()

    async def invoke(self, invocation: ModelInvocation) -> AsyncIterator[ModelEvent]:
        self.invocations.append(invocation)
        try:
            yield TextDelta(text="Partial output.", phase="final_answer")
            await asyncio.Event().wait()
        finally:
            self.cancelled.set()


def _synchronize_two_resume_turn_reads(monkeypatch, *, turn_id: str) -> None:
    original_get = AgentTurnRepository.get
    both_workers_loaded = asyncio.Event()
    load_lock = asyncio.Lock()
    loaded_repositories: set[int] = set()

    async def synchronized_get(repo, item_id):
        turn = await original_get(repo, item_id)
        repo_id = id(repo)
        if (
            item_id == turn_id
            and turn is not None
            and turn.status
            in {AgentTurnStatus.WAITING_APPROVAL, AgentTurnStatus.RUNNING}
            and repo_id not in loaded_repositories
            and not both_workers_loaded.is_set()
        ):
            async with load_lock:
                loaded_repositories.add(repo_id)
                if len(loaded_repositories) == 2:
                    both_workers_loaded.set()
            await asyncio.wait_for(both_workers_loaded.wait(), timeout=2)
        return turn

    monkeypatch.setattr(AgentTurnRepository, "get", synchronized_get)


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
    monkeypatch.setattr(settings, "bioinfoflow_credential_key", "team-test-key")
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
    monkeypatch.setattr(settings, "bioinfoflow_credential_key", "team-test-key")
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
    monkeypatch.setattr(settings, "bioinfoflow_credential_key", "team-test-key")
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
@pytest.mark.parametrize(
    ("user_id", "role", "scope"),
    [
        ("member-1", "member", "workspace"),
        ("admin-1", "admin", "user"),
        ("owner-1", "owner", "global"),
    ],
)
async def test_public_provider_scope_or_admin_authority_never_grants_unrestricted_network(
    db_session,
    monkeypatch,
    user_id: str,
    role: str,
    scope: str,
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "bioinfoflow_credential_key", "team-test-key")
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("1.1.1.1", 0))],
    )
    session, turn = await _turn(db_session, user_id=user_id)
    db_session.add(
        WorkspaceMembership(
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id=user_id,
            role=role,
        )
    )
    await db_session.commit()
    await _select_catalog_model(
        db_session,
        session=session,
        name=f"{scope}-public-provider",
        user_id=("admin-1" if scope == "workspace" else user_id),
        scope=scope,
        base_url="https://relay.example.com/v1",
    )
    gateway = FakeModelGateway(
        (
            TextDelta(text="public provider completed"),
            CompletionMetadata(response_id="public-shared-ok", finish_reason="stop"),
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
    monkeypatch.setattr(settings, "bioinfoflow_credential_key", "team-test-key")
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
    monkeypatch.setattr(settings, "bioinfoflow_credential_key", "team-test-key")
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

    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
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
async def test_model_attempt_timeout_is_bounded_and_structured(
    db_session,
    monkeypatch,
) -> None:
    _session, turn = await _turn(db_session, input_text="Never finish this request.")
    gateway = NeverCompletingGateway()
    monkeypatch.setitem(settings.__dict__, "agent_model_attempt_timeout_seconds", 0.01)
    monkeypatch.setattr(settings, "agent_retry_max_attempts", 1)

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
    assert result.error_message == "The model provider request timed out."
    assert result.model_replay_safe is True
    assert result.model_error == {
        "category": "timeout",
        "message": "The model provider request timed out.",
        "http_status": None,
        "provider_code": "model_attempt_timeout",
        "retryable": True,
        "replay_safe": True,
        "retry_after_seconds": None,
        "request_id": None,
    }
    assert len(gateway.invocations) == 1
    assert gateway.cancelled.is_set()


@pytest.mark.asyncio
async def test_model_attempt_timeout_after_output_is_not_replay_safe(
    db_session,
    monkeypatch,
) -> None:
    _session, turn = await _turn(db_session, input_text="Start and then stall.")
    gateway = PartialThenBlockingGateway()
    monkeypatch.setitem(settings.__dict__, "agent_model_attempt_timeout_seconds", 0.01)
    monkeypatch.setattr(settings, "agent_retry_max_attempts", 2)
    monkeypatch.setattr(settings, "agent_retry_base_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "agent_retry_max_delay_seconds", 0.0)

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
    assert result.model_error is not None
    assert result.model_error["category"] == "timeout"
    assert result.model_error["replay_safe"] is False
    assert len(gateway.invocations) == 1
    assert gateway.cancelled.is_set()


@pytest.mark.asyncio
async def test_model_attempt_timeout_closes_stream_after_processing_timeout(
    db_session,
    monkeypatch,
) -> None:
    _session, turn = await _turn(db_session, input_text="Start and then stall.")
    gateway = PartialThenBlockingGateway()
    original_append = AgentEventLedger.append

    async def blocking_text_delta_append(self, **kwargs):
        if kwargs.get("type") == AgentEventType.ASSISTANT_TEXT_DELTA:
            await asyncio.Event().wait()
        return await original_append(self, **kwargs)

    monkeypatch.setattr(AgentEventLedger, "append", blocking_text_delta_append)
    monkeypatch.setitem(settings.__dict__, "agent_model_attempt_timeout_seconds", 0.01)
    monkeypatch.setattr(settings, "agent_retry_max_attempts", 2)
    monkeypatch.setattr(settings, "agent_retry_base_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "agent_retry_max_delay_seconds", 0.0)

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
    assert len(gateway.invocations) == 1
    assert gateway.cancelled.is_set()


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
        target_revision="commentary-target-revision",
    )
    continuation = ResponsesContinuation(
        response_id="resp-commentary",
        canonical_input_count=1,
        canonical_input_digest=canonical_input_prefix_digest(
            (TextPart(text="Work in two visible phases."),)
        ),
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
    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    assert [message.role for message in messages] == ["user", "assistant", "assistant"]
    assert messages[1].content_parts == [
        {"type": "text", "text": "Still checking.", "phase": "commentary"}
    ]


@pytest.mark.asyncio
async def test_non_stream_turn_emits_completed_event_without_text_delta(
    db_session,
) -> None:
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
        strategy=RuntimeStrategy(
            use_streaming=True, allow_tools=False, allow_thinking=True
        ),
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
    _session, turn = await _turn(
        db_session, input_text="List projects, then summarize."
    )
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
async def test_failed_tool_result_round_trips_with_error_flag(
    db_session, monkeypatch
) -> None:
    _session, turn = await _turn(
        db_session, input_text="Run a command and report failure."
    )
    gateway = FakeModelGateway(
        (
            ToolCallDelta(
                index=0,
                call_id="call-failed",
                name="bash",
                arguments_delta="{}",
            ),
            CompletionMetadata(
                response_id="chatcmpl-failed", finish_reason="tool_calls"
            ),
        ),
        (
            TextDelta(text="The command failed."),
            CompletionMetadata(
                response_id="chatcmpl-after-failure", finish_reason="stop"
            ),
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
            CompletionMetadata(
                response_id="chatcmpl-approval", finish_reason="tool_calls"
            ),
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
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None
    )
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
    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    assert [message.role for message in messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]


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
    await service.session_repo.update_all(
        session, default_model_profile_id=str(profile.id)
    )
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

    completed = await AgentCoreRuntime(db_session, model_gateway=gateway).run_turn(
        str(turn.id)
    )

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
    session, turn = await _turn(
        db_session, input_text="Fallback, then request approval."
    )
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
    await service.session_repo.update_all(
        session, default_model_profile_id=str(profile.id)
    )
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
            CompletionMetadata(
                response_id="chatcmpl-fallback-resume", finish_reason="stop"
            ),
        ),
    )

    waiting = await AgentCoreRuntime(db_session, model_gateway=gateway).run_turn(
        str(turn.id)
    )

    assert waiting.status == "waiting_approval"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None
    )
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
@pytest.mark.parametrize(
    ("rotation", "decision", "preexisting_tool_result"),
    [
        ("none", "approve", False),
        ("endpoint", "approve", False),
        ("credential", "approve", False),
        ("env_credential", "approve", False),
        pytest.param(
            "endpoint",
            "reject",
            False,
            id="endpoint-rejected-without-tool-result",
        ),
        pytest.param(
            "endpoint",
            "reject",
            True,
            id="endpoint-rejected-with-existing-tool-result",
        ),
    ],
)
async def test_responses_approval_resume_survives_service_restart(
    db_session,
    monkeypatch,
    caplog,
    rotation,
    decision,
    preexisting_tool_result,
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
    if rotation == "env_credential":
        monkeypatch.setenv("RESPONSES_APPROVAL_API_KEY", "initial-responses-key")
        credential = LlmProviderCredential(
            provider_id=str(provider.id),
            source=LlmCredentialSource.ENV,
            env_var_name="RESPONSES_APPROVAL_API_KEY",
            fingerprint="initial-responses-fingerprint",
            masked_hint="env:RESPONSES_APPROVAL_API_KEY",
            updated_by="dev",
        )
    else:
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
    routed_model_name = route_provider_model_name(
        "openai_compatible",
        "gpt-responses-test",
        wire_protocol="responses",
    )
    initial_target_revision = derive_model_target_revision(
        endpoint_id=str(provider.id),
        provider_kind="openai_compatible",
        model_name="gpt-responses-test",
        wire_protocol="responses",
        routed_model_name=routed_model_name,
        base_url="https://responses.example/v1",
        credential_material=resolve_credential_material(credential),
    )
    continuation_target = ModelTarget(
        endpoint_id=str(provider.id),
        provider_kind="openai_compatible",
        model_name="gpt-responses-test",
        routed_model_name=routed_model_name,
        wire_protocol="responses",
        base_url="https://responses.example/v1",
        target_revision=initial_target_revision,
    ).continuation_target()
    first_continuation = ResponsesContinuation(
        response_id="resp-approval",
        canonical_input_count=1,
        canonical_input_digest=canonical_input_prefix_digest(
            (
                TextPart(
                    text=(
                        "Explain the command, run it with approval, then report the result."
                    )
                ),
            )
        ),
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
    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    assistant = next(message for message in messages if message.role == "assistant")
    assert (
        sum(
            "_responses_continuation" in (message.message_metadata or {})
            for message in messages
        )
        == 1
    )
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
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None
    )
    await service.decide_action(
        action_id=str(actions[0].id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision=decision,
    )

    rejected_error = {
        "type": "UserRejected",
        "message": "The user rejected this tool call.",
    }
    if preexisting_tool_result:
        await AgentTranscriptStore(db_session).append_parts(
            session_id=str(session.id),
            turn_id=str(turn.id),
            role="tool",
            parts=[
                text_part(
                    json.dumps(
                        {
                            "tool": actions[0].name,
                            "status": "rejected",
                            "result": None,
                            "error": rejected_error,
                        },
                        separators=(",", ":"),
                    )
                )
            ],
            metadata={
                "tool_call_id": actions[0].tool_call_id,
                "tool": actions[0].name,
                "is_error": True,
            },
        )

    if rotation == "endpoint":
        provider.base_url = "https://changed.example/v1"
        provider.wire_protocol = "chat_completions"
        await db_session.commit()
    elif rotation == "credential":
        credential.encrypted_secret = encrypt_secret("rotated-responses-key")
        credential.fingerprint = "rotated-responses-fingerprint"
        await db_session.commit()
    elif rotation == "env_credential":
        monkeypatch.setenv("RESPONSES_APPROVAL_API_KEY", "rotated-responses-key")

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
        if decision == "reject":
            assert failed_action.status == "rejected"
            assert failed_action.error is None
            expected_tool_error = rejected_error
        else:
            assert failed_action.status == "failed"
            assert failed_action.error == {
                "type": "ModelConfigurationChanged",
                "message": (
                    "The model configuration changed while approval was pending; "
                    "the tool was not executed."
                ),
            }
            assert failed_action.completed_at is not None
            expected_tool_error = failed_action.error

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
        assert json.loads(tool_message["content"])["error"] == expected_tool_error
        assert all(
            "_responses_continuation" not in (message.message_metadata or {})
            for message in messages
        )

        events = await AgentEventRepository(db_session).list_for_turn(
            turn_id=str(turn.id)
        )
        action_failed_events = [
            event for event in events if event.type == AgentEventType.ACTION_FAILED
        ]
        assert len(action_failed_events) == (0 if decision == "reject" else 1)

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
    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
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


async def _responses_batch_approval_fixture(db_session, *, session, input_text: str):
    provider = LlmProvider(
        name="Responses batch approval provider",
        kind="openai_compatible",
        base_url="https://responses-batch.example/v1",
        wire_protocol="responses",
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "openai-compatible"},
    )
    db_session.add(provider)
    await db_session.flush()
    credential = LlmProviderCredential(
        provider_id=str(provider.id),
        source=LlmCredentialSource.STORED,
        encrypted_secret=encrypt_secret("responses-batch-key"),
        fingerprint="responses-batch-fingerprint",
        masked_hint="resp...-key",
        updated_by="dev",
    )
    db_session.add(credential)
    model = LlmModel(
        provider_id=str(provider.id),
        model_id="gpt-responses-batch-test",
        display_name="Responses batch test model",
        supports_tools=True,
        supports_streaming=True,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(provider)
    await AgentCoreService(db_session).session_repo.update_all(
        session,
        session_metadata={"model_selection": {"model_id": str(model.id)}},
        toolset_policy={"name": "execution"},
    )
    routed_model_name = route_provider_model_name(
        "openai_compatible",
        model.model_id,
        wire_protocol="responses",
    )
    target_revision = derive_model_target_revision(
        endpoint_id=str(provider.id),
        provider_kind="openai_compatible",
        model_name=model.model_id,
        wire_protocol="responses",
        routed_model_name=routed_model_name,
        base_url=provider.base_url,
        credential_material=resolve_credential_material(credential),
    )
    continuation_target = ModelTarget(
        endpoint_id=str(provider.id),
        provider_kind="openai_compatible",
        model_name=model.model_id,
        routed_model_name=routed_model_name,
        wire_protocol="responses",
        base_url=provider.base_url,
        target_revision=target_revision,
    ).continuation_target()
    return provider, ResponsesContinuation(
        response_id="resp-batch-approval",
        canonical_input_count=1,
        canonical_input_digest=canonical_input_prefix_digest(
            (TextPart(text=input_text),)
        ),
        output_items=(),
        target=continuation_target,
    )


@pytest.mark.asyncio
async def test_responses_tool_call_batch_waits_for_every_approval_before_resume(
    db_session,
    monkeypatch,
    tmp_path,
) -> None:
    input_text = "Run both commands only after deciding each approval."
    session, turn = await _turn(db_session, input_text=input_text)
    _provider, continuation = await _responses_batch_approval_fixture(
        db_session,
        session=session,
        input_text=input_text,
    )
    first_marker = tmp_path / "first-approved.txt"
    rejected_marker = tmp_path / "second-rejected.txt"
    first_command = (
        f'{sys.executable} -c "from pathlib import Path; '
        f"Path({str(first_marker)!r}).write_text('ran')\""
    )
    rejected_command = (
        f'{sys.executable} -c "from pathlib import Path; '
        f"Path({str(rejected_marker)!r}).write_text('ran')\""
    )
    gateway = FakeModelGateway(
        (
            ToolCallDelta(
                index=0,
                call_id="call-responses-batch-first",
                name="bash",
                arguments_delta=json.dumps(
                    {"command": first_command, "cwd": str(settings.bioinfoflow_home)}
                ),
            ),
            ToolCallDelta(
                index=1,
                call_id="call-responses-batch-second",
                name="bash",
                arguments_delta=json.dumps(
                    {"command": rejected_command, "cwd": str(settings.bioinfoflow_home)}
                ),
            ),
            CompletionMetadata(
                response_id="resp-batch-approval",
                finish_reason="tool_calls",
                continuation=continuation,
            ),
        ),
        (
            TextDelta(text="The approved batch is resolved.", phase="final_answer"),
            CompletionMetadata(response_id="resp-batch-final", finish_reason="stop"),
        ),
    )
    waiting = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).run_turn(str(turn.id))

    assert waiting.status == AgentTurnStatus.WAITING_APPROVAL
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    actions_by_call_id = {action.tool_call_id: action for action in actions}
    first_action = actions_by_call_id["call-responses-batch-first"]
    second_action = actions_by_call_id["call-responses-batch-second"]
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_: None
    )
    await AgentCoreService(db_session).decide_action(
        action_id=str(first_action.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )

    still_waiting = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).resume_turn_after_action(str(first_action.id))

    assert still_waiting.status == AgentTurnStatus.WAITING_APPROVAL
    assert len(gateway.invocations) == 1
    assert first_marker.read_text() == "ran"
    assert not rejected_marker.exists()
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    actions_by_call_id = {action.tool_call_id: action for action in actions}
    assert [
        actions_by_call_id[call_id].status
        for call_id in ("call-responses-batch-first", "call-responses-batch-second")
    ] == [
        AgentActionStatus.COMPLETED,
        AgentActionStatus.WAITING_DECISION,
    ]
    assert [
        actions_by_call_id[call_id].requires_resume
        for call_id in ("call-responses-batch-first", "call-responses-batch-second")
    ] == [False, True]
    tool_messages = [
        message
        for message in await AgentMessageRepository(db_session).list_for_session(
            str(session.id)
        )
        if message.role == "tool"
    ]
    assert [message.message_metadata["tool_call_id"] for message in tool_messages] == [
        "call-responses-batch-first"
    ]

    idempotent_retry = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).resume_turn_after_action(str(first_action.id))
    assert idempotent_retry.status == AgentTurnStatus.WAITING_APPROVAL
    assert len(gateway.invocations) == 1
    tool_messages = [
        message
        for message in await AgentMessageRepository(db_session).list_for_session(
            str(session.id)
        )
        if message.role == "tool"
    ]
    assert [message.message_metadata["tool_call_id"] for message in tool_messages] == [
        "call-responses-batch-first"
    ]

    await AgentCoreService(db_session).decide_action(
        action_id=str(second_action.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="reject",
    )
    completed = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).resume_turn_after_action(str(second_action.id))

    assert completed.status == AgentTurnStatus.COMPLETED
    assert completed.final_text == "The approved batch is resolved."
    assert len(gateway.invocations) == 2
    assert not rejected_marker.exists()
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    actions_by_call_id = {action.tool_call_id: action for action in actions}
    assert [
        actions_by_call_id[call_id].status
        for call_id in ("call-responses-batch-first", "call-responses-batch-second")
    ] == [
        AgentActionStatus.COMPLETED,
        AgentActionStatus.REJECTED,
    ]
    assert [
        actions_by_call_id[call_id].requires_resume
        for call_id in ("call-responses-batch-first", "call-responses-batch-second")
    ] == [False, False]
    tool_results = [
        item
        for item in gateway.invocations[1].input_items
        if isinstance(item, ToolResultPart)
    ]
    assert [item.call_id for item in tool_results] == [
        "call-responses-batch-first",
        "call-responses-batch-second",
    ]
    assert tool_results[0].is_error is False
    assert tool_results[1].is_error is True
    assert "UserRejected" in tool_results[1].output


@pytest.mark.asyncio
async def test_stale_resume_job_cannot_claim_after_a_new_approval_batch(
    db_session,
    monkeypatch,
    tmp_path,
) -> None:
    input_text = "Run the first approved command, then request a second approval."
    session, turn = await _turn(db_session, input_text=input_text)
    _provider, continuation = await _responses_batch_approval_fixture(
        db_session,
        session=session,
        input_text=input_text,
    )
    first_marker = tmp_path / "old-approval-batch.txt"
    first_command = (
        f'{sys.executable} -c "from pathlib import Path; '
        f"Path({str(first_marker)!r}).write_text('ran')\""
    )
    gateway = FakeModelGateway(
        (
            ToolCallDelta(
                index=0,
                call_id="call-old-batch",
                name="bash",
                arguments_delta=json.dumps(
                    {"command": first_command, "cwd": str(settings.bioinfoflow_home)}
                ),
            ),
            CompletionMetadata(
                response_id="resp-old-batch",
                finish_reason="tool_calls",
                continuation=continuation,
            ),
        ),
        (
            ToolCallDelta(
                index=0,
                call_id="call-current-batch",
                name="ask_user",
                arguments_delta=json.dumps(
                    {
                        "questions": [
                            {
                                "question": "Continue with the current batch?",
                                "header": "Continue",
                                "options": [
                                    {"label": "Yes", "description": "Continue."},
                                    {"label": "No", "description": "Stop."},
                                ],
                            }
                        ]
                    }
                ),
            ),
            CompletionMetadata(
                response_id="resp-current-batch",
                finish_reason="tool_calls",
            ),
        ),
        (
            TextDelta(
                text="A stale job incorrectly advanced the turn.", phase="final_answer"
            ),
            CompletionMetadata(response_id="resp-stale-final", finish_reason="stop"),
        ),
    )
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_: None
    )
    waiting = await AgentCoreRuntime(db_session, model_gateway=gateway).run_turn(
        str(turn.id)
    )
    first_action = (
        await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    )[0]
    assert waiting.status == AgentTurnStatus.WAITING_APPROVAL
    old_batch_token = waiting.resume_batch_token
    assert old_batch_token
    await AgentCoreService(db_session).decide_action(
        action_id=str(first_action.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )
    second_wait = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).resume_turn_after_action(str(first_action.id))
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    second_action = next(
        action for action in actions if action.tool_call_id == "call-current-batch"
    )

    assert second_wait.status == AgentTurnStatus.WAITING_APPROVAL
    assert first_marker.read_text() == "ran"
    assert first_action.tool_call_id == "call-old-batch"
    assert second_action.status == AgentActionStatus.WAITING_DECISION
    assert len(gateway.invocations) == 2

    stale_claim_turn, stale_claimed = await AgentTurnRepository(
        db_session
    ).claim_action_resume(
        str(turn.id),
        owner_token="stale-old-batch-owner",
        expected_resume_batch_token=old_batch_token,
        claimed_at=datetime.now(timezone.utc),
        lease_until=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    assert stale_claimed is False
    assert stale_claim_turn.status == AgentTurnStatus.WAITING_APPROVAL

    stale_result = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).resume_turn_after_action(str(first_action.id))
    durable_turn = await AgentTurnRepository(db_session).get(str(turn.id))

    assert stale_result.status == AgentTurnStatus.WAITING_APPROVAL
    assert durable_turn.status == AgentTurnStatus.WAITING_APPROVAL
    assert durable_turn.claimed_at is None
    assert durable_turn.lease_until is None
    assert len(gateway.invocations) == 2


@pytest.mark.asyncio
async def test_turn_heartbeat_keeps_long_model_call_out_of_startup_recovery(
    db_engine,
    db_session,
    monkeypatch,
) -> None:
    input_text = "Wait for the long model response."
    session, turn = await _turn(db_session, input_text=input_text)
    await _responses_batch_approval_fixture(
        db_session,
        session=session,
        input_text=input_text,
    )
    monkeypatch.setattr(settings, "agent_turn_lease_seconds", 1)
    enqueued: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_run",
        lambda *args: enqueued.append(tuple(args)),
    )
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume",
        lambda *args: enqueued.append(tuple(args)),
    )
    gateway = BlockingFinalGateway()
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async def run_from_worker():
        async with session_factory() as worker_session:
            return await AgentCoreRuntime(
                worker_session,
                model_gateway=gateway,
            ).run_turn(str(turn.id))

    worker = asyncio.create_task(run_from_worker())
    await asyncio.wait_for(gateway.started.wait(), timeout=2)
    await asyncio.sleep(1.2)
    async with session_factory() as recovery_session:
        summary = await AgentCoreService(recovery_session).recover_orphaned_turns()

    assert summary == {"enqueued": 0, "failed": 0, "waiting": 0, "skipped": 1}
    assert enqueued == []

    gateway.release.set()
    completed = await asyncio.wait_for(worker, timeout=2)
    assert completed.status == AgentTurnStatus.COMPLETED
    assert completed.final_text == "Long model call completed."


@pytest.mark.asyncio
async def test_replaced_turn_owner_cannot_publish_or_complete_after_long_model_call(
    db_engine,
    db_session,
) -> None:
    input_text = "Fence a stale model worker."
    session, turn = await _turn(db_session, input_text=input_text)
    await _responses_batch_approval_fixture(
        db_session,
        session=session,
        input_text=input_text,
    )
    gateway = BlockingFinalGateway("This stale answer must not be committed.")
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async def run_from_worker():
        async with session_factory() as worker_session:
            return await AgentCoreRuntime(
                worker_session,
                model_gateway=gateway,
            ).run_turn(str(turn.id))

    stale_worker = asyncio.create_task(run_from_worker())
    await asyncio.wait_for(gateway.started.wait(), timeout=2)
    replacement_time = datetime.now(timezone.utc)
    async with session_factory() as replacement_session:
        repo = AgentTurnRepository(replacement_session)
        durable_turn = await repo.get(str(turn.id))
        original_token = durable_turn.owner_token
        await repo.update_all(
            durable_turn,
            owner_token="replacement-owner",
            claimed_at=replacement_time,
            lease_until=replacement_time + timedelta(minutes=5),
        )

    assert original_token
    gateway.release.set()
    await asyncio.wait_for(stale_worker, timeout=2)

    async with session_factory() as inspector:
        durable_turn = await AgentTurnRepository(inspector).get(str(turn.id))
        messages = await AgentMessageRepository(inspector).list_for_session(
            str(session.id)
        )
        events = await AgentEventRepository(inspector).list_for_turn(
            turn_id=str(turn.id)
        )

    assert durable_turn.status == AgentTurnStatus.RUNNING
    assert durable_turn.owner_token == "replacement-owner"
    assert durable_turn.final_text is None
    assert [message.role for message in messages] == ["user"]
    assert all(event.type != AgentEventType.TURN_COMPLETED for event in events)


@pytest.mark.asyncio
async def test_responses_config_rotation_closes_entire_pending_tool_call_batch(
    db_session,
    monkeypatch,
    tmp_path,
) -> None:
    input_text = "Request two commands, then wait for both decisions."
    session, turn = await _turn(db_session, input_text=input_text)
    provider, continuation = await _responses_batch_approval_fixture(
        db_session,
        session=session,
        input_text=input_text,
    )
    markers = [tmp_path / "rotation-first.txt", tmp_path / "rotation-second.txt"]
    gateway = FakeModelGateway(
        (
            *(
                ToolCallDelta(
                    index=index,
                    call_id=f"call-responses-rotation-{index + 1}",
                    name="bash",
                    arguments_delta=json.dumps(
                        {
                            "command": (
                                f'{sys.executable} -c "from pathlib import Path; '
                                f"Path({str(marker)!r}).write_text('ran')\""
                            ),
                            "cwd": str(settings.bioinfoflow_home),
                        }
                    ),
                )
                for index, marker in enumerate(markers)
            ),
            CompletionMetadata(
                response_id="resp-batch-approval",
                finish_reason="tool_calls",
                continuation=continuation,
            ),
        )
    )
    waiting = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).run_turn(str(turn.id))
    assert waiting.status == AgentTurnStatus.WAITING_APPROVAL
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    actions_by_call_id = {action.tool_call_id: action for action in actions}
    first_action = actions_by_call_id["call-responses-rotation-1"]
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_: None
    )
    await AgentCoreService(db_session).decide_action(
        action_id=str(first_action.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )
    provider.base_url = "https://responses-batch-rotated.example/v1"
    await db_session.commit()

    failed = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).resume_turn_after_action(str(first_action.id))

    assert failed.status == AgentTurnStatus.FAILED
    assert failed.error_code == "model_selection_missing"
    assert len(gateway.invocations) == 1
    assert all(not marker.exists() for marker in markers)
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    actions_by_call_id = {action.tool_call_id: action for action in actions}
    rotation_call_ids = ("call-responses-rotation-1", "call-responses-rotation-2")
    assert [actions_by_call_id[call_id].status for call_id in rotation_call_ids] == [
        AgentActionStatus.FAILED,
        AgentActionStatus.FAILED,
    ]
    assert [
        actions_by_call_id[call_id].requires_resume for call_id in rotation_call_ids
    ] == [False, False]
    assert all(
        (actions_by_call_id[call_id].error or {}).get("type")
        == "ModelConfigurationChanged"
        for call_id in rotation_call_ids
    )
    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    tool_messages = [message for message in messages if message.role == "tool"]
    assert [message.message_metadata["tool_call_id"] for message in tool_messages] == [
        "call-responses-rotation-1",
        "call-responses-rotation-2",
    ]
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
        input_text="Continue after the cancelled approval batch.",
    )
    follow_up = await AgentCoreRuntime(
        db_session,
        model_gateway=follow_up_gateway,
    ).run_turn(str(follow_up_turn.id))

    assert follow_up.status == AgentTurnStatus.COMPLETED
    assert follow_up.final_text == "The follow-up turn completed."
    assert follow_up_gateway.invocations[0].continuation is None


@pytest.mark.asyncio
@pytest.mark.parametrize("recovery_enqueued", [False, True])
async def test_concurrent_full_runtime_resume_has_one_durable_owner(
    db_engine,
    db_session,
    monkeypatch,
    tmp_path,
    recovery_enqueued,
) -> None:
    input_text = "Run the approved command exactly once, then continue."
    session, turn = await _turn(db_session, input_text=input_text)
    _provider, continuation = await _responses_batch_approval_fixture(
        db_session,
        session=session,
        input_text=input_text,
    )
    marker = tmp_path / "single-resume-owner.txt"
    command = (
        f'{sys.executable} -c "import time; from pathlib import Path; '
        f"time.sleep(0.15); Path({str(marker)!r}).write_text('ran')\""
    )
    gateway = FakeModelGateway(
        (
            ToolCallDelta(
                index=0,
                call_id="call-single-resume-owner",
                name="bash",
                arguments_delta=json.dumps(
                    {"command": command, "cwd": str(settings.bioinfoflow_home)}
                ),
            ),
            CompletionMetadata(
                response_id="resp-single-resume-owner",
                finish_reason="tool_calls",
                continuation=continuation,
            ),
        ),
        (
            TextDelta(text="The command ran once.", phase="final_answer"),
            CompletionMetadata(
                response_id="resp-single-resume-final",
                finish_reason="stop",
            ),
        ),
    )
    waiting = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).run_turn(str(turn.id))
    assert waiting.status == AgentTurnStatus.WAITING_APPROVAL
    action = (await AgentActionRepository(db_session).list_for_turn(str(turn.id)))[0]
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_: None
    )
    await AgentCoreService(db_session).decide_action(
        action_id=str(action.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )
    if recovery_enqueued:
        waiting = await AgentTurnRepository(db_session).get(str(turn.id))
        waiting = await AgentTurnRepository(db_session).update_all(
            waiting,
            status=AgentTurnStatus.RUNNING,
            claimed_at=None,
            lease_until=None,
            loop_state={
                "state": "running",
                "recovered": True,
                "resume_action_id": str(action.id),
            },
        )
        assert waiting.status == AgentTurnStatus.RUNNING

    _synchronize_two_resume_turn_reads(monkeypatch, turn_id=str(turn.id))
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async def resume_from_fresh_worker():
        async with session_factory() as worker_session:
            return await AgentCoreRuntime(
                worker_session,
                model_gateway=gateway,
            ).resume_turn_after_action(str(action.id))

    worker_results = await asyncio.gather(
        resume_from_fresh_worker(),
        resume_from_fresh_worker(),
    )
    assert sorted(result.status for result in worker_results) == [
        AgentTurnStatus.COMPLETED,
        AgentTurnStatus.RUNNING,
    ]

    async with session_factory() as inspector:
        durable_turn = await AgentTurnRepository(inspector).get(str(turn.id))
        durable_action = await AgentActionRepository(inspector).get(str(action.id))
        messages = await AgentMessageRepository(inspector).list_for_session(
            str(session.id)
        )
        events = await AgentEventRepository(inspector).list_for_turn(
            turn_id=str(turn.id)
        )

    assert durable_turn.status == AgentTurnStatus.COMPLETED
    assert durable_turn.final_text == "The command ran once."
    assert durable_action.status == AgentActionStatus.COMPLETED
    assert marker.read_text() == "ran"
    assert len(gateway.invocations) == 2
    tool_messages = [message for message in messages if message.role == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0].message_metadata["tool_call_id"] == (
        "call-single-resume-owner"
    )
    assert '"status":"completed"' in tool_messages[0].content_parts[0]["text"]
    assert '"status":"running"' not in json.dumps(
        [message.content_parts for message in tool_messages]
    )
    assert sum(event.type == AgentEventType.TURN_STARTED for event in events) == 2
    assert sum(event.type == AgentEventType.ACTION_STARTED for event in events) == 1
    assert sum(event.type == AgentEventType.ACTION_COMPLETED for event in events) == 1

    before_late_worker = (
        len(gateway.invocations),
        len(messages),
        len(events),
    )
    async with session_factory() as late_session:
        late_turn = await AgentCoreRuntime(
            late_session,
            model_gateway=gateway,
        ).resume_turn_after_action(str(action.id))
    async with session_factory() as inspector:
        late_messages = await AgentMessageRepository(inspector).list_for_session(
            str(session.id)
        )
        late_events = await AgentEventRepository(inspector).list_for_turn(
            turn_id=str(turn.id)
        )
    assert late_turn.status == AgentTurnStatus.COMPLETED
    assert (
        len(gateway.invocations),
        len(late_messages),
        len(late_events),
    ) == before_late_worker


@pytest.mark.asyncio
async def test_concurrent_config_rotation_cleanup_has_one_durable_owner(
    db_engine,
    db_session,
    monkeypatch,
    tmp_path,
) -> None:
    input_text = "Request two commands and close both if the model target rotates."
    session, turn = await _turn(db_session, input_text=input_text)
    provider, continuation = await _responses_batch_approval_fixture(
        db_session,
        session=session,
        input_text=input_text,
    )
    markers = [
        tmp_path / "rotation-owner-first.txt",
        tmp_path / "rotation-owner-second.txt",
    ]
    gateway = FakeModelGateway(
        (
            *(
                ToolCallDelta(
                    index=index,
                    call_id=f"call-rotation-owner-{index + 1}",
                    name="bash",
                    arguments_delta=json.dumps(
                        {
                            "command": (
                                f'{sys.executable} -c "from pathlib import Path; '
                                f"Path({str(marker)!r}).write_text('ran')\""
                            ),
                            "cwd": str(settings.bioinfoflow_home),
                        }
                    ),
                )
                for index, marker in enumerate(markers)
            ),
            CompletionMetadata(
                response_id="resp-rotation-owner",
                finish_reason="tool_calls",
                continuation=continuation,
            ),
        )
    )
    waiting = await AgentCoreRuntime(
        db_session,
        model_gateway=gateway,
    ).run_turn(str(turn.id))
    assert waiting.status == AgentTurnStatus.WAITING_APPROVAL
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    first_action = next(
        action for action in actions if action.tool_call_id == "call-rotation-owner-1"
    )
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_: None
    )
    await AgentCoreService(db_session).decide_action(
        action_id=str(first_action.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )
    provider.base_url = "https://rotated-owner.example/v1"
    await db_session.commit()

    _synchronize_two_resume_turn_reads(monkeypatch, turn_id=str(turn.id))
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async def resume_from_fresh_worker():
        async with session_factory() as worker_session:
            return await AgentCoreRuntime(
                worker_session,
                model_gateway=gateway,
            ).resume_turn_after_action(str(first_action.id))

    await asyncio.gather(
        resume_from_fresh_worker(),
        resume_from_fresh_worker(),
    )

    async with session_factory() as inspector:
        durable_turn = await AgentTurnRepository(inspector).get(str(turn.id))
        durable_actions = await AgentActionRepository(inspector).list_for_turn(
            str(turn.id)
        )
        messages = await AgentMessageRepository(inspector).list_for_session(
            str(session.id)
        )
        events = await AgentEventRepository(inspector).list_for_turn(
            turn_id=str(turn.id)
        )

    assert durable_turn.status == AgentTurnStatus.FAILED
    assert durable_turn.error_code == "model_selection_missing"
    assert len(gateway.invocations) == 1
    assert all(not marker.exists() for marker in markers)
    assert all(action.status == AgentActionStatus.FAILED for action in durable_actions)
    tool_messages = [message for message in messages if message.role == "tool"]
    assert sorted(
        message.message_metadata["tool_call_id"] for message in tool_messages
    ) == ["call-rotation-owner-1", "call-rotation-owner-2"]
    assert sum(event.type == AgentEventType.TURN_STARTED for event in events) == 2
    assert sum(event.type == AgentEventType.ACTION_FAILED for event in events) == 2
    assert all(
        "_responses_continuation" not in (message.message_metadata or {})
        for message in messages
    )

    before_late_worker = (len(messages), len(events))
    async with session_factory() as late_session:
        late_turn = await AgentCoreRuntime(
            late_session,
            model_gateway=gateway,
        ).resume_turn_after_action(str(first_action.id))
    async with session_factory() as inspector:
        late_messages = await AgentMessageRepository(inspector).list_for_session(
            str(session.id)
        )
        late_events = await AgentEventRepository(inspector).list_for_turn(
            turn_id=str(turn.id)
        )
    assert late_turn.status == AgentTurnStatus.FAILED
    assert (len(late_messages), len(late_events)) == before_late_worker


@pytest.mark.asyncio
async def test_responses_two_tool_rounds_advance_canonical_suffix_without_duplicates(
    db_session,
    monkeypatch,
) -> None:
    _session, turn = await _turn(
        db_session, input_text="Run two commands, then finish."
    )
    target = ModelTarget(
        endpoint_id="endpoint-responses",
        provider_kind="openai_compatible",
        model_name="gpt-responses-test",
        wire_protocol="responses",
        target_revision="two-tool-target-revision",
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
                    canonical_input_digest=canonical_input_prefix_digest(
                        (TextPart(text="Run two commands, then finish."),)
                    ),
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
                    canonical_input_digest=canonical_input_prefix_digest(
                        (
                            TextPart(text="Run two commands, then finish."),
                            ToolCallPart(
                                call_id="call-one",
                                name="bash",
                                arguments={"command": "first"},
                            ),
                            ToolResultPart(
                                call_id="call-one",
                                output=(
                                    '{"tool":"bash","status":"completed",'
                                    '"result":{"ok":true},"error":null}'
                                ),
                            ),
                        )
                    ),
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
    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
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
    warning = next(
        event for event in events if event.type == AgentEventType.MODEL_WARNING
    )
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
        target_revision="session-target-revision",
    )
    first_continuation = ResponsesContinuation(
        response_id="resp-first-turn",
        canonical_input_count=1,
        canonical_input_digest=canonical_input_prefix_digest(
            (TextPart(text="Inspect the workflow and remember the result."),)
        ),
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
        canonical_input_digest=canonical_input_prefix_digest(
            (
                TextPart(text="Inspect the workflow and remember the result."),
                TextPart(text="First result.", phase="final_answer"),
                TextPart(text="Use that result for a follow-up."),
            )
        ),
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
    await controller.complete_turn_from_result(turn=first_turn, result=first_result)

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
        target_revision="compaction-target-revision",
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
                    canonical_input_digest=canonical_input_prefix_digest(
                        (TextPart(text="A" * 80),)
                    ),
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
            CompletionMetadata(
                response_id="resp-after-compaction", finish_reason="completed"
            ),
        ),
    )
    controller = AgentLoopController(db_session, model_gateway=gateway)
    first_result = await controller.run_turn(turn_id=str(first_turn.id), target=target)
    await controller.complete_turn_from_result(turn=first_turn, result=first_result)
    before_compaction = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    assert (
        sum(
            "_responses_continuation" in (message.message_metadata or {})
            for message in before_compaction
        )
        == 1
    )
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
        isinstance(item, TextPart)
        and "Conversation summary for continuity" in item.text
        for item in gateway.invocations[1].input_items
    )
    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    assert "discard-after-compaction" not in repr(
        [message.message_metadata for message in messages]
    )
