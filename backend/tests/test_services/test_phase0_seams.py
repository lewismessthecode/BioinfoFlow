from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from app.models.project import Project
from app.models.project_workflow_binding import ProjectWorkflowBinding
from app.models.run import RunStatus
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.models.run_config import RunConfigHelper
from app.schemas.run import RunCreate
from app.services import image_service
from app.services.image_service import ImageService
from app.services.run_compiler import RunCompiler
from app.services.run_service import RunService
from app.services.run_lifecycle_service import RunLifecycleService


async def _bind_workflow(db_session, *, project_id: str, workflow_id: str) -> None:
    db_session.add(
        ProjectWorkflowBinding(project_id=project_id, workflow_id=workflow_id)
    )
    await db_session.commit()


def test_run_config_helper_build_v1_keeps_v1_namespaces_and_legacy_aliases():
    legacy_dag = {"nodes": [{"id": "fastqc"}], "edges": []}
    legacy = RunConfigHelper(
        {
            "params": {"outdir": "results"},
            "inputs": {"sample": "S1"},
            "config_overrides": {"process.cpus": 4},
            "resolved_runspec": {"params": {"outdir": "results"}},
            "dag": legacy_dag,
            "runtime": {"pid": 123, "engine": "nextflow", "resume_from": "nf-run"},
        }
    )

    assert legacy.version == 0
    assert legacy.params == {"outdir": "results"}
    assert legacy.inputs == {"sample": "S1"}
    assert legacy.config_overrides == {"process.cpus": 4}
    assert legacy.resolved_runspec == {"params": {"outdir": "results"}}
    assert legacy.pid == 123
    assert legacy.engine == "nextflow"
    assert legacy.resume_token == "nf-run"
    assert legacy.dag == legacy_dag

    config = RunConfigHelper.build_v1(
        params={"outdir": "results"},
        inputs={"sample": "S1"},
        config_overrides={"process.cpus": 4},
        resolved_runspec={"params": {"outdir": "results"}},
    )
    helper = RunConfigHelper(config)

    assert helper.version == 1
    assert helper.params == {"outdir": "results"}
    assert helper.inputs == {"sample": "S1"}
    assert helper.config_overrides == {"process.cpus": 4}
    assert helper.resolved_runspec == {"params": {"outdir": "results"}}
    assert config["request"]["params"] == {"outdir": "results"}
    assert config["resolved"]["runspec"] == {"params": {"outdir": "results"}}
    assert config["params"] == {"outdir": "results"}
    assert config["inputs"] == {"sample": "S1"}
    assert config["config_overrides"] == {"process.cpus": 4}
    assert config["resolved_runspec"] == {"params": {"outdir": "results"}}


@dataclass
class SpyDispatcher:
    dispatched: list[str] = field(default_factory=list)

    def dispatch(self, run_id: str, *, priority: str = "normal") -> None:
        assert priority == "normal"
        self.dispatched.append(run_id)


async def _create_run_via_compiler(
    session,
    *,
    project: Project,
    workflow: Workflow,
    dispatcher,
):
    compiler = RunCompiler(session, dispatcher=dispatcher)
    return await compiler.create_run(
        RunCreate.model_validate(
            {
                "project_id": str(project.id),
                "workflow_id": str(workflow.id),
                "values": {},
            }
        ),
        user_id=project.user_id,
        workspace_id=project.workspace_id,
    )


@pytest.mark.asyncio
async def test_run_service_dispatches_create_resume_and_retry_via_injected_dispatcher(
    db_session, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        RunLifecycleService,
        "_require_engine_binary",
        lambda self, engine: None,
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project = Project(
        name="Dispatch Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
    )
    workflow = Workflow(
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version=str(uuid4()),
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)
    await _bind_workflow(
        db_session, project_id=str(project.id), workflow_id=str(workflow.id)
    )

    dispatcher = SpyDispatcher()
    service = RunService(db_session, dispatcher=dispatcher)

    created = await _create_run_via_compiler(
        db_session,
        project=project,
        workflow=workflow,
        dispatcher=dispatcher,
    )
    created = await service.repo.update(
        created,
        status=RunStatus.FAILED.value,
        nextflow_run_name="nf-run",
    )

    resumed = await service.resume_run(created.run_id)
    retried = await service.retry_run(created.run_id)

    assert dispatcher.dispatched == [
        created.run_id,
        resumed.run_id,
        retried.run_id,
    ]


@pytest.mark.asyncio
async def test_image_service_pull_uses_background_tasks_submit(db_session, monkeypatch):
    captured: dict[str, object] = {}

    def fake_submit(func, *args, **kwargs):
        captured["func"] = func
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(image_service.background_tasks, "submit", fake_submit)

    service = ImageService(db_session)
    image = await service.pull_image(
        name="bioinfoflow/bwa",
        tag="v2.2.1",
        registry="docker.io",
        project_id="project-1",
    )

    assert image.status == "pulling"
    assert captured["func"] == service._pull_task
    assert captured["args"] == (
        image.id,
        "bioinfoflow/bwa",
        "v2.2.1",
        "docker.io",
        "project-1",
    )
    assert captured["kwargs"] == {}


@pytest.mark.asyncio
async def test_run_service_uses_engine_adapter_for_cancel_and_resume(
    db_session, monkeypatch, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project = Project(
        name="Engine Adapter Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
    )
    workflow = Workflow(
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version=str(uuid4()),
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)
    await _bind_workflow(
        db_session, project_id=str(project.id), workflow_id=str(workflow.id)
    )

    class FakeAdapter:
        binary = "/opt/fake-nextflow"
        supports_native_resume = True

        def __init__(self) -> None:
            self.cancel_calls: list[dict] = []
            self.resume_configs: list[dict] = []

        async def cancel(self, **kwargs) -> bool:
            self.cancel_calls.append(kwargs)
            return True

        def get_resume_token(self, run_config: dict) -> str | None:
            self.resume_configs.append(run_config)
            return "steady_hopper"

    adapter = FakeAdapter()
    monkeypatch.setattr("app.services.run_lifecycle_service.get_adapter", lambda engine: adapter)
    monkeypatch.setattr(RunLifecycleService, "_binary_exists", lambda self, binary: True)

    service = RunService(db_session)
    config = RunConfigHelper.build_v1(
        params={"outdir": "results"},
        inputs={},
        config_overrides={},
        resolved_runspec={},
    )
    config["runtime"] = {"pid": 4321}
    running = await service.repo.create(
        run_id="run_engine_cancel",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.RUNNING.value,
        config=config,
        nextflow_run_name="steady_hopper",
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )

    cancelled = await service.cancel_run(running.run_id)
    assert cancelled.status == RunStatus.CANCELLED.value
    assert adapter.cancel_calls == [{"pid": 4321, "run_name": "steady_hopper"}]

    failed = await service.repo.create(
        run_id="run_engine_resume",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.FAILED.value,
        config=RunConfigHelper.build_v1(
            params={"outdir": "results"},
            inputs={},
            config_overrides={},
            resolved_runspec={},
        ),
        nextflow_run_name="steady_hopper",
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )

    resumed = await service.resume_run(failed.run_id)

    assert resumed.status == RunStatus.QUEUED.value
    assert resumed.config["resume"] is True
    assert resumed.config["resume_from"] == "steady_hopper"
    assert adapter.resume_configs
