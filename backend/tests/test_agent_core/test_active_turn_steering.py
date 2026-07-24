from __future__ import annotations

import pytest

from app.models.agent_core import AgentTurnStatus
from app.models.workspace import Workspace
from app.services.agent_core import AgentCoreService
from app.workspace import DEFAULT_WORKSPACE_ID


async def _running_turn(db_session):
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
