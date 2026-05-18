from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.project import Project
from app.models.run import RunStatus
from app.models.workflow import Workflow, WorkflowEngine
from app.schemas.run import RunCreate
from app.services import run_service
from app.services.batch_service import BatchService
from tests.support.path_contract import bind_workflow, create_project, create_workflow


@pytest.fixture(autouse=True)
def _phase6_batch_guards(monkeypatch):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        run_service.RunLifecycleService,
        "_require_engine_binary",
        lambda self, engine: None,
    )


async def _seed_project_and_workflow(
    db_session, *, workspace
) -> tuple[Project, Workflow]:
    project = await create_project(
        db_session,
        name=f"Project {uuid4()}",
        storage_mode="external",
        external_root_path=str(workspace),
    )
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        engine=WorkflowEngine.NEXTFLOW,
        content="workflow { }\n",
    )
    await bind_workflow(
        db_session, project_id=str(project.id), workflow_id=str(workflow.id)
    )
    return project, workflow


def _run_spec(project: Project, workflow: Workflow, **overrides) -> RunCreate:
    payload = {
        "project_id": str(project.id),
        "workflow_id": str(workflow.id),
        "values": {},
    }
    payload.update(overrides)
    return RunCreate.model_validate(payload)


@pytest.mark.asyncio
async def test_create_batch_returns_mixed_queue_and_failure_results(
    db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project, workflow = await _seed_project_and_workflow(
        db_session, workspace=workspace
    )
    data_root = workspace / "data"
    data_root.mkdir(parents=True, exist_ok=True)
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
    service = BatchService(db_session)

    result = await service.create_batch(
        project_id=str(project.id),
        runs=[
            _run_spec(project, workflow, values={"samplesheet": "samplesheet.csv"}),
            _run_spec(project, workflow, values={"samplesheet": "missing.csv"}),
        ],
        description="phase 6 batch",
    )

    assert result["total"] == 2
    assert result["queued"] == 1
    assert result["failed"] == 1
    assert len(result["runs"]) == 2
    assert result["runs"][0]["status"] == RunStatus.QUEUED.value
    assert result["runs"][0]["run_id"].startswith("run_")
    assert result["runs"][1]["status"] == RunStatus.FAILED.value
    assert result["runs"][1]["error_code"] == "COMPILE_ERROR"
    assert result["runs"][1]["error"] == "Run input validation failed."

    batch = await service.get_batch(result["batch_id"])
    assert batch is not None
    assert batch["total_runs"] == 2
    assert batch["failed_runs"] == 1


@pytest.mark.asyncio
async def test_update_batch_status_marks_active_batches_running(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project, workflow = await _seed_project_and_workflow(
        db_session, workspace=workspace
    )
    service = BatchService(db_session)

    created = await service.create_batch(
        project_id=str(project.id),
        runs=[
            _run_spec(project, workflow),
            _run_spec(project, workflow),
        ],
    )
    batch = await service.get_batch(created["batch_id"])

    assert created["status"] == "running"
    assert batch is not None
    assert batch["status"] == "running"
    assert batch["completed_runs"] == 0
    assert batch["failed_runs"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([RunStatus.COMPLETED.value, RunStatus.COMPLETED.value], "completed"),
        ([RunStatus.FAILED.value, RunStatus.FAILED.value], "failed"),
        ([RunStatus.COMPLETED.value, RunStatus.FAILED.value], "partial"),
    ],
)
async def test_update_batch_status_aggregates_terminal_run_states(
    db_session, tmp_path, statuses, expected
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project, workflow = await _seed_project_and_workflow(
        db_session, workspace=workspace
    )
    service = BatchService(db_session)

    created = await service.create_batch(
        project_id=str(project.id),
        runs=[
            _run_spec(project, workflow),
            _run_spec(project, workflow),
        ],
    )

    for run_entry, status in zip(created["runs"], statuses, strict=True):
        run = await service._run_service.repo.get_by_run_id(run_entry["run_id"])
        await service._run_service.repo.update(run, status=status)

    await service.update_batch_status(created["batch_id"])
    batch = await service.get_batch(created["batch_id"])

    assert batch is not None
    assert batch["status"] == expected
    assert batch["completed_runs"] == statuses.count(RunStatus.COMPLETED.value)
    assert batch["failed_runs"] == statuses.count(RunStatus.FAILED.value)


@pytest.mark.asyncio
async def test_cancel_batch_cancels_active_runs_and_updates_batch_status(
    db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project, workflow = await _seed_project_and_workflow(
        db_session, workspace=workspace
    )
    service = BatchService(db_session)

    created = await service.create_batch(
        project_id=str(project.id),
        runs=[
            _run_spec(project, workflow),
            _run_spec(project, workflow),
        ],
    )

    cancelled = await service.cancel_batch(created["batch_id"])

    assert cancelled["status"] == "cancelled"
    assert cancelled["cancelled_runs"] == 2
    batch = await service.get_batch(created["batch_id"])
    assert batch is not None
    assert batch["status"] == "cancelled"
