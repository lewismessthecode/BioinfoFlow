from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.project import Project
from app.models.run import Run
from app.models.run import RunStatus
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.path_layout import run_audit_root, run_home, run_results_root


@pytest.mark.asyncio
async def test_runs_cleanup_and_audit_endpoints(async_client, db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project = Project(
        name="Cleanup Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
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

    run = Run(
        run_id="run_cleanup_api",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={"params": {"outdir": "results"}},
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )

    db_session.add(run)
    await db_session.commit()

    archive_dir = run_home(project, run.run_id)
    audit_dir = run_audit_root(project, run.run_id)
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "run.manifest.json").write_text("{}", encoding="utf-8")

    cleanup_resp = await async_client.post(f"/api/v1/runs/{run.run_id}/cleanup")
    assert cleanup_resp.status_code == 200
    assert cleanup_resp.json()["data"]["deleted"] == [str(archive_dir)]
    assert archive_dir.exists() is False

    audit_resp = await async_client.get(f"/api/v1/runs/{run.run_id}/audit")
    assert audit_resp.status_code == 200
    actions = [entry["action"] for entry in audit_resp.json()["data"]]
    assert "run.cleanup" in actions


@pytest.mark.asyncio
async def test_runs_artifact_endpoints_return_not_found_when_missing(
    async_client, db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project = Project(
        name="Artifacts Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
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

    run = Run(
        run_id="run_missing_artifacts",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={"params": {"outdir": "missing-results"}},
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )

    db_session.add(run)
    await db_session.commit()

    logs_resp = await async_client.get(f"/api/v1/runs/{run.run_id}/logs")
    assert logs_resp.status_code == 404
    assert logs_resp.json()["error"]["code"] == "NOT_FOUND"

    dag_resp = await async_client.get(f"/api/v1/runs/{run.run_id}/dag")
    assert dag_resp.status_code == 404
    assert dag_resp.json()["error"]["code"] == "NOT_FOUND"

    outputs_resp = await async_client.get(f"/api/v1/runs/{run.run_id}/outputs")
    assert outputs_resp.status_code == 404
    assert outputs_resp.json()["error"]["code"] == "NOT_FOUND"

    download_resp = await async_client.get(
        f"/api/v1/runs/{run.run_id}/outputs/download"
    )
    assert download_resp.status_code == 404
    assert download_resp.json()["error"]["code"] == "FILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_runs_artifact_endpoints_return_success_when_files_exist(
    async_client, db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = Project(
        name="Artifact Success Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
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

    log_dir = run_audit_root(project, "run_success_artifacts")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "run.log"
    log_path.write_text("started\nfinished\n", encoding="utf-8")

    output_dir = run_results_root(project, "run_success_artifacts")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.txt"
    report_path.write_text("ok\n", encoding="utf-8")

    run = Run(
        run_id="run_success_artifacts",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={
            "log_path": "runs/run_success_artifacts/audit/run.log",
            "params": {"outdir": "results"},
            "dag": {"nodes": [{"id": "task-1"}], "edges": []},
        },
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    db_session.add(run)
    await db_session.commit()

    logs_resp = await async_client.get(f"/api/v1/runs/{run.run_id}/logs")
    assert logs_resp.status_code == 200
    assert [entry["message"] for entry in logs_resp.json()["data"]["logs"]] == [
        "started",
        "finished",
    ]

    dag_resp = await async_client.get(f"/api/v1/runs/{run.run_id}/dag")
    assert dag_resp.status_code == 200
    assert dag_resp.json()["data"]["nodes"] == [{"id": "task-1"}]

    outputs_resp = await async_client.get(f"/api/v1/runs/{run.run_id}/outputs")
    assert outputs_resp.status_code == 200
    assert outputs_resp.json()["data"]["files"][0]["path"] == (
        f"runs/{run.run_id}/results/report.txt"
    )

    download_resp = await async_client.get(
        f"/api/v1/runs/{run.run_id}/outputs/download"
    )
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"] == "application/gzip"


@pytest.mark.asyncio
async def test_run_outputs_fall_back_to_configured_outdir_when_default_results_root_is_missing(
    async_client, db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = Project(
        name="Artifact Fallback Project",
        storage_mode="external",
        external_root_path=str(workspace),
        user_id="dev",
    )
    workflow = Workflow(
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.WDL,
        version=str(uuid4()),
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)

    legacy_output_dir = workspace / "legacy-results"
    legacy_output_dir.mkdir(parents=True, exist_ok=True)
    (legacy_output_dir / "summary.tsv").write_text("ok\n", encoding="utf-8")

    run = Run(
        run_id="run_results_fallback",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={
            "params": {"outdir": "legacy-results"},
            "request": {"params": {"outdir": "legacy-results"}},
        },
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    db_session.add(run)
    await db_session.commit()

    outputs_resp = await async_client.get(f"/api/v1/runs/{run.run_id}/outputs")

    assert outputs_resp.status_code == 200
    assert outputs_resp.json()["data"]["files"] == [
        {
            "name": "summary.tsv",
            "path": "legacy-results/summary.tsv",
            "uri": None,
            "size_bytes": 3,
            "type": "file",
        }
    ]


@pytest.mark.asyncio
async def test_new_schema_run_outputs_do_not_fall_back_to_configured_outdir(
    async_client, db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = Project(
        name="Artifact No Fallback Project",
        storage_mode="external",
        external_root_path=str(workspace),
        user_id="dev",
    )
    workflow = Workflow(
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.WDL,
        version=str(uuid4()),
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)

    legacy_output_dir = workspace / "legacy-results"
    legacy_output_dir.mkdir(parents=True, exist_ok=True)
    (legacy_output_dir / "summary.tsv").write_text("ok\n", encoding="utf-8")

    run = Run(
        run_id="run_results_no_fallback",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={
            "config_schema_version": 1,
            "params": {"outdir": "legacy-results"},
            "request": {"params": {"outdir": "legacy-results"}},
        },
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    db_session.add(run)
    await db_session.commit()

    outputs_resp = await async_client.get(f"/api/v1/runs/{run.run_id}/outputs")

    assert outputs_resp.status_code == 404
    assert outputs_resp.json()["error"]["code"] == "NOT_FOUND"
