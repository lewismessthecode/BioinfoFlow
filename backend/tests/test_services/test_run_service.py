from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.database import Base
from app.models.project import Project
from app.models.run import RunStatus
from app.models.workflow import Workflow, WorkflowEngine
from app.path_layout import project_data_root, project_home, run_home
from app.schemas.run import RunCreate
from app.services import run_service
from app.services.run_compiler import RunCompiler
from app.services.run_service import RunService
from tests.support.path_contract import (
    bind_workflow,
    create_project,
    create_workflow,
    write_project_file,
)


class NullDispatcher:
    def dispatch(self, run_id: str, *, priority: str = "normal") -> None:
        del run_id, priority


async def _create_external_project_and_workflow(
    db_session,
    *,
    external_root: Path,
    workflow_name: str = "demo-workflow",
    engine: WorkflowEngine = WorkflowEngine.NEXTFLOW,
    workflow_content: str | None = None,
) -> tuple[Project, Workflow]:
    project = await create_project(
        db_session,
        name=f"Project {uuid4()}",
        storage_mode="external",
        external_root_path=str(external_root),
    )
    workflow = await create_workflow(
        db_session,
        name=workflow_name,
        engine=engine,
        content=workflow_content
        or (
            "version 1.0\nworkflow demo {}\n"
            if engine == WorkflowEngine.WDL
            else "workflow { }\n"
        ),
    )
    await bind_workflow(
        db_session, project_id=str(project.id), workflow_id=str(workflow.id)
    )
    return project, workflow


async def _create_run_via_compiler(
    session,
    *,
    project: Project,
    workflow,
    values: dict | None = None,
    dispatcher=None,
):
    compiler = RunCompiler(session, dispatcher=dispatcher or NullDispatcher())
    return await compiler.create_run(
        RunCreate.model_validate(
            {
                "project_id": str(project.id),
                "workflow_id": str(workflow.id),
                "values": values or {},
            }
        ),
        user_id=project.user_id,
        workspace_id=project.workspace_id,
    )


@pytest.mark.asyncio
async def test_run_service_lifecycle(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project, workflow = await _create_external_project_and_workflow(
        db_session, external_root=workspace
    )

    dispatcher = NullDispatcher()
    service = RunService(db_session, dispatcher=dispatcher)
    run = await _create_run_via_compiler(
        db_session,
        project=project,
        workflow=workflow,
        dispatcher=dispatcher,
    )

    assert getattr(run.status, "value", run.status) == RunStatus.QUEUED.value
    assert run.run_id.startswith("run_")

    cancelled = await service.cancel_run(run.run_id)
    assert (
        getattr(cancelled.status, "value", cancelled.status)
        == RunStatus.CANCELLED.value
    )

    run = await _create_run_via_compiler(
        db_session,
        project=project,
        workflow=workflow,
        dispatcher=dispatcher,
    )
    run = await service.repo.update(
        run, status=RunStatus.FAILED.value, nextflow_run_name="nf-run"
    )

    resumed = await service.resume_run(run.run_id, config_overrides={"process.cpus": 4})
    assert getattr(resumed.status, "value", resumed.status) == RunStatus.QUEUED.value

    retried = await service.retry_run(run.run_id, params={"foo": "bar"})
    assert getattr(retried.status, "value", retried.status) == RunStatus.QUEUED.value


@pytest.mark.asyncio
async def test_create_run_persists_run_archive(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project, workflow = await _create_external_project_and_workflow(
        db_session, external_root=workspace
    )
    data_root = project_data_root(project)
    write_project_file(
        data_root,
        "samplesheet.csv",
        "sample,fastq_1,fastq_2\n",
    )
    workflow.form_spec = {
        "fields": [
            {
                "id": "samplesheet",
                "label": "Samplesheet",
                "section": "data",
                "kind": "file",
                "required": True,
                "allow_roots": ["project_data"],
            }
        ]
    }
    await db_session.commit()
    await db_session.refresh(workflow)

    run = await _create_run_via_compiler(
        db_session,
        project=project,
        workflow=workflow,
        values={"samplesheet": "samplesheet.csv"},
    )

    archive_dir = run_home(project, run.run_id)
    assert archive_dir.exists()
    assert (archive_dir / "input").is_dir()
    assert (archive_dir / "audit" / "run.manifest.json").is_file()

    params_path = archive_dir / "input" / "params.json"
    inputs_path = archive_dir / "input" / "inputs.json"
    overrides_path = archive_dir / "input" / "config_overrides.json"
    assert params_path.is_file()
    assert inputs_path.is_file()
    assert overrides_path.is_file()

    manifest = json.loads((archive_dir / "audit" / "run.manifest.json").read_text())
    assert manifest["run_id"] == run.run_id
    assert manifest["resolved_inputs"]["workspace"] == str(project_home(project))
    assert manifest["resolved_inputs"]["params"]["samplesheet"].endswith(
        "/data/samplesheet.csv"
    )
    assert manifest["resolved_inputs"]["files"]


@pytest.mark.asyncio
async def test_create_run_succeeds_when_audit_logs_table_is_missing(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)

    db_path = tmp_path / "auditless.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("DROP TABLE audit_logs"))

    session_maker = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    try:
        async with session_maker() as session:
            project, workflow = await _create_external_project_and_workflow(
                session, external_root=workspace
            )

            run = await _create_run_via_compiler(
                session,
                project=project,
                workflow=workflow,
            )

            assert getattr(run.status, "value", run.status) == RunStatus.QUEUED.value
            assert run.run_id.startswith("run_")
    finally:
        await engine.dispose()
        if db_path.exists():
            db_path.unlink()


@pytest.mark.asyncio
async def test_resume_run_supports_wdl_best_effort_and_validates_nextflow_token(
    db_session, monkeypatch, tmp_path
):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = await create_project(
        db_session,
        name="Resume Project",
        storage_mode="external",
        external_root_path=str(workspace),
    )
    nf_workflow = await create_workflow(
        db_session,
        name=f"nf-{uuid4()}",
        engine=WorkflowEngine.NEXTFLOW,
        content="workflow { }\n",
    )
    wdl_workflow = await create_workflow(
        db_session,
        name=f"wdl-{uuid4()}",
        engine=WorkflowEngine.WDL,
        content="version 1.0\nworkflow w {}\n",
    )
    await bind_workflow(
        db_session, project_id=str(project.id), workflow_id=str(nf_workflow.id)
    )
    await bind_workflow(
        db_session, project_id=str(project.id), workflow_id=str(wdl_workflow.id)
    )

    service = RunService(db_session)

    failed_wdl = await service.repo.create(
        run_id="run_wdl_resume",
        project_id=str(project.id),
        workflow_id=str(wdl_workflow.id),
        status=RunStatus.FAILED.value,
        config={
            "params": {},
            "inputs": {},
            "config_overrides": {},
            "runtime": {"wdl_work_dir": "runs/run_wdl_resume/engine/wdl/work"},
        },
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )

    resumed_wdl = await service.resume_run(failed_wdl.run_id)
    assert (
        getattr(resumed_wdl.status, "value", resumed_wdl.status)
        == RunStatus.QUEUED.value
    )
    assert resumed_wdl.config["resume"] is True
    assert resumed_wdl.config["resume_type"] == "best_effort"
    assert (
        resumed_wdl.config["resume_work_dir"]
        == "runs/run_wdl_resume/engine/wdl/work"
    )

    failed_nf = await service.repo.create(
        run_id="run_nf_resume",
        project_id=str(project.id),
        workflow_id=str(nf_workflow.id),
        status=RunStatus.FAILED.value,
        config={"params": {}, "inputs": {}, "config_overrides": {}},
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )

    with pytest.raises(ValueError, match="cannot be resumed"):
        await service.resume_run(failed_nf.run_id)


@pytest.mark.asyncio
async def test_retry_run_prefers_resolved_runspec_when_original_params_changed(
    db_session, monkeypatch, tmp_path
):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project, workflow = await _create_external_project_and_workflow(
        db_session, external_root=workspace
    )
    data_root = project_data_root(project)
    (data_root / "samplesheet.csv").write_text(
        "sample,fastq_1,fastq_2\n",
        encoding="utf-8",
    )
    workflow.form_spec = {
        "fields": [
            {
                "id": "samplesheet",
                "label": "Samplesheet",
                "section": "data",
                "kind": "file",
                "required": True,
                "allow_roots": ["project_data"],
            }
        ]
    }
    await db_session.commit()
    await db_session.refresh(workflow)

    service = RunService(db_session)
    run = await _create_run_via_compiler(
        db_session,
        project=project,
        workflow=workflow,
        values={"samplesheet": "samplesheet.csv"},
    )
    broken_config = {
        **run.config,
        "params": {"samplesheet": "missing.csv"},
    }
    run = await service.repo.update(
        run,
        status=RunStatus.FAILED.value,
        config=broken_config,
        nextflow_run_name="steady_hopper",
    )

    retried = await service.retry_run(run.run_id)
    assert retried.config["params"]["samplesheet"].endswith(
        "/data/samplesheet.csv"
    )
