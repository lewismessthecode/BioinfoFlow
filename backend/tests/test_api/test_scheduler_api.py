from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.database as app_database
import app.runtime.jobs as runtime_jobs
from app.models.run import Run, RunStatus
from app.models.workflow import WorkflowEngine
from app.scheduler.resources import SystemResources
from app.scheduler.scheduler import SchedulerStorageUnavailableError
from app.services.run_dispatch import (
    get_run_scheduler,
    set_run_dispatcher,
    set_run_scheduler,
)
from tests.support.path_contract import create_project, create_workflow


@pytest.mark.asyncio
async def test_scheduler_status_endpoint_returns_unavailable_persistent_status(async_client):
    original_scheduler = get_run_scheduler()
    set_run_scheduler(None)
    set_run_dispatcher(None)
    try:
        response = await async_client.get("/api/v1/scheduler/status")

        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["mode"] == "persistent"
        assert payload["effective_mode"] == "persistent"
        assert payload["scheduler_available"] is False
        assert payload["resource_monitoring_enabled"] is False
        assert payload["queue_depth"] == 0
        assert payload["states"] == {
            "queued": 0,
            "dispatched": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
        }
    finally:
        set_run_scheduler(original_scheduler)


@pytest.mark.asyncio
async def test_scheduler_resources_endpoint_returns_snapshot_when_available(
    async_client,
    monkeypatch,
):
    class FakeScheduler:
        def get_status(self):
            raise AssertionError("status is not queried by the resources endpoint")

        def get_resource_snapshot(self):
            return SystemResources(
                cpu_count=16,
                cpu_available=11.5,
                memory_total_gb=64.0,
                memory_available_gb=40.0,
                disk_total_gb=500.0,
                disk_available_gb=320.0,
                gpu_count=1,
                gpu_memory_gb=24.0,
                sampled_at="2026-03-18T12:00:00Z",
            )

    set_run_scheduler(FakeScheduler())

    response = await async_client.get("/api/v1/scheduler/resources")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["mode"] == "persistent"
    assert payload["enabled"] is True
    assert payload["sampled_at"] == "2026-03-18T12:00:00Z"
    assert payload["cpu"] == {"total": 16, "available": 11.5}
    assert payload["memory"] == {"total_gb": 64.0, "available_gb": 40.0}
    assert payload["disk"] == {"total_gb": 500.0, "available_gb": 320.0}
    assert payload["gpu"] == {"count": 1, "memory_gb": 24.0}


@pytest.mark.asyncio
async def test_app_lifespan_raises_when_scheduler_storage_is_unavailable(
    app,
    db_session,
    monkeypatch,
):
    session_maker = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    original_engine = app_database.engine
    original_session_maker = app_database.async_session_maker
    original_jobs_session_maker = runtime_jobs.async_session_maker

    app_database.engine = db_session.bind
    app_database.async_session_maker = session_maker
    runtime_jobs.async_session_maker = session_maker

    async def fail_scheduler_start(self):
        del self
        raise SchedulerStorageUnavailableError("scheduled_tasks table is missing")

    async def noop_ensure_default_workspace(self):
        del self
        return None

    async def noop_reconcile_stale_hermes_responses(session, stale_before):
        del session, stale_before
        return 0

    monkeypatch.setattr("app.main.RunScheduler.start", fail_scheduler_start)
    monkeypatch.setattr(
        "app.main.WorkspaceService.ensure_default_workspace",
        noop_ensure_default_workspace,
    )
    monkeypatch.setattr(
        "app.main.reconcile_stale_hermes_responses",
        noop_reconcile_stale_hermes_responses,
    )

    from app.api.deps import get_db

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with pytest.raises(
            SchedulerStorageUnavailableError,
            match="scheduled_tasks table is missing",
        ):
            async with app.router.lifespan_context(app):
                pass
    finally:
        app.dependency_overrides.clear()
        app_database.engine = original_engine
        app_database.async_session_maker = original_session_maker
        runtime_jobs.async_session_maker = original_jobs_session_maker
        set_run_scheduler(None)
        set_run_dispatcher(None)


@pytest.mark.asyncio
async def test_scheduler_status_endpoint_returns_effective_scheduler_health(
    async_client,
    monkeypatch,
):
    class FakeScheduler:
        async def get_status(self):
            return {
                "workers": 4,
                "queue_depth": 7,
                "resource_monitoring_enabled": True,
                "states": {
                    "queued": 2,
                    "dispatched": 1,
                    "completed": 8,
                    "failed": 1,
                    "cancelled": 0,
                },
            }

        def get_resource_snapshot(self):
            return None

    set_run_scheduler(FakeScheduler())

    response = await async_client.get("/api/v1/scheduler/status")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["mode"] == "persistent"
    assert payload["effective_mode"] == "persistent"
    assert payload["scheduler_available"] is True
    assert payload["workers"] == 4
    assert payload["queue_depth"] == 7
    assert payload["resource_monitoring_enabled"] is True
    assert payload["states"]["completed"] == 8


@pytest.mark.asyncio
async def test_scheduler_status_enriches_active_runs_with_workflow_name(
    async_client,
    db_session,
    monkeypatch,
):
    """/scheduler/status should attach workflow_name to every active run.

    The raw scheduler returns ``[{run_id, weight}]`` — the API layer joins
    through runs + workflows to add human-readable context for the UI.
    """
    project = await create_project(
        db_session, name=f"proj-{uuid4()}", storage_mode="managed"
    )
    workflow = await create_workflow(
        db_session, name="bulk-rnaseq", engine=WorkflowEngine.NEXTFLOW
    )
    run_id = f"r-{uuid4().hex[:6]}"
    run = Run(
        run_id=run_id,
        project_id=project.id,
        workflow_id=workflow.id,
        status=RunStatus.RUNNING.value,
    )
    db_session.add(run)
    await db_session.commit()

    class FakeScheduler:
        async def get_status(self):
            return {
                "workers": 2,
                "queue_depth": 0,
                "resource_monitoring_enabled": True,
                "states": {
                    "queued": 0,
                    "dispatched": 1,
                    "completed": 0,
                    "failed": 0,
                    "cancelled": 0,
                },
                "total_slots": 4,
                "used_slots": 1,
                "available_slots": 3,
                "active_runs": [{"run_id": run_id, "weight": 2}],
            }

        def get_resource_snapshot(self):
            return None

    set_run_scheduler(FakeScheduler())

    response = await async_client.get("/api/v1/scheduler/status")

    assert response.status_code == 200
    active = response.json()["data"]["active_runs"]
    assert active == [{"run_id": run_id, "weight": 2, "workflow_name": "bulk-rnaseq"}]


@pytest.mark.asyncio
async def test_scheduler_status_enriches_active_runs_handles_missing_run(
    async_client,
    monkeypatch,
):
    """Active run without a DB record still serialises — workflow_name is None.

    Belt-and-braces: the scheduler and the runs table can drift for a tick
    during a cancel. We must never 500 just because a row hasn't synced yet.
    """

    class FakeScheduler:
        async def get_status(self):
            return {
                "workers": 1,
                "queue_depth": 0,
                "resource_monitoring_enabled": True,
                "states": {
                    "queued": 0,
                    "dispatched": 0,
                    "completed": 0,
                    "failed": 0,
                    "cancelled": 0,
                },
                "total_slots": 1,
                "used_slots": 0,
                "available_slots": 1,
                "active_runs": [{"run_id": "r-ghost", "weight": 1}],
            }

        def get_resource_snapshot(self):
            return None

    set_run_scheduler(FakeScheduler())

    response = await async_client.get("/api/v1/scheduler/status")

    assert response.status_code == 200
    active = response.json()["data"]["active_runs"]
    assert active == [{"run_id": "r-ghost", "weight": 1, "workflow_name": None}]


@pytest.mark.asyncio
async def test_scheduler_resources_stream_emits_initial_frame(
    async_client,
    db_session,
    monkeypatch,
):
    """SSE stream must emit the first frame immediately and include
    enriched active_runs + the resource snapshot on the same envelope.
    """
    from app.api.v1.scheduler import _enrich_active_runs, _resource_payload
    from app.scheduler.stream import resource_stream_generator

    project = await create_project(
        db_session, name=f"proj-{uuid4()}", storage_mode="managed"
    )
    workflow = await create_workflow(
        db_session, name="variant-calling", engine=WorkflowEngine.NEXTFLOW
    )
    run_id = f"r-{uuid4().hex[:6]}"
    run = Run(
        run_id=run_id,
        project_id=project.id,
        workflow_id=workflow.id,
        status=RunStatus.RUNNING.value,
    )
    db_session.add(run)
    await db_session.commit()

    class FakeScheduler:
        async def get_status(self):
            return {
                "workers": 2,
                "queue_depth": 1,
                "resource_monitoring_enabled": True,
                "states": {
                    "queued": 1,
                    "dispatched": 1,
                    "completed": 0,
                    "failed": 0,
                    "cancelled": 0,
                },
                "total_slots": 4,
                "used_slots": 1,
                "available_slots": 3,
                "active_runs": [{"run_id": run_id, "weight": 2}],
            }

        def get_resource_snapshot(self):
            return SystemResources(
                cpu_count=8,
                cpu_available=6.2,
                memory_total_gb=32.0,
                memory_available_gb=20.0,
                disk_total_gb=500.0,
                disk_available_gb=284.0,
                gpu_count=0,
                gpu_memory_gb=0.0,
                sampled_at="2026-04-17T14:00:00Z",
            )

    class FakeRequest:
        async def is_disconnected(self):
            return False

    gen = resource_stream_generator(
        request=FakeRequest(),
        scheduler=FakeScheduler(),
        resource_payload_builder=_resource_payload,
        enrich_active_runs=_enrich_active_runs,
        mode="persistent",
    )

    # First frame is emitted immediately — no tick wait required.
    first = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    await gen.aclose()

    assert first.startswith("id: ")
    assert "event: scheduler.resources" in first

    data_line = next(line for line in first.splitlines() if line.startswith("data: "))
    frame = json.loads(data_line[len("data: ") :])

    assert frame["scheduler_available"] is True
    assert frame["queue_depth"] == 1
    assert frame["resources"]["enabled"] is True
    assert frame["resources"]["cpu"]["total"] == 8
    assert frame["active_runs"] == [
        {"run_id": run_id, "weight": 2, "workflow_name": "variant-calling"}
    ]


@pytest.mark.asyncio
async def test_scheduler_resources_stream_works_without_scheduler(
    async_client,
):
    """Legacy mode (no scheduler) still delivers a valid frame: empty
    active_runs + disabled resources. Stream endpoint must never 500.
    """
    from app.api.v1.scheduler import _enrich_active_runs, _resource_payload
    from app.scheduler.stream import resource_stream_generator

    class FakeRequest:
        async def is_disconnected(self):
            return False

    gen = resource_stream_generator(
        request=FakeRequest(),
        scheduler=None,
        resource_payload_builder=_resource_payload,
        enrich_active_runs=_enrich_active_runs,
        mode="legacy",
    )
    first = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    await gen.aclose()

    data_line = next(line for line in first.splitlines() if line.startswith("data: "))
    frame = json.loads(data_line[len("data: ") :])

    assert frame["scheduler_available"] is False
    assert frame["effective_mode"] == "legacy"
    assert frame["active_runs"] == []
    assert frame["resources"]["enabled"] is False


@pytest.mark.asyncio
async def test_scheduler_resources_stream_breaks_on_disconnect():
    """Generator cleanly ends when the request reports disconnected."""
    from app.api.v1.scheduler import _enrich_active_runs, _resource_payload
    from app.scheduler.stream import resource_stream_generator

    disconnect_after = {"count": 0}

    class FakeRequest:
        async def is_disconnected(self):
            disconnect_after["count"] += 1
            # Disconnect on the very first check inside the loop so the
            # generator exits without yielding a second frame.
            return True

    gen = resource_stream_generator(
        request=FakeRequest(),
        scheduler=None,
        resource_payload_builder=_resource_payload,
        enrich_active_runs=_enrich_active_runs,
        mode="legacy",
        tick_seconds=0.05,  # tight loop for fast test
    )

    # First yield is the eager initial frame
    await asyncio.wait_for(gen.__anext__(), timeout=1.0)

    # Second iteration should complete (StopAsyncIteration) once the
    # request reports disconnected.
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(gen.__anext__(), timeout=2.0)
