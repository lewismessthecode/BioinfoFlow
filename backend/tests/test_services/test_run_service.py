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
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.path_layout import (
    project_data_root,
    project_home,
    run_home,
    run_results_root,
)
from app.schemas.run import RunCreate
from app.services import run_compiler as run_compiler_module
from app.services import run_service
from app.services.run_compiler import RunCompiler
from app.services.run_lifecycle_service import RunLifecycleService
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
    options: dict | None = None,
    dispatcher=None,
):
    compiler = RunCompiler(session, dispatcher=dispatcher or NullDispatcher())
    return await compiler.create_run(
        RunCreate.model_validate(
            {
                "project_id": str(project.id),
                "workflow_id": str(workflow.id),
                "values": values or {},
                **({"options": options} if options else {}),
            }
        ),
        user_id=project.user_id,
        workspace_id=project.workspace_id,
    )


@pytest.mark.asyncio
async def test_run_service_lifecycle(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)
    # Tests should not require the host to have a real `nextflow` binary.
    monkeypatch.setattr(RunLifecycleService, "_binary_exists", lambda self, binary: True)

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

    params_path = archive_dir / "input" / "request" / "params.json"
    inputs_path = archive_dir / "input" / "request" / "inputs.json"
    overrides_path = archive_dir / "input" / "request" / "config_overrides.json"
    assert params_path.is_file()
    assert inputs_path.is_file()
    assert overrides_path.is_file()
    assert not (archive_dir / "input" / "params.json").exists()
    assert not (archive_dir / "input" / "inputs.json").exists()
    assert not (archive_dir / "input" / "config_overrides.json").exists()

    manifest = json.loads((archive_dir / "audit" / "run.manifest.json").read_text())
    assert manifest["run_id"] == run.run_id
    assert manifest["resolved_inputs"]["workspace"] == str(project_home(project))
    assert manifest["resolved_inputs"]["params"]["samplesheet"].endswith(
        "/data/samplesheet.csv"
    )
    assert manifest["resolved_inputs"]["files"]


@pytest.mark.asyncio
async def test_nfcore_nextflow_run_compiles_revision_profile_and_params(
    db_session,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)

    class FakeDockerService:
        async def is_available(self) -> bool:
            return True

    from app.engine.adapters import nextflow as nextflow_module

    monkeypatch.setattr(nextflow_module, "DockerService", FakeDockerService)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = await create_project(
        db_session,
        name="nf-core project",
        storage_mode="external",
        external_root_path=str(workspace),
    )
    data_root = project_data_root(project)
    write_project_file(
        data_root,
        "samplesheet.csv",
        "sample,fastq_1,fastq_2\nS1,S1_R1.fastq.gz,S1_R2.fastq.gz\n",
    )
    workflow = await create_workflow(
        db_session,
        name="rnaseq",
        source=WorkflowSource.NFCORE,
        engine=WorkflowEngine.NEXTFLOW,
        version="3.24.0",
        source_ref="nf-core/rnaseq",
        schema_json={
            "inputs": [
                {
                    "name": "input",
                    "type": "string",
                    "value_kind": "file",
                    "optional": False,
                    "source_hint": "project",
                },
                {
                    "name": "outdir",
                    "type": "string",
                    "value_kind": "directory",
                    "optional": False,
                    "is_internal": True,
                },
            ],
        },
    )
    await bind_workflow(
        db_session, project_id=str(project.id), workflow_id=str(workflow.id)
    )

    run = await _create_run_via_compiler(
        db_session,
        project=project,
        workflow=workflow,
        values={"input": "samplesheet.csv"},
        options={"profile": "test,docker", "max_retries": 2},
    )

    argv = run.config["launch"]["argv"]
    run_index = argv.index("run")
    assert argv[run_index + 1] == "nf-core/rnaseq"
    assert argv[argv.index("-r") + 1] == "3.24.0"
    assert argv[argv.index("-profile") + 1] == "test,docker"
    assert argv[argv.index("--input") + 1].endswith("/data/samplesheet.csv")
    assert run.config["revision"] == "3.24.0"
    assert run.config["profile"] == "test,docker"
    assert "profile" not in run.config["config_overrides"]


@pytest.mark.asyncio
async def test_wdl_run_compile_ignores_nextflow_profile_and_revision(
    db_session,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)

    class FakeWDLAdapter:
        engine_name = "wdl"
        display_name = "MiniWDL"
        binary = "miniwdl"
        supports_native_resume = False

        async def pre_submit(self, config: dict, workspace: str) -> dict:
            return config

        async def build_command(self, config: dict, workspace: str) -> list[str]:
            command = ["miniwdl", "run", config["workflow_path"]]
            inputs_path = config.get("inputs_path")
            if inputs_path:
                command.extend(["--input", str(inputs_path)])
            return command

    monkeypatch.setattr(
        run_compiler_module,
        "get_adapter",
        lambda engine: FakeWDLAdapter(),
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project, workflow = await _create_external_project_and_workflow(
        db_session,
        external_root=workspace,
        engine=WorkflowEngine.WDL,
        workflow_content="version 1.0\nworkflow demo { input { String sample } }\n",
    )
    workflow.version = "3.24.0"
    workflow.schema_json = {
        "workflow_name": "demo",
        "inputs": [
            {
                "name": "sample",
                "type": "String",
                "value_kind": "scalar",
                "optional": False,
            }
        ],
    }
    await db_session.commit()
    await db_session.refresh(workflow)

    run = await _create_run_via_compiler(
        db_session,
        project=project,
        workflow=workflow,
        values={"sample": "S1"},
        options={"profile": "test,docker"},
    )

    argv = run.config["launch"]["argv"]
    assert "-r" not in argv
    assert "-profile" not in argv
    assert "revision" not in run.config
    assert "profile" not in run.config
    assert "profile" not in run.config["config_overrides"]


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
    monkeypatch.setattr(RunLifecycleService, "_binary_exists", lambda self, binary: True)

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


@pytest.mark.asyncio
async def test_retry_wdl_run_rewrites_outdir_to_new_run_results(
    db_session, monkeypatch, tmp_path
):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)
    monkeypatch.setattr(RunLifecycleService, "_binary_exists", lambda self, binary: True)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = await create_project(
        db_session,
        name=f"WDL Retry Project {uuid4()}",
        storage_mode="external",
        external_root_path=str(workspace),
    )
    workflow = await create_workflow(
        db_session,
        name="demo",
        engine=WorkflowEngine.WDL,
        content=(
            "version 1.0\n"
            "workflow demo {\n"
            "  input { String sample String outdir }\n"
            "}\n"
        ),
        schema_json={
            "workflow_name": "demo",
            "inputs": [
                {
                    "name": "sample",
                    "type": "String",
                    "value_kind": "scalar",
                    "optional": False,
                },
                {
                    "name": "outdir",
                    "type": "String",
                    "value_kind": "directory",
                    "is_internal": True,
                    "optional": True,
                },
            ],
        },
    )
    await bind_workflow(
        db_session, project_id=str(project.id), workflow_id=str(workflow.id)
    )

    dispatcher = NullDispatcher()
    service = RunService(db_session, dispatcher=dispatcher)
    run = await _create_run_via_compiler(
        db_session,
        project=project,
        workflow=workflow,
        values={"sample": "S1"},
        dispatcher=dispatcher,
    )
    source_results = str(run_results_root(project, run.run_id).resolve())
    run = await service.repo.update(
        run,
        status=RunStatus.FAILED.value,
        nextflow_run_name="failed_wdl",
    )

    retried = await service.retry_run(run.run_id)

    retried_results = str(run_results_root(project, retried.run_id).resolve())
    assert retried.run_id != run.run_id
    assert retried.config["params"]["outdir"] == retried_results
    assert retried.config["inputs"]["demo.outdir"] == retried_results
    assert source_results not in json.dumps(retried.config, sort_keys=True)

    engine_inputs_path = (
        run_home(project, retried.run_id) / "engine" / "wdl" / "inputs.json"
    )
    assert engine_inputs_path.exists()
    engine_inputs = json.loads(engine_inputs_path.read_text(encoding="utf-8"))
    assert engine_inputs["demo.outdir"] == retried_results
    assert source_results not in json.dumps(engine_inputs, sort_keys=True)


@pytest.mark.asyncio
async def test_retry_wdl_archive_manifest_uses_new_run_results(
    db_session, monkeypatch, tmp_path
):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)
    monkeypatch.setattr(RunLifecycleService, "_binary_exists", lambda self, binary: True)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = await create_project(
        db_session,
        name=f"WDL Retry Archive Project {uuid4()}",
        storage_mode="external",
        external_root_path=str(workspace),
    )
    workflow = await create_workflow(
        db_session,
        name="demo",
        engine=WorkflowEngine.WDL,
        content=(
            "version 1.0\n"
            "workflow demo {\n"
            "  input { String sample String outdir }\n"
            "}\n"
        ),
        schema_json={
            "workflow_name": "demo",
            "inputs": [
                {
                    "name": "sample",
                    "type": "String",
                    "value_kind": "scalar",
                    "optional": False,
                },
                {
                    "name": "outdir",
                    "type": "String",
                    "value_kind": "directory",
                    "is_internal": True,
                    "optional": True,
                },
            ],
        },
    )
    await bind_workflow(
        db_session, project_id=str(project.id), workflow_id=str(workflow.id)
    )

    dispatcher = NullDispatcher()
    service = RunService(db_session, dispatcher=dispatcher)
    run = await _create_run_via_compiler(
        db_session,
        project=project,
        workflow=workflow,
        values={"sample": "S1"},
        dispatcher=dispatcher,
    )
    source_results = str(run_results_root(project, run.run_id).resolve())
    run = await service.repo.update(
        run,
        status=RunStatus.FAILED.value,
        nextflow_run_name="failed_wdl",
    )

    retried = await service.retry_run(run.run_id)

    retried_results = str(run_results_root(project, retried.run_id).resolve())
    manifest_path = run_home(project, retried.run_id) / "audit" / "run.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == retried.run_id
    assert manifest["documents"]["engine_inputs"] == (
        f"runs/{retried.run_id}/engine/wdl/inputs.json"
    )
    assert manifest["resolved_inputs"]["params"]["outdir"] == retried_results
    assert manifest["resolved_inputs"]["inputs"]["demo.outdir"] == retried_results
    assert source_results not in json.dumps(manifest, sort_keys=True)
