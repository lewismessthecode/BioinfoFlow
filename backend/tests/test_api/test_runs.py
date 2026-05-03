from __future__ import annotations

from uuid import uuid4
from pathlib import Path

import pytest

from app.models.run import Run
from app.models.run import RunStatus
from app.models.workflow import WorkflowEngine, WorkflowSource
from app.path_layout import project_data_root, run_manifest_materialized_root
from app.services import run_service
from app.services.run_lifecycle_service import RunLifecycleService
from tests.support.path_contract import bind_workflow, create_project, create_workflow

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.asyncio
async def test_runs_endpoints(async_client, db_session, monkeypatch):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)
    # Resume/retry preflight checks for the engine binary; bypass it under test.
    monkeypatch.setattr(RunLifecycleService, "_binary_exists", lambda self, binary: True)

    project = await create_project(db_session, name="Run Project")
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version=str(uuid4()),
    )
    await bind_workflow(
        db_session, project_id=str(project.id), workflow_id=str(workflow.id)
    )

    payload = {
        "project_id": str(project.id),
        "workflow_id": str(workflow.id),
        "values": {"threads": 4},
    }

    create_resp = await async_client.post("/api/v1/runs", json=payload)
    assert create_resp.status_code == 202, create_resp.json()
    run_id = create_resp.json()["data"]["run_id"]

    list_resp = await async_client.get(
        f"/api/v1/runs?project_id={project.id}&limit=100"
    )
    assert list_resp.status_code == 200
    assert any(run["run_id"] == run_id for run in list_resp.json()["data"])

    get_resp = await async_client.get(f"/api/v1/runs/{run_id}")
    assert get_resp.status_code == 200

    cancel_resp = await async_client.post(f"/api/v1/runs/{run_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["data"]["status"] == RunStatus.CANCELLED.value

    create_resp = await async_client.post("/api/v1/runs", json=payload)
    run_id = create_resp.json()["data"]["run_id"]

    run = await run_service.RunService(db_session).get_run(run_id)
    await run_service.RunService(db_session).repo.update(
        run,
        status=RunStatus.FAILED.value,
        nextflow_run_name="nf-run",
    )

    resume_resp = await async_client.post(f"/api/v1/runs/{run_id}/resume", json={})
    assert resume_resp.status_code == 202

    retry_resp = await async_client.post(f"/api/v1/runs/{run_id}/retry", json={})
    assert retry_resp.status_code == 202


@pytest.mark.asyncio
async def test_runs_create_accepts_retry_and_timeout_policy(
    async_client, db_session, monkeypatch
):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)

    project = await create_project(db_session, name="Run Policy Project")
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version=str(uuid4()),
    )
    await bind_workflow(
        db_session, project_id=str(project.id), workflow_id=str(workflow.id)
    )

    payload = {
        "project_id": str(project.id),
        "workflow_id": str(workflow.id),
        "values": {"threads": 4},
        "options": {
            "max_retries": 2,
            "timeout_seconds": 900,
        },
    }

    resp = await async_client.post("/api/v1/runs", json=payload)

    assert resp.status_code == 202, resp.json()
    config = resp.json()["data"]["config"]
    assert config["policy"]["retry"]["max_retries"] == 2
    assert config["policy"]["timeout_seconds"] == 900


@pytest.mark.asyncio
async def test_runs_create_requires_bound_workflow_for_project(
    async_client, db_session, monkeypatch
):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)

    project = await create_project(db_session, name="Binding Project")
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version=str(uuid4()),
    )

    payload = {
        "project_id": str(project.id),
        "workflow_id": str(workflow.id),
        "values": {"threads": 4},
    }

    resp = await async_client.post("/api/v1/runs", json=payload)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "WORKFLOW_NOT_ENABLED_FOR_PROJECT"


@pytest.mark.asyncio
async def test_runs_create_returns_validation_error_for_invalid_payload(async_client):
    resp = await async_client.post(
        "/api/v1/runs",
        json={
            "project_id": "not-a-uuid",
            "workflow_id": "also-not-a-uuid",
        },
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_runs_create_rejects_missing_required_form_values(
    async_client, db_session, monkeypatch
):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)

    project = await create_project(db_session, name="Required Values Project")
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version=str(uuid4()),
        schema_json={
            "inputs": [
                {
                    "name": "reads",
                    "type": "File",
                    "value_kind": "file",
                    "optional": False,
                }
            ]
        },
    )
    await bind_workflow(
        db_session, project_id=str(project.id), workflow_id=str(workflow.id)
    )

    resp = await async_client.post(
        "/api/v1/runs",
        json={
            "project_id": str(project.id),
            "workflow_id": str(workflow.id),
            "values": {},
        },
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_FORM_VALUES"


@pytest.mark.asyncio
async def test_runs_create_rejects_unknown_form_field_ids(
    async_client, db_session, monkeypatch
):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)

    project = await create_project(db_session, name="Unknown Fields Project")
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version=str(uuid4()),
        schema_json={
            "inputs": [
                {
                    "name": "threads",
                    "type": "Int",
                    "value_kind": "scalar",
                    "optional": True,
                }
            ]
        },
    )
    await bind_workflow(
        db_session, project_id=str(project.id), workflow_id=str(workflow.id)
    )

    resp = await async_client.post(
        "/api/v1/runs",
        json={
            "project_id": str(project.id),
            "workflow_id": str(workflow.id),
            "values": {"bogus": "value"},
        },
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_FORM_VALUES"


@pytest.mark.asyncio
async def test_runs_create_rejects_paths_outside_field_allow_roots(
    async_client, db_session, monkeypatch
):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)

    project = await create_project(db_session, name="Reference Path Project")
    forbidden = project_data_root(project) / "refs" / "hg38.fa"
    forbidden.parent.mkdir(parents=True, exist_ok=True)
    forbidden.write_text(">chr1\nACGT", encoding="utf-8")

    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.WDL,
        version=str(uuid4()),
        schema_json={
            "workflow_name": "demo",
            "inputs": [
                {
                    "name": "reference",
                    "type": "File",
                    "value_kind": "file",
                    "source_hint": "reference",
                    "allow_roots": ["reference"],
                    "optional": False,
                }
            ],
        },
    )
    await bind_workflow(
        db_session, project_id=str(project.id), workflow_id=str(workflow.id)
    )

    resp = await async_client.post(
        "/api/v1/runs",
        json={
            "project_id": str(project.id),
            "workflow_id": str(workflow.id),
            "values": {"reference": str(forbidden)},
        },
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "PATH_OUTSIDE_ALLOWED_ROOT"


@pytest.mark.asyncio
async def test_runs_actions_return_conflict_for_illegal_status_transitions(
    async_client, db_session, monkeypatch
):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)

    project = await create_project(db_session, name="Conflict Project")
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version=str(uuid4()),
        source_ref="local",
        entrypoint_relpath="main.nf",
        bundle_kind="local_bundle",
        content="workflow { }",
    )
    await bind_workflow(
        db_session, project_id=str(project.id), workflow_id=str(workflow.id)
    )

    completed_run = Run(
        run_id="run_completed_conflict",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={"params": {"outdir": "results"}},
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    queued_run = Run(
        run_id="run_queued_conflict",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.QUEUED.value,
        config={"params": {"outdir": "results"}},
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    db_session.add_all([completed_run, queued_run])
    await db_session.commit()

    cancel_resp = await async_client.post(f"/api/v1/runs/{completed_run.run_id}/cancel")
    assert cancel_resp.status_code == 409
    assert cancel_resp.json()["error"]["code"] == "CONFLICT"

    resume_resp = await async_client.post(f"/api/v1/runs/{completed_run.run_id}/resume")
    assert resume_resp.status_code == 409
    assert resume_resp.json()["error"]["code"] == "CONFLICT"

    retry_resp = await async_client.post(f"/api/v1/runs/{queued_run.run_id}/retry")
    assert retry_resp.status_code == 409
    assert retry_resp.json()["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_runs_create_requires_explicit_manifest_documents(
    async_client, db_session
):
    project = await create_project(db_session, name="Bundle Defaults Project")

    workflow_resp = await async_client.post(
        "/api/v1/workflows",
        json={
            "source": "local",
            "engine": "nextflow",
            "bundle_path": str(REPO_ROOT / "demo" / "rnaseq-quant-mini"),
        },
    )
    assert workflow_resp.status_code == 201, workflow_resp.json()
    workflow_id = workflow_resp.json()["data"]["id"]

    await bind_workflow(
        db_session,
        project_id=str(project.id),
        workflow_id=str(workflow_id),
    )

    run_resp = await async_client.post(
        "/api/v1/runs",
        json={
            "project_id": str(project.id),
            "workflow_id": workflow_id,
            "values": {},
        },
    )

    assert run_resp.status_code == 422, run_resp.json()
    assert run_resp.json()["error"]["code"] == "INVALID_FORM_VALUES"


@pytest.mark.asyncio
async def test_runs_uploads_and_snapshots_manifest_documents(async_client, db_session):
    project = await create_project(db_session, name="Uploaded Manifest Project")

    workflow_resp = await async_client.post(
        "/api/v1/workflows",
        json={
            "source": "local",
            "engine": "nextflow",
            "bundle_path": str(REPO_ROOT / "demo" / "rnaseq-quant-mini"),
        },
    )
    assert workflow_resp.status_code == 201, workflow_resp.json()
    workflow_id = workflow_resp.json()["data"]["id"]

    await bind_workflow(
        db_session,
        project_id=str(project.id),
        workflow_id=str(workflow_id),
    )

    manifest_bytes = (
        "sample,fastq_1,fastq_2,strandedness\n"
        "sampleA,/abs/deliveries/sampleA_R1.fq.gz,/abs/deliveries/sampleA_R2.fq.gz,auto\n"
    ).encode("utf-8")
    upload_resp = await async_client.post(
        "/api/v1/runs/uploads",
        data={"project_id": str(project.id)},
        files={"file": ("samplesheet.csv", manifest_bytes, "text/csv")},
    )
    assert upload_resp.status_code == 201, upload_resp.json()
    uploaded_uri = upload_resp.json()["data"]["uri"]

    run_resp = await async_client.post(
        "/api/v1/runs",
        json={
            "project_id": str(project.id),
            "workflow_id": workflow_id,
            "values": {
                "samplesheet": uploaded_uri,
            },
        },
    )
    assert run_resp.status_code == 202, run_resp.json()
    run_data = run_resp.json()["data"]

    expected_manifest = (
        run_manifest_materialized_root(project, run_data["run_id"])
        / "attachments"
        / "samplesheet"
        / "samplesheet.csv"
    )
    assert run_data["config"]["params"]["genome"] == "GRCh38"
    assert run_data["config"]["params"]["samplesheet"] == str(expected_manifest)
    assert expected_manifest.read_bytes() == manifest_bytes


@pytest.mark.asyncio
async def test_run_endpoints_return_not_found_for_missing_run(async_client):
    missing_run_id = "run_missing"

    get_resp = await async_client.get(f"/api/v1/runs/{missing_run_id}")
    assert get_resp.status_code == 404
    assert get_resp.json()["error"]["code"] == "NOT_FOUND"

    cancel_resp = await async_client.post(f"/api/v1/runs/{missing_run_id}/cancel")
    assert cancel_resp.status_code == 404
    assert cancel_resp.json()["error"]["code"] == "NOT_FOUND"

    resume_resp = await async_client.post(f"/api/v1/runs/{missing_run_id}/resume")
    assert resume_resp.status_code == 404
    assert resume_resp.json()["error"]["code"] == "NOT_FOUND"

    retry_resp = await async_client.post(f"/api/v1/runs/{missing_run_id}/retry")
    assert retry_resp.status_code == 404
    assert retry_resp.json()["error"]["code"] == "NOT_FOUND"

    delete_resp = await async_client.delete(f"/api/v1/runs/{missing_run_id}")
    assert delete_resp.status_code == 404
    assert delete_resp.json()["error"]["code"] == "NOT_FOUND"
