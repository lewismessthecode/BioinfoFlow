from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.project import Project
from app.models.project_workflow_binding import ProjectWorkflowBinding
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.services import run_service


@pytest.fixture(autouse=True)
def _phase6_api_guards(monkeypatch):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        run_service.RunLifecycleService,
        "_require_engine_binary",
        lambda self, engine: None,
    )


async def _seed_project_and_workflow(
    db_session,
    *,
    workspace,
) -> tuple[Project, Workflow]:
    project = Project(
        name=f"Project {uuid4()}", storage_mode="external", external_root_path=str(workspace), user_id="dev"
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
    db_session.add(
        ProjectWorkflowBinding(
            project_id=str(project.id),
            workflow_id=str(workflow.id),
        )
    )
    await db_session.commit()
    return project, workflow


def _batch_payload(project: Project, workflow: Workflow, **overrides) -> dict:
    payload = {
        "project_id": str(project.id),
        "runs": [
            {
                "workflow_id": str(workflow.id),
                "values": {},
            },
            {
                "workflow_id": str(workflow.id),
                "values": {},
            },
        ],
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_batch_api_create_get_and_cancel(async_client, db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project, workflow = await _seed_project_and_workflow(
        db_session, workspace=workspace
    )

    create_resp = await async_client.post(
        "/api/v1/runs/batch",
        json=_batch_payload(project, workflow),
    )

    assert create_resp.status_code == 202
    created = create_resp.json()["data"]
    assert created["total"] == 2
    assert created["queued"] == 2
    batch_id = created["batch_id"]

    get_resp = await async_client.get(f"/api/v1/runs/batch/{batch_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["batch_id"] == batch_id

    cancel_resp = await async_client.post(f"/api/v1/runs/batch/{batch_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["data"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_batch_api_reports_partial_submission_failures(
    async_client, db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project, workflow = await _seed_project_and_workflow(
        db_session, workspace=workspace
    )
    (workspace / "data").mkdir(parents=True, exist_ok=True)
    (workspace / "data" / "samplesheet.csv").write_text(
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
    payload = _batch_payload(
        project,
        workflow,
        runs=[
            {
                "workflow_id": str(workflow.id),
                "values": {"samplesheet": "samplesheet.csv"},
            },
            {
                "workflow_id": str(workflow.id),
                "values": {"samplesheet": "missing.csv"},
            },
        ],
    )

    resp = await async_client.post("/api/v1/runs/batch", json=payload)

    assert resp.status_code == 202
    data = resp.json()["data"]
    assert data["queued"] == 1
    assert data["failed"] == 1


@pytest.mark.asyncio
async def test_batch_api_validates_minimum_batch_size(
    async_client, db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project, workflow = await _seed_project_and_workflow(
        db_session, workspace=workspace
    )
    payload = _batch_payload(
        project,
        workflow,
        runs=[
            {
                "workflow_id": str(workflow.id),
                "values": {},
            }
        ],
    )

    resp = await async_client.post("/api/v1/runs/batch", json=payload)

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_notifications_api_create_list_and_delete(
    async_client, db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project, _workflow = await _seed_project_and_workflow(
        db_session, workspace=workspace
    )

    create_resp = await async_client.post(
        "/api/v1/notifications",
        json={
            "project_id": str(project.id),
            "channel": "webhook",
            "trigger": "on_complete",
            "config": {"url": "https://example.test/hook"},
            "enabled": True,
        },
    )

    assert create_resp.status_code == 201
    notification_id = create_resp.json()["data"]["id"]

    list_resp = await async_client.get(f"/api/v1/notifications?project_id={project.id}")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["data"]) == 1
    assert list_resp.json()["data"][0]["id"] == notification_id

    delete_resp = await async_client.delete(f"/api/v1/notifications/{notification_id}")
    assert delete_resp.status_code == 200

    list_resp = await async_client.get(f"/api/v1/notifications?project_id={project.id}")
    assert list_resp.status_code == 200
    assert list_resp.json()["data"] == []
