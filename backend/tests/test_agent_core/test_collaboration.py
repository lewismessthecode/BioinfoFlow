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
    AgentSession,
    AgentSessionStatus,
    AgentTurn,
    AgentTurnStatus,
)
from app.models.llm import LlmModel, LlmProvider, LlmProviderCredential
from app.models.workspace import Workspace
from app.repositories.agent_core_repo import AgentSessionRepository
from app.services.agent_core.collaboration.context_fork import (
    InvalidForkTurnsError,
    fork_agent_context,
)
from app.services.agent_core.collaboration.model_preflight import AgentModelPreflight
from app.services.agent_core.collaboration.contracts import AgentModelChoice
from app.services.agent_core.collaboration.service import AgentCollaborationService
from app.services.llm.credentials import encrypt_secret
from app.services.llm.probe import LlmProviderProbeResult
from app.config import settings
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
            "reasoning_effort": "high",
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
    assert result.effective_model_id == str(model.id)
    assert result.reasoning_effort == "low"
    assert result.fallback is False
    assert [call["model_id"] for call in calls] == ["cheap-model"]


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
    await db_session.commit()
    calls: list[str] = []

    async def forbidden_probe(_self, **kwargs):
        calls.append(kwargs["model_id"])
        raise AssertionError("invisible or inactive models must not be probed")

    monkeypatch.setattr(
        "app.services.llm.catalog.LlmProviderProbe.probe",
        forbidden_probe,
    )

    for model in models:
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
        parent_session_id=str(root.id),
        parent_turn_id=str(turn.id),
        task_name="reader",
        message="work",
        fork_turns="none",
        model="cheap-model",
    )

    assert result.requested_model == "cheap-model"
    assert result.effective_model == "parent-model"
    assert result.model_fallback is True
    assert result.fallback_reason == "requested_model_unavailable"


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
