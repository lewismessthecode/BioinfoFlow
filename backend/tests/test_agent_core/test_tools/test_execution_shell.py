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
from app.services.agent_core.tools.execution import ExecuteShellTool
from app.workspace import DEFAULT_WORKSPACE_ID


def test_bash_assess_risk_escalates_out_of_root_paths():
    tool = ExecuteShellTool()
    # Safe inspection inside the sandbox auto-runs.
    assert tool.assess_risk({"command": "cat README.md"}) == "act_low"
    # Reaching an absolute path outside the allowed roots must ask, even though
    # `cat`/`find` are read-only executables.
    assert tool.assess_risk({"command": "cat /etc/passwd"}) == "act_high"
    assert tool.assess_risk({"command": "find / -maxdepth 1"}) == "act_high"
    assert tool.assess_risk({"command": "cat $HOME/.ssh/id_rsa"}) == "act_high"


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
    turn = await core.create_turn_record(
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
async def test_bash_tool_waits_for_approval_for_elevated_command(db_session):
    dispatcher, context, workspace_root = await _shell_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="bash",
        input={
            "command": f"{sys.executable} -c \"print('should not run')\"",
            "cwd": str(workspace_root),
        },
        context=context,
        permission_mode="guarded_auto",
    )

    assert result.status == "waiting_decision"
    assert result.permission_decision["decision"] == "ask"
    assert result.result is None


@pytest.mark.asyncio
async def test_bash_tool_auto_runs_safe_command_with_pipe_and_glob(db_session):
    dispatcher, context, workspace_root = await _shell_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="bash",
        input={
            "command": "echo agent-core-ok | cat",
            "cwd": str(workspace_root),
        },
        context=context,
        permission_mode="guarded_auto",
    )

    # A read-only command auto-runs even under guarded_auto, and the pipe works.
    assert result.status == "completed"
    assert result.result["exit_code"] == 0
    assert result.result["stdout"].strip() == "agent-core-ok"

    events = await AgentCoreService(db_session).list_events_for_turn(
        turn_id=context.turn_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    started = next(event for event in events if event.type == "action.started")
    completed = next(event for event in events if event.type == "action.completed")
    assert started.payload["name"] == "bash"
    assert started.payload["input_preview"] == "echo agent-core-ok | cat"
    assert completed.payload["name"] == "bash"
    assert completed.payload["input_preview"] == "echo agent-core-ok | cat"


@pytest.mark.asyncio
async def test_bash_tool_hard_blocks_catastrophic_command_even_in_bypass(db_session):
    dispatcher, context, workspace_root = await _shell_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="bash",
        input={"command": "rm -rf /", "cwd": str(workspace_root)},
        context=context,
        permission_mode="bypass",
    )

    assert result.status == "rejected"
    assert result.permission_decision["decision"] == "deny"
    assert result.permission_decision["risk_level"] == "critical"
    assert result.result is None


@pytest.mark.asyncio
async def test_bash_tool_defaults_cwd_to_repo_root(db_session):
    dispatcher, context, _workspace_root = await _shell_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="bash",
        input={"command": "pwd"},
        context=context,
        permission_mode="bypass",
    )

    assert result.status == "completed"
    assert result.result["cwd"] == str(Path(settings.repo_root).expanduser().resolve())


@pytest.mark.asyncio
async def test_bash_tool_rejects_cwd_outside_allowed_roots(db_session):
    dispatcher, context, _workspace_root = await _shell_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="bash",
        input={"command": "echo hi", "cwd": "/"},
        context=context,
        permission_mode="bypass",
    )

    assert result.status == "failed"
    assert result.error["type"] == "PermissionDeniedError"


@pytest.mark.asyncio
async def test_bash_tool_resumes_after_approval_without_registering_output_artifact(db_session, monkeypatch):
    dispatcher, context, workspace_root = await _shell_context(db_session)
    monkeypatch.setattr("app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None)

    pending = await dispatcher.dispatch(
        tool_name="bash",
        input={
            "command": f"{sys.executable} -c \"print('before-approval')\"",
            "cwd": str(workspace_root),
        },
        context=context,
        permission_mode="guarded_auto",
    )
    assert pending.status == "waiting_decision"

    decided = await AgentCoreService(db_session).decide_action(
        action_id=pending.action_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
        note="approved for test",
    )
    assert decided.status == "requested"

    resumed = await dispatcher.resume_action(action_id=pending.action_id, context=context)
    assert resumed.status == "completed"
    assert resumed.result["exit_code"] == 0
    assert resumed.result["stdout"].strip() == "before-approval"

    artifacts = await AgentCoreService(db_session).list_artifacts_for_turn(
        turn_id=context.turn_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert artifacts == []

    events = await AgentCoreService(db_session).list_events_for_turn(
        turn_id=context.turn_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    event_types = [event.type for event in events]
    assert "action.decision_recorded" in event_types
    assert "action.started" in event_types
    assert "artifact.created" not in event_types
    assert "action.completed" in event_types


@pytest.mark.asyncio
async def test_bash_tool_uses_modified_input_when_approval_changes_command(db_session, monkeypatch):
    dispatcher, context, workspace_root = await _shell_context(db_session)
    monkeypatch.setattr("app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None)

    pending = await dispatcher.dispatch(
        tool_name="bash",
        input={
            "command": f"{sys.executable} -c \"print('old-command')\"",
            "cwd": str(workspace_root),
        },
        context=context,
        permission_mode="guarded_auto",
    )

    decided = await AgentCoreService(db_session).decide_action(
        action_id=pending.action_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="modify",
        note="use safer command",
        modified_input={
            "command": f"{sys.executable} -c \"print('new-command')\"",
            "cwd": str(workspace_root),
        },
    )
    assert decided.status == "requested"

    resumed = await dispatcher.resume_action(action_id=pending.action_id, context=context)
    assert resumed.status == "completed"
    assert resumed.result["stdout"].strip() == "new-command"
    action = await AgentActionRepository(db_session).get(pending.action_id)
    assert "new-command" in action.input["command"]
