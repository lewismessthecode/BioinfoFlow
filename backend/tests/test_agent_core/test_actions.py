from __future__ import annotations

import pytest

from app.models.project import Project
from app.models.workspace import Workspace
from app.services.agent_core import AgentActionService, AgentCoreService
from app.workspace import DEFAULT_WORKSPACE_ID


async def _create_completed_turn(db_session) -> tuple[AgentCoreService, str]:
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    project = Project(
        name="Action Project",
        description="AgentCore action test",
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
        title="Actions",
    )
    turn = await core.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Prepare an action.",
    )
    return core, str(turn.id)


@pytest.mark.asyncio
async def test_action_service_allows_low_risk_actions(db_session):
    core, turn_id = await _create_completed_turn(db_session)
    action = await AgentActionService(db_session).request_action(
        turn_id=turn_id,
        kind="platform",
        name="list_runs",
        input={"project_id": "project-1"},
        requested_risk="act_low",
        permission_mode="guarded_auto",
        automation_mode="assisted",
    )

    assert action.status == "requested"
    assert action.permission_decision["decision"] == "allow"

    events = await core.list_events_for_turn(
        turn_id=turn_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert "action.requested" in [event.type for event in events]
    assert "action.risk_assessed" in [event.type for event in events]


@pytest.mark.asyncio
async def test_action_service_waits_for_high_risk_decision(db_session):
    core, turn_id = await _create_completed_turn(db_session)
    action = await AgentActionService(db_session).request_action(
        turn_id=turn_id,
        kind="run",
        name="submit_run",
        input={"run_id": "run-1"},
        requested_risk="act_high",
        permission_mode="guarded_auto",
        automation_mode="assisted",
    )

    assert action.status == "waiting_decision"
    assert action.permission_decision["decision"] == "ask"

    events = await core.list_events_for_turn(
        turn_id=turn_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert "action.waiting_decision" in [event.type for event in events]


@pytest.mark.asyncio
async def test_action_service_rejects_advise_only_side_effects(db_session):
    _core, turn_id = await _create_completed_turn(db_session)
    action = await AgentActionService(db_session).request_action(
        turn_id=turn_id,
        kind="workflow",
        name="register_workflow",
        input={"workflow_id": "workflow-1"},
        requested_risk="act_low",
        permission_mode="bypass",
        automation_mode="advise_only",
    )

    assert action.status == "rejected"
    assert action.permission_decision["decision"] == "deny"
