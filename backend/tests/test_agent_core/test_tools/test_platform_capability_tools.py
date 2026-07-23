from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.config import settings
from app.models.project import Project
from app.models.workspace import Workspace, WorkspaceMembership
from app.services.agent_core import AgentCoreService
from app.services.agent_core.tools import (
    AgentToolContext,
    AgentToolDispatcher,
    build_default_tool_registry,
)
from app.workspace import DEFAULT_WORKSPACE_ID


async def _context(
    db_session,
    *,
    permission_mode: str = "bypass",
) -> tuple[AgentToolDispatcher, AgentToolContext]:
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
        permission_mode=permission_mode,
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
async def test_patch_tool_asks_for_approval_in_default_session(db_session):
    dispatcher, context = await _context(db_session, permission_mode="guarded_auto")

    result = await dispatcher.dispatch(
        tool_name="files.apply_patch",
        input={
            "operations": [
                {"op": "create", "path": "agent-scratch.txt", "content": "hello"}
            ]
        },
        context=context,
        permission_mode="guarded_auto",
    )

    assert result.status == "waiting_decision"
    assert result.permission_decision["decision"] == "ask"


@pytest.mark.asyncio
async def test_workflows_create_wraps_service_and_emits_workflow_artifact(
    db_session, monkeypatch
):
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
async def test_runs_submit_wraps_compiler_and_emits_run_artifact(
    db_session, monkeypatch
):
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


@pytest.mark.asyncio
async def test_platform_mutation_tools_wrap_services(db_session, monkeypatch):
    dispatcher, context = await _context(db_session)
    project_id = str(uuid4())
    workflow_id = str(uuid4())
    image_id = str(uuid4())

    async def fake_create_project(self, data, *, user_id):
        return SimpleNamespace(
            id=project_id,
            name=data["name"],
            description=data.get("description"),
            storage_mode="managed",
            project_root="/tmp/project",
            is_default=False,
        )

    async def fake_update_project(self, project, data):
        return SimpleNamespace(
            id=project_id,
            name=data["name"],
            description=data.get("description"),
            storage_mode="managed",
            project_root="/tmp/project",
            is_default=False,
        )

    async def fake_get_project(self, project_id_arg, *, workspace_id=None):
        return SimpleNamespace(
            id=project_id_arg,
            name="old",
            description=None,
            storage_mode="managed",
            project_root="/tmp/project",
            is_default=False,
        )

    async def fake_delete_project(self, project):
        return None

    async def fake_get_workflow(self, workflow_id_arg):
        return SimpleNamespace(
            id=workflow_id_arg,
            name="wf",
            description="workflow",
            source="local",
            engine="wdl",
            version="1.0",
            source_ref="local",
            entrypoint_relpath="main.wdl",
            schema_json={},
            form_spec={},
        )

    async def fake_update_workflow(self, workflow, payload):
        workflow.description = payload["description"]
        return workflow

    async def fake_delete_workflow(self, workflow):
        return None

    async def fake_get_image(self, image_id_arg):
        return SimpleNamespace(
            id=image_id_arg,
            name="fastqc",
            tag="latest",
            full_name="fastqc:latest",
            registry="docker.io",
            status="local",
            size_bytes=1,
            entrypoint=[],
            env={},
            labels={},
        )

    async def fake_delete_image(self, image, *, force=False):
        return True

    async def fake_run_mutation(self, run_id, **kwargs):
        return SimpleNamespace(
            id=uuid4(),
            run_id=f"{run_id}-new",
            project_id=project_id,
            workflow_id=workflow_id,
            status="queued",
            samples_count=0,
            tasks_total=0,
            tasks_completed=0,
            current_task=None,
            error_message=None,
            started_at=None,
            completed_at=None,
        )

    async def fake_cleanup(self, run_id, **kwargs):
        return {"run_id": run_id, "removed": True}

    async def fake_delete_run(self, run_id, **kwargs):
        return None

    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.projects.ProjectService.create_project",
        fake_create_project,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.projects.ProjectService.get_project",
        fake_get_project,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.projects.ProjectService.update_project",
        fake_update_project,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.projects.ProjectService.delete_project",
        fake_delete_project,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.workflows.WorkflowService.get_workflow",
        fake_get_workflow,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.workflows.WorkflowService.update_workflow",
        fake_update_workflow,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.workflows.WorkflowService.delete_workflow",
        fake_delete_workflow,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.images.ImageService.get_image",
        fake_get_image,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.images.ImageService.delete_image",
        fake_delete_image,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.runs.RunService.resume_run",
        fake_run_mutation,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.runs.RunService.cleanup_run",
        fake_cleanup,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.runs.RunService.delete_run",
        fake_delete_run,
    )

    created_project = await dispatcher.dispatch(
        tool_name="projects.create",
        input={"name": "new", "description": "project"},
        context=context,
        permission_mode="bypass",
    )
    updated_project = await dispatcher.dispatch(
        tool_name="projects.update",
        input={"project_id": project_id, "name": "renamed"},
        context=context,
        permission_mode="bypass",
    )
    deleted_project = await dispatcher.dispatch(
        tool_name="projects.delete",
        input={"project_id": project_id},
        context=context,
        permission_mode="bypass",
    )
    updated_workflow = await dispatcher.dispatch(
        tool_name="workflows.update",
        input={"workflow_id": workflow_id, "description": "renamed-wf"},
        context=context,
        permission_mode="bypass",
    )
    deleted_workflow = await dispatcher.dispatch(
        tool_name="workflows.delete",
        input={"workflow_id": workflow_id},
        context=context,
        permission_mode="bypass",
    )
    deleted_image = await dispatcher.dispatch(
        tool_name="images.delete",
        input={"image_id": image_id},
        context=context,
        permission_mode="bypass",
    )
    resumed = await dispatcher.dispatch(
        tool_name="runs.resume",
        input={"run_id": "run-old"},
        context=context,
        permission_mode="bypass",
    )
    cleanup = await dispatcher.dispatch(
        tool_name="runs.cleanup",
        input={"run_id": "run-old"},
        context=context,
        permission_mode="bypass",
    )
    deleted_run = await dispatcher.dispatch(
        tool_name="runs.delete",
        input={"run_id": "run-old"},
        context=context,
        permission_mode="bypass",
    )

    assert created_project.result["project"]["name"] == "new"
    assert updated_project.result["project"]["name"] == "renamed"
    assert deleted_project.result == {"project_id": project_id, "deleted": True}
    assert updated_workflow.result["workflow"]["description"] == "renamed-wf"
    assert deleted_workflow.result == {"workflow_id": workflow_id, "deleted": True}
    assert deleted_image.result == {"image_id": image_id, "deleted": True}
    assert resumed.result["run"]["run_id"] == "run-old-new"
    assert cleanup.result == {"cleanup": {"run_id": "run-old", "removed": True}}
    assert deleted_run.result == {"run_id": "run-old", "deleted": True}


@pytest.mark.asyncio
async def test_images_pull_tool_accepts_registry_id(db_session, monkeypatch):
    dispatcher, context = await _context(db_session)
    captured: dict[str, object] = {}

    async def fake_pull_image(self, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            id=uuid4(),
            name=kwargs["name"],
            tag=kwargs["tag"],
            full_name=f"{kwargs['registry']}/{kwargs['name']}:{kwargs['tag']}",
            registry=kwargs["registry"],
            status="pulling",
            size_bytes=None,
            entrypoint=[],
            env={},
            labels={},
        )

    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.images.ImageService.pull_image",
        fake_pull_image,
    )

    result = await dispatcher.dispatch(
        tool_name="images.pull",
        input={
            "name": "bioinfoflow/bwa",
            "tag": "v2.2.1",
            "registry_id": "registry-1",
        },
        context=context,
        permission_mode="bypass",
    )

    assert result.status == "completed"
    assert result.result["image"]["name"] == "bioinfoflow/bwa"
    assert captured["registry_id"] == "registry-1"


@pytest.mark.asyncio
async def test_images_pull_tool_rejects_registry_id_for_members(
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "auth_mode", "team")
    dispatcher, context = await _context(db_session)
    db_session.add(
        WorkspaceMembership(
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id=context.user_id,
            role="member",
        )
    )
    await db_session.commit()
    called = False

    async def fake_pull_image(self, **kwargs):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.images.ImageService.pull_image",
        fake_pull_image,
    )

    result = await dispatcher.dispatch(
        tool_name="images.pull",
        input={
            "name": "bioinfoflow/bwa",
            "tag": "v2.2.1",
            "registry_id": "registry-1",
        },
        context=context,
        permission_mode="bypass",
    )

    assert result.status == "failed"
    assert result.error == {
        "type": "PermissionDeniedError",
        "message": "Only workspace admins can select a configured registry",
    }
    assert called is False


@pytest.mark.asyncio
async def test_update_tools_reject_fields_outside_public_mutation_schemas(
    db_session, monkeypatch
):
    dispatcher, context = await _context(db_session)
    project_id = str(uuid4())
    workflow_id = str(uuid4())
    project_update_called = False
    workflow_update_called = False

    async def fake_get_project(self, project_id_arg, *, workspace_id=None):
        return SimpleNamespace(
            id=project_id_arg,
            name="project",
            description=None,
            storage_mode="managed",
            project_root="/tmp/project",
            is_default=False,
        )

    async def fake_update_project(self, project, data):
        nonlocal project_update_called
        project_update_called = True
        return project

    async def fake_get_workflow(self, workflow_id_arg):
        return SimpleNamespace(
            id=workflow_id_arg,
            name="wf",
            description="workflow",
            source="local",
            engine="wdl",
            version="1.0",
            source_ref="local",
            entrypoint_relpath="main.wdl",
            schema_json={},
            form_spec={},
        )

    async def fake_update_workflow(self, workflow, payload):
        nonlocal workflow_update_called
        workflow_update_called = True
        return workflow

    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.projects.ProjectService.get_project",
        fake_get_project,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.projects.ProjectService.update_project",
        fake_update_project,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.workflows.WorkflowService.get_workflow",
        fake_get_workflow,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.workflows.WorkflowService.update_workflow",
        fake_update_workflow,
    )

    project_result = await dispatcher.dispatch(
        tool_name="projects.update",
        input={"project_id": project_id, "storage_mode": "external"},
        context=context,
        permission_mode="bypass",
    )
    workflow_result = await dispatcher.dispatch(
        tool_name="workflows.update",
        input={
            "workflow_id": workflow_id,
            "name": "renamed",
            "form_spec": {"fields": []},
        },
        context=context,
        permission_mode="bypass",
    )

    assert project_result.status == "failed"
    assert project_result.error["type"] == "BadRequestError"
    assert "unknown tool arguments: storage_mode" in project_result.error["message"]
    assert project_update_called is False
    assert workflow_result.status == "failed"
    assert workflow_result.error["type"] == "BadRequestError"
    assert "unknown tool arguments: name, form_spec" in workflow_result.error["message"]
    assert workflow_update_called is False


@pytest.mark.asyncio
async def test_workflow_mutation_tools_require_admin_in_team_mode(
    db_session, monkeypatch
):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_mode", "team")
    dispatcher, context = await _context(db_session)
    workflow_id = str(uuid4())
    calls = {"create": 0, "update": 0, "delete": 0}

    async def fake_create_workflow(self, payload):
        calls["create"] += 1
        return None

    async def fake_get_workflow(self, workflow_id_arg):
        return SimpleNamespace(
            id=workflow_id_arg,
            name="wf",
            description="workflow",
            source="local",
            engine="wdl",
            version="1.0",
            source_ref="local",
            entrypoint_relpath="main.wdl",
            schema_json={},
            form_spec={},
        )

    async def fake_update_workflow(self, workflow, payload):
        calls["update"] += 1
        return workflow

    async def fake_delete_workflow(self, workflow):
        calls["delete"] += 1

    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.workflows.WorkflowService.create_workflow",
        fake_create_workflow,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.workflows.WorkflowService.get_workflow",
        fake_get_workflow,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.workflows.WorkflowService.update_workflow",
        fake_update_workflow,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.workflows.WorkflowService.delete_workflow",
        fake_delete_workflow,
    )

    created = await dispatcher.dispatch(
        tool_name="workflows.create",
        input={
            "source": "local",
            "content": "version 1.0\nworkflow hello {}",
            "file_name": "hello.wdl",
        },
        context=context,
        permission_mode="bypass",
    )
    updated = await dispatcher.dispatch(
        tool_name="workflows.update",
        input={"workflow_id": workflow_id, "description": "changed"},
        context=context,
        permission_mode="bypass",
    )
    deleted = await dispatcher.dispatch(
        tool_name="workflows.delete",
        input={"workflow_id": workflow_id},
        context=context,
        permission_mode="bypass",
    )

    for result in (created, updated, deleted):
        assert result.status == "failed"
        assert result.error["type"] == "PermissionDeniedError"
    assert calls == {"create": 0, "update": 0, "delete": 0}


@pytest.mark.asyncio
async def test_projects_delete_rejects_default_project(db_session, monkeypatch):
    dispatcher, context = await _context(db_session)
    project_id = str(uuid4())
    delete_called = False

    async def fake_get_project(self, project_id_arg, *, workspace_id=None):
        return SimpleNamespace(
            id=project_id_arg,
            name="Recent",
            description=None,
            storage_mode="managed",
            project_root="/tmp/project",
            is_default=True,
        )

    async def fake_delete_project(self, project):
        nonlocal delete_called
        delete_called = True

    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.projects.ProjectService.get_project",
        fake_get_project,
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.projects.ProjectService.delete_project",
        fake_delete_project,
    )

    result = await dispatcher.dispatch(
        tool_name="projects.delete",
        input={"project_id": project_id},
        context=context,
        permission_mode="bypass",
    )

    assert result.status == "failed"
    assert result.error["type"] == "PermissionDeniedError"
    assert result.error["message"] == "Cannot delete the default project"
    assert delete_called is False
