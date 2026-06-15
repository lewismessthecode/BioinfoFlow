from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

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


async def _context(db_session) -> tuple[AgentToolDispatcher, AgentToolContext]:
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    project = Project(
        name="Platform Project",
        description="Capability tools",
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
    )
    turn = await core.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Operate the platform.",
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
    )


@pytest.mark.asyncio
async def test_write_tool_asks_for_approval_in_default_session(db_session):
    dispatcher, context = await _context(db_session)

    result = await dispatcher.dispatch(
        tool_name="files.write",
        input={"path": "agent-scratch.txt", "content": "hello"},
        context=context,
        permission_mode="guarded_auto",
    )

    assert result.status == "waiting_decision"
    assert result.permission_decision["decision"] == "ask"


@pytest.mark.asyncio
async def test_workflows_create_wraps_service_and_emits_workflow_artifact(db_session, monkeypatch):
    dispatcher, context = await _context(db_session)

    fake_workflow = SimpleNamespace(
        id=uuid4(),
        name="hello-wdl",
        description="A tiny workflow",
        source="local",
        engine="wdl",
        version="local",
        source_ref="local",
        entrypoint_relpath="hello.wdl",
    )

    async def fake_create(self, payload):
        assert payload["source"] == "local"
        return fake_workflow

    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.workflows.WorkflowService.create_workflow",
        fake_create,
    )

    result = await dispatcher.dispatch(
        tool_name="workflows.create",
        input={
            "source": "local",
            "content": "version 1.0\nworkflow hello {}",
            "file_name": "hello.wdl",
        },
        context=context,
        permission_mode="bypass",
    )

    assert result.status == "completed"
    assert result.result["workflow"]["name"] == "hello-wdl"

    artifacts = await AgentCoreService(db_session).list_artifacts_for_turn(
        turn_id=context.turn_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert [artifact.type for artifact in artifacts] == ["workflow"]


@pytest.mark.asyncio
async def test_runs_submit_wraps_compiler_and_emits_run_artifact(db_session, monkeypatch):
    dispatcher, context = await _context(db_session)

    fake_run = SimpleNamespace(
        id=uuid4(),
        run_id="run-abc123",
        project_id=uuid4(),
        workflow_id=uuid4(),
        status="queued",
        samples_count=1,
        tasks_total=0,
        tasks_completed=0,
        current_task=None,
        error_message=None,
        started_at=None,
        completed_at=datetime.now(timezone.utc),
    )

    async def fake_create_run(self, payload, *, user_id=None, workspace_id=None):
        return fake_run

    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.runs.RunCompiler.create_run",
        fake_create_run,
    )

    result = await dispatcher.dispatch(
        tool_name="runs.submit",
        input={
            "project_id": str(uuid4()),
            "workflow_id": str(uuid4()),
            "values": {"sample": "s1"},
        },
        context=context,
        permission_mode="bypass",
    )

    assert result.status == "completed"
    assert result.result["run"]["run_id"] == "run-abc123"

    artifacts = await AgentCoreService(db_session).list_artifacts_for_turn(
        turn_id=context.turn_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert [artifact.type for artifact in artifacts] == ["run"]
