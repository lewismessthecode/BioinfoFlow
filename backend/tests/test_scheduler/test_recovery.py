from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.project import Project
from app.models.run import Run, RunStatus
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.scheduler.config import SchedulerConfig
from app.scheduler.models import TaskState
from app.scheduler.queue import TaskQueue
from app.scheduler.scheduler import RunScheduler


class NoopBackend:
    async def submit(self, adapter, config: dict, workspace: str):
        del adapter, config, workspace
        if False:
            yield None

    async def cancel(self, adapter, *, pid: int | None, **kwargs) -> bool:
        del adapter, pid, kwargs
        return True


@pytest.mark.asyncio
async def test_scheduler_recover_marks_stale_dispatched_tasks_failed(db_session):
    project = Project(
        name=f"Recovery Project {uuid4()}", storage_mode="managed", external_root_path=None, user_id="dev"
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
        run_id=f"run_recovery_{uuid4().hex[:10]}",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.RUNNING.value,
        config={"params": {"outdir": "results"}},
        started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)
    task = await queue.enqueue(run.run_id)
    await queue.mark_dispatched(
        task.id,
        "worker-0",
        dispatched_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )

    scheduler = RunScheduler(
        config=SchedulerConfig(stale_timeout_minutes=30, poll_interval_seconds=0.01),
        backend=NoopBackend(),
        session_factory=session_factory,
        queue=queue,
    )

    recovered = await scheduler.recover()
    await db_session.refresh(run)

    assert recovered == 1
    assert run.status == RunStatus.FAILED.value
    assert run.error_message.startswith("Run recovery:")

    result = await db_session.execute(
        select(queue.model).where(queue.model.id == task.id)
    )
    refreshed = result.scalars().one()
    assert refreshed.state == TaskState.FAILED.value
    assert refreshed.error_message.startswith("Run recovery:")
