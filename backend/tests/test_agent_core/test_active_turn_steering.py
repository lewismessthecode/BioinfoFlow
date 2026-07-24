from __future__ import annotations

import pytest

from app.models.agent_core import AgentMessageStatus, AgentTurnStatus
from app.models.workspace import Workspace
from app.repositories.agent_core_repo import (
    AgentEventRepository,
    AgentMessageRepository,
)
from app.services.agent_core import AgentCoreService
from app.services.agent_core.events import AgentEventType
from app.utils.exceptions import ConflictError
from app.workspace import DEFAULT_WORKSPACE_ID


async def _running_turn(db_session):
    if await db_session.get(Workspace, DEFAULT_WORKSPACE_ID) is None:
        db_session.add(
            Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
        )
        await db_session.commit()

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        title="Steering test",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Start the task",
    )
    turn = await service.turn_repo.update_all(
        turn,
        status=AgentTurnStatus.RUNNING,
    )
    return service, turn


@pytest.mark.asyncio
async def test_running_turn_accepts_steer_until_terminal(db_session):
    service, turn = await _running_turn(db_session)

    assert turn.accepts_steer is True

    completed = await service.turn_repo.update_all(
        turn,
        status=AgentTurnStatus.COMPLETED,
        accepts_steer=False,
    )

    assert completed.accepts_steer is False


@pytest.mark.asyncio
async def test_steer_active_turn_persists_draft_user_message(db_session):
    service, turn = await _running_turn(db_session)

    result = await service.steer_turn(
        turn_id=str(turn.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Use the project virtualenv instead.",
        input_parts=[
            {"type": "text", "text": "Use the project virtualenv instead."}
        ],
        metadata={"input_display": {"inline_parts": []}},
    )

    assert result.delivery == "pending"
    assert str(result.turn_id) == str(turn.id)

    messages = await AgentMessageRepository(db_session).list_for_session(
        str(turn.session_id)
    )
    steering_message = next(
        message
        for message in messages
        if (message.message_metadata or {}).get("kind") == "steer"
    )
    assert steering_message.role == "user"
    assert steering_message.status == AgentMessageStatus.DRAFT
    assert steering_message.ordering_index == 0
    assert steering_message.message_metadata == {
        "kind": "steer",
        "steer_id": str(result.steer_id),
        "input_display": {"inline_parts": []},
    }

    events = await AgentEventRepository(db_session).list_for_session(
        session_id=str(turn.session_id)
    )
    received = events[-1]
    assert received.type == AgentEventType.TURN_STEER_RECEIVED
    assert received.payload["steer_id"] == str(result.steer_id)
    assert received.payload["input_text"] == "Use the project virtualenv instead."
    assert received.payload["delivery"] == "pending"


@pytest.mark.asyncio
async def test_steer_rejects_sealed_turn(db_session):
    service, turn = await _running_turn(db_session)
    await service.turn_repo.update_all(turn, accepts_steer=False)

    with pytest.raises(ConflictError, match="no longer accepts guidance"):
        await service.steer_turn(
            turn_id=str(turn.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text="Too late",
        )


@pytest.mark.asyncio
async def test_steer_active_turn_api_returns_pending(async_client, db_session):
    _, turn = await _running_turn(db_session)

    response = await async_client.post(
        f"/api/v1/agent/turns/{turn.id}/steer",
        json={"input_text": "Keep the current process running."},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "steer_id": response.json()["data"]["steer_id"],
        "turn_id": str(turn.id),
        "delivery": "pending",
    }


@pytest.mark.asyncio
async def test_steer_sealed_turn_api_returns_conflict(async_client, db_session):
    service, turn = await _running_turn(db_session)
    await service.turn_repo.update_all(turn, accepts_steer=False)

    response = await async_client.post(
        f"/api/v1/agent/turns/{turn.id}/steer",
        json={"input_text": "Too late"},
    )

    assert response.status_code == 409
