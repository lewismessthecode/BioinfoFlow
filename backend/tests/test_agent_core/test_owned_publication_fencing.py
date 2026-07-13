from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agent_core import (
    AgentActionStatus,
    AgentSession,
    AgentTurn,
    AgentTurnStatus,
)
from app.models.workspace import Workspace
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentArtifactRepository,
    AgentEventRepository,
    AgentMessageRepository,
    AgentTurnRepository,
)
from app.services.agent_core.actions import AgentActionService
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.ownership import TurnOwnershipLostError
from app.services.agent_core.transcript import AgentTranscriptStore, text_part
from app.workspace import DEFAULT_WORKSPACE_ID


async def _owned_turn(db_session, *, owner_token: str = "owner-a"):
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    session = AgentSession(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        title="Owned publication fencing",
    )
    db_session.add_all([workspace, session])
    await db_session.commit()
    await db_session.refresh(session)
    now = datetime.now(timezone.utc)
    turn = AgentTurn(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Fence all owned publications.",
        status=AgentTurnStatus.RUNNING,
        owner_token=owner_token,
        claimed_at=now,
        lease_until=now + timedelta(minutes=5),
    )
    db_session.add(turn)
    await db_session.commit()
    await db_session.refresh(turn)
    return session, turn


async def _replace_owner(session_factory, turn_id: str, owner_token: str) -> None:
    async with session_factory() as replacement_session:
        repo = AgentTurnRepository(replacement_session)
        turn = await repo.get(turn_id)
        assert turn is not None
        await repo.update_all(
            turn,
            owner_token=owner_token,
            claimed_at=datetime.now(timezone.utc),
            lease_until=datetime.now(timezone.utc) + timedelta(minutes=5),
        )


async def _assert_dirty_workspace_rejected(
    session_factory,
    operation: Callable[[AsyncSession], Awaitable[Any]],
) -> None:
    async with session_factory() as owned_session:
        workspace = await owned_session.get(Workspace, DEFAULT_WORKSPACE_ID)
        assert workspace is not None
        workspace.name = "must not be published"
        with pytest.raises(
            RuntimeError,
            match="Owner-conditioned publication requires a clean database session",
        ):
            await operation(owned_session)
        await owned_session.rollback()

    async with session_factory() as inspector:
        workspace = await inspector.get(Workspace, DEFAULT_WORKSPACE_ID)
        assert workspace is not None
        assert workspace.name == "Team"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entrypoint",
    [
        "transcript_explicit",
        "transcript_bound",
        "event_explicit",
        "event_bound",
        "action",
    ],
)
async def test_owned_service_entrypoints_reject_dirty_session_before_autoflush(
    db_engine,
    db_session,
    entrypoint: str,
) -> None:
    session, turn = await _owned_turn(db_session)
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async def operation(owned_session: AsyncSession) -> None:
        if entrypoint.startswith("transcript"):
            transcript = AgentTranscriptStore(
                owned_session,
                owned_turn_id=(
                    str(turn.id) if entrypoint == "transcript_bound" else None
                ),
                expected_owner_token=(
                    "owner-a" if entrypoint == "transcript_bound" else None
                ),
            )
            await transcript.append_parts(
                session_id=str(session.id),
                turn_id=str(turn.id),
                role="assistant",
                parts=[text_part("must not publish")],
                expected_owner_token=(
                    "owner-a" if entrypoint == "transcript_explicit" else None
                ),
            )
        elif entrypoint.startswith("event"):
            ledger = AgentEventLedger(
                owned_session,
                owned_turn_id=str(turn.id) if entrypoint == "event_bound" else None,
                expected_owner_token=(
                    "owner-a" if entrypoint == "event_bound" else None
                ),
            )
            await ledger.append(
                session_id=str(session.id),
                turn_id=str(turn.id),
                type=AgentEventType.TURN_STARTED,
                payload={},
                expected_owner_token=(
                    "owner-a" if entrypoint == "event_explicit" else None
                ),
            )
        else:
            await AgentActionService(owned_session).request_action(
                turn_id=str(turn.id),
                kind="tool",
                name="must_not_publish",
                input={},
                permission_mode="bypass",
                expected_owner_token="owner-a",
            )

    await _assert_dirty_workspace_rejected(session_factory, operation)

    async with session_factory() as inspector:
        assert (
            await AgentMessageRepository(inspector).list_for_session(str(session.id))
            == []
        )
        assert (
            await AgentEventRepository(inspector).list_for_turn(turn_id=str(turn.id))
            == []
        )
        assert await AgentActionRepository(inspector).list_for_turn(str(turn.id)) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", ["compact", "clear_turn", "clear_session"])
async def test_owned_transcript_mutations_reject_dirty_session_before_autoflush(
    db_engine,
    db_session,
    entrypoint: str,
) -> None:
    session, turn = await _owned_turn(db_session)
    transcript = AgentTranscriptStore(db_session)
    for index in range(4):
        await transcript.append_parts(
            session_id=str(session.id),
            turn_id=str(turn.id),
            role="assistant",
            parts=[text_part(f"message-{index}")],
            metadata=(
                {"continuation": {"response_id": "resp-old"}}
                if index == 3
                else None
            ),
        )
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async def operation(owned_session: AsyncSession) -> None:
        owned_transcript = AgentTranscriptStore(
            owned_session,
            owned_turn_id=str(turn.id),
            expected_owner_token="owner-a",
        )
        if entrypoint == "compact":
            await owned_transcript.compact_session(
                session_id=str(session.id),
                turn_id=str(turn.id),
                threshold_chars=1,
                preserve_recent_messages=1,
            )
        elif entrypoint == "clear_turn":
            await owned_transcript.clear_turn_metadata(
                turn_id=str(turn.id),
                metadata_key="continuation",
            )
        else:
            await owned_transcript.clear_session_metadata(
                session_id=str(session.id),
                metadata_key="continuation",
            )

    await _assert_dirty_workspace_rejected(session_factory, operation)

    async with session_factory() as inspector:
        messages = await AgentMessageRepository(inspector).list_for_session(
            str(session.id)
        )
        assert [message.ordering_index for message in messages] == [1, 2, 3, 4]
        assert all(message.status == "committed" for message in messages)
        assert (messages[-1].message_metadata or {})["continuation"] == {
            "response_id": "resp-old"
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["turn", "session"])
async def test_owned_metadata_replacement_repository_rejects_dirty_session_before_read(
    db_engine,
    db_session,
    scope: str,
) -> None:
    session, turn = await _owned_turn(db_session)
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async def operation(owned_session: AsyncSession) -> None:
        data = {
            "session_id": str(session.id),
            "turn_id": str(turn.id),
            "role": "assistant",
            "content_parts": [text_part("must not replace")],
            "message_metadata": {"continuation": {}},
            "status": "committed",
            "ordering_index": 1,
        }
        messages = AgentMessageRepository(owned_session)
        if scope == "turn":
            await messages.create_replacing_turn_metadata(
                metadata_key="continuation",
                expected_owner_token="owner-a",
                **data,
            )
        else:
            await messages.create_replacing_session_metadata(
                metadata_key="continuation",
                expected_owner_token="owner-a",
                **data,
            )

    await _assert_dirty_workspace_rejected(session_factory, operation)

    async with session_factory() as inspector:
        assert (
            await AgentMessageRepository(inspector).list_for_session(str(session.id))
            == []
        )


@pytest.mark.asyncio
async def test_non_owned_transcript_append_keeps_existing_dirty_session_behavior(
    db_engine,
    db_session,
) -> None:
    session, turn = await _owned_turn(db_session)
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with session_factory() as ordinary_session:
        workspace = await ordinary_session.get(Workspace, DEFAULT_WORKSPACE_ID)
        assert workspace is not None
        workspace.name = "ordinary publication"
        message = await AgentTranscriptStore(ordinary_session).append_parts(
            session_id=str(session.id),
            turn_id=str(turn.id),
            role="assistant",
            parts=[text_part("ordinary append")],
        )

    async with session_factory() as inspector:
        workspace = await inspector.get(Workspace, DEFAULT_WORKSPACE_ID)
        assert workspace is not None
        assert workspace.name == "ordinary publication"
        messages = await AgentMessageRepository(inspector).list_for_session(
            str(session.id)
        )

    assert str(messages[0].id) == str(message.id)


@pytest.mark.asyncio
async def test_stale_owner_cannot_publish_transcript_events_or_actions_after_preflight(
    db_engine,
    db_session,
) -> None:
    session, turn = await _owned_turn(db_session)
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with session_factory() as stale_session:
        stale_turns = AgentTurnRepository(stale_session)
        assert await stale_turns.is_owned(str(turn.id), owner_token="owner-a")

        await _replace_owner(session_factory, str(turn.id), "owner-b")

        transcript = AgentTranscriptStore(stale_session)
        with pytest.raises(TurnOwnershipLostError):
            await transcript.append_parts(
                session_id=str(session.id),
                turn_id=str(turn.id),
                role="assistant",
                parts=[text_part("stale assistant")],
                expected_owner_token="owner-a",
            )
        with pytest.raises(TurnOwnershipLostError):
            await transcript.append_parts(
                session_id=str(session.id),
                turn_id=str(turn.id),
                role="tool",
                parts=[text_part("stale tool result")],
                expected_owner_token="owner-a",
            )
        with pytest.raises(TurnOwnershipLostError):
            await AgentEventLedger(stale_session).append(
                session_id=str(session.id),
                turn_id=str(turn.id),
                type=AgentEventType.TURN_STARTED,
                payload={},
                expected_owner_token="owner-a",
            )
        with pytest.raises(TurnOwnershipLostError):
            await AgentActionService(stale_session).request_action(
                turn_id=str(turn.id),
                kind="tool",
                name="stale_tool",
                input={},
                permission_mode="bypass",
                expected_owner_token="owner-a",
            )

    async with session_factory() as inspector:
        assert (
            await AgentMessageRepository(inspector).list_for_session(str(session.id))
            == []
        )
        assert (
            await AgentEventRepository(inspector).list_for_turn(turn_id=str(turn.id))
            == []
        )
        assert await AgentActionRepository(inspector).list_for_turn(str(turn.id)) == []

    async with session_factory() as replacement_worker:
        transcript = AgentTranscriptStore(replacement_worker)
        assistant = await transcript.append_parts(
            session_id=str(session.id),
            turn_id=str(turn.id),
            role="assistant",
            parts=[text_part("replacement assistant")],
            expected_owner_token="owner-b",
        )
        tool = await transcript.append_parts(
            session_id=str(session.id),
            turn_id=str(turn.id),
            role="tool",
            parts=[text_part("replacement tool result")],
            expected_owner_token="owner-b",
        )
        event = await AgentEventLedger(replacement_worker).append(
            session_id=str(session.id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_STARTED,
            payload={"replacement": True},
            expected_owner_token="owner-b",
        )
        action = await AgentActionService(replacement_worker).request_action(
            turn_id=str(turn.id),
            kind="tool",
            name="replacement_tool",
            input={},
            permission_mode="bypass",
            expected_owner_token="owner-b",
        )

    assert assistant.ordering_index == 1
    assert tool.ordering_index == 2
    assert event.seq == 1
    assert action.status == AgentActionStatus.REQUESTED


@pytest.mark.asyncio
async def test_stale_owner_cannot_finish_action_or_register_artifact_after_preflight(
    db_engine,
    db_session,
) -> None:
    session, turn = await _owned_turn(db_session)
    action = await AgentActionService(db_session).request_action(
        turn_id=str(turn.id),
        kind="tool",
        name="write_file",
        input={"path": "result.txt"},
        permission_mode="bypass",
        expected_owner_token="owner-a",
    )
    action = await AgentActionRepository(db_session).update_all(
        action,
        requires_resume=True,
    )
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with session_factory() as stale_session:
        stale_turns = AgentTurnRepository(stale_session)
        stale_actions = AgentActionRepository(stale_session)
        stale_artifacts = AgentArtifactRepository(stale_session)
        stale_action = await stale_actions.get(str(action.id))
        assert stale_action is not None
        assert await stale_turns.is_owned(str(turn.id), owner_token="owner-a")

        await _replace_owner(session_factory, str(turn.id), "owner-b")

        claimed_action, claimed = await stale_actions.claim_requested_resume(
            str(action.id),
            started_at=datetime.now(timezone.utc),
            expected_owner_token="owner-a",
        )
        assert claimed is False
        assert claimed_action is not None
        assert claimed_action.status == AgentActionStatus.REQUESTED
        assert claimed_action.requires_resume is True

        updated, owned = await stale_actions.update_all_owned(
            stale_action,
            expected_owner_token="owner-a",
            status=AgentActionStatus.COMPLETED,
            result={"path": "stale.txt"},
            completed_at=datetime.now(timezone.utc),
        )
        assert updated is None
        assert owned is False

        artifact, owned = await stale_artifacts.create_for_owned_turn(
            turn_id=str(turn.id),
            expected_owner_token="owner-a",
            session_id=str(session.id),
            action_id=str(action.id),
            type="file",
            title="stale.txt",
            payload={"path": "stale.txt"},
        )
        assert artifact is None
        assert owned is False

        with pytest.raises(TurnOwnershipLostError):
            await AgentEventLedger(stale_session).append(
                session_id=str(session.id),
                turn_id=str(turn.id),
                type=AgentEventType.ARTIFACT_CREATED,
                payload={"title": "stale.txt"},
                expected_owner_token="owner-a",
            )

    async with session_factory() as inspector:
        persisted_action = await AgentActionRepository(inspector).get(str(action.id))
        assert persisted_action is not None
        assert persisted_action.status == AgentActionStatus.REQUESTED
        assert persisted_action.result is None
        assert persisted_action.requires_resume is True
        assert (
            await AgentArtifactRepository(inspector).list_for_turn(str(turn.id)) == []
        )
        events = await AgentEventRepository(inspector).list_for_turn(
            turn_id=str(turn.id)
        )
        assert all(event.payload.get("title") != "stale.txt" for event in events)

    async with session_factory() as replacement_worker:
        replacement_actions = AgentActionRepository(replacement_worker)
        replacement_action = await replacement_actions.get(str(action.id))
        assert replacement_action is not None
        replacement_action, owned = await replacement_actions.update_all_owned(
            replacement_action,
            expected_owner_token="owner-b",
            status=AgentActionStatus.COMPLETED,
            result={"path": "replacement.txt"},
            completed_at=datetime.now(timezone.utc),
            requires_resume=False,
        )
        assert owned is True
        assert replacement_action is not None
        artifact, owned = await AgentArtifactRepository(
            replacement_worker
        ).create_for_owned_turn(
            turn_id=str(turn.id),
            expected_owner_token="owner-b",
            session_id=str(session.id),
            action_id=str(action.id),
            type="file",
            title="replacement.txt",
            payload={"path": "replacement.txt"},
        )
        assert owned is True
        assert artifact is not None
        artifact_event = await AgentEventLedger(replacement_worker).append(
            session_id=str(session.id),
            turn_id=str(turn.id),
            type=AgentEventType.ARTIFACT_CREATED,
            payload={"artifact_id": str(artifact.id)},
            expected_owner_token="owner-b",
        )

    assert replacement_action.status == AgentActionStatus.COMPLETED
    assert artifact.title == "replacement.txt"
    assert artifact_event.seq == 3


@pytest.mark.asyncio
async def test_stale_owner_cannot_clear_continuation_or_compact_transcript(
    db_engine,
    db_session,
) -> None:
    session, turn = await _owned_turn(db_session)
    transcript = AgentTranscriptStore(db_session)
    for index in range(4):
        await transcript.append_parts(
            session_id=str(session.id),
            turn_id=str(turn.id),
            role="assistant",
            parts=[text_part(f"message-{index}")],
            metadata=(
                {"_responses_continuation": {"response_id": "resp-old"}}
                if index == 3
                else None
            ),
        )
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with session_factory() as stale_session:
        assert await AgentTurnRepository(stale_session).is_owned(
            str(turn.id),
            owner_token="owner-a",
        )
        await _replace_owner(session_factory, str(turn.id), "owner-b")
        stale_transcript = AgentTranscriptStore(
            stale_session,
            owned_turn_id=str(turn.id),
            expected_owner_token="owner-a",
        )
        with pytest.raises(TurnOwnershipLostError):
            await stale_transcript.clear_session_metadata(
                session_id=str(session.id),
                metadata_key="_responses_continuation",
            )
        with pytest.raises(TurnOwnershipLostError):
            await stale_transcript.compact_session(
                session_id=str(session.id),
                turn_id=str(turn.id),
                threshold_chars=1,
                preserve_recent_messages=1,
            )

    async with session_factory() as inspector:
        messages = await AgentMessageRepository(inspector).list_for_session(
            str(session.id)
        )

    assert [message.ordering_index for message in messages] == [1, 2, 3, 4]
    assert all(message.status == "committed" for message in messages)
    assert all(
        (message.message_metadata or {}).get("kind") != "compaction_summary"
        for message in messages
    )
    assert (messages[-1].message_metadata or {})["_responses_continuation"] == {
        "response_id": "resp-old"
    }
