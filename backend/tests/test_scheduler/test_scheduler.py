from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.engine.backend import EngineEvent, EngineEventType
from app.models.run import Run, RunStatus
from app.models.workflow import WorkflowEngine
from app.scheduler.config import SchedulerConfig
from app.scheduler.models import TaskState
from app.scheduler.queue import TaskQueue
from app.scheduler.scheduler import (
    QueueFullError,
    RunScheduler,
    SchedulerStorageUnavailableError,
)
from app.services.run_dispatch import SchedulerDispatcher
from tests.support.path_contract import create_project, create_workflow


class FakeBackend:
    def __init__(self) -> None:
        self.cancel_calls: list[dict[str, object]] = []

    async def submit(self, adapter, config: dict, workspace: str):
        del adapter, config, workspace
        yield EngineEvent(
            EngineEventType.PROCESS_INFO,
            {"pid": 4321, "engine": "nextflow"},
        )
        yield EngineEvent(EngineEventType.COMPLETED, {"success": True})

    async def cancel(self, adapter, *, pid: int | None, **kwargs) -> bool:
        del adapter
        self.cancel_calls.append({"pid": pid, **kwargs})
        return True


async def _seed_run(
    db_session: AsyncSession,
    *,
    status: str = RunStatus.QUEUED.value,
    engine: WorkflowEngine = WorkflowEngine.NEXTFLOW,
    config: dict | None = None,
) -> Run:
    project = await create_project(
        db_session,
        name=f"Scheduler Project {uuid4()}",
        storage_mode="managed",
    )
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        engine=engine,
        content=(
            "version 1.0\nworkflow demo {}\n"
            if engine == WorkflowEngine.WDL
            else "workflow { }\n"
        ),
    )

    run = Run(
        run_id=f"run_scheduler_{uuid4().hex[:10]}",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=status,
        config=config or {"params": {"outdir": "results"}},
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


@pytest.mark.asyncio
async def test_scheduler_enqueue_rejects_when_queue_is_full(db_session):
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)
    scheduler = RunScheduler(
        config=SchedulerConfig(max_queue_depth=1, poll_interval_seconds=0.01),
        backend=FakeBackend(),
        session_factory=session_factory,
        queue=queue,
    )
    first = await _seed_run(db_session)
    second = await _seed_run(db_session)
    baseline_depth = await queue.depth()
    scheduler = RunScheduler(
        config=SchedulerConfig(
            max_queue_depth=baseline_depth + 1,
            poll_interval_seconds=0.01,
        ),
        backend=FakeBackend(),
        session_factory=session_factory,
        queue=queue,
    )

    await scheduler.enqueue(first.run_id)

    with pytest.raises(QueueFullError):
        await scheduler.enqueue(second.run_id)


@pytest.mark.asyncio
async def test_scheduler_enqueue_logs_warning_when_queue_is_full(db_session, caplog):
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)
    first = await _seed_run(db_session)
    second = await _seed_run(db_session)
    baseline_depth = await queue.depth()
    scheduler = RunScheduler(
        config=SchedulerConfig(
            max_queue_depth=baseline_depth + 1,
            poll_interval_seconds=0.01,
        ),
        backend=FakeBackend(),
        session_factory=session_factory,
        queue=queue,
    )

    await scheduler.enqueue(first.run_id)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(QueueFullError):
            await scheduler.enqueue(second.run_id)

    assert "scheduler.queue.full" in caplog.text
    assert second.run_id in caplog.text


@pytest.mark.asyncio
async def test_scheduler_status_payload_includes_config_block(db_session):
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    scheduler = RunScheduler(
        config=SchedulerConfig(
            total_slots=7,
            max_workers=3,
            max_queue_depth=17,
            poll_interval_seconds=0.25,
            stale_timeout_minutes=9,
            worker_heartbeat_grace_seconds=11,
            resource_check_enabled=True,
        ),
        backend=FakeBackend(),
        session_factory=session_factory,
        queue=TaskQueue(session_factory=session_factory),
    )

    status = await scheduler.get_status()

    assert status["config"] == {
        "total_slots": 7,
        "max_workers": 3,
        "max_queue_depth": 17,
        "poll_interval_seconds": 0.25,
        "stale_timeout_minutes": 9,
        "worker_heartbeat_grace_seconds": 11,
        "resource_check_enabled": True,
    }


@pytest.mark.asyncio
async def test_scheduler_executes_enqueued_run_and_completes_task(
    db_session, monkeypatch
):
    monkeypatch.setattr("app.scheduler.scheduler.get_adapter", lambda engine: object())
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)
    scheduler = RunScheduler(
        config=SchedulerConfig(max_concurrency=1, poll_interval_seconds=0.01),
        backend=FakeBackend(),
        session_factory=session_factory,
        queue=queue,
    )
    run = await _seed_run(db_session)

    await scheduler.start()
    try:
        await scheduler.enqueue(run.run_id)
        for _ in range(100):
            await db_session.refresh(run)
            if run.status == RunStatus.COMPLETED.value:
                break
            await asyncio.sleep(0.02)
        else:
            raise AssertionError("run did not complete")
    finally:
        await scheduler.stop()

    assert run.status == RunStatus.COMPLETED.value

    for _ in range(100):
        result = await db_session.execute(
            select(queue.model).where(queue.model.run_id == run.run_id)
        )
        task = result.scalars().one()
        if task.state == TaskState.COMPLETED.value:
            break
        await asyncio.sleep(0.02)
    else:
        raise AssertionError("scheduled task did not reach completed state")

    assert task.state == TaskState.COMPLETED.value
    assert task.worker_id == "worker-0"


@pytest.mark.asyncio
async def test_scheduler_start_raises_when_scheduled_tasks_table_is_missing(
    db_session,
    monkeypatch,
):
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)
    scheduler = RunScheduler(
        config=SchedulerConfig(max_concurrency=0, poll_interval_seconds=0.01),
        backend=FakeBackend(),
        session_factory=session_factory,
        queue=queue,
    )

    async def raise_missing_table(timeout_minutes: int):
        del timeout_minutes
        raise OperationalError(
            "SELECT scheduled_tasks.id FROM scheduled_tasks",
            {},
            Exception("no such table: scheduled_tasks"),
        )

    monkeypatch.setattr(queue, "get_stale", raise_missing_table)

    try:
        with pytest.raises(SchedulerStorageUnavailableError):
            await scheduler.start()
    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_cancel_queued_run_updates_task_and_run(db_session):
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)
    scheduler = RunScheduler(
        config=SchedulerConfig(poll_interval_seconds=0.01),
        backend=FakeBackend(),
        session_factory=session_factory,
        queue=queue,
    )
    run = await _seed_run(db_session)

    await scheduler.enqueue(run.run_id)
    cancelled = await scheduler.cancel(run.run_id)
    await db_session.refresh(run)

    assert cancelled is True
    assert run.status == RunStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_scheduler_complete_does_not_overwrite_cancelled_run(
    db_session, monkeypatch
):
    async def noop_terminal_hook(run, **kwargs):
        del run, kwargs
        return {}

    monkeypatch.setattr(
        RunScheduler,
        "_hooks",
        lambda self, session: SimpleNamespace(on_run_terminal=noop_terminal_hook),
    )
    monkeypatch.setattr("app.scheduler.scheduler.publish_run_status", AsyncMock())
    monkeypatch.setattr("app.scheduler.scheduler.publish_run_dag", AsyncMock())

    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)
    scheduler = RunScheduler(
        config=SchedulerConfig(poll_interval_seconds=0.01),
        backend=FakeBackend(),
        session_factory=session_factory,
        queue=queue,
    )
    run = await _seed_run(db_session, status=RunStatus.RUNNING.value)
    task = await queue.enqueue(run.run_id)
    await queue.mark_dispatched(task.id, "worker-0")

    async with session_factory() as worker_session:
        stale_run = await worker_session.get(Run, run.id)
        assert stale_run is not None

        async with session_factory() as other_session:
            fresh_run = await other_session.get(Run, run.id)
            fresh_task = await other_session.get(TaskQueue.model, task.id)
            assert fresh_run is not None
            assert fresh_task is not None
            fresh_run.status = RunStatus.CANCELLED.value
            fresh_task.state = TaskState.CANCELLED.value
            await other_session.commit()

        await scheduler._complete_run(
            worker_session,
            stale_run,
            task_id=task.id,
            workspace_path=str(Path.cwd()),
            engine=WorkflowEngine.NEXTFLOW.value,
        )

    await db_session.refresh(run)
    refreshed_task = await queue.get(task.id)
    assert run.status == RunStatus.CANCELLED.value
    assert refreshed_task is not None
    assert refreshed_task.state == TaskState.CANCELLED.value


@pytest.mark.asyncio
async def test_scheduler_retry_does_not_orphan_run_when_task_requeue_loses_race(
    db_session,
):
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)
    scheduler = RunScheduler(
        config=SchedulerConfig(poll_interval_seconds=0.01),
        backend=FakeBackend(),
        session_factory=session_factory,
        queue=queue,
    )
    run = await _seed_run(
        db_session,
        status=RunStatus.RUNNING.value,
        config={
            "params": {"outdir": "results"},
            "policy": {"retry": {"max_retries": 1, "retry_on": ["137"]}},
        },
    )
    task = await queue.enqueue(run.run_id, max_attempts=2)
    await queue.mark_dispatched(task.id, "worker-0")

    async with session_factory() as worker_session:
        stale_run = await worker_session.get(Run, run.id)
        stale_task = await worker_session.get(TaskQueue.model, task.id)
        assert stale_run is not None
        assert stale_task is not None

        async with session_factory() as other_session:
            fresh_run = await other_session.get(Run, run.id)
            fresh_task = await other_session.get(TaskQueue.model, task.id)
            assert fresh_run is not None
            assert fresh_task is not None
            fresh_run.status = RunStatus.CANCELLED.value
            fresh_task.state = TaskState.CANCELLED.value
            await other_session.commit()

        scheduled = await scheduler._schedule_retry(
            worker_session,
            stale_run,
            stale_task,
            "Executor killed with exit 137",
        )

    await db_session.refresh(run)
    refreshed_task = await queue.get(task.id)
    assert scheduled is False
    assert run.status == RunStatus.CANCELLED.value
    assert refreshed_task is not None
    assert refreshed_task.state == TaskState.CANCELLED.value


@pytest.mark.asyncio
async def test_scheduler_persists_wdl_work_dir_for_resume(db_session, monkeypatch):
    monkeypatch.setattr("app.scheduler.scheduler.get_adapter", lambda engine: object())
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)
    scheduler = RunScheduler(
        config=SchedulerConfig(max_concurrency=1, poll_interval_seconds=0.01),
        backend=FakeBackend(),
        session_factory=session_factory,
        queue=queue,
    )
    run = await _seed_run(db_session, engine=WorkflowEngine.WDL)

    await scheduler.start()
    try:
        await scheduler.enqueue(run.run_id)
        for _ in range(100):
            await db_session.refresh(run)
            runtime = dict(run.config.get("runtime", {}) or {})
            if runtime.get("wdl_work_dir"):
                break
            await asyncio.sleep(0.02)
        else:
            raise AssertionError("wdl work dir was not persisted")
    finally:
        await scheduler.stop()

    assert run.config["runtime"]["wdl_work_dir"] == (
        "runs/" + run.run_id + "/engine/wdl/work"
    )


@pytest.mark.asyncio
async def test_scheduler_dispatcher_marks_run_failed_when_enqueue_rejects(
    db_session,
    monkeypatch,
):
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    monkeypatch.setattr("app.database.async_session_maker", session_factory)
    run = await _seed_run(db_session)

    class FullScheduler:
        async def enqueue(self, run_id: str, *, priority: str = "normal"):
            del run_id, priority
            raise QueueFullError("run scheduler queue is full")

    dispatcher = SchedulerDispatcher(FullScheduler())
    dispatcher.dispatch(run.run_id)

    for _ in range(100):
        await db_session.refresh(run)
        if run.status == RunStatus.FAILED.value:
            break
        await asyncio.sleep(0.02)
    else:
        raise AssertionError("run was not marked failed after enqueue rejection")

    assert run.error_message == "run scheduler queue is full"


@pytest.mark.asyncio
async def test_scheduler_holds_task_when_slots_insufficient(
    db_session,
    monkeypatch,
):
    """A task whose weight exceeds available slots stays QUEUED."""
    monkeypatch.setattr("app.scheduler.scheduler.get_adapter", lambda engine: object())
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)

    class GuardedBackend(FakeBackend):
        async def submit(self, adapter, config: dict, workspace: str):
            for event in ():
                yield event
            raise AssertionError("heavy task must not execute when slots are full")

    # total_slots=1 but the task will have weight=3 → can never fit
    scheduler = RunScheduler(
        config=SchedulerConfig(
            total_slots=1,
            max_workers=1,
            poll_interval_seconds=0.01,
        ),
        backend=GuardedBackend(),
        session_factory=session_factory,
        queue=queue,
    )
    run = await _seed_run(db_session)

    # Enqueue with weight=3 directly via queue (bypasses workflow lookup)
    await queue.enqueue(run.run_id, weight=3)

    await scheduler.start()
    try:
        # Give the scheduler a few cycles to poll
        await asyncio.sleep(0.15)
        async with session_factory() as verify_session:
            result = await verify_session.execute(
                select(queue.model).where(queue.model.run_id == run.run_id)
            )
            task = result.scalars().one()
    finally:
        await scheduler.stop()

    # Task stays QUEUED because weight(3) > available_slots(1)
    assert task.state == TaskState.QUEUED.value
    assert task.worker_id is None


@pytest.mark.asyncio
async def test_scheduler_finalizes_dag_on_failure(db_session, monkeypatch):
    monkeypatch.setattr("app.scheduler.scheduler.get_adapter", lambda engine: object())

    async def fake_initialize_run_dag(session, run, workflow, workspace_path):
        del workflow, workspace_path
        run.config = {
            **run.config,
            "dag": {
                "nodes": [
                    {
                        "id": "align",
                        "type": "task",
                        "data": {"label": "ALIGN", "status": "pending"},
                    }
                ],
                "edges": [],
            },
        }
        await session.commit()

    async def noop_terminal_hook(run, **kwargs):
        del run, kwargs
        return {}

    monkeypatch.setattr(
        "app.scheduler.scheduler.initialize_run_dag",
        fake_initialize_run_dag,
    )
    monkeypatch.setattr(
        RunScheduler,
        "_hooks",
        lambda self, session: SimpleNamespace(on_run_terminal=noop_terminal_hook),
    )

    class FailingDagBackend(FakeBackend):
        async def submit(self, adapter, config: dict, workspace: str):
            del adapter, config, workspace
            yield EngineEvent(
                EngineEventType.PROCESS_INFO,
                {"pid": 4321, "engine": "nextflow"},
            )
            yield EngineEvent(
                EngineEventType.TASK_UPDATE,
                {"name": "ALIGN", "status": "RUNNING"},
            )
            yield EngineEvent(EngineEventType.ERROR, {"message": "boom"})

    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)
    scheduler = RunScheduler(
        config=SchedulerConfig(max_concurrency=1, poll_interval_seconds=0.01),
        backend=FailingDagBackend(),
        session_factory=session_factory,
        queue=queue,
    )
    run = await _seed_run(db_session)

    await scheduler.start()
    try:
        await scheduler.enqueue(run.run_id)
        for _ in range(100):
            await db_session.refresh(run)
            dag = dict(run.config.get("dag", {}) or {})
            nodes = list(dag.get("nodes", []))
            if run.status == RunStatus.FAILED.value and nodes:
                break
            await asyncio.sleep(0.02)
        else:
            raise AssertionError("run did not fail with a persisted DAG")
    finally:
        await scheduler.stop()

    assert run.status == RunStatus.FAILED.value
    assert run.config["dag"]["nodes"][0]["data"]["status"] == "failed"


@pytest.mark.asyncio
async def test_scheduler_cancel_finalizes_running_dag_nodes(db_session, monkeypatch):
    monkeypatch.setattr("app.scheduler.scheduler.get_adapter", lambda engine: object())

    async def noop_terminal_hook(run, **kwargs):
        del run, kwargs
        return {}

    monkeypatch.setattr(
        RunScheduler,
        "_hooks",
        lambda self, session: SimpleNamespace(on_run_terminal=noop_terminal_hook),
    )

    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)
    scheduler = RunScheduler(
        config=SchedulerConfig(poll_interval_seconds=0.01),
        backend=FakeBackend(),
        session_factory=session_factory,
        queue=queue,
    )
    run = await _seed_run(
        db_session,
        status=RunStatus.RUNNING.value,
        config={
            "params": {"outdir": "results"},
            "runtime": {"pid": 1234},
            "dag": {
                "nodes": [
                    {
                        "id": "align",
                        "type": "task",
                        "data": {"label": "ALIGN", "status": "running"},
                    }
                ],
                "edges": [],
            },
        },
    )
    task = await queue.enqueue(run.run_id)
    await queue.mark_dispatched(task.id, "worker-0")

    cancelled = await scheduler.cancel(run.run_id)
    await db_session.refresh(run)

    assert cancelled is True
    assert run.status == RunStatus.CANCELLED.value
    assert run.config["dag"]["nodes"][0]["data"]["status"] == "failed"


# --- Phase 2 Fix 12: Worker crash recovery ---


@pytest.mark.asyncio
async def test_scheduler_worker_survives_execute_task_exception(
    db_session, monkeypatch
):
    """Worker should continue processing after an unhandled exception in _execute_task."""
    monkeypatch.setattr("app.scheduler.scheduler.get_adapter", lambda engine: object())
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)

    call_count = 0
    original_execute_run_id = RunScheduler._execute_run_id

    async def crashing_then_normal(self, run_id, *, task_id=None, worker_id):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Simulated worker crash")
        return await original_execute_run_id(
            self, run_id, task_id=task_id, worker_id=worker_id
        )

    monkeypatch.setattr(RunScheduler, "_execute_run_id", crashing_then_normal)

    scheduler = RunScheduler(
        config=SchedulerConfig(max_concurrency=1, poll_interval_seconds=0.01),
        backend=FakeBackend(),
        session_factory=session_factory,
        queue=queue,
    )

    run1 = await _seed_run(db_session)
    run2 = await _seed_run(db_session)

    await scheduler.start()
    try:
        await scheduler.enqueue(run1.run_id)
        # Wait for the first task to be claimed (and crash)
        await asyncio.sleep(0.1)
        await scheduler.enqueue(run2.run_id)

        # Worker should still be alive and process the second task
        for _ in range(200):
            await db_session.refresh(run2)
            if run2.status == RunStatus.COMPLETED.value:
                break
            await asyncio.sleep(0.02)
        else:
            raise AssertionError(
                "Worker did not recover after exception — second run was not completed"
            )
    finally:
        await scheduler.stop()

    assert run2.status == RunStatus.COMPLETED.value
    assert call_count >= 2


@pytest.mark.asyncio
async def test_scheduler_resolve_run_context_returns_workspace_path(db_session):
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    scheduler = RunScheduler(
        config=SchedulerConfig(poll_interval_seconds=0.01),
        backend=FakeBackend(),
        session_factory=session_factory,
        queue=TaskQueue(session_factory=session_factory),
    )
    run = await _seed_run(db_session)

    workspace_path, engine = await scheduler._resolve_run_context(db_session, run)

    assert isinstance(workspace_path, Path)
    assert engine == WorkflowEngine.NEXTFLOW.value


@pytest.mark.asyncio
async def test_scheduler_releases_slot_when_execute_raises(db_session, monkeypatch):
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)
    scheduler = RunScheduler(
        config=SchedulerConfig(
            total_slots=2, max_workers=1, poll_interval_seconds=0.01
        ),
        backend=FakeBackend(),
        session_factory=session_factory,
        queue=queue,
    )
    run = await _seed_run(db_session)
    executed = asyncio.Event()

    async def crashing_execute(self, run_id, *, task_id=None, worker_id):
        del self, run_id, task_id, worker_id
        executed.set()
        raise RuntimeError("simulated execute failure")

    monkeypatch.setattr(RunScheduler, "_execute_run_id", crashing_execute)

    await scheduler.start()
    try:
        await scheduler.enqueue(run.run_id)
        await asyncio.wait_for(executed.wait(), timeout=2)
        for _ in range(50):
            if scheduler._slots.used == 0:
                break
            await asyncio.sleep(0.02)
        else:
            raise AssertionError("slot was not released after execute failure")
    finally:
        await scheduler.stop()

    assert scheduler._slots.used == 0
