from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.image import DockerImage, ImageStatus
from app.models.project import Project
from app.models.run import Run, RunStatus
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource


@pytest.mark.asyncio
async def test_stats_dashboard_returns_correct_shape(async_client):
    """Response envelope has the expected top-level keys and sub-keys."""
    resp = await async_client.get("/api/v1/stats")
    assert resp.status_code == 200

    body = resp.json()
    assert body["success"] is True
    assert "data" in body
    assert "meta" in body

    data = body["data"]
    for key in ("runs", "workflows", "images", "projects", "recent_runs"):
        assert key in data

    runs = data["runs"]
    for field in (
        "total",
        "running",
        "completed",
        "failed",
        "queued",
        "pending",
        "cancelled",
    ):
        assert field in runs
        assert isinstance(runs[field], int)

    assert "total" in data["workflows"]
    assert "total" in data["projects"]

    images = data["images"]
    for field in ("total", "local", "remote", "pulling"):
        assert field in images
        assert isinstance(images[field], int)

    assert isinstance(data["recent_runs"], list)


@pytest.mark.asyncio
async def test_stats_dashboard_counts_reflect_zero_for_integers(async_client):
    """All count fields are non-negative integers (basic sanity on shape)."""
    resp = await async_client.get("/api/v1/stats")
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert data["runs"]["total"] >= 0
    assert data["workflows"]["total"] >= 0
    assert data["projects"]["total"] >= 0
    assert data["images"]["total"] >= 0


@pytest.mark.asyncio
async def test_stats_dashboard_counts_increase_after_seeding(
    async_client, db_session, tmp_path
):
    """Stats counts increase after inserting projects, workflows, runs, and images."""
    # Capture baseline counts
    baseline_resp = await async_client.get("/api/v1/stats")
    assert baseline_resp.status_code == 200
    baseline = baseline_resp.json()["data"]

    workspace = tmp_path / "stats_ws"
    workspace.mkdir()

    project = Project(
        name="Stats Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
    )
    uid = uuid4().hex[:8]
    workflow = Workflow(
        name=f"wf-stats-{uid}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version=uid,
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)

    runs = [
        Run(
            run_id=f"run_stats_{uid}_completed_{i}",
            project_id=str(project.id),
            workflow_id=str(workflow.id),
            status=RunStatus.COMPLETED.value,
            config={},
            samples_count=0,
            tasks_total=0,
            tasks_completed=0,
        )
        for i in range(3)
    ]
    runs.append(
        Run(
            run_id=f"run_stats_{uid}_running",
            project_id=str(project.id),
            workflow_id=str(workflow.id),
            status=RunStatus.RUNNING.value,
            config={},
            samples_count=0,
            tasks_total=0,
            tasks_completed=0,
        )
    )
    runs.append(
        Run(
            run_id=f"run_stats_{uid}_failed",
            project_id=str(project.id),
            workflow_id=str(workflow.id),
            status=RunStatus.FAILED.value,
            config={},
            samples_count=0,
            tasks_total=0,
            tasks_completed=0,
        )
    )

    image = DockerImage(
        name=f"test-image-{uid}",
        tag="latest",
        full_name=f"test-image-{uid}:latest",
        status=ImageStatus.LOCAL,
        registry="docker.io",
    )

    db_session.add_all(runs + [image])
    await db_session.commit()

    resp = await async_client.get("/api/v1/stats")
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert data["runs"]["total"] >= baseline["runs"]["total"] + 5
    assert data["runs"]["completed"] >= baseline["runs"]["completed"] + 3
    assert data["runs"]["running"] >= baseline["runs"]["running"] + 1
    assert data["runs"]["failed"] >= baseline["runs"]["failed"] + 1
    assert data["workflows"]["total"] >= baseline["workflows"]["total"] + 1
    assert data["projects"]["total"] >= baseline["projects"]["total"] + 1
    assert data["images"]["total"] >= baseline["images"]["total"] + 1
    assert data["images"]["local"] >= baseline["images"]["local"] + 1


@pytest.mark.asyncio
async def test_stats_dashboard_recent_runs_have_expected_fields(
    async_client, db_session, tmp_path
):
    """recent_runs entries contain run_id, status, workflow_id, started_at,
    duration_seconds, and current_task fields."""
    workspace = tmp_path / "stats_recent_ws"
    workspace.mkdir()

    project = Project(
        name="Stats Recent Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
    )
    uid = uuid4().hex[:8]
    workflow = Workflow(
        name=f"wf-recent-{uid}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version=uid,
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)

    run = Run(
        run_id=f"run_stats_recent_{uid}",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={},
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
        current_task="FASTQC",
    )
    db_session.add(run)
    await db_session.commit()

    resp = await async_client.get("/api/v1/stats")
    assert resp.status_code == 200

    recent = resp.json()["data"]["recent_runs"]
    assert isinstance(recent, list)
    # The endpoint caps recent_runs at 5; we inserted at least one run
    assert len(recent) > 0
    assert len(recent) <= 5

    # Every entry in recent_runs must have the documented fields
    for entry in recent:
        assert "run_id" in entry
        assert "status" in entry
        assert "workflow_id" in entry
        assert "started_at" in entry
        assert "duration_seconds" in entry
        assert "current_task" in entry
