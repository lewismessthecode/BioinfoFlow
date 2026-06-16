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
    turn = await core.create_turn_record(
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
        {"project": project, "workflow": workflow, "image": image, "run": run, "core": core},
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
async def test_projects_get_tool_returns_platform_project_projection(db_session):
    dispatcher, context, resources = await _tool_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="projects.get",
        input={"project_id": str(resources["project"].id)},
        context=context,
    )

    assert result.status == "completed"
    assert result.result["project"]["id"] == str(resources["project"].id)
    assert result.result["project"]["name"] == "Resource Project"


@pytest.mark.asyncio
async def test_project_workflow_tools_wrap_binding_service(db_session):
    dispatcher, context, resources = await _tool_context(db_session)

    bind = await dispatcher.dispatch(
        tool_name="projects.workflows.bind",
        input={
            "project_id": str(resources["project"].id),
            "workflow_id": str(resources["workflow"].id),
        },
        context=context,
        permission_mode="bypass",
    )
    listed = await dispatcher.dispatch(
        tool_name="projects.workflows.list",
        input={"project_id": str(resources["project"].id)},
        context=context,
    )
    pinned = await dispatcher.dispatch(
        tool_name="projects.workflows.pin",
        input={
            "project_id": str(resources["project"].id),
            "workflow_id": str(resources["workflow"].id),
        },
        context=context,
        permission_mode="bypass",
    )
    unbind = await dispatcher.dispatch(
        tool_name="projects.workflows.unbind",
        input={
            "project_id": str(resources["project"].id),
            "workflow_id": str(resources["workflow"].id),
        },
        context=context,
        permission_mode="bypass",
    )

    assert bind.status == "completed"
    assert listed.result["groups"][0]["pinned_workflow"]["id"] == str(resources["workflow"].id)
    assert pinned.result == {
        "project_id": str(resources["project"].id),
        "pinned_workflow_id": str(resources["workflow"].id),
    }
    assert unbind.result == {
        "project_id": str(resources["project"].id),
        "workflow_id": str(resources["workflow"].id),
        "unbound": True,
    }


@pytest.mark.asyncio
async def test_project_workflow_tools_reject_foreign_workspace_project(db_session):
    dispatcher, context, resources = await _tool_context(db_session)
    foreign_workspace = Workspace(id="foreign-workspace", name="Foreign", slug="foreign")
    foreign_project = Project(
        name="Foreign Project",
        description="Not in agent workspace",
        user_id="other-user",
        created_by_user_id="other-user",
        workspace_id="foreign-workspace",
    )
    db_session.add_all([foreign_workspace, foreign_project])
    await db_session.commit()
    await db_session.refresh(foreign_project)

    foreign_project_id = str(foreign_project.id)
    workflow_id = str(resources["workflow"].id)
    list_result = await dispatcher.dispatch(
        tool_name="projects.workflows.list",
        input={"project_id": foreign_project_id},
        context=context,
    )
    unbind_result = await dispatcher.dispatch(
        tool_name="projects.workflows.unbind",
        input={"project_id": foreign_project_id, "workflow_id": workflow_id},
        context=context,
        permission_mode="bypass",
    )
    bind_result = await dispatcher.dispatch(
        tool_name="projects.workflows.bind",
        input={"project_id": foreign_project_id, "workflow_id": workflow_id},
        context=context,
        permission_mode="bypass",
    )
    pin_result = await dispatcher.dispatch(
        tool_name="projects.workflows.pin",
        input={"project_id": foreign_project_id, "workflow_id": workflow_id},
        context=context,
        permission_mode="bypass",
    )

    for result in (list_result, bind_result, pin_result, unbind_result):
        assert result.status == "failed"
        assert result.error["type"] == "NotFoundError"
        assert result.error["message"] == "Project not found"


@pytest.mark.asyncio
async def test_workflow_read_tools_return_form_spec_dag_and_source(db_session, monkeypatch, tmp_path):
    dispatcher, context, resources = await _tool_context(db_session)

    def fake_resolve_source_path(self, workflow):
        source = tmp_path / "main.nf"
        source.write_text("workflow { }\n", encoding="utf-8")
        return source

    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.workflows.WorkflowService.resolve_source_path",
        fake_resolve_source_path,
    )

    workflow_id = str(resources["workflow"].id)
    get_result = await dispatcher.dispatch(
        tool_name="workflows.get",
        input={"workflow_id": workflow_id},
        context=context,
    )
    form_spec = await dispatcher.dispatch(
        tool_name="workflows.form_spec",
        input={"workflow_id": workflow_id},
        context=context,
    )
    dag = await dispatcher.dispatch(
        tool_name="workflows.dag",
        input={"workflow_id": workflow_id},
        context=context,
    )
    source = await dispatcher.dispatch(
        tool_name="workflows.source",
        input={"workflow_id": workflow_id},
        context=context,
    )

    assert get_result.result["workflow"]["id"] == workflow_id
    assert form_spec.result["form_spec"]["fields"] == []
    assert dag.result["dag"] == {"nodes": [], "edges": []}
    assert source.result["source"]["content"] == "workflow { }\n"


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
async def test_images_get_tool_returns_platform_image_projection(db_session):
    dispatcher, context, resources = await _tool_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="images.get",
        input={"image_id": str(resources["image"].id)},
        context=context,
    )

    assert result.status == "completed"
    assert result.result["image"]["full_name"] == "biocontainers/fastqc:latest"


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
async def test_run_evidence_tools_wrap_run_service(db_session, monkeypatch):
    dispatcher, context, resources = await _tool_context(db_session)

    async def fake_outputs(self, run_id, **kwargs):
        assert run_id == "run-resource-1"
        return {"files": [{"path": "results/out.txt", "size_bytes": 12}]}

    async def fake_dag(self, run_id, **kwargs):
        assert run_id == "run-resource-1"
        return {"nodes": [{"id": "align"}], "edges": []}

    async def fake_audit(self, run_id, **kwargs):
        assert run_id == "run-resource-1"
        return [{"event": "created"}]

    monkeypatch.setattr("app.services.agent_core.tools.platform.runs.RunService.list_outputs", fake_outputs)
    monkeypatch.setattr("app.services.agent_core.tools.platform.runs.RunService.get_dag", fake_dag)
    monkeypatch.setattr("app.services.agent_core.tools.platform.runs.RunService.get_run_audit", fake_audit)

    get_result = await dispatcher.dispatch(
        tool_name="runs.get",
        input={"run_id": "run-resource-1"},
        context=context,
    )
    outputs = await dispatcher.dispatch(
        tool_name="runs.outputs",
        input={"run_id": "run-resource-1"},
        context=context,
    )
    dag = await dispatcher.dispatch(
        tool_name="runs.dag",
        input={"run_id": "run-resource-1"},
        context=context,
    )
    audit = await dispatcher.dispatch(
        tool_name="runs.audit",
        input={"run_id": "run-resource-1"},
        context=context,
    )

    assert get_result.result["run"]["run_id"] == "run-resource-1"
    assert outputs.result["outputs"]["files"][0]["path"] == "results/out.txt"
    assert dag.result["dag"]["nodes"][0]["id"] == "align"
    assert audit.result["audit"] == [{"event": "created"}]


@pytest.mark.asyncio
async def test_scheduler_tools_return_status_and_resources(db_session, monkeypatch):
    dispatcher, context, _resources = await _tool_context(db_session)

    class FakeSnapshot:
        sampled_at = None
        cpu_count = 16
        cpu_available = 8
        memory_total_gb = 64.0
        memory_available_gb = 32.0
        disk_total_gb = 1000.0
        disk_available_gb = 750.0
        gpu_count = 1
        gpu_memory_gb = 24.0

    class FakeScheduler:
        async def get_status(self):
            return {"workers": 2, "queue_depth": 3, "active_runs": []}

        def get_resource_snapshot(self):
            return FakeSnapshot()

    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.scheduler.get_run_scheduler",
        lambda: FakeScheduler(),
    )

    status = await dispatcher.dispatch(
        tool_name="scheduler.status",
        input={},
        context=context,
    )
    resources = await dispatcher.dispatch(
        tool_name="scheduler.resources",
        input={},
        context=context,
    )

    assert status.result["status"]["scheduler_available"] is True
    assert status.result["status"]["queue_depth"] == 3
    assert resources.result["resources"]["cpu"]["available"] == 8


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
