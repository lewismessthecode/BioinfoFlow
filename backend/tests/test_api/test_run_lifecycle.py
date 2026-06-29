from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.models.project import Project
from app.models.project_workflow_binding import ProjectWorkflowBinding
from app.models.run import Run, RunStatus
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.services import run_service


@pytest.fixture(autouse=True)
def _phase0_run_guards(monkeypatch):
    monkeypatch.setattr(run_service.task_runner, "submit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        run_service.RunLifecycleService,
        "_require_engine_binary",
        lambda self, engine: None,
    )


async def _seed_project_and_workflow(
    db_session,
    *,
    workspace: Path,
    engine: WorkflowEngine = WorkflowEngine.NEXTFLOW,
    schema_json: dict | None = None,
    bind: bool = True,
) -> tuple[Project, Workflow]:
    project = Project(
        name=f"Project {uuid4()}", storage_mode="external", external_root_path=str(workspace), user_id="dev"
    )
    workflow = Workflow(
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=engine,
        version=str(uuid4()),
        schema_json=schema_json,
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)

    if bind:
        db_session.add(
            ProjectWorkflowBinding(
                project_id=str(project.id),
                workflow_id=str(workflow.id),
            )
        )
        await db_session.commit()

    return project, workflow


def _run_payload(project: Project, workflow: Workflow, **overrides) -> dict:
    payload = {
        "project_id": str(project.id),
        "workflow_id": str(workflow.id),
        "values": {"threads": 4},
    }
    payload.update(overrides)
    return payload


async def _mark_run_failed(
    db_session,
    *,
    run_id: str,
    nextflow_run_name: str | None = "nf-run",
) -> Run:
    service = run_service.RunService(db_session)
    run = await service.get_run(run_id)
    assert run is not None
    return await service.repo.update(
        run,
        status=RunStatus.FAILED.value,
        nextflow_run_name=nextflow_run_name,
    )


class TestRunLifecycle:
    @pytest.mark.asyncio
    async def test_create_run_returns_202_with_queued_status(
        self, async_client, db_session, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project, workflow = await _seed_project_and_workflow(
            db_session, workspace=workspace
        )

        resp = await async_client.post(
            "/api/v1/runs",
            json=_run_payload(project, workflow),
        )

        assert resp.status_code == 202, resp.json()
        data = resp.json()["data"]
        assert data["status"] == RunStatus.QUEUED.value
        assert data["run_id"].startswith("run_")
        assert "outdir" in data["config"]["params"]

    @pytest.mark.asyncio
    async def test_create_run_auto_binds_unbound_workflow(
        self, async_client, db_session, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project, workflow = await _seed_project_and_workflow(
            db_session,
            workspace=workspace,
            bind=False,
        )

        resp = await async_client.post(
            "/api/v1/runs",
            json=_run_payload(project, workflow),
        )

        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "WORKFLOW_NOT_ENABLED_FOR_PROJECT"

    @pytest.mark.asyncio
    async def test_create_run_rejects_legacy_workspace_field(
        self, async_client, db_session, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project, workflow = await _seed_project_and_workflow(
            db_session, workspace=workspace
        )

        resp = await async_client.post(
            "/api/v1/runs",
            json=_run_payload(project, workflow, workspace="missing"),
        )

        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_create_run_returns_validation_error_for_invalid_payload(
        self, async_client
    ):
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
    async def test_list_runs_includes_created_run(
        self, async_client, db_session, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project, workflow = await _seed_project_and_workflow(
            db_session, workspace=workspace
        )
        create_resp = await async_client.post(
            "/api/v1/runs",
            json=_run_payload(project, workflow),
        )
        run_id = create_resp.json()["data"]["run_id"]

        list_resp = await async_client.get(
            f"/api/v1/runs?project_id={project.id}&limit=100"
        )

        assert list_resp.status_code == 200
        assert any(run["run_id"] == run_id for run in list_resp.json()["data"])

    @pytest.mark.asyncio
    async def test_get_run_returns_created_run(
        self, async_client, db_session, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project, workflow = await _seed_project_and_workflow(
            db_session, workspace=workspace
        )
        create_resp = await async_client.post(
            "/api/v1/runs",
            json=_run_payload(project, workflow),
        )
        run_id = create_resp.json()["data"]["run_id"]

        get_resp = await async_client.get(f"/api/v1/runs/{run_id}")

        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["run_id"] == run_id

    @pytest.mark.asyncio
    async def test_cancel_queued_run(self, async_client, db_session, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project, workflow = await _seed_project_and_workflow(
            db_session, workspace=workspace
        )
        create_resp = await async_client.post(
            "/api/v1/runs",
            json=_run_payload(project, workflow),
        )
        run_id = create_resp.json()["data"]["run_id"]

        cancel_resp = await async_client.post(f"/api/v1/runs/{run_id}/cancel")

        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["data"]["status"] == RunStatus.CANCELLED.value

    @pytest.mark.asyncio
    async def test_cancel_completed_run_is_conflict(
        self, async_client, db_session, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project, workflow = await _seed_project_and_workflow(
            db_session, workspace=workspace
        )
        run = Run(
            run_id="run_completed_cancel",
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

        resp = await async_client.post(f"/api/v1/runs/{run.run_id}/cancel")

        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    @pytest.mark.asyncio
    async def test_resume_failed_nextflow_run_returns_202_with_new_run(
        self, async_client, db_session, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project, workflow = await _seed_project_and_workflow(
            db_session, workspace=workspace
        )
        create_resp = await async_client.post(
            "/api/v1/runs",
            json=_run_payload(project, workflow),
        )
        original_run_id = create_resp.json()["data"]["run_id"]
        await _mark_run_failed(db_session, run_id=original_run_id)

        resp = await async_client.post(
            f"/api/v1/runs/{original_run_id}/resume", json={}
        )

        assert resp.status_code == 202
        data = resp.json()["data"]
        assert data["run_id"] == original_run_id
        assert data["new_run_id"] != original_run_id
        assert data["status"] == RunStatus.QUEUED.value

    @pytest.mark.asyncio
    async def test_resume_requires_failed_status(
        self, async_client, db_session, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project, workflow = await _seed_project_and_workflow(
            db_session, workspace=workspace
        )
        create_resp = await async_client.post(
            "/api/v1/runs",
            json=_run_payload(project, workflow),
        )
        run_id = create_resp.json()["data"]["run_id"]

        resp = await async_client.post(f"/api/v1/runs/{run_id}/resume", json={})

        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    @pytest.mark.asyncio
    async def test_resume_failed_wdl_run_returns_best_effort_metadata(
        self, async_client, db_session, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project, workflow = await _seed_project_and_workflow(
            db_session,
            workspace=workspace,
            engine=WorkflowEngine.WDL,
        )
        run = Run(
            run_id="run_failed_wdl_resume",
            project_id=str(project.id),
            workflow_id=str(workflow.id),
            status=RunStatus.FAILED.value,
            config={
                "params": {},
                "inputs": {},
                "config_overrides": {},
                "runtime": {
                    "wdl_work_dir": "runs/run_failed_wdl_resume/engine/wdl/work"
                },
            },
            samples_count=0,
            tasks_total=0,
            tasks_completed=0,
        )
        db_session.add(run)
        await db_session.commit()
        (
            workspace / "runs" / run.run_id / "engine" / "wdl" / "work"
        ).mkdir(parents=True)

        resp = await async_client.post(f"/api/v1/runs/{run.run_id}/resume", json={})

        assert resp.status_code == 202
        data = resp.json()["data"]
        assert data["run_id"] == run.run_id
        assert data["new_run_id"] != run.run_id
        assert data["resume_type"] == "best_effort"

    @pytest.mark.asyncio
    async def test_retry_creates_new_run(self, async_client, db_session, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project, workflow = await _seed_project_and_workflow(
            db_session, workspace=workspace
        )
        create_resp = await async_client.post(
            "/api/v1/runs",
            json=_run_payload(project, workflow),
        )
        original_run_id = create_resp.json()["data"]["run_id"]
        await _mark_run_failed(db_session, run_id=original_run_id)

        resp = await async_client.post(f"/api/v1/runs/{original_run_id}/retry", json={})

        assert resp.status_code == 202, resp.json()
        data = resp.json()["data"]
        assert data["run_id"] == original_run_id
        assert data["new_run_id"] != original_run_id
        assert data["status"] == RunStatus.QUEUED.value

    @pytest.mark.asyncio
    async def test_retry_requires_failed_status(
        self, async_client, db_session, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project, workflow = await _seed_project_and_workflow(
            db_session, workspace=workspace
        )
        create_resp = await async_client.post(
            "/api/v1/runs",
            json=_run_payload(project, workflow),
        )
        run_id = create_resp.json()["data"]["run_id"]

        resp = await async_client.post(f"/api/v1/runs/{run_id}/retry", json={})

        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    @pytest.mark.asyncio
    async def test_get_dag_returns_stored_dag_when_present(
        self, async_client, db_session, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project, workflow = await _seed_project_and_workflow(
            db_session,
            workspace=workspace,
            schema_json={"tasks": [], "dependencies": []},
        )
        run = Run(
            run_id="run_with_dag",
            project_id=str(project.id),
            workflow_id=str(workflow.id),
            status=RunStatus.QUEUED.value,
            config={
                "params": {"outdir": "results"},
                "dag": {"nodes": [{"id": "task-1"}], "edges": []},
            },
            samples_count=0,
            tasks_total=0,
            tasks_completed=0,
        )
        db_session.add(run)
        await db_session.commit()

        resp = await async_client.get(f"/api/v1/runs/{run.run_id}/dag")

        assert resp.status_code == 200
        assert resp.json()["data"] == {"nodes": [{"id": "task-1"}], "edges": []}

    @pytest.mark.asyncio
    async def test_get_dag_falls_back_to_schema(
        self, async_client, db_session, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        schema = {
            "tasks": [
                {
                    "name": "FASTQC",
                    "inputs": ["reads"],
                    "outputs": ["report"],
                    "container": "biocontainers/fastqc:0.12.1",
                }
            ],
            "dependencies": [],
        }
        project, workflow = await _seed_project_and_workflow(
            db_session,
            workspace=workspace,
            schema_json=schema,
        )
        run = Run(
            run_id="run_schema_fallback",
            project_id=str(project.id),
            workflow_id=str(workflow.id),
            status=RunStatus.QUEUED.value,
            config={"params": {"outdir": "results"}},
            samples_count=0,
            tasks_total=1,
            tasks_completed=0,
        )
        db_session.add(run)
        await db_session.commit()

        workflow_resp = await async_client.get(f"/api/v1/workflows/{workflow.id}/dag")
        run_resp = await async_client.get(f"/api/v1/runs/{run.run_id}/dag")

        assert workflow_resp.status_code == 200
        assert run_resp.status_code == 200
        assert run_resp.json()["data"] == workflow_resp.json()["data"]

    @pytest.mark.asyncio
    async def test_get_logs_respects_tail(self, async_client, db_session, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project, workflow = await _seed_project_and_workflow(
            db_session, workspace=workspace
        )
        log_dir = workspace / ".bioinfoflow" / "run_tail_logs"
        log_dir.mkdir(parents=True)
        (log_dir / "run.log").write_text(
            "\n".join(f"line-{idx}" for idx in range(1, 11)) + "\n",
            encoding="utf-8",
        )
        run = Run(
            run_id="run_tail_logs",
            project_id=str(project.id),
            workflow_id=str(workflow.id),
            status=RunStatus.COMPLETED.value,
            config={
                "log_path": ".bioinfoflow/run_tail_logs/run.log",
                "params": {"outdir": "results"},
            },
            samples_count=0,
            tasks_total=0,
            tasks_completed=0,
        )
        db_session.add(run)
        await db_session.commit()

        resp = await async_client.get(f"/api/v1/runs/{run.run_id}/logs?tail=5")

        assert resp.status_code == 200
        assert [entry["message"] for entry in resp.json()["data"]["logs"]] == [
            "line-6",
            "line-7",
            "line-8",
            "line-9",
            "line-10",
        ]

    @pytest.mark.asyncio
    async def test_get_logs_tail_zero_returns_all_lines(
        self, async_client, db_session, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project, workflow = await _seed_project_and_workflow(
            db_session, workspace=workspace
        )
        log_dir = workspace / ".bioinfoflow" / "run_all_logs"
        log_dir.mkdir(parents=True)
        (log_dir / "run.log").write_text("first\nsecond\nthird\n", encoding="utf-8")
        run = Run(
            run_id="run_all_logs",
            project_id=str(project.id),
            workflow_id=str(workflow.id),
            status=RunStatus.COMPLETED.value,
            config={
                "log_path": ".bioinfoflow/run_all_logs/run.log",
                "params": {"outdir": "results"},
            },
            samples_count=0,
            tasks_total=0,
            tasks_completed=0,
        )
        db_session.add(run)
        await db_session.commit()

        resp = await async_client.get(f"/api/v1/runs/{run.run_id}/logs?tail=0")

        assert resp.status_code == 200
        assert [entry["message"] for entry in resp.json()["data"]["logs"]] == [
            "first",
            "second",
            "third",
        ]
