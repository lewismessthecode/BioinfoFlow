from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.models.project import Project
from app.models.run import Run, RunStatus
from app.schemas.run import RunErrorCode
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
        name=f"Recovery Project {uuid4()}",
        storage_mode="managed",
        external_root_path=None,
        user_id="dev",
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


@pytest.mark.asyncio
async def test_scheduler_recover_uses_configured_worker_heartbeat_grace(
    db_session, tmp_path, monkeypatch
):
    project = Project(
        name=f"Heartbeat Recovery Project {uuid4()}",
        storage_mode="managed",
        external_root_path=None,
        user_id="dev",
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
        run_id=f"run_worker_lost_{uuid4().hex[:10]}",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.RUNNING.value,
        config={"params": {"outdir": "results"}},
        started_at=datetime.now(timezone.utc),
        last_heartbeat_at=datetime.now(timezone.utc) - timedelta(seconds=10),
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    root_home = (tmp_path / "root-home").resolve()
    root_env = tmp_path / "root.env"
    backend_env = tmp_path / "backend.env"
    root_env.write_text(
        f"BIOINFOFLOW_HOME={root_home}\nSCHEDULER_WORKER_HEARTBEAT_GRACE_SECONDS=5\n",
        encoding="utf-8",
    )
    backend_env.write_text("", encoding="utf-8")
    monkeypatch.delenv("BIOINFOFLOW_HOME", raising=False)
    monkeypatch.delenv("SCHEDULER_WORKER_HEARTBEAT_GRACE_SECONDS", raising=False)
    config = SchedulerConfig.from_settings(Settings(_env_file=(root_env, backend_env)))

    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    scheduler = RunScheduler(
        config=config,
        backend=NoopBackend(),
        session_factory=session_factory,
        queue=TaskQueue(session_factory=session_factory),
    )

    recovered = await scheduler.recover()
    await db_session.refresh(run)

    assert recovered == 1
    assert run.status == RunStatus.FAILED.value
    assert run.error_json["code"] == RunErrorCode.WORKER_LOST


@pytest.mark.asyncio
async def test_scheduler_recover_syncs_slots_from_dispatched_weight_sum(
    db_session,
):
    project = Project(
        name=f"Weighted Recovery Project {uuid4()}",
        storage_mode="managed",
        external_root_path=None,
        user_id="dev",
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

    first = Run(
        run_id=f"run_weighted_{uuid4().hex[:10]}",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.RUNNING.value,
        config={"params": {"outdir": "results"}},
        started_at=datetime.now(timezone.utc),
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    second = Run(
        run_id=f"run_weighted_{uuid4().hex[:10]}",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.RUNNING.value,
        config={"params": {"outdir": "results"}},
        started_at=datetime.now(timezone.utc),
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    db_session.add_all([first, second])
    await db_session.commit()

    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    queue = TaskQueue(session_factory=session_factory)
    first_task = await queue.enqueue(first.run_id, weight=2)
    second_task = await queue.enqueue(second.run_id, weight=3)
    await queue.mark_dispatched(first_task.id, "worker-0")
    await queue.mark_dispatched(second_task.id, "worker-1")

    scheduler = RunScheduler(
        config=SchedulerConfig(total_slots=10, poll_interval_seconds=0.01),
        backend=NoopBackend(),
        session_factory=session_factory,
        queue=queue,
    )

    await scheduler.recover()

    assert scheduler._slots.used == 5
    assert scheduler._slots.available == 5
