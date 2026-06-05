from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.repositories.agent_core_repo import AgentActionRepository
from app.config import settings
from app.models.project import Project
from app.models.workspace import Workspace
from app.services.agent_core import AgentCoreService
from app.services.agent_core.tools import (
    AgentToolContext,
    AgentToolDispatcher,
    build_default_tool_registry,
)
from app.workspace import DEFAULT_WORKSPACE_ID


async def _shell_context(db_session) -> tuple[AgentToolDispatcher, AgentToolContext, Path]:
    workspace_root = Path(settings.bioinfoflow_home)
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    project = Project(
        name="Shell Project",
        description="Controlled execution",
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
        title="Shell",
    )
    turn = await core.create_turn(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Run a controlled command.",
    )
    return (
        AgentToolDispatcher(db_session, build_default_tool_registry()),
        AgentToolContext(
            db=db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            session_id=str(session.id),
            turn_id=str(turn.id),
        ),
        workspace_root,
    )


@pytest.mark.asyncio
async def test_shell_tool_waits_for_approval_in_guarded_auto(db_session):
    dispatcher, context, workspace_root = await _shell_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="execution.shell",
        input={
            "command": [sys.executable, "-c", "print('should not run')"],
            "cwd": str(workspace_root),
        },
        context=context,
        permission_mode="guarded_auto",
    )

    assert result.status == "waiting_decision"
    assert result.permission_decision["decision"] == "ask"
    assert result.result is None


@pytest.mark.asyncio
async def test_shell_tool_executes_safe_argv_in_bypass_mode(db_session):
    dispatcher, context, workspace_root = await _shell_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="execution.shell",
        input={
            "command": [sys.executable, "-c", "print('agent-core-ok')"],
            "cwd": str(workspace_root),
        },
        context=context,
        permission_mode="bypass",
    )

    assert result.status == "completed"
    assert result.result["exit_code"] == 0
    assert result.result["stdout"].strip() == "agent-core-ok"


@pytest.mark.asyncio
async def test_shell_tool_blocks_dangerous_commands_even_in_bypass(db_session):
    dispatcher, context, workspace_root = await _shell_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="execution.shell",
        input={"command": ["rm", "-rf", "anything"], "cwd": str(workspace_root)},
        context=context,
        permission_mode="bypass",
    )

    assert result.status == "failed"
    assert result.error["type"] == "PermissionDeniedError"
    assert "blocked" in result.error["message"]


@pytest.mark.asyncio
async def test_shell_tool_resumes_after_approval_and_registers_output_artifact(db_session):
    dispatcher, context, workspace_root = await _shell_context(db_session)

    pending = await dispatcher.dispatch(
        tool_name="execution.shell",
        input={
            "command": [sys.executable, "-c", "print('before-approval')"],
            "cwd": str(workspace_root),
        },
        context=context,
        permission_mode="guarded_auto",
    )
    assert pending.status == "waiting_decision"

    resumed = await AgentCoreService(db_session).decide_action(
        action_id=pending.action_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
        note="approved for test",
    )

    assert resumed.status == "completed"
    assert resumed.result["exit_code"] == 0
    assert resumed.result["stdout"].strip() == "before-approval"

    artifacts = await AgentCoreService(db_session).list_artifacts_for_turn(
        turn_id=context.turn_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert len(artifacts) == 1
    assert artifacts[0].type == "log_summary"
    assert str(artifacts[0].action_id) == pending.action_id
    assert artifacts[0].payload["stdout"].strip() == "before-approval"

    events = await AgentCoreService(db_session).list_events_for_turn(
        turn_id=context.turn_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    event_types = [event.type for event in events]
    assert "action.decision_recorded" in event_types
    assert "action.started" in event_types
    assert "artifact.created" in event_types
    assert "action.completed" in event_types


@pytest.mark.asyncio
async def test_shell_tool_uses_modified_input_when_approval_changes_command(db_session):
    dispatcher, context, workspace_root = await _shell_context(db_session)

    pending = await dispatcher.dispatch(
        tool_name="execution.shell",
        input={
            "command": [sys.executable, "-c", "print('old-command')"],
            "cwd": str(workspace_root),
        },
        context=context,
        permission_mode="guarded_auto",
    )

    resumed = await AgentCoreService(db_session).decide_action(
        action_id=pending.action_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="modify",
        note="use safer command",
        modified_input={
            "command": [sys.executable, "-c", "print('new-command')"],
            "cwd": str(workspace_root),
        },
    )

    assert resumed.status == "completed"
    assert resumed.result["stdout"].strip() == "new-command"
    action = await AgentActionRepository(db_session).get(pending.action_id)
    assert action.input["command"][-1] == "print('new-command')"
