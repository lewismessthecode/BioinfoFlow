from __future__ import annotations

import pytest

from app.models.project import Project
from app.models.workspace import Workspace
from app.services.agent_core import AgentCoreService
from app.workspace import DEFAULT_WORKSPACE_ID


@pytest.mark.asyncio
async def test_agent_core_no_tool_runtime_writes_ordered_events(db_session):
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    project = Project(
        name="Kernel Project",
        description="AgentCore kernel test",
        user_id="dev",
        created_by_user_id="dev",
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    db_session.add_all([workspace, project])
    await db_session.commit()
    await db_session.refresh(project)

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=str(project.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        title="Kernel",
    )
    turn = await service.create_turn(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Summarize this run.",
    )

    assert turn.status == "completed"
    assert turn.final_text

    events = await service.list_events_for_turn(
        turn_id=str(turn.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert [event.seq for event in events] == [1, 2, 3, 4, 5]
    assert [event.type for event in events] == [
        "turn.created",
        "turn.started",
        "assistant.thinking.summary",
        "assistant.text.completed",
        "turn.completed",
    ]
