from __future__ import annotations

import pytest

from app.models.project import Project
from app.models.workspace import Workspace
from app.services.agent_core import AgentCoreService
from app.services.agent_core.tools import (
    AgentToolContext,
    AgentToolDispatcher,
    build_default_tool_registry,
)
from app.workspace import DEFAULT_WORKSPACE_ID


@pytest.mark.asyncio
async def test_projects_list_tool_runs_through_action_ledger(db_session):
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    project = Project(
        name="Tool Project",
        description="Visible to the project listing tool",
        user_id="dev",
        created_by_user_id="dev",
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    db_session.add_all([workspace, project])
    await db_session.commit()
    await db_session.refresh(project)

    core = AgentCoreService(db_session)
    session = await core.create_session(
        project_id=str(project.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        title="Tools",
    )
    turn = await core.create_turn(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="List projects.",
    )

    dispatcher = AgentToolDispatcher(db_session, build_default_tool_registry())
    result = await dispatcher.dispatch(
        tool_name="projects.list",
        input={"search": "Tool", "limit": 10},
        context=AgentToolContext(
            db=db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            session_id=str(session.id),
            turn_id=str(turn.id),
        ),
    )

    assert result.status == "completed"
    assert result.permission_decision["decision"] == "allow"
    assert result.result["projects"][0]["name"] == "Tool Project"

    events = await core.list_events_for_turn(
        turn_id=str(turn.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    event_types = [event.type for event in events]
    assert "action.requested" in event_types
    assert "action.completed" in event_types
