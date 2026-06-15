from __future__ import annotations

import pytest

from app.models.workspace import Workspace
from app.services.agent_core import AgentCoreService
from app.services.agent_core.tools import (
    AgentToolContext,
    AgentToolDispatcher,
    build_default_tool_registry,
)
from app.workspace import DEFAULT_WORKSPACE_ID


async def _context(db_session):
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()
    core = AgentCoreService(db_session)
    session = await core.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev", title="Todos"
    )
    turn = await core.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Track tasks.",
    )
    dispatcher = AgentToolDispatcher(db_session, build_default_tool_registry())
    context = AgentToolContext(
        db=db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        session_id=str(session.id),
        turn_id=str(turn.id),
    )
    return core, dispatcher, context, str(turn.id)


@pytest.mark.asyncio
async def test_todo_write_auto_runs_and_creates_todo_list_artifact(db_session):
    core, dispatcher, context, turn_id = await _context(db_session)

    todos = [
        {"content": "Read the code", "status": "completed", "activeForm": "Reading the code"},
        {"content": "Make the change", "status": "in_progress", "activeForm": "Making the change"},
        {"content": "Run tests", "status": "pending", "activeForm": "Running tests"},
    ]
    result = await dispatcher.dispatch(
        tool_name="todo_write",
        input={"todos": todos},
        context=context,
        permission_mode="guarded_auto",
    )
    assert result.status == "completed"
    assert result.result["todos"] == todos

    artifacts = await core.list_artifacts_for_turn(
        turn_id=turn_id, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    assert len(artifacts) == 1
    assert artifacts[0].type == "todo_list"
    assert artifacts[0].payload["todos"] == todos
    assert artifacts[0].summary == "1/3 completed"


@pytest.mark.asyncio
async def test_todo_write_rejects_multiple_in_progress(db_session):
    _core, dispatcher, context, _turn_id = await _context(db_session)
    result = await dispatcher.dispatch(
        tool_name="todo_write",
        input={
            "todos": [
                {"content": "A", "status": "in_progress"},
                {"content": "B", "status": "in_progress"},
            ]
        },
        context=context,
        permission_mode="guarded_auto",
    )
    assert result.status == "failed"
    assert result.error["type"] == "BadRequestError"
