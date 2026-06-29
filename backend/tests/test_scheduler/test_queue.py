from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.project import Project
from app.models.run import Run, RunStatus
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.scheduler.models import TaskPriority, TaskState
from app.scheduler.queue import TaskQueue


async def _seed_runs(
    db_session: AsyncSession,
    *,
    count: int,
) -> list[Run]:
    project = Project(
        name=f"Queue Project {uuid4()}", storage_mode="managed", external_root_path=None, user_id="dev"
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

    runs: list[Run] = []
    for index in range(count):
        run = Run(
            run_id=f"run_queue_{index}_{uuid4().hex[:8]}",
            project_id=str(project.id),
            workflow_id=str(workflow.id),
            status=RunStatus.QUEUED.value,
            config={"params": {"outdir": "results"}},
            samples_count=0,
            tasks_total=0,
            tasks_completed=0,
        )
        db_session.add(run)
        runs.append(run)
    await db_session.commit()
    return runs


@pytest.mark.asyncio
async def test_queue_dequeues_by_priority_then_created_at(db_session):
    runs = await _seed_runs(db_session, count=3)
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)

    await queue.enqueue(runs[0].run_id, priority=TaskPriority.NORMAL.value)
    await queue.enqueue(runs[1].run_id, priority=TaskPriority.LOW.value)
    await queue.enqueue(runs[2].run_id, priority=TaskPriority.URGENT.value)

    first = await queue.dequeue()
    assert first is not None
    assert first.run_id == runs[2].run_id
    await queue.mark_dispatched(first.id, "worker-0")

    second = await queue.dequeue()
    assert second is not None
    assert second.run_id == runs[0].run_id
    await queue.mark_dispatched(second.id, "worker-0")

    third = await queue.dequeue()
    assert third is not None
    assert third.run_id == runs[1].run_id


@pytest.mark.asyncio
async def test_queue_cancel_marks_queued_task_cancelled(db_session):
    runs = await _seed_runs(db_session, count=1)
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)

    task = await queue.enqueue(runs[0].run_id, priority=TaskPriority.NORMAL.value)

    cancelled = await queue.cancel(runs[0].run_id)

    assert cancelled is True

    refreshed = await queue.get(task.id)
    assert refreshed is not None
    assert refreshed.state == TaskState.CANCELLED.value
    assert refreshed.completed_at is not None


@pytest.mark.asyncio
async def test_concurrent_enqueue_allows_only_one_active_task(db_session):
    runs = await _seed_runs(db_session, count=1)
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    first_queue = TaskQueue(session_factory=session_factory)
    second_queue = TaskQueue(session_factory=session_factory)

    first, second = await asyncio.gather(
        first_queue.enqueue(runs[0].run_id),
        second_queue.enqueue(runs[0].run_id),
    )

    assert first.id == second.id
    result = await db_session.execute(
        select(TaskQueue.model).where(
            TaskQueue.model.run_id == runs[0].run_id,
            TaskQueue.model.state.in_(
                [TaskState.QUEUED.value, TaskState.DISPATCHED.value]
            ),
        )
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_queue_refuses_invalid_terminal_state_transitions(db_session):
    runs = await _seed_runs(db_session, count=1)
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)
    task = await queue.enqueue(runs[0].run_id)
    completed = await queue.mark_completed(task.id)
    assert completed is not None

    redispatched = await queue.mark_dispatched(task.id, "worker-after-terminal")
    requeued = await queue.re_enqueue(task.id, attempt=2)

    assert redispatched is None
    assert requeued is None
    refreshed = await queue.get(task.id)
    assert refreshed is not None
    assert refreshed.state == TaskState.COMPLETED.value
