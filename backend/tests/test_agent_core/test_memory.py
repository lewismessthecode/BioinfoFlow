from __future__ import annotations

import pytest

from app.models.project import Project
from app.models.workspace import Workspace
from app.services.agent_core import AgentCoreService
from app.services.agent_core.memory import AgentMemoryService
from app.services.agent_core.tools import (
    AgentToolContext,
    AgentToolDispatcher,
    build_default_tool_registry,
)
from app.workspace import DEFAULT_WORKSPACE_ID


async def _memory_context(db_session):
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    project = Project(
        name="Memory Project",
        description="Structured memory tests",
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
        title="Memory",
    )
    turn = await core.create_turn(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Remember validated conventions.",
    )
    return core, project, session, turn


@pytest.mark.asyncio
async def test_memory_service_records_proposal_accept_and_reject_events(db_session):
    core, project, session, turn = await _memory_context(db_session)
    service = AgentMemoryService(db_session)

    memory = await service.propose_memory(
        workspace_id=DEFAULT_WORKSPACE_ID,
        project_id=str(project.id),
        session_id=str(session.id),
        turn_id=str(turn.id),
        scope="project",
        type="project_convention",
        content={"reference_genome": "hg38"},
        source={"kind": "agent_turn", "turn_id": str(turn.id)},
        confidence=90,
    )
    assert memory.status == "proposed"

    accepted = await service.update_memory_status(
        memory_id=str(memory.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        status="accepted",
        note="confirmed by project owner",
    )
    assert accepted.status == "accepted"

    rejected = await service.propose_memory(
        workspace_id=DEFAULT_WORKSPACE_ID,
        project_id=str(project.id),
        session_id=str(session.id),
        turn_id=str(turn.id),
        scope="workflow",
        type="run_lesson",
        content={"failure": "obsolete"},
    )
    rejected = await service.update_memory_status(
        memory_id=str(rejected.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        status="rejected",
        note="not reusable",
    )
    assert rejected.status == "rejected"

    memories = await service.list_memories(
        workspace_id=DEFAULT_WORKSPACE_ID,
        project_id=str(project.id),
        status="accepted",
    )
    assert [item.content for item in memories] == [{"reference_genome": "hg38"}]

    events = await core.list_events_for_turn(
        turn_id=str(turn.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    event_types = [event.type for event in events]
    assert "memory.proposed" in event_types
    assert "memory.written" in event_types
    assert "memory.rejected" in event_types


@pytest.mark.asyncio
async def test_memory_tools_run_through_action_ledger(db_session):
    core, project, session, turn = await _memory_context(db_session)
    dispatcher = AgentToolDispatcher(db_session, build_default_tool_registry())
    context = AgentToolContext(
        db=db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        session_id=str(session.id),
        turn_id=str(turn.id),
    )

    proposed = await dispatcher.dispatch(
        tool_name="memory.propose",
        input={
            "project_id": str(project.id),
            "scope": "project",
            "type": "validated_preset",
            "content": {"workflow": "rna-seq", "genome": "hg38"},
            "confidence": 80,
        },
        context=context,
    )
    assert proposed.status == "completed"
    assert proposed.permission_decision["decision"] == "allow"
    memory_id = proposed.result["memory"]["id"]

    listed = await dispatcher.dispatch(
        tool_name="memory.list",
        input={"project_id": str(project.id), "status": "proposed"},
        context=context,
    )
    assert listed.status == "completed"
    assert [item["id"] for item in listed.result["memories"]] == [memory_id]

    events = await core.list_events_for_turn(
        turn_id=str(turn.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    event_types = [event.type for event in events]
    assert "action.completed" in event_types
    assert "memory.proposed" in event_types
    assert "memory.read" in event_types
