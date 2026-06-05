from __future__ import annotations

import pytest

from app.models.image import DockerImage, ImageStatus
from app.models.project import Project
from app.models.run import Run, RunStatus
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.models.workspace import Workspace
from app.services.agent_core import AgentCoreService
from app.services.agent_core.tools import (
    AgentToolContext,
    AgentToolDispatcher,
    build_default_tool_registry,
)
from app.workspace import DEFAULT_WORKSPACE_ID


async def _tool_context(db_session) -> tuple[AgentToolDispatcher, AgentToolContext, dict]:
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    project = Project(
        name="Resource Project",
        description="AgentCore resource tools",
        user_id="dev",
        created_by_user_id="dev",
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    workflow = Workflow(
        name="rnaseq",
        description="RNA-seq workflow",
        source=WorkflowSource.LOCAL.value,
        engine=WorkflowEngine.NEXTFLOW.value,
        source_ref="local",
        version="1.0.0",
        schema_json={"inputs": []},
        form_spec={"fields": []},
    )
    image = DockerImage(
        name="biocontainers/fastqc",
        tag="latest",
        full_name="biocontainers/fastqc:latest",
        registry="quay.io",
        status=ImageStatus.REMOTE.value,
    )
    db_session.add_all([workspace, project, workflow, image])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)

    run = Run(
        run_id="run-resource-1",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={},
        samples_count=2,
        tasks_total=4,
        tasks_completed=4,
    )
    db_session.add(run)
    await db_session.commit()

    core = AgentCoreService(db_session)
    session = await core.create_session(
        project_id=str(project.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        title="Resource tools",
    )
    turn = await core.create_turn(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Inspect platform resources.",
    )
    context = AgentToolContext(
        db=db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        session_id=str(session.id),
        turn_id=str(turn.id),
    )
    return (
        AgentToolDispatcher(db_session, build_default_tool_registry()),
        context,
        {"project": project, "workflow": workflow, "run": run, "core": core},
    )


@pytest.mark.asyncio
async def test_workflows_list_tool_uses_workflow_service(db_session):
    dispatcher, context, resources = await _tool_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="workflows.list",
        input={"search": "rna"},
        context=context,
    )

    assert result.status == "completed"
    assert result.result["workflows"][0]["id"] == str(resources["workflow"].id)
    assert result.result["workflows"][0]["has_form_spec"] is True


@pytest.mark.asyncio
async def test_images_list_tool_uses_image_service_without_forcing_docker_sync(db_session):
    dispatcher, context, _resources = await _tool_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="images.list",
        input={"search": "fastqc", "status": "remote"},
        context=context,
    )

    assert result.status == "completed"
    assert result.result["images"][0]["full_name"] == "biocontainers/fastqc:latest"
    assert result.result["status"]["docker"] == "available"


@pytest.mark.asyncio
async def test_runs_list_tool_uses_run_service(db_session):
    dispatcher, context, resources = await _tool_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="runs.list",
        input={"project_id": str(resources["project"].id), "status": ["completed"]},
        context=context,
    )

    assert result.status == "completed"
    assert result.result["runs"][0]["run_id"] == "run-resource-1"
    assert result.result["runs"][0]["tasks_completed"] == 4


@pytest.mark.asyncio
async def test_run_logs_tool_returns_empty_logs_for_non_terminal_running_run(db_session):
    dispatcher, context, resources = await _tool_context(db_session)
    resources["run"].status = RunStatus.RUNNING.value
    await db_session.commit()

    result = await dispatcher.dispatch(
        tool_name="runs.logs",
        input={"run_id": "run-resource-1", "tail": 20},
        context=context,
    )

    assert result.status == "completed"
    assert result.result == {"logs": []}
