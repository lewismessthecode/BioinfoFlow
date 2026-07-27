from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agent_core import (
    AgentAttachment,
    AgentAttachmentStatus,
    AgentMessage,
    AgentMessageStatus,
    AgentSession,
    AgentSessionStatus,
    AgentTurn,
    AgentTurnStatus,
)
from app.models.llm import LlmModel, LlmProvider, LlmProviderCredential
from app.models.workspace import Workspace, WorkspaceMembership
from app.repositories.agent_core_repo import AgentSessionRepository, AgentTurnRepository
from app.services.agent_core.collaboration.context_fork import (
    InvalidForkTurnsError,
    fork_agent_context,
)
from app.services.agent_core.collaboration.model_preflight import AgentModelPreflight
from app.services.agent_core.collaboration.contracts import AgentModelChoice
from app.services.agent_core.collaboration.service import AgentCollaborationService
from app.services.agent_core.collaboration.service import _collaboration_waiter_count
from app.services.agent_core.context import AgentContextAssembler
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.service import AgentCoreService
from app.services.agent_core.transcript.messages import parts_to_text
from app.services.llm.credentials import encrypt_secret
from app.services.llm.catalog import ExactModelProbeResult
from app.services.llm.probe import LlmProviderProbeResult
from app.config import settings
from app.path_layout import agent_attachment_root, agent_attachments_root
from app.workspace import DEFAULT_WORKSPACE_ID


async def _seed_workspace(db_session: AsyncSession) -> None:
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    await db_session.commit()


async def _create_session(
    db_session: AsyncSession,
    *,
    user_id: str = "dev",
    parent_session_id: str | None = None,
    root_session_id: str | None = None,
    agent_name: str | None = None,
    collaboration_slot: int | None = None,
) -> AgentSession:
    session = AgentSession(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id=user_id,
        parent_session_id=parent_session_id,
        root_session_id=root_session_id,
        agent_name=agent_name,
        collaboration_slot=collaboration_slot,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


async def _create_parent_turn(db_session: AsyncSession) -> tuple[AgentSession, AgentTurn]:
    root = await _create_session(db_session)
    turn = AgentTurn(
        session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="parent request",
        status=AgentTurnStatus.RUNNING,
        model_profile_snapshot={
            "resolved_model_id": "parent-id",
            "resolved_model_selection": {
                "provider": "openai_compatible",
                "model": "parent-model",
            },
            "resolved_model_capabilities": {"supports_reasoning": True},
            "resolved_runtime_strategy": {
                "allow_thinking": True,
                "reasoning_effort": "high",
            },
        },
    )
    db_session.add(turn)
    await db_session.flush()
    root.active_turn_id = str(turn.id)
    await db_session.commit()
    await db_session.refresh(root)
    await db_session.refresh(turn)
    return root, turn


@pytest.mark.asyncio
async def test_root_tree_queries_and_target_resolution_are_root_scoped(db_session) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child = await _create_session(
        db_session,
        parent_session_id=str(root.id),
        root_session_id=str(root.id),
        agent_name="reader",
    )
    other_root = await _create_session(db_session)
    other_child = await _create_session(
        db_session,
        parent_session_id=str(other_root.id),
        root_session_id=str(other_root.id),
        agent_name="reader",
    )
    await _create_session(
        db_session,
        user_id="other-user",
        parent_session_id=str(root.id),
        root_session_id=str(root.id),
        agent_name="outsider",
    )

    repo = AgentSessionRepository(db_session)

    tree = await repo.list_agent_tree(
        str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert tree[0].id == root.id
    assert [session.id for session in tree[1:]] == [child.id]
    assert (
        await repo.list_agent_tree(
            str(root.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="other-user",
        )
        == []
    )
    assert await repo.get_agent_target(
        str(root.id),
        "reader",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    ) == child
    assert await repo.get_agent_target(
        str(root.id),
        f"/root/{child.agent_name}",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    ) == child
    assert await repo.get_agent_target(
        str(root.id),
        str(child.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    ) == child
    assert await repo.get_agent_target(
        str(root.id),
        "/root",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    ) == root
    assert (
        await repo.get_agent_target(
            str(root.id),
            str(other_child.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )
        is None
    )
    assert (
        await repo.get_agent_target(
            str(root.id),
            "outsider",
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )
        is None
    )


@pytest.mark.asyncio
async def test_duplicate_sibling_agent_name_is_permanently_rejected(db_session) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child = await _create_session(
        db_session,
        parent_session_id=str(root.id),
        root_session_id=str(root.id),
        agent_name="reader",
    )
    child.status = AgentSessionStatus.ARCHIVED
    await db_session.commit()

    db_session.add(
        AgentSession(
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            parent_session_id=str(root.id),
            root_session_id=str(root.id),
            agent_name="reader",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_release_child_slot_keeps_name_reserved(db_session) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child = await _create_session(
        db_session,
        parent_session_id=str(root.id),
        root_session_id=str(root.id),
        agent_name="reader",
    )
    repo = AgentSessionRepository(db_session)

    reserved = await repo.reserve_child_slot(child)

    assert reserved is child
    assert reserved.collaboration_slot == 1
    assert await repo.release_child_slot(str(child.id)) is True

    await db_session.refresh(child)
    assert child.collaboration_slot is None
    assert child.agent_name == "reader"


@pytest.mark.asyncio
async def test_last_child_slot_is_acquired_atomically(db_session) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    root_id = str(root.id)
    for slot in range(1, 7):
        await _create_session(
            db_session,
            parent_session_id=str(root.id),
            root_session_id=str(root.id),
            agent_name=f"worker_{slot}",
            collaboration_slot=slot,
        )
    candidates = [
        await _create_session(
            db_session,
            parent_session_id=str(root.id),
            root_session_id=str(root.id),
            agent_name=name,
        )
        for name in ("seven_a", "seven_b")
    ]
    maker = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async def reserve(child_id: str) -> int:
        async with maker() as worker:
            child = await worker.get(AgentSession, child_id)
            assert child is not None
            reserved = await AgentSessionRepository(worker).reserve_child_slot(child)
            await worker.commit()
            assert reserved.collaboration_slot is not None
            return reserved.collaboration_slot

    results = await asyncio.gather(
        *(reserve(str(child.id)) for child in candidates),
        return_exceptions=True,
    )

    assert sum(result == 7 for result in results) == 1
    assert sum(
        isinstance(result, RuntimeError)
        and "collaboration slot" in str(result).lower()
        for result in results
    ) == 1
    db_session.expire_all()
    reserved = await db_session.scalars(
        select(AgentSession).where(
            AgentSession.root_session_id == root_id,
            AgentSession.collaboration_slot == 7,
        )
    )
    assert len(reserved.all()) == 1


@pytest.mark.asyncio
async def test_staged_child_and_slot_share_the_callers_transaction(db_session) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child = AgentSession(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        parent_session_id=str(root.id),
        root_session_id=str(root.id),
        agent_name="staged_worker",
    )
    db_session.add(child)

    reserved = await AgentSessionRepository(db_session).reserve_child_slot(child)
    child_id = str(child.id)

    assert reserved is child
    assert child.collaboration_slot == 1
    assert await db_session.get(AgentSession, child_id) is child

    await db_session.rollback()

    assert await db_session.get(AgentSession, child_id) is None


def _message(
    role: str,
    text: str,
    *,
    phase: str | None = None,
    kind: str | None = None,
    parts: list[dict] | None = None,
    status: str = "committed",
    metadata: dict | None = None,
):
    metadata = {**(metadata or {}), **({"kind": kind} if kind else {})} or None
    content_parts = parts or [
        {
            "type": "text",
            "text": text,
            **({"phase": phase} if phase else {}),
        }
    ]
    return SimpleNamespace(
        role=role,
        content_parts=content_parts,
        message_metadata=metadata,
        status=status,
    )


def _fork_texts(messages) -> list[str]:
    return [
        "\n".join(
            part["text"]
            for part in message["content_parts"]
            if part.get("type") == "text"
        )
        for message in messages
    ]


def test_numeric_context_fork_keeps_last_user_turns_and_final_answers() -> None:
    messages = [
        _message("system", "system rules"),
        _message("developer", "developer rules"),
        _message("user", "user one"),
        _message("assistant", "assistant one reasoning", phase="commentary"),
        _message("assistant", "assistant one final", phase="final_answer"),
        _message(
            "assistant",
            "",
            parts=[
                {"type": "text", "text": "not a terminal answer"},
                {
                    "type": "tool_calls",
                    "tool_calls": [
                        {"id": "call-1", "name": "spawn_agent", "arguments": {}}
                    ],
                }
            ],
        ),
        _message("tool", "spawn result"),
        _message("user", "user two"),
        _message("assistant", "assistant two final", phase="final_answer"),
        _message("user", "user three"),
        _message("assistant", "assistant three final", phase="final_answer"),
        _message("user", "pending draft", status="draft"),
    ]

    forked = fork_agent_context(messages, fork_turns="2")

    assert _fork_texts(forked) == [
        "system rules",
        "developer rules",
        "user two",
        "assistant two final",
        "user three",
        "assistant three final",
    ]
    assert all(message["role"] != "tool" for message in forked)


def test_all_context_fork_keeps_accepted_summary_but_filters_runtime_noise() -> None:
    messages = [
        _message("developer", "developer rules"),
        _message(
            "assistant",
            "accepted compacted history",
            kind="compaction_summary",
        ),
        _message("user", "current request"),
        _message("assistant", "progress", phase="commentary"),
        _message("assistant", "final answer", phase="final_answer"),
        {
            "role": "assistant",
            "content_parts": [
                {
                    "type": "text",
                    "text": "provider continuation",
                    "phase": "final_answer",
                }
            ],
            "message_metadata": {
                "_responses_continuation": {
                    "response_id": "private",
                    "output_items": [
                        {
                            "type": "function_call",
                            "call_id": "private-call",
                            "name": "read",
                            "arguments": "{}",
                        }
                    ],
                }
            },
        },
        _message("assistant", "mailbox", kind="inter_agent_message"),
        _message("assistant", "lifecycle", kind="agent_lifecycle"),
        _message("tool", "tool output"),
    ]

    forked = fork_agent_context(messages, fork_turns="all")

    assert _fork_texts(forked) == [
        "developer rules",
        "accepted compacted history",
        "current request",
        "final answer",
        "provider continuation",
    ]
    assert forked[-1]["message_metadata"] is None


@pytest.mark.parametrize(
    "tool_bearing_message",
    [
        {
            "role": "assistant",
            "content": "text beside a provider tool call",
            "tool_calls": [{"id": "call-1", "name": "read", "arguments": {}}],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "text beside tool use"},
                {"type": "tool_use", "id": "call-2", "name": "read"},
            ],
        },
        {
            "role": "assistant",
            "content_parts": [
                {"type": "text", "text": "text beside function call"},
                {"type": "function_call", "name": "read", "arguments": {}},
            ],
        },
        {
            "role": "assistant",
            "content_parts": [
                {"type": "text", "text": "text beside nested tool call"},
                {"type": "output", "tool_call": {"name": "read"}},
            ],
        },
    ],
)
def test_all_context_fork_rejects_tool_bearing_assistant_items_without_metadata(
    tool_bearing_message,
) -> None:
    forked = fork_agent_context(
        [
            _message("user", "inspect"),
            tool_bearing_message,
            _message("assistant", "terminal answer", phase="final_answer"),
        ],
        fork_turns="all",
    )

    assert _fork_texts(forked) == ["inspect", "terminal answer"]


def test_context_fork_preserves_sanitized_canonical_user_image_reference() -> None:
    message = AgentMessage(
        session_id="parent-session",
        turn_id="parent-turn",
        role="user",
        content_parts=[
            {"type": "text", "text": "Inspect this image."},
            {
                "type": "image_ref",
                "attachment_id": "parent-attachment",
                "mime_type": "image/png",
                "sha256": "a" * 64,
                "detail": "high",
                "storage_path": "parent/private/path",
                "session_id": "parent-session",
            },
        ],
        message_metadata={
            "input_display": "private",
            "attachment_ids": ["parent-attachment"],
        },
        status="committed",
        ordering_index=1,
    )

    forked = fork_agent_context([message], fork_turns="all")

    assert forked == [
        {
            "role": "user",
            "content_parts": [
                {"type": "text", "text": "Inspect this image."},
                {
                    "type": "image_ref",
                    "source_attachment_id": "parent-attachment",
                    "mime_type": "image/png",
                    "sha256": "a" * 64,
                    "detail": "high",
                },
            ],
            "message_metadata": None,
        }
    ]


def test_none_context_fork_returns_no_parent_conversation() -> None:
    assert fork_agent_context([_message("user", "hello")], fork_turns="none") == []


@pytest.mark.parametrize("fork_turns", ["0", "-1", "recent", "", 2])
def test_invalid_context_fork_values_raise_stable_error(fork_turns) -> None:
    with pytest.raises(InvalidForkTurnsError) as caught:
        fork_agent_context([], fork_turns=fork_turns)

    assert caught.value.code == "invalid_fork_turns"


async def _create_probe_model(
    db_session: AsyncSession,
    *,
    model_name: str = "cheap-model",
    enabled: bool = True,
    supports_tools: bool = True,
    supports_reasoning: bool = True,
    test_status: dict | None = None,
    scope: str = "user",
    workspace_id: str | None = DEFAULT_WORKSPACE_ID,
    user_id: str | None = "dev",
    credential_source: str = "stored",
    base_url: str = "https://probe.example/v1",
) -> LlmModel:
    provider = LlmProvider(
        name=f"Provider for {model_name}",
        kind="openai_compatible",
        wire_protocol="chat_completions",
        base_url=base_url,
        scope=scope,
        workspace_id=workspace_id,
        user_id=user_id,
        enabled=enabled,
        test_status=test_status,
    )
    db_session.add(provider)
    await db_session.flush()
    db_session.add(
        LlmProviderCredential(
            provider_id=str(provider.id),
            source=credential_source,
            env_var_name="CHILD_MODEL_API_KEY"
            if credential_source == "env"
            else None,
            encrypted_secret=encrypt_secret("super-secret-child-key")
            if credential_source == "stored"
            else None,
            masked_hint="su...ey",
            updated_by="dev",
        )
    )
    model = LlmModel(
        provider_id=str(provider.id),
        model_id=model_name,
        display_name=model_name,
        supports_tools=supports_tools,
        supports_streaming=True,
        supports_reasoning=supports_reasoning,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


@pytest.mark.asyncio
async def test_available_requested_model_is_selected_with_fresh_exact_probe(
    db_session,
    monkeypatch,
) -> None:
    await _seed_workspace(db_session)
    model = await _create_probe_model(
        db_session,
        test_status={"success": True, "model": "cheap-model"},
    )
    model_id = str(model.id)
    calls: list[dict] = []

    async def fake_probe(_self, **kwargs):
        calls.append(kwargs)
        return LlmProviderProbeResult(
            success=True,
            latency_ms=1,
            wire_protocol="chat_completions",
            model_id=kwargs["model_id"],
        )

    monkeypatch.setattr(
        "app.services.llm.catalog.LlmProviderProbe.probe",
        fake_probe,
    )

    result = await AgentModelPreflight(db_session).resolve(
        requested_model="cheap-model",
        parent_model="parent-model",
        parent_model_id="parent-id",
        parent_reasoning_effort="high",
        requested_reasoning_effort="low",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        role="owner",
    )

    assert result.requested_model == "cheap-model"
    assert result.effective_model == "cheap-model"
    assert result.effective_model_id == model_id
    assert result.reasoning_effort == "low"
    assert result.fallback is False
    assert [call["model_id"] for call in calls] == ["cheap-model"]


@pytest.mark.asyncio
async def test_exact_model_network_probe_runs_after_read_transaction_is_closed(
    db_session,
    monkeypatch,
) -> None:
    await _seed_workspace(db_session)
    model = await _create_probe_model(db_session, model_name="cheap-model")
    observed_transaction_state: list[bool] = []

    async def execute(snapshot):
        observed_transaction_state.append(db_session.in_transaction())
        return ExactModelProbeResult(
            available=True,
            requested_model=snapshot.requested_model,
            model_id=snapshot.model_id,
            model_name=snapshot.model_name,
            supports_reasoning=snapshot.supports_reasoning,
        )

    preflight = AgentModelPreflight(db_session)
    monkeypatch.setattr(preflight.catalog, "execute_exact_model_probe", execute)

    result = await preflight.resolve(
        requested_model=str(model.id),
        parent_model="parent-model",
        parent_model_id="parent-id",
        parent_reasoning_effort="high",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        role="owner",
    )

    assert result.fallback is False
    assert observed_transaction_state == [False]


@pytest.mark.asyncio
async def test_unavailable_requested_model_falls_back_without_leaking_probe_details(
    db_session,
    monkeypatch,
) -> None:
    await _seed_workspace(db_session)
    await _create_probe_model(db_session, model_name="unavailable-model")

    async def fake_probe(_self, **kwargs):
        return LlmProviderProbeResult(
            success=False,
            latency_ms=1,
            wire_protocol="chat_completions",
            model_id=kwargs["model_id"],
            error_code="authentication_error",
            error_message="bad key super-secret-child-key",
            http_status=401,
        )

    monkeypatch.setattr(
        "app.services.llm.catalog.LlmProviderProbe.probe",
        fake_probe,
    )

    result = await AgentModelPreflight(db_session).resolve(
        requested_model="unavailable-model",
        parent_model="parent-model",
        parent_model_id="parent-id",
        parent_reasoning_effort="high",
        requested_reasoning_effort="ultra",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        role="owner",
    )

    assert result.effective_model == "parent-model"
    assert result.reasoning_effort == "high"
    assert result.effective_model_id == "parent-id"
    assert result.reasoning_effort == "high"
    assert result.fallback is True
    assert result.fallback_reason == "requested_model_unavailable"
    assert "secret" not in repr(result).lower()


@pytest.mark.asyncio
async def test_omitted_requested_model_inherits_parent_without_probe(
    db_session,
    monkeypatch,
) -> None:
    async def forbidden_probe(*args, **kwargs):
        raise AssertionError("omitted model must not be probed")

    monkeypatch.setattr(
        "app.services.llm.catalog.LlmProviderProbe.probe",
        forbidden_probe,
    )

    result = await AgentModelPreflight(db_session).resolve(
        requested_model=None,
        parent_model="parent-model",
        parent_model_id="parent-id",
        parent_reasoning_effort="high",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    assert result.requested_model is None
    assert result.effective_model == "parent-model"
    assert result.effective_model_id == "parent-id"
    assert result.reasoning_effort == "high"
    assert result.fallback is False


@pytest.mark.asyncio
async def test_supported_model_rejects_invalid_or_unsupported_explicit_effort(
    db_session,
    monkeypatch,
) -> None:
    await _seed_workspace(db_session)
    await _create_probe_model(
        db_session,
        model_name="plain-model",
        supports_reasoning=False,
    )

    async def fake_probe(_self, **kwargs):
        return LlmProviderProbeResult(
            success=True,
            latency_ms=1,
            wire_protocol="chat_completions",
            model_id=kwargs["model_id"],
        )

    monkeypatch.setattr(
        "app.services.llm.catalog.LlmProviderProbe.probe",
        fake_probe,
    )

    with pytest.raises(ValueError, match="invalid_reasoning_effort"):
        await AgentModelPreflight(db_session).resolve(
            requested_model="plain-model",
            parent_model="parent-model",
            parent_model_id="parent-id",
            parent_reasoning_effort="high",
            requested_reasoning_effort="ultra",
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            role="owner",
        )

    with pytest.raises(ValueError, match="unsupported_reasoning_effort"):
        await AgentModelPreflight(db_session).resolve(
            requested_model="plain-model",
            parent_model="parent-model",
            parent_model_id="parent-id",
            parent_reasoning_effort="high",
            requested_reasoning_effort="low",
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            role="owner",
        )


@pytest.mark.asyncio
async def test_exact_model_preflight_fails_closed_for_invisible_or_inactive_models(
    db_session,
    monkeypatch,
) -> None:
    await _seed_workspace(db_session)
    other_workspace_id = "00000000-0000-0000-0000-000000000099"
    db_session.add(Workspace(id=other_workspace_id, name="Other", slug="other"))
    await db_session.commit()
    models = [
        await _create_probe_model(
            db_session,
            model_name="cross-user",
            user_id="other-user",
        ),
        await _create_probe_model(
            db_session,
            model_name="cross-workspace",
            workspace_id=other_workspace_id,
        ),
        await _create_probe_model(
            db_session,
            model_name="malformed-user-scope",
            user_id=None,
        ),
        await _create_probe_model(
            db_session,
            model_name="malformed-workspace-scope",
            scope="workspace",
            user_id="dev",
        ),
        await _create_probe_model(
            db_session,
            model_name="malformed-global-scope",
            scope="global",
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id=None,
        ),
        await _create_probe_model(
            db_session,
            model_name="disabled-provider",
            enabled=False,
        ),
        await _create_probe_model(
            db_session,
            model_name="stale-model",
        ),
        await _create_probe_model(
            db_session,
            model_name="no-tools",
            supports_tools=False,
        ),
    ]
    models[6].model_metadata = {"catalog_status": "stale"}
    model_ids = [str(model.id) for model in models]
    await db_session.commit()
    calls: list[str] = []

    async def forbidden_probe(_self, **kwargs):
        calls.append(kwargs["model_id"])
        raise AssertionError("invisible or inactive models must not be probed")

    monkeypatch.setattr(
        "app.services.llm.catalog.LlmProviderProbe.probe",
        forbidden_probe,
    )

    for model_id in model_ids:
        result = await AgentModelPreflight(db_session).resolve(
            requested_model=model_id,
            parent_model="parent-model",
            parent_model_id="parent-id",
            parent_reasoning_effort="high",
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            role="member",
        )
        assert result.fallback is True
        assert result.fallback_reason == "requested_model_unavailable"
    assert calls == []


@pytest.mark.asyncio
async def test_exact_model_preflight_rejects_unauthorized_environment_credential(
    db_session,
    monkeypatch,
) -> None:
    await _seed_workspace(db_session)
    model = await _create_probe_model(
        db_session,
        model_name="owner-only-env-model",
        credential_source="env",
    )
    monkeypatch.setattr(settings, "auth_mode", "team")

    async def forbidden_probe(*args, **kwargs):
        raise AssertionError("unauthorized env credentials must not be probed")

    monkeypatch.setattr(
        "app.services.llm.catalog.LlmProviderProbe.probe",
        forbidden_probe,
    )

    result = await AgentModelPreflight(db_session).resolve(
        requested_model=str(model.id),
        parent_model="parent-model",
        parent_model_id="parent-id",
        parent_reasoning_effort="high",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        role="member",
    )

    assert result.fallback is True
    assert result.fallback_reason == "requested_model_unavailable"


@pytest.mark.parametrize(
    ("scope", "provider_workspace_id"),
    [("workspace", DEFAULT_WORKSPACE_ID), ("global", None)],
)
@pytest.mark.asyncio
async def test_member_can_preflight_admin_managed_shared_env_private_provider(
    db_session,
    monkeypatch,
    scope,
    provider_workspace_id,
) -> None:
    await _seed_workspace(db_session)
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setenv("CHILD_MODEL_API_KEY", "shared-env-secret")
    model = await _create_probe_model(
        db_session,
        model_name=f"{scope}-shared-model",
        scope=scope,
        workspace_id=provider_workspace_id,
        user_id=None,
        credential_source="env",
        base_url="http://127.0.0.1:8000/v1",
    )
    calls: list[dict] = []

    async def successful_probe(_self, **kwargs):
        calls.append(kwargs)
        return LlmProviderProbeResult(
            success=True,
            latency_ms=1,
            wire_protocol="chat_completions",
            model_id=kwargs["model_id"],
        )

    monkeypatch.setattr(
        "app.services.llm.catalog.LlmProviderProbe.probe",
        successful_probe,
    )

    result = await AgentModelPreflight(db_session).resolve(
        requested_model=str(model.id),
        parent_model="parent-model",
        parent_model_id="parent-id",
        parent_reasoning_effort="high",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        role="member",
    )

    assert result.fallback is False
    assert calls[0]["network_access"] == "unrestricted"
    assert calls[0]["credential"].api_key == "shared-env-secret"


@pytest.mark.asyncio
async def test_parent_reasoning_override_checks_capability_without_live_probe(
    db_session,
    monkeypatch,
) -> None:
    await _seed_workspace(db_session)
    plain_parent = await _create_probe_model(
        db_session,
        model_name="plain-parent",
        supports_reasoning=False,
    )
    reasoning_parent = await _create_probe_model(
        db_session,
        model_name="reasoning-parent",
        supports_reasoning=True,
    )

    async def forbidden_probe(*args, **kwargs):
        raise AssertionError("inherited parent models must not be live-probed")

    monkeypatch.setattr(
        "app.services.llm.catalog.LlmProviderProbe.probe",
        forbidden_probe,
    )

    with pytest.raises(ValueError, match="unsupported_reasoning_effort"):
        await AgentModelPreflight(db_session).resolve(
            requested_model=None,
            parent_model="plain-parent",
            parent_model_id=str(plain_parent.id),
            parent_reasoning_effort=None,
            requested_reasoning_effort="low",
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )

    selected = await AgentModelPreflight(db_session).resolve(
        requested_model=None,
        parent_model="reasoning-parent",
        parent_model_id=str(reasoning_parent.id),
        parent_reasoning_effort=None,
        requested_reasoning_effort="low",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert selected.reasoning_effort == "low"

    selected_from_snapshot = await AgentModelPreflight(db_session).resolve(
        requested_model=None,
        parent_model="snapshot-parent",
        parent_model_id="not-in-catalog",
        parent_reasoning_effort=None,
        requested_reasoning_effort="medium",
        parent_supports_reasoning=True,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert selected_from_snapshot.reasoning_effort == "medium"

    with pytest.raises(ValueError, match="unsupported_reasoning_effort"):
        await AgentModelPreflight(db_session).resolve(
            requested_model=None,
            parent_model="snapshot-parent",
            parent_model_id="not-in-catalog",
            parent_reasoning_effort=None,
            requested_reasoning_effort="medium",
            parent_supports_reasoning=False,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )


@pytest.mark.asyncio
async def test_spawn_agent_returns_after_enqueue_without_waiting_for_child(
    db_session, monkeypatch
) -> None:
    await _seed_workspace(db_session)
    root, turn = await _create_parent_turn(db_session)
    root_id = str(root.id)
    turn_id = str(turn.id)
    enqueued: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda turn_id, session_id: enqueued.append((turn_id, session_id)),
    )

    result = await AgentCollaborationService(db_session).spawn_agent(
        parent_session_id=root_id,
        parent_turn_id=turn_id,
        task_name="reader",
        message="Inspect README",
        fork_turns="none",
    )

    assert result.status == "pending_init"
    assert result.task_name == "/root/reader"
    assert result.effective_model == "parent-model"
    assert enqueued == [(result.child_turn_id, result.child_session_id)]
    child = await db_session.get(AgentSession, result.child_session_id)
    child_turn = await db_session.get(AgentTurn, result.child_turn_id)
    assert child is not None and child.collaboration_slot == 1
    assert child_turn is not None and child_turn.status == AgentTurnStatus.QUEUED
    assert child_turn.model_profile_snapshot["metadata"]["collaboration"][
        "reasoning_effort"
    ] == "high"


@pytest.mark.asyncio
async def test_spawn_without_override_ignores_authentication_failing_catalog_default_and_completes(
    db_session, monkeypatch
) -> None:
    await _seed_workspace(db_session)
    await _create_probe_model(
        db_session,
        model_name="catalog-default-auth-failing",
        test_status={
            "success": False,
            "error_code": "authentication_error",
            "http_status": 401,
        },
    )
    root, parent_turn = await _create_parent_turn(db_session)
    probe_calls: list[dict] = []

    async def forbidden_probe(_self, **kwargs):
        probe_calls.append(kwargs)
        raise AssertionError("an omitted override must inherit the parent turn model")

    monkeypatch.setattr(
        "app.services.llm.catalog.LlmProviderProbe.probe",
        forbidden_probe,
    )
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )

    service = AgentCollaborationService(db_session)
    spawned = await service.spawn_agent(
        parent_session_id=str(root.id),
        parent_turn_id=str(parent_turn.id),
        task_name="inherits_parent",
        message="Use the explicitly working parent model.",
        fork_turns="none",
    )
    child_turn = await service.turns.get_fresh(spawned.child_turn_id)
    assert child_turn is not None
    child_turn.status = AgentTurnStatus.COMPLETED
    child_turn.final_text = "completed with parent model"
    await db_session.commit()
    await service.publish_child_terminal(turn_id=spawned.child_turn_id)

    agents = await service.list_agents(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    child = next(agent for agent in agents if agent.task_name == "/root/inherits_parent")
    assert probe_calls == []
    assert spawned.requested_model is None
    assert spawned.effective_model == "parent-model"
    assert child.status == "completed"
    assert child.final_text == "completed with parent model"


@pytest.mark.asyncio
async def test_spawn_authentication_failing_model_is_fresh_probed_then_falls_back_to_parent(
    db_session, monkeypatch
) -> None:
    await _seed_workspace(db_session)
    failing_model = await _create_probe_model(
        db_session,
        model_name="catalog-default-auth-failing",
    )
    failing_model_id = str(failing_model.id)
    root, parent_turn = await _create_parent_turn(db_session)
    probe_calls: list[dict] = []

    async def authentication_failure(_self, **kwargs):
        probe_calls.append(kwargs)
        return LlmProviderProbeResult(
            success=False,
            latency_ms=1,
            wire_protocol="chat_completions",
            model_id=kwargs["model_id"],
            error_code="authentication_error",
            error_message="HTTP 401 secret provider payload",
            http_status=401,
        )

    monkeypatch.setattr(
        "app.services.llm.catalog.LlmProviderProbe.probe",
        authentication_failure,
    )
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )

    spawned = await AgentCollaborationService(db_session).spawn_agent(
        parent_session_id=str(root.id),
        parent_turn_id=str(parent_turn.id),
        task_name="fallback_parent",
        message="Probe the requested model first.",
        fork_turns="none",
        model=failing_model_id,
    )
    child = await db_session.get(AgentSession, spawned.child_session_id)
    child_turn = await db_session.get(AgentTurn, spawned.child_turn_id)

    assert [call["model_id"] for call in probe_calls] == [
        "catalog-default-auth-failing"
    ]
    assert spawned.requested_model == failing_model_id
    assert spawned.effective_model == "parent-model"
    assert spawned.model_fallback is True
    assert spawned.fallback_reason == "requested_model_unavailable"
    assert child is not None
    assert child.session_metadata["collaboration"]["model_fallback"] is True
    assert child.session_metadata["collaboration"]["fallback_reason"] == (
        "requested_model_unavailable"
    )
    assert child_turn is not None
    turn_collaboration = child_turn.model_profile_snapshot["metadata"][
        "collaboration"
    ]
    assert turn_collaboration["effective_model"] == "parent-model"
    assert turn_collaboration["model_fallback"] is True
    assert "secret" not in repr(child.session_metadata).lower()


@pytest.mark.asyncio
async def test_spawn_agent_fails_closed_for_child_callers(db_session) -> None:
    await _seed_workspace(db_session)
    root, root_turn = await _create_parent_turn(db_session)
    child = AgentSession(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        parent_session_id=str(root.id),
        root_session_id=str(root.id),
        agent_name="reader",
        collaboration_slot=1,
    )
    db_session.add(child)
    await db_session.flush()
    child_turn = AgentTurn(
        session_id=str(child.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="child task",
        status=AgentTurnStatus.RUNNING,
        model_profile_snapshot=root_turn.model_profile_snapshot,
    )
    db_session.add(child_turn)
    await db_session.commit()

    with pytest.raises(Exception, match="root_agent_required"):
        await AgentCollaborationService(db_session).spawn_agent(
            parent_session_id=str(child.id),
            parent_turn_id=str(child_turn.id),
            task_name="nested",
            message="not allowed",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("task_name", ["", "Upper", "has-dash", "two words"])
async def test_spawn_agent_rejects_invalid_task_names(
    db_session, task_name: str
) -> None:
    await _seed_workspace(db_session)
    root, turn = await _create_parent_turn(db_session)

    with pytest.raises(Exception, match="invalid_agent_name"):
        await AgentCollaborationService(db_session).spawn_agent(
            parent_session_id=str(root.id),
            parent_turn_id=str(turn.id),
            task_name=task_name,
            message="work",
        )


@pytest.mark.asyncio
async def test_spawn_agent_rejects_duplicate_and_capacity(db_session, monkeypatch) -> None:
    await _seed_workspace(db_session)
    root, turn = await _create_parent_turn(db_session)
    root_id = str(root.id)
    turn_id = str(turn.id)
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )
    service = AgentCollaborationService(db_session)
    await service.spawn_agent(
        parent_session_id=root_id,
        parent_turn_id=turn_id,
        task_name="reader",
        message="first",
        fork_turns="none",
    )
    with pytest.raises(Exception, match="agent_name_reserved"):
        await service.spawn_agent(
            parent_session_id=root_id,
            parent_turn_id=turn_id,
            task_name="reader",
            message="second",
            fork_turns="none",
        )

    for slot in range(2, 8):
        db_session.add(
            AgentSession(
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                parent_session_id=root_id,
                root_session_id=root_id,
                agent_name=f"worker_{slot}",
                collaboration_slot=slot,
            )
        )
    await db_session.commit()
    with pytest.raises(Exception, match="agent_limit_reached"):
        await service.spawn_agent(
            parent_session_id=root_id,
            parent_turn_id=turn_id,
            task_name="eighth",
            message="work",
            fork_turns="none",
        )


@pytest.mark.asyncio
async def test_spawn_agent_reports_requested_model_fallback(
    db_session, monkeypatch
) -> None:
    await _seed_workspace(db_session)
    root, turn = await _create_parent_turn(db_session)
    root_id = str(root.id)
    turn_id = str(turn.id)

    async def fallback(**_kwargs):
        return AgentModelChoice(
            requested_model="cheap-model",
            effective_model="parent-model",
            effective_model_id="parent-id",
            reasoning_effort="high",
            fallback=True,
            fallback_reason="requested_model_unavailable",
        )

    service = AgentCollaborationService(db_session)
    monkeypatch.setattr(service.model_preflight, "resolve", fallback)
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )
    result = await service.spawn_agent(
        parent_session_id=root_id,
        parent_turn_id=turn_id,
        task_name="reader",
        message="work",
        fork_turns="none",
        model="cheap-model",
    )

    assert result.requested_model == "cheap-model"
    assert result.effective_model == "parent-model"
    assert result.model_fallback is True
    assert result.fallback_reason == "requested_model_unavailable"

    events_before_start = await service.ledger.event_repo.list_for_session(
        session_id=root_id,
        event_types={
            "agent.spawned",
            "agent.model_fallback",
            "agent.running",
        },
    )
    assert [event.type for event in events_before_start] == [
        "agent.spawned",
        "agent.model_fallback",
    ]

    assert all(event.visibility == "internal" for event in events_before_start)
    assert events_before_start[0].payload["child_session_id"] == result.child_session_id
    assert events_before_start[0].payload["task_name"] == "/root/reader"
    assert (
        events_before_start[1].payload["fallback_reason"]
        == "requested_model_unavailable"
    )


@pytest.mark.asyncio
async def test_spawn_lifecycle_event_failure_rolls_back_without_reserving_name(
    db_session,
    monkeypatch,
) -> None:
    await _seed_workspace(db_session)
    root, turn = await _create_parent_turn(db_session)
    root_id = str(root.id)
    turn_id = str(turn.id)
    service = AgentCollaborationService(db_session)
    original_append = service.ledger.append

    async def fail_event(*args, **kwargs):
        raise RuntimeError("lifecycle event unavailable")

    monkeypatch.setattr(service.ledger, "append", fail_event)
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )

    with pytest.raises(RuntimeError, match="lifecycle event unavailable"):
        await service.spawn_agent(
            parent_session_id=root_id,
            parent_turn_id=turn_id,
            task_name="reader",
            message="first attempt",
            fork_turns="none",
        )

    await db_session.rollback()
    children = await service.sessions.list_agent_tree(
        root_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert [item.agent_name for item in children if item.agent_name] == []

    monkeypatch.setattr(service.ledger, "append", original_append)
    result = await service.spawn_agent(
        parent_session_id=root_id,
        parent_turn_id=turn_id,
        task_name="reader",
        message="retry",
        fork_turns="none",
    )
    children = await service.sessions.list_agent_tree(
        root_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert result.task_name == "/root/reader"
    assert [item.agent_name for item in children if item.agent_name] == ["reader"]


@pytest.mark.asyncio
async def test_spawn_returns_committed_child_when_notification_fails(
    db_session,
    monkeypatch,
) -> None:
    await _seed_workspace(db_session)
    root, turn = await _create_parent_turn(db_session)
    root_id = str(root.id)
    turn_id = str(turn.id)
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.notify_collaboration_waiters",
        lambda *_: (_ for _ in ()).throw(RuntimeError("notifier unavailable")),
    )
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.logger.warning",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("sentinel-notification-log-secret")
        ),
    )
    service = AgentCollaborationService(db_session)

    result = await service.spawn_agent(
        parent_session_id=root_id,
        parent_turn_id=turn_id,
        task_name="reader",
        message="work",
        fork_turns="none",
    )

    child = await service.sessions.get_fresh(result.child_session_id)
    assert child is not None and child.agent_name == "reader"
    with pytest.raises(Exception, match="agent_name_reserved"):
        await service.spawn_agent(
            parent_session_id=root_id,
            parent_turn_id=turn_id,
            task_name="reader",
            message="duplicate",
            fork_turns="none",
        )


@pytest.mark.asyncio
async def test_running_event_is_owner_fenced_against_terminal_publication(
    db_session,
    db_engine,
) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    terminal_first, terminal_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="terminal_first",
        status=AgentTurnStatus.RUNNING,
        slot=1,
    )
    running_first, running_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="running_first",
        status=AgentTurnStatus.RUNNING,
        slot=2,
    )
    terminal_turn.owner_token = "terminal-owner"
    running_turn.owner_token = "running-owner"
    await db_session.commit()
    root_id = str(root.id)
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    terminal_committed = asyncio.Event()

    async def complete_before_running() -> None:
        async with maker() as worker:
            repo = AgentTurnRepository(worker)
            completed = await repo.update_claimed_execution(
                str(terminal_turn.id),
                owner_token="terminal-owner",
                status=AgentTurnStatus.COMPLETED,
                final_text="terminal won",
            )
            assert completed is not None
            await AgentCollaborationService(worker).publish_child_terminal(
                turn_id=str(terminal_turn.id)
            )
        terminal_committed.set()

    async def publish_after_terminal() -> bool:
        await terminal_committed.wait()
        async with maker() as worker:
            return await AgentCollaborationService(worker).publish_child_running(
                turn_id=str(terminal_turn.id),
                expected_owner_token="terminal-owner",
            )

    _, published_after_terminal = await asyncio.gather(
        complete_before_running(), publish_after_terminal()
    )

    running_committed = asyncio.Event()

    async def publish_before_terminal() -> bool:
        async with maker() as worker:
            published = await AgentCollaborationService(worker).publish_child_running(
                turn_id=str(running_turn.id),
                expected_owner_token="running-owner",
            )
        running_committed.set()
        return published

    async def complete_after_running() -> None:
        await running_committed.wait()
        async with maker() as worker:
            repo = AgentTurnRepository(worker)
            completed = await repo.update_claimed_execution(
                str(running_turn.id),
                owner_token="running-owner",
                status=AgentTurnStatus.COMPLETED,
                final_text="running published first",
            )
            assert completed is not None
            await AgentCollaborationService(worker).publish_child_terminal(
                turn_id=str(running_turn.id)
            )

    published_before_terminal, _ = await asyncio.gather(
        publish_before_terminal(), complete_after_running()
    )
    assert published_after_terminal is False
    assert published_before_terminal is True

    async with maker() as verify:
        events = await AgentCollaborationService(
            verify
        ).ledger.event_repo.list_for_session(
            session_id=root_id,
            event_types={"agent.running", "agent.result.received"},
        )
    terminal_first_events = [
        event
        for event in events
        if event.payload.get("child_session_id") == str(terminal_first.id)
    ]
    running_first_events = [
        event
        for event in events
        if event.payload.get("child_session_id") == str(running_first.id)
    ]
    assert [event.type for event in terminal_first_events] == ["agent.result.received"]
    assert [event.type for event in running_first_events] == [
        "agent.running",
        "agent.result.received",
    ]


@pytest.mark.parametrize(
    ("role", "expects_fallback", "expected_probe_calls"),
    [("owner", False, 1), ("member", True, 0)],
)
@pytest.mark.asyncio
async def test_spawn_resolves_workspace_role_for_user_env_private_model(
    db_session,
    monkeypatch,
    role,
    expects_fallback,
    expected_probe_calls,
) -> None:
    await _seed_workspace(db_session)
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setenv("CHILD_MODEL_API_KEY", "owner-env-secret")
    db_session.add(
        WorkspaceMembership(
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            role=role,
        )
    )
    await db_session.commit()
    model = await _create_probe_model(
        db_session,
        model_name="private-child",
        credential_source="env",
        base_url="http://127.0.0.1:8000/v1",
    )
    model_id = str(model.id)
    root, turn = await _create_parent_turn(db_session)
    root_id = str(root.id)
    turn_id = str(turn.id)
    calls: list[dict] = []

    async def successful_probe(_self, **kwargs):
        calls.append(kwargs)
        return LlmProviderProbeResult(
            success=True,
            latency_ms=1,
            wire_protocol="chat_completions",
            model_id=kwargs["model_id"],
        )

    monkeypatch.setattr(
        "app.services.llm.catalog.LlmProviderProbe.probe",
        successful_probe,
    )
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )

    result = await AgentCollaborationService(db_session).spawn_agent(
        parent_session_id=root_id,
        parent_turn_id=turn_id,
        task_name=f"child_{role}",
        message="work",
        fork_turns="none",
        model=model_id,
    )

    assert result.model_fallback is expects_fallback
    assert len(calls) == expected_probe_calls
    if role == "owner":
        assert calls[0]["network_access"] == "unrestricted"
        assert calls[0]["credential"].api_key == "owner-env-secret"


@pytest.mark.asyncio
async def test_spawn_enqueue_failure_keeps_recoverable_queued_turn(
    db_session, monkeypatch
) -> None:
    await _seed_workspace(db_session)
    root, turn = await _create_parent_turn(db_session)
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: (_ for _ in ()).throw(RuntimeError("queue offline")),
    )

    result = await AgentCollaborationService(db_session).spawn_agent(
        parent_session_id=str(root.id),
        parent_turn_id=str(turn.id),
        task_name="reader",
        message="work",
        fork_turns="none",
    )

    child_turn = await db_session.get(AgentTurn, result.child_turn_id)
    assert child_turn is not None and child_turn.status == AgentTurnStatus.QUEUED
    assert result.status == "pending_init"


@pytest.mark.asyncio
async def test_spawn_commit_failure_rolls_back_child_turn_and_slot(
    db_session, monkeypatch
) -> None:
    await _seed_workspace(db_session)
    root, turn = await _create_parent_turn(db_session)
    root_id = str(root.id)
    turn_id = str(turn.id)
    original_commit = db_session.commit

    async def fail_commit():
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        await AgentCollaborationService(db_session).spawn_agent(
            parent_session_id=root_id,
            parent_turn_id=turn_id,
            task_name="reader",
            message="work",
            fork_turns="none",
        )
    monkeypatch.setattr(db_session, "commit", original_commit)

    children = list(
        (
            await db_session.scalars(
                select(AgentSession).where(AgentSession.root_session_id == root_id)
            )
        ).all()
    )
    assert children == []


@pytest.mark.asyncio
async def test_forked_image_reference_is_reowned_by_child(
    db_session, monkeypatch
) -> None:
    await _seed_workspace(db_session)
    root, turn = await _create_parent_turn(db_session)
    source = AgentAttachment(
        session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        kind="image",
        source="clipboard",
        filename="image.png",
        storage_path=f"{root.id}/source",
        mime_type="image/png",
        size_bytes=3,
        status=AgentAttachmentStatus.READY,
        attachment_metadata={"sha256": "a" * 64},
    )
    db_session.add(source)
    await db_session.flush()
    source_id = str(source.id)
    root_id = str(root.id)
    turn_id = str(turn.id)
    db_session.add(
        AgentMessage(
            session_id=str(root.id),
            turn_id=str(turn.id),
            role="user",
            content_parts=[
                {
                    "type": "image_ref",
                    "attachment_id": source_id,
                    "mime_type": "image/png",
                }
            ],
            status="committed",
            ordering_index=1,
        )
    )
    await db_session.commit()
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service._clone_attachment_files",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )

    result = await AgentCollaborationService(db_session).spawn_agent(
        parent_session_id=root_id,
        parent_turn_id=turn_id,
        task_name="vision",
        message="inspect image",
        fork_turns="all",
    )
    messages = list(
        (
            await db_session.scalars(
                select(AgentMessage)
                .where(AgentMessage.session_id == result.child_session_id)
                .order_by(AgentMessage.ordering_index)
            )
        ).all()
    )
    image_part = messages[0].content_parts[0]
    assert "source_attachment_id" not in image_part
    clone = await db_session.get(AgentAttachment, image_part["attachment_id"])
    assert clone is not None
    assert str(clone.session_id) == result.child_session_id
    assert str(clone.id) != source_id


@pytest.mark.parametrize("failure_type", [RuntimeError, asyncio.CancelledError])
@pytest.mark.asyncio
async def test_attachment_clone_partial_failure_removes_files_and_rolls_back_db(
    db_session,
    monkeypatch,
    tmp_path,
    failure_type,
) -> None:
    await _seed_workspace(db_session)
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    root, turn = await _create_parent_turn(db_session)
    root_id = str(root.id)
    turn_id = str(turn.id)
    sources: list[AgentAttachment] = []
    for index in range(2):
        source = AgentAttachment(
            session_id=root_id,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            kind="image",
            source="clipboard",
            filename=f"image-{index}.png",
            storage_path="pending",
            mime_type="image/png",
            size_bytes=3,
            status=AgentAttachmentStatus.READY,
            attachment_metadata={"sha256": str(index) * 64},
        )
        db_session.add(source)
        await db_session.flush()
        source.storage_path = f"{root_id}/{source.id}"
        source_root = agent_attachment_root(root_id, str(source.id))
        source_root.mkdir(parents=True)
        (source_root / "original").write_bytes(b"png")
        sources.append(source)
    db_session.add(
        AgentMessage(
            session_id=root_id,
            turn_id=turn_id,
            role="user",
            content_parts=[
                {"type": "image_ref", "attachment_id": str(source.id)}
                for source in sources
            ],
            status="committed",
            ordering_index=1,
        )
    )
    await db_session.commit()
    original_clone = __import__(
        "app.services.agent_core.collaboration.service",
        fromlist=["_clone_attachment_files"],
    )._clone_attachment_files
    calls = 0

    def fail_second_clone(*, source, destination):
        nonlocal calls
        calls += 1
        if calls == 1:
            return original_clone(source=source, destination=destination)
        destination.mkdir(parents=True)
        (destination / "partial").write_bytes(b"orphan")
        raise failure_type("clone interrupted")

    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service._clone_attachment_files",
        fail_second_clone,
    )

    with pytest.raises(failure_type, match="clone interrupted"):
        await AgentCollaborationService(db_session).spawn_agent(
            parent_session_id=root_id,
            parent_turn_id=turn_id,
            task_name="vision_failure",
            message="inspect images",
            fork_turns="all",
        )

    assert db_session.in_transaction() is False
    children = list(
        (
            await db_session.scalars(
                select(AgentSession).where(AgentSession.root_session_id == root_id)
            )
        ).all()
    )
    assert children == []
    attachment_sessions = {
        path.name for path in agent_attachments_root().iterdir() if path.is_dir()
    }
    assert attachment_sessions == {root_id}


@pytest.mark.asyncio
async def test_list_agents_is_root_scoped_deterministic_and_projects_status(
    db_session,
) -> None:
    await _seed_workspace(db_session)
    root, _turn = await _create_parent_turn(db_session)
    completed = AgentSession(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        parent_session_id=str(root.id),
        root_session_id=str(root.id),
        agent_name="alpha",
        session_metadata={"collaboration": {"effective_model": "cheap"}},
    )
    running = AgentSession(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        parent_session_id=str(root.id),
        root_session_id=str(root.id),
        agent_name="beta",
        collaboration_slot=1,
        session_metadata={"collaboration": {"effective_model": "parent-model"}},
    )
    db_session.add_all([completed, running])
    await db_session.flush()
    db_session.add_all(
        [
            AgentTurn(
                session_id=str(completed.id),
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                input_text="done",
                status=AgentTurnStatus.COMPLETED,
                final_text="finished",
            ),
            AgentTurn(
                session_id=str(running.id),
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                input_text="active",
                status=AgentTurnStatus.RUNNING,
            ),
        ]
    )
    await db_session.commit()

    result = await AgentCollaborationService(db_session).list_agents(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    assert [agent.task_name for agent in result] == [
        "/root",
        "/root/alpha",
        "/root/beta",
    ]
    assert result[1].status == "completed"
    assert result[1].final_text == "finished"
    assert result[2].status == "running"

    assert (
        await AgentCollaborationService(db_session).list_agents(
            caller_session_id=str(root.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="other-user",
        )
        == []
    )


@pytest.mark.asyncio
async def test_list_agents_projects_safe_nonempty_errors_without_provider_details(
    db_session,
) -> None:
    await _seed_workspace(db_session)
    root, _turn = await _create_parent_turn(db_session)
    child = AgentSession(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        parent_session_id=str(root.id),
        root_session_id=str(root.id),
        agent_name="broken",
    )
    db_session.add(child)
    await db_session.flush()
    db_session.add(
        AgentTurn(
            session_id=str(child.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text="fail",
            status=AgentTurnStatus.FAILED,
            error_code="model_request_failed",
            error_message="HTTP 401 raw-secret-token authentication denied",
        )
    )
    await db_session.commit()

    result = await AgentCollaborationService(db_session).list_agents(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    broken = next(agent for agent in result if agent.task_name == "/root/broken")
    assert broken.status == "errored"
    assert broken.error_code == "model_request_failed"
    assert broken.error_message == "Model provider authentication failed."
    assert "secret" not in broken.error_message


@pytest.mark.asyncio
async def test_list_agents_uses_generic_nonempty_error_for_unknown_empty_failure(
    db_session,
) -> None:
    await _seed_workspace(db_session)
    root, _turn = await _create_parent_turn(db_session)
    child = AgentSession(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        parent_session_id=str(root.id),
        root_session_id=str(root.id),
        agent_name="unknown_failure",
    )
    db_session.add(child)
    await db_session.flush()
    db_session.add(
        AgentTurn(
            session_id=str(child.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text="fail",
            status=AgentTurnStatus.FAILED,
            error_code="provider_internal_opaque",
            error_message="",
        )
    )
    await db_session.commit()

    result = await AgentCollaborationService(db_session).list_agents(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    failed = next(
        agent for agent in result if agent.task_name == "/root/unknown_failure"
    )
    assert failed.error_code == "provider_internal_opaque"
    assert failed.error_message == "Agent failed before completing the task."


@pytest.mark.asyncio
async def test_authentication_failure_persists_safe_nonempty_child_error(
    db_session,
) -> None:
    await _seed_workspace(db_session)
    root, _turn = await _create_parent_turn(db_session)
    child, failed_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="auth_failure",
        status=AgentTurnStatus.FAILED,
    )
    failed_turn.error_code = "model_request_failed"
    failed_turn.error_message = "HTTP 401 raw-secret-token authentication denied"
    await db_session.commit()

    await AgentCollaborationService(db_session).publish_child_terminal(
        turn_id=str(failed_turn.id)
    )

    await db_session.refresh(failed_turn)
    assert failed_turn.final_text in {None, ""}
    assert failed_turn.error_code == "model_request_failed"
    assert failed_turn.error_message == "Model provider authentication failed."
    assert "secret" not in failed_turn.error_message.lower()


async def _create_child_with_turn(
    db_session: AsyncSession,
    *,
    root: AgentSession,
    name: str,
    status: str = AgentTurnStatus.COMPLETED,
    slot: int | None = None,
) -> tuple[AgentSession, AgentTurn]:
    child = AgentSession(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        parent_session_id=str(root.id),
        root_session_id=str(root.id),
        agent_name=name,
        collaboration_slot=slot,
        session_metadata={
            "collaboration": {
                "effective_model": "parent-model",
                "effective_model_id": "parent-id",
            }
        },
    )
    db_session.add(child)
    await db_session.flush()
    turn = AgentTurn(
        session_id=str(child.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="child task",
        status=status,
        accepts_steer=status
        not in {
            AgentTurnStatus.COMPLETED,
            AgentTurnStatus.FAILED,
            AgentTurnStatus.CANCELLED,
        },
        model_profile_snapshot={
            "resolved_model_id": "parent-id",
            "resolved_model_selection": {"model": "parent-model"},
        },
    )
    db_session.add(turn)
    await db_session.flush()
    child.active_turn_id = (
        str(turn.id)
        if status
        not in {
            AgentTurnStatus.COMPLETED,
            AgentTurnStatus.FAILED,
            AgentTurnStatus.CANCELLED,
        }
        else None
    )
    await db_session.commit()
    return child, turn


@pytest.mark.asyncio
async def test_send_message_to_idle_child_is_durable_without_starting_turn(
    db_session,
    monkeypatch,
) -> None:
    await _seed_workspace(db_session)
    root, _ = await _create_parent_turn(db_session)
    child, prior_turn = await _create_child_with_turn(
        db_session, root=root, name="reader"
    )
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.notify_collaboration_waiters",
        lambda *_: (_ for _ in ()).throw(RuntimeError("idle notifier unavailable")),
    )
    result = await AgentCollaborationService(db_session).send_message(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
        message="Extra context",
    )

    turns = await AgentCollaborationService(db_session).turns.list_for_session(
        str(child.id)
    )
    assert [str(turn.id) for turn in turns] == [str(prior_turn.id)]
    messages = await AgentCollaborationService(db_session).transcript.list_messages(
        str(child.id)
    )
    mailbox = [
        message
        for message in messages
        if (message.message_metadata or {}).get("kind") == "inter_agent_message"
    ]
    assert result.delivery == "queued"
    assert len(mailbox) == 1
    assert [parts_to_text(message.content_parts) for message in mailbox] == [
        "Extra context"
    ]
    assert mailbox[0].status == AgentMessageStatus.DRAFT
    events = await AgentCollaborationService(
        db_session
    ).ledger.event_repo.list_for_session(
        session_id=str(root.id),
        event_types={"agent.message.received"},
    )
    assert events[-1].payload == {
        "child_session_id": str(child.id),
        "task_name": "/root/reader",
        "delivery": "queued",
    }
    assert len(events) == 1


@pytest.mark.asyncio
async def test_followup_task_reuses_idle_child_and_acquires_slot(
    db_session, monkeypatch
) -> None:
    await _seed_workspace(db_session)
    root, _ = await _create_parent_turn(db_session)
    child, _ = await _create_child_with_turn(db_session, root=root, name="reader")
    enqueued: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda turn_id, session_id: enqueued.append((turn_id, session_id)),
    )

    result = await AgentCollaborationService(db_session).followup_task(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
        message="Now inspect pyproject.toml",
    )

    await db_session.refresh(child)
    turns = await AgentCollaborationService(db_session).turns.list_for_session(
        str(child.id)
    )
    followup_turn = next(turn for turn in turns if str(turn.id) == result.turn_id)
    assert result.delivery == "followup"
    assert followup_turn.input_text == "Now inspect pyproject.toml"
    assert child.collaboration_slot == 1
    assert enqueued == [(str(followup_turn.id), str(child.id))]
    events = await AgentCollaborationService(
        db_session
    ).ledger.event_repo.list_for_session(
        session_id=str(root.id),
        event_types={"agent.followup.received"},
    )
    assert events[-1].payload["child_session_id"] == str(child.id)
    assert events[-1].payload["child_turn_id"] == str(followup_turn.id)
    assert events[-1].payload["delivery"] == "followup"


@pytest.mark.asyncio
async def test_followup_lifecycle_event_failure_rolls_back_and_retry_is_unique(
    db_session,
    monkeypatch,
) -> None:
    await _seed_workspace(db_session)
    root, _ = await _create_parent_turn(db_session)
    child, prior_turn = await _create_child_with_turn(
        db_session, root=root, name="reader"
    )
    root_id = str(root.id)
    child_id = str(child.id)
    prior_turn_id = str(prior_turn.id)
    service = AgentCollaborationService(db_session)
    original_append = service.ledger.append

    async def fail_event(*args, **kwargs):
        raise RuntimeError("followup event unavailable")

    monkeypatch.setattr(service.ledger, "append", fail_event)
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )

    with pytest.raises(RuntimeError, match="followup event unavailable"):
        await service.followup_task(
            caller_session_id=root_id,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            target="/root/reader",
            message="first followup",
        )

    await db_session.rollback()
    turns = await service.turns.list_for_session(child_id)
    assert [str(item.id) for item in turns] == [prior_turn_id]

    monkeypatch.setattr(service.ledger, "append", original_append)
    result = await service.followup_task(
        caller_session_id=root_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
        message="retry followup",
    )
    turns = await service.turns.list_for_session(child_id)
    assert result.turn_id is not None
    assert [item.input_text for item in turns].count("retry followup") == 1


@pytest.mark.asyncio
async def test_followup_returns_unique_turn_when_notification_fails(
    db_session,
    monkeypatch,
) -> None:
    await _seed_workspace(db_session)
    root, _ = await _create_parent_turn(db_session)
    child, _ = await _create_child_with_turn(db_session, root=root, name="reader")
    root_id = str(root.id)
    child_id = str(child.id)
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.notify_collaboration_waiters",
        lambda *_: (_ for _ in ()).throw(RuntimeError("notifier unavailable")),
    )
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.logger.warning",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("sentinel-notification-log-secret")
        ),
    )
    service = AgentCollaborationService(db_session)

    result = await service.followup_task(
        caller_session_id=root_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
        message="followup",
    )

    turns = await service.turns.list_for_session(child_id)
    assert result.turn_id is not None
    assert [item.input_text for item in turns].count("followup") == 1


@pytest.mark.asyncio
async def test_active_followup_returns_steer_when_notification_fails(
    db_session,
    monkeypatch,
    caplog,
) -> None:
    await _seed_workspace(db_session)
    root, _ = await _create_parent_turn(db_session)
    child, active_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.RUNNING,
        slot=1,
    )
    root_id = str(root.id)
    active_turn_id = str(active_turn.id)
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.notify_collaboration_waiters",
        lambda *_: (_ for _ in ()).throw(
            RuntimeError("sentinel-steer-notifier-secret")
        ),
    )
    service = AgentCollaborationService(db_session)

    result = await service.followup_task(
        caller_session_id=root_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
        message="steer despite notifier failure",
    )

    events = await service.ledger.event_repo.list_for_session(
        session_id=root_id,
        event_types={AgentEventType.AGENT_FOLLOWUP_RECEIVED},
    )
    assert result.delivery == "steer"
    assert result.turn_id == active_turn_id
    assert events[-1].payload["delivery"] == "steer"
    assert "sentinel-steer-notifier-secret" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["factory", "enter", "cleanup"])
async def test_active_followup_survives_lifecycle_event_session_failure(
    db_session,
    monkeypatch,
    caplog,
    failure_stage,
) -> None:
    await _seed_workspace(db_session)
    root, _ = await _create_parent_turn(db_session)
    child, active_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.RUNNING,
        slot=1,
    )
    root_id = str(root.id)
    child_id = str(child.id)
    active_turn_id = str(active_turn.id)

    class FailingEventSession:
        async def rollback(self):
            raise RuntimeError("sentinel-lifecycle-rollback-secret")

    class FailingEventContext:
        async def __aenter__(self):
            if failure_stage == "enter":
                raise RuntimeError("sentinel-lifecycle-enter-secret")
            return FailingEventSession()

        async def __aexit__(self, exc_type, exc, traceback):
            if failure_stage == "cleanup":
                raise RuntimeError("sentinel-lifecycle-exit-secret")
            return False

    class FailingEventSessionFactory:
        def __call__(self):
            return FailingEventContext()

    def event_sessionmaker(*args, **kwargs):
        if failure_stage == "factory":
            raise RuntimeError("sentinel-lifecycle-factory-secret")
        return FailingEventSessionFactory()

    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.async_sessionmaker",
        event_sessionmaker,
    )
    if failure_stage == "cleanup":
        async def fail_lifecycle_publication(*args, **kwargs):
            raise RuntimeError("sentinel-lifecycle-publication-secret")

        monkeypatch.setattr(
            AgentCollaborationService,
            "_publish_root_activity",
            fail_lifecycle_publication,
        )
    service = AgentCollaborationService(db_session)

    result = await service.followup_task(
        caller_session_id=root_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
        message=f"steer despite {failure_stage} failure",
    )

    messages = await service.transcript.list_messages(child_id)
    assert result.delivery == "steer"
    assert result.turn_id == active_turn_id
    assert any(
        item.role == "user"
        and (item.message_metadata or {}).get("kind") == "steer"
        for item in messages
    )
    assert "sentinel-lifecycle" not in caplog.text


@pytest.mark.asyncio
async def test_child_can_message_parent_and_follow_up_sibling(
    db_session, monkeypatch
) -> None:
    await _seed_workspace(db_session)
    root, _ = await _create_parent_turn(db_session)
    sender, _ = await _create_child_with_turn(
        db_session, root=root, name="reader"
    )
    sibling, _ = await _create_child_with_turn(
        db_session, root=root, name="reviewer"
    )
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )
    service = AgentCollaborationService(db_session)

    sent = await service.send_message(
        caller_session_id=str(sender.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root",
        message="I found the config",
    )
    followed = await service.followup_task(
        caller_session_id=str(sender.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reviewer",
        message="Check the config I found",
    )

    assert sent.delivery == "steer"
    assert followed.delivery == "followup"
    sibling_turns = await service.turns.list_for_session(str(sibling.id))
    sibling_followup = next(
        turn for turn in sibling_turns if str(turn.id) == followed.turn_id
    )
    assert sibling_followup.input_text == "Check the config I found"
    events = await service.ledger.event_repo.list_for_session(
        session_id=str(root.id),
        event_types={"agent.message.received"},
    )
    assert events[-1].payload["child_session_id"] == str(sender.id)
    assert events[-1].payload["task_name"] == "/root/reader"


@pytest.mark.asyncio
async def test_collaboration_targets_fail_closed_across_roots(db_session) -> None:
    await _seed_workspace(db_session)
    root, _ = await _create_parent_turn(db_session)
    other = await _create_session(db_session)
    outsider, _ = await _create_child_with_turn(
        db_session, root=other, name="reader"
    )

    with pytest.raises(Exception, match="agent_target_not_found"):
        await AgentCollaborationService(db_session).send_message(
            caller_session_id=str(root.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            target=str(outsider.id),
            message="leak",
        )


@pytest.mark.asyncio
async def test_followup_rejects_root_and_interrupt_rejects_root_or_self(
    db_session,
) -> None:
    await _seed_workspace(db_session)
    root, _ = await _create_parent_turn(db_session)
    child, _ = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.RUNNING,
        slot=1,
    )
    service = AgentCollaborationService(db_session)

    with pytest.raises(Exception, match="child_agent_required"):
        await service.followup_task(
            caller_session_id=str(child.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            target="/root",
            message="not allowed",
        )
    with pytest.raises(Exception, match="child_agent_required"):
        await service.interrupt_agent(
            caller_session_id=str(root.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            target="/root",
        )
    with pytest.raises(Exception, match="cannot_interrupt_self"):
        await service.interrupt_agent(
            caller_session_id=str(child.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            target="/root/reader",
        )


@pytest.mark.asyncio
async def test_interrupt_uses_terminal_result_as_the_only_lifecycle_authority(
    db_session,
    monkeypatch,
) -> None:
    await _seed_workspace(db_session)
    root, _ = await _create_parent_turn(db_session)
    child, child_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.RUNNING,
        slot=1,
    )
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.notify_collaboration_waiters",
        lambda *_: (_ for _ in ()).throw(RuntimeError("interrupt notifier unavailable")),
    )
    service = AgentCollaborationService(db_session)

    result = await service.interrupt_agent(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
    )

    assert result.status == "running"
    events = await service.ledger.event_repo.list_for_session(
        session_id=str(root.id),
        event_types={"agent.interrupted", "agent.result.received"},
    )
    assert [event.type for event in events] == ["agent.result.received"]
    assert events[0].payload["child_session_id"] == str(child.id)
    assert events[0].payload["child_turn_id"] == str(child_turn.id)
    assert events[0].payload["status"] == "interrupted"
    results = [
        message
        for message in await service.transcript.list_messages(str(root.id))
        if (message.message_metadata or {}).get("collaboration_kind")
        == "agent_result"
    ]
    assert len(results) == 1


@pytest.mark.asyncio
async def test_interrupt_loses_cleanly_when_completion_cas_wins(
    db_session,
    db_engine,
    monkeypatch,
) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child, child_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.RUNNING,
        slot=1,
    )
    child_turn.owner_token = "completion-owner"
    await db_session.commit()
    root_id = str(root.id)
    child_id = str(child.id)
    turn_id = str(child_turn.id)
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    service = AgentCollaborationService(db_session)
    completion_committed = asyncio.Event()
    interrupt_reached_cas = asyncio.Event()
    original_interrupt = service.core.interrupt_turn

    async def delayed_interrupt(**kwargs):
        interrupt_reached_cas.set()
        await completion_committed.wait()
        return await original_interrupt(**kwargs)

    monkeypatch.setattr(service.core, "interrupt_turn", delayed_interrupt)
    monkeypatch.setattr(
        "app.services.agent_core.service.cancel_turn_run",
        lambda *_: False,
    )

    interrupt_task = asyncio.create_task(
        service.interrupt_agent(
            caller_session_id=root_id,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            target="/root/reader",
        )
    )
    await interrupt_reached_cas.wait()
    async with maker() as completer:
        completed = await AgentTurnRepository(completer).update_claimed_execution(
            turn_id,
            owner_token="completion-owner",
            status=AgentTurnStatus.COMPLETED,
            final_text="completion won",
        )
        assert completed is not None
        await AgentCollaborationService(completer).publish_child_terminal(
            turn_id=turn_id
        )
    completion_committed.set()
    previous = await interrupt_task

    assert previous.status == "running"
    async with maker() as verify:
        persisted = await AgentTurnRepository(verify).get_fresh(turn_id)
        events = await AgentCollaborationService(
            verify
        ).ledger.event_repo.list_for_session(
            session_id=root_id,
            event_types={"agent.interrupted", "agent.result.received"},
        )
    assert persisted is not None and persisted.status == AgentTurnStatus.COMPLETED
    child_events = [
        event for event in events if event.payload.get("child_session_id") == child_id
    ]
    assert [event.type for event in child_events] == ["agent.result.received"]
    assert child_events[0].payload["status"] == "completed"


@pytest.mark.asyncio
async def test_terminal_child_publishes_safe_exactly_once_parent_result(
    db_session,
) -> None:
    await _seed_workspace(db_session)
    root, _ = await _create_parent_turn(db_session)
    child, child_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.FAILED,
        slot=1,
    )
    child_turn.error_code = "model_request_failed"
    child_turn.error_message = "HTTP 401 raw-secret-token authentication denied"
    await db_session.commit()
    service = AgentCollaborationService(db_session)

    await service.publish_child_terminal(turn_id=str(child_turn.id))
    await service.publish_child_terminal(turn_id=str(child_turn.id))

    await db_session.refresh(child)
    messages = await service.transcript.list_messages(str(root.id))
    results = [
        message
        for message in messages
        if (message.message_metadata or {}).get("collaboration_kind")
        == "agent_result"
    ]
    assert child.collaboration_slot is None
    assert len(results) == 1
    payload = (results[0].message_metadata or {})["agent_result"]
    assert payload["status"] == "errored"
    assert payload["error_message"] == "Model provider authentication failed."
    assert "secret" not in parts_to_text(results[0].content_parts)


@pytest.mark.asyncio
async def test_terminal_publication_notification_failure_keeps_result_once(
    db_session,
    monkeypatch,
) -> None:
    await _seed_workspace(db_session)
    root, _ = await _create_parent_turn(db_session)
    child, child_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.COMPLETED,
        slot=1,
    )
    child_turn.final_text = "README found"
    await db_session.commit()
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.notify_collaboration_waiters",
        lambda *_: (_ for _ in ()).throw(RuntimeError("terminal notifier unavailable")),
    )
    service = AgentCollaborationService(db_session)

    await service.publish_child_terminal(turn_id=str(child_turn.id))
    await service.publish_child_terminal(turn_id=str(child_turn.id))

    results = [
        message
        for message in await service.transcript.list_messages(str(root.id))
        if (message.message_metadata or {}).get("collaboration_kind")
        == "agent_result"
    ]
    assert len(results) == 1
    assert (results[0].message_metadata or {})["agent_result"]["status"] == "completed"


@pytest.mark.asyncio
async def test_wait_agent_observes_terminal_update_without_returning_content(
    db_session,
) -> None:
    await _seed_workspace(db_session)
    root, _ = await _create_parent_turn(db_session)
    child, child_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.COMPLETED,
        slot=1,
    )
    child_turn.final_text = "README found"
    await db_session.commit()
    service = AgentCollaborationService(db_session)
    await service.publish_child_terminal(turn_id=str(child_turn.id))

    result = await service.wait_agent(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        timeout_ms=0,
    )

    assert result.timed_out is False
    assert result.updated_agents == ["/root/reader"]
    assert "README found" not in repr(result)


@pytest.mark.asyncio
async def test_idle_parent_consumes_terminal_mailbox_once_on_next_turn(
    db_session,
) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child, child_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.COMPLETED,
        slot=1,
    )
    child_turn.final_text = "README found"
    await db_session.commit()
    collaboration = AgentCollaborationService(db_session)
    await collaboration.publish_child_terminal(turn_id=str(child_turn.id))

    queued = [
        message
        for message in await collaboration.transcript.list_messages(str(root.id))
        if (message.message_metadata or {}).get("collaboration_kind")
        == "agent_result"
    ]
    assert len(queued) == 1 and queued[0].status == AgentMessageStatus.DRAFT

    parent_turn = await AgentCoreService(db_session).create_turn_record(
        session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Continue",
    )
    messages = await collaboration.transcript.list_messages(str(root.id))
    results = [
        message
        for message in messages
        if (message.message_metadata or {}).get("collaboration_kind")
        == "agent_result"
    ]
    assert len(results) == 1
    assert results[0].status == AgentMessageStatus.COMMITTED
    assert results[0].turn_id == parent_turn.id
    assert (results[0].message_metadata or {})["consumed"] is True
    first_context = await AgentContextAssembler(db_session).model_context(
        agent_session=root,
        turn=parent_turn,
    )
    second_context = await AgentContextAssembler(db_session).model_context(
        agent_session=root,
        turn=parent_turn,
    )
    assert repr(first_context.input_items).count("README found") == 1
    assert repr(second_context.input_items).count("README found") == 1


@pytest.mark.asyncio
async def test_send_message_to_running_child_uses_durable_steer(db_session) -> None:
    await _seed_workspace(db_session)
    root, _ = await _create_parent_turn(db_session)
    child, child_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.RUNNING,
        slot=1,
    )

    result = await AgentCollaborationService(db_session).send_message(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
        message="Use the exact path",
    )

    messages = await AgentCollaborationService(db_session).transcript.list_messages(
        str(child.id)
    )
    steer = next(
        message
        for message in messages
        if (message.message_metadata or {}).get("collaboration_kind")
        == "inter_agent_message"
    )
    assert result.delivery == "steer"
    assert steer.turn_id == child_turn.id
    assert steer.status == AgentMessageStatus.DRAFT


@pytest.mark.asyncio
async def test_terminal_hook_schedules_only_one_queued_followup(
    db_session, monkeypatch
) -> None:
    await _seed_workspace(db_session)
    root, _ = await _create_parent_turn(db_session)
    child, child_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.RUNNING,
        slot=1,
    )
    child_turn.accepts_steer = False
    await db_session.commit()
    enqueued: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda turn_id, session_id: enqueued.append((turn_id, session_id)),
    )
    service = AgentCollaborationService(db_session)

    queued = await service.followup_task(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
        message="Retry with a smaller task",
    )
    assert queued.delivery == "queued"
    child_turn.status = AgentTurnStatus.COMPLETED
    child_turn.accepts_steer = False
    child_turn.final_text = "first task done"
    await db_session.commit()

    await service.publish_child_terminal(turn_id=str(child_turn.id))
    await service.publish_child_terminal(turn_id=str(child_turn.id))

    turns = await service.turns.list_for_session(str(child.id))
    followups = [turn for turn in turns if turn.input_text == "Retry with a smaller task"]
    assert len(followups) == 1
    assert enqueued == [(str(followups[0].id), str(child.id))]
    await db_session.refresh(child)
    assert child.collaboration_slot is not None


@pytest.mark.asyncio
async def test_interrupted_child_remains_reusable(db_session, monkeypatch) -> None:
    await _seed_workspace(db_session)
    root, _ = await _create_parent_turn(db_session)
    child, _ = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.RUNNING,
        slot=1,
    )
    monkeypatch.setattr(
        "app.services.agent_core.service.cancel_turn_run",
        lambda *_: False,
    )
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )
    service = AgentCollaborationService(db_session)

    previous = await service.interrupt_agent(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
    )
    followup = await service.followup_task(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
        message="Try a smaller task",
    )

    assert previous.status == "running"
    assert followup.delivery == "followup"
    await db_session.refresh(child)
    assert child.collaboration_slot is not None


@pytest.mark.asyncio
async def test_active_parent_delivers_terminal_result_exactly_once_at_boundary(
    db_session,
) -> None:
    await _seed_workspace(db_session)
    root, parent_turn = await _create_parent_turn(db_session)
    root_id = str(root.id)
    parent_turn_id = str(parent_turn.id)
    parent_turn.owner_token = "owner-token"
    _child, child_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.COMPLETED,
        slot=1,
    )
    child_turn.final_text = "README found"
    await db_session.commit()
    service = AgentCollaborationService(db_session)
    await service.publish_child_terminal(turn_id=str(child_turn.id))

    first = await service.transcript.deliver_pending_steers(
        session_id=root_id,
        turn_id=parent_turn_id,
        expected_owner_token="owner-token",
    )
    second = await service.transcript.deliver_pending_steers(
        session_id=root_id,
        turn_id=parent_turn_id,
        expected_owner_token="owner-token",
    )
    messages = await service.transcript.list_messages(root_id)
    results = [
        message
        for message in messages
        if (message.message_metadata or {}).get("collaboration_kind")
        == "agent_result"
    ]

    assert len(first) == 1
    assert second == []
    assert len(results) == 1
    assert results[0].status == AgentMessageStatus.COMMITTED
    assert (results[0].message_metadata or {})["consumed"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal_status",
    [
        AgentTurnStatus.COMPLETED,
        AgentTurnStatus.FAILED,
        AgentTurnStatus.CANCELLED,
    ],
)
async def test_startup_recovery_publishes_committed_child_terminal_from_new_session(
    db_session, db_engine, terminal_status
) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child, child_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=terminal_status,
        slot=1,
    )
    child.active_turn_id = str(child_turn.id)
    if terminal_status == AgentTurnStatus.COMPLETED:
        child_turn.final_text = "README found"
    elif terminal_status == AgentTurnStatus.FAILED:
        child_turn.error_code = "model_request_failed"
        child_turn.error_message = "Model provider authentication failed."
    else:
        child_turn.termination_reason = "interrupted"
    await db_session.commit()
    root_id = str(root.id)
    child_id = str(child.id)
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async with maker() as restarted:
        summary = await AgentCoreService(restarted).recover_orphaned_turns()

    async with maker() as verify:
        messages = await AgentCollaborationService(verify).transcript.list_messages(
            root_id
        )
        recovered_child = await verify.get(AgentSession, child_id)
        results = [
            message
            for message in messages
            if (message.message_metadata or {}).get("source_turn_id")
            == str(child_turn.id)
        ]
        assert summary["collaboration_published"] == 1
        assert len(results) == 1
        assert recovered_child is not None
        assert recovered_child.active_turn_id is None
        assert recovered_child.collaboration_slot is None


@pytest.mark.asyncio
async def test_two_sessions_concurrently_publish_terminal_result_once(
    db_session, db_engine
) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child, child_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.FAILED,
        slot=1,
    )
    child_turn.error_code = "model_request_failed"
    child_turn.error_message = "Model provider authentication failed."
    await db_session.commit()
    root_id = str(root.id)
    child_id = str(child.id)
    turn_id = str(child_turn.id)
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def publish() -> None:
        async with maker() as worker:
            await AgentCollaborationService(worker).publish_child_terminal(
                turn_id=turn_id
            )

    await asyncio.gather(publish(), publish())

    async with maker() as verify:
        messages = await AgentCollaborationService(verify).transcript.list_messages(
            root_id
        )
        results = [
            message
            for message in messages
            if (message.message_metadata or {}).get("source_turn_id") == turn_id
        ]
        root_events = await AgentCollaborationService(
            verify
        ).ledger.event_repo.list_for_session(
            session_id=root_id,
            event_types={"agent.result.received"},
        )
        marker_events = await AgentCollaborationService(
            verify
        ).ledger.event_repo.list_for_session(
            session_id=child_id,
            event_types={"agent.result.published"},
        )
        assert len(results) == 1
        assert len(root_events) == 1
        assert len(marker_events) == 1


@pytest.mark.asyncio
async def test_terminal_event_contains_complete_safe_payload(db_session) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child, child_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.FAILED,
        slot=1,
    )
    child_turn.error_code = "model_request_failed"
    child_turn.error_message = "HTTP 401 secret-token authentication denied"
    child_turn.termination_reason = "model_failed"
    child_turn.token_usage = {"input_tokens": 10, "output_tokens": 2}
    await db_session.commit()

    service = AgentCollaborationService(db_session)
    await service.publish_child_terminal(turn_id=str(child_turn.id))
    events = await service.ledger.event_repo.list_for_session(
        session_id=str(root.id),
        event_types={"agent.result.received"},
    )
    payload = events[-1].payload

    assert payload["child_session_id"] == str(child.id)
    assert payload["task_name"] == "/root/reader"
    assert payload["status"] == "errored"
    assert payload["error_code"] == "model_request_failed"
    assert payload["error_message"] == "Model provider authentication failed."
    assert payload["error_message"]
    assert payload["termination_reason"] == "model_failed"
    assert payload["token_usage"] == {"input_tokens": 10, "output_tokens": 2}
    assert payload["effective_model"] == "parent-model"
    assert "secret" not in repr(payload)


@pytest.mark.asyncio
async def test_child_wait_observes_direct_child_steer(db_session) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child, child_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.RUNNING,
        slot=1,
    )
    service = AgentCollaborationService(db_session)
    await service.core.steer_turn(
        turn_id=str(child_turn.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Use the exact path",
    )

    result = await service.wait_agent(
        caller_session_id=str(child.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        timeout_ms=0,
    )

    assert result.timed_out is False
    assert result.updated_agents == ["/root/reader"]
    assert "Use the exact path" not in repr(result)


@pytest.mark.asyncio
async def test_mailbox_consumption_rolls_back_with_failed_turn_claim_and_retries(
    db_session, db_engine
) -> None:
    await _seed_workspace(db_session)
    root, active_turn = await _create_parent_turn(db_session)
    _child, child_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.COMPLETED,
        slot=1,
    )
    child_turn.final_text = "README found"
    await db_session.commit()
    root_id = str(root.id)
    await AgentCollaborationService(db_session).publish_child_terminal(
        turn_id=str(child_turn.id)
    )

    with pytest.raises(Exception, match="another turn is active"):
        await AgentCoreService(db_session).create_turn_record(
            session_id=root_id,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text="Conflicting turn",
        )
    active_turn.status = AgentTurnStatus.COMPLETED
    root.active_turn_id = None
    await db_session.commit()
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async with maker() as retried:
        turn = await AgentCoreService(retried).create_turn_record(
            session_id=root_id,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text="Continue",
        )
        messages = await AgentCollaborationService(retried).transcript.list_messages(
            root_id
        )
        results = [
            message
            for message in messages
            if (message.message_metadata or {}).get("collaboration_kind")
            == "agent_result"
        ]
        assert len(results) == 1
        assert results[0].turn_id == turn.id
        assert results[0].status == AgentMessageStatus.COMMITTED


@pytest.mark.asyncio
async def test_two_idle_followups_race_to_one_active_turn(
    db_session, db_engine, monkeypatch
) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child, _ = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.COMPLETED,
    )
    root_id = str(root.id)
    child_id = str(child.id)
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def follow(message: str):
        async with maker() as worker:
            return await AgentCollaborationService(worker).followup_task(
                caller_session_id=root_id,
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                target="/root/reader",
                message=message,
            )

    results = await asyncio.gather(follow("first"), follow("second"))

    async with maker() as verify:
        turns = await AgentCollaborationService(verify).turns.list_for_session(
            child_id
        )
        active = [
            turn
            for turn in turns
            if turn.status
            in {
                AgentTurnStatus.QUEUED,
                AgentTurnStatus.RUNNING,
                AgentTurnStatus.WAITING_USER,
                AgentTurnStatus.WAITING_APPROVAL,
            }
        ]
        assert len(active) == 1
        assert sorted(result.delivery for result in results) == ["followup", "steer"]


@pytest.mark.asyncio
async def test_old_terminal_recovery_does_not_release_new_followup_slot_new_session(
    db_session, db_engine, monkeypatch
) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child, old_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.RUNNING,
        slot=1,
    )
    old_turn.accepts_steer = False
    await db_session.commit()
    root_id = str(root.id)
    child_id = str(child.id)
    old_turn_id = str(old_turn.id)
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )
    service = AgentCollaborationService(db_session)
    await service.followup_task(
        caller_session_id=root_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
        message="new work",
    )
    old_turn.status = AgentTurnStatus.COMPLETED
    old_turn.accepts_steer = False
    await db_session.commit()
    await service.publish_child_terminal(turn_id=old_turn_id)
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async with maker() as restarted:
        await AgentCollaborationService(restarted).publish_child_terminal(
            turn_id=old_turn_id
        )

    async with maker() as verify:
        recovered = await verify.get(AgentSession, child_id)
        assert recovered is not None
        assert recovered.active_turn_id != old_turn_id
        assert recovered.active_turn_id is not None
        assert recovered.collaboration_slot is not None


@pytest.mark.asyncio
async def test_startup_recovers_followup_after_post_publication_crash(
    db_session, db_engine, monkeypatch
) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child, terminal = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.RUNNING,
        slot=1,
    )
    terminal.accepts_steer = False
    await db_session.commit()
    root_id = str(root.id)
    child_id = str(child.id)
    terminal_id = str(terminal.id)
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )
    service = AgentCollaborationService(db_session)
    await service.followup_task(
        caller_session_id=root_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
        message="recover this followup",
    )
    terminal.status = AgentTurnStatus.COMPLETED
    terminal.accepts_steer = False
    await db_session.commit()

    async def crash_after_publication(**_kwargs):
        raise RuntimeError("simulated process crash")

    monkeypatch.setattr(service, "_schedule_pending_followup", crash_after_publication)
    with pytest.raises(RuntimeError, match="simulated process crash"):
        await service.publish_child_terminal(turn_id=terminal_id)

    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as restarted:
        summary = await AgentCoreService(restarted).recover_orphaned_turns()

    async with maker() as verify:
        collaboration = AgentCollaborationService(verify)
        turns = await collaboration.turns.list_for_session(child_id)
        followups = [turn for turn in turns if turn.input_text == "recover this followup"]
        messages = await collaboration.transcript.list_messages(child_id)
        queued = [
            message
            for message in messages
            if (message.message_metadata or {}).get("kind") == "agent_followup"
        ]
        recovered = await verify.get(AgentSession, child_id)
        assert summary["collaboration_followups"] == 1
        assert len(followups) == 1
        assert len(queued) == 1
        assert queued[0].status == AgentMessageStatus.SUPERSEDED
        assert recovered is not None
        assert recovered.active_turn_id == str(followups[0].id)
        assert recovered.collaboration_slot is not None


@pytest.mark.asyncio
async def test_concurrent_startup_recovery_schedules_pending_followup_once(
    db_session, db_engine, monkeypatch
) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child, terminal = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.RUNNING,
        slot=1,
    )
    terminal.accepts_steer = False
    await db_session.commit()
    root_id = str(root.id)
    child_id = str(child.id)
    terminal_id = str(terminal.id)
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )
    service = AgentCollaborationService(db_session)
    await service.followup_task(
        caller_session_id=root_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
        message="one recovered followup",
    )
    terminal.status = AgentTurnStatus.COMPLETED
    terminal.accepts_steer = False
    await db_session.commit()

    async def crash_after_publication(**_kwargs):
        raise RuntimeError("simulated process crash")

    monkeypatch.setattr(service, "_schedule_pending_followup", crash_after_publication)
    with pytest.raises(RuntimeError):
        await service.publish_child_terminal(turn_id=terminal_id)
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def recover() -> dict[str, int]:
        async with maker() as worker:
            return await AgentCoreService(worker).recover_orphaned_turns()

    await asyncio.gather(recover(), recover())

    async with maker() as verify:
        collaboration = AgentCollaborationService(verify)
        turns = await collaboration.turns.list_for_session(child_id)
        followups = [turn for turn in turns if turn.input_text == "one recovered followup"]
        messages = await collaboration.transcript.list_messages(child_id)
        queued = [
            message
            for message in messages
            if (message.message_metadata or {}).get("kind") == "agent_followup"
        ]
        recovered = await verify.get(AgentSession, child_id)
        assert len(followups) == 1
        assert len(queued) == 1
        assert queued[0].status == AgentMessageStatus.SUPERSEDED
        assert recovered is not None and recovered.collaboration_slot is not None


@pytest.mark.asyncio
async def test_undelivered_followup_steer_requeues_when_target_turn_terminates(
    db_session, monkeypatch
) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child, active = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.RUNNING,
        slot=1,
    )
    monkeypatch.setattr(
        "app.services.agent_core.service.cancel_turn_run",
        lambda *_: False,
    )
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )
    service = AgentCollaborationService(db_session)
    steered = await service.followup_task(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
        message="Do not lose this followup",
    )
    assert steered.delivery == "steer"

    await service.interrupt_agent(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
    )

    turns = await service.turns.list_for_session(str(child.id))
    followups = [turn for turn in turns if turn.input_text == "Do not lose this followup"]
    messages = await service.transcript.list_messages(str(child.id))
    collaboration_messages = [
        message
        for message in messages
        if (message.message_metadata or {}).get("collaboration_kind")
        == "agent_followup"
    ]
    assert active.status == AgentTurnStatus.CANCELLED
    assert len(followups) == 1
    assert len(collaboration_messages) == 1
    assert collaboration_messages[0].status == AgentMessageStatus.SUPERSEDED


@pytest.mark.asyncio
async def test_undelivered_inter_agent_steer_survives_for_next_turn(
    db_session, monkeypatch
) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child, _active = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.RUNNING,
        slot=1,
    )
    monkeypatch.setattr(
        "app.services.agent_core.service.cancel_turn_run",
        lambda *_: False,
    )
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )
    service = AgentCollaborationService(db_session)
    await service.send_message(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
        message="Persistent context",
    )
    await service.interrupt_agent(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
    )
    followup = await service.followup_task(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        target="/root/reader",
        message="Continue",
    )

    messages = await service.transcript.list_messages(str(child.id))
    persistent = [
        message
        for message in messages
        if (message.message_metadata or {}).get("collaboration_kind")
        == "inter_agent_message"
    ]
    assert followup.delivery == "followup"
    assert len(persistent) == 1
    assert str(persistent[0].turn_id) == followup.turn_id
    assert persistent[0].status == AgentMessageStatus.COMMITTED


@pytest.mark.asyncio
async def test_wait_notifier_wakes_multiple_waiters_and_cleans_up(
    db_session, db_engine
) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child, child_turn = await _create_child_with_turn(
        db_session,
        root=root,
        name="reader",
        status=AgentTurnStatus.RUNNING,
        slot=1,
    )
    child_id = str(child.id)
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def wait_once():
        async with maker() as worker:
            return await AgentCollaborationService(worker).wait_agent(
                caller_session_id=child_id,
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                timeout_ms=5_000,
            )

    first = asyncio.create_task(wait_once())
    second = asyncio.create_task(wait_once())
    loop = asyncio.get_running_loop()
    waiter_deadline = loop.time() + 1.0
    while _collaboration_waiter_count() != 2 and loop.time() < waiter_deadline:
        await asyncio.sleep(0.01)
    assert _collaboration_waiter_count() == 2
    async with maker() as sender:
        await AgentCoreService(sender).steer_turn(
            turn_id=str(child_turn.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text="Wake both",
        )
    results = await asyncio.gather(first, second)

    assert [result.updated_agents for result in results] == [
        ["/root/reader"],
        ["/root/reader"],
    ]
    assert _collaboration_waiter_count() == 0


@pytest.mark.asyncio
async def test_wait_notifier_cancellation_does_not_leak(db_session, db_engine) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def wait_forever():
        async with maker() as worker:
            return await AgentCollaborationService(worker).wait_agent(
                caller_session_id=str(root.id),
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                timeout_ms=5_000,
            )

    waiter = asyncio.create_task(wait_forever())
    for _ in range(50):
        if _collaboration_waiter_count() == 1:
            break
        await asyncio.sleep(0.01)
    assert _collaboration_waiter_count() == 1
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert _collaboration_waiter_count() == 0


@pytest.mark.asyncio
async def test_wait_timeout_uses_bounded_durable_checks(
    db_session, monkeypatch
) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    service = AgentCollaborationService(db_session)
    calls = 0
    original = service.ledger.event_repo.list_for_session

    async def counted(**kwargs):
        nonlocal calls
        calls += 1
        return await original(**kwargs)

    monkeypatch.setattr(service.ledger.event_repo, "list_for_session", counted)
    result = await service.wait_agent(
        caller_session_id=str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        timeout_ms=120,
    )

    assert result.timed_out is True
    assert calls <= 2


@pytest.mark.asyncio
async def test_wait_rechecks_durable_state_without_local_notification(
    db_session, db_engine
) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    root_id = str(root.id)
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def wait_once():
        async with maker() as worker:
            return await AgentCollaborationService(worker).wait_agent(
                caller_session_id=root_id,
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                timeout_ms=2_000,
            )

    waiter = asyncio.create_task(wait_once())
    for _ in range(50):
        if _collaboration_waiter_count() == 1:
            break
        await asyncio.sleep(0.01)
    async with maker() as external_process:
        await AgentCollaborationService(external_process).ledger.append(
            session_id=root_id,
            turn_id=None,
            type="agent.message.received",
            payload={"task_name": "/root/reader", "delivery": "queued"},
        )

    result = await waiter
    assert result.timed_out is False
    assert result.updated_agents == ["/root/reader"]
    assert _collaboration_waiter_count() == 0
