from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.engine.backend import EngineEvent, EngineEventType
from app.models.run import Run, RunStatus
from app.models.workflow import WorkflowEngine
from app.scheduler.config import SchedulerConfig
from app.scheduler.models import TaskState
from app.scheduler.queue import TaskQueue
from app.scheduler.scheduler import RunScheduler
from tests.support.path_contract import create_project, create_workflow


class FailingBackend:
    async def submit(self, adapter, config: dict, workspace: str):
        del adapter, config, workspace
        yield EngineEvent(
            EngineEventType.ERROR,
            {"message": "Executor killed with exit 137"},
        )

    async def cancel(self, adapter, *, pid: int | None, **kwargs) -> bool:
        del adapter, pid, kwargs
        return True


async def _seed_run(
    db_session: AsyncSession,
    *,
    status: str = RunStatus.QUEUED.value,
    config: dict | None = None,
) -> Run:
    project = await create_project(
        db_session,
        name=f"Retry Project {uuid4()}",
        storage_mode="managed",
    )
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        engine=WorkflowEngine.NEXTFLOW,
        content="workflow { }\n",
    )

    run = Run(
        run_id=f"run_retry_{uuid4().hex[:10]}",
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
async def test_retry_evaluator_matches_policy_and_caps_backoff():
    from app.scheduler.retry import RetryEvaluator, RetryPolicy

    policy = RetryPolicy(
        max_retries=3,
        delay_seconds=10,
        backoff_multiplier=3.0,
        max_delay_seconds=25,
        retry_on=["oom", "137"],
    )
    evaluator = RetryEvaluator()

    task = type(
        "Task",
        (),
        {
            "attempt": 2,
            "max_attempts": 4,
            "retry_policy": {
                "max_retries": policy.max_retries,
                "delay_seconds": policy.delay_seconds,
                "backoff_multiplier": policy.backoff_multiplier,
                "max_delay_seconds": policy.max_delay_seconds,
                "retry_on": list(policy.retry_on),
            },
        },
    )()

    assert evaluator.should_retry(task, "worker exited 137") is True
    assert evaluator.should_retry(task, "validation failed") is False
    assert evaluator.next_delay(task) == 25
    assert evaluator.is_oom_error("Out of memory while allocating buffer") is True
    assert evaluator.is_oom_error("permission denied") is False


@pytest.mark.asyncio
async def test_retry_evaluator_stops_after_max_attempts():
    from app.scheduler.retry import RetryEvaluator

    evaluator = RetryEvaluator()
    task = type(
        "Task",
        (),
        {
            "attempt": 3,
            "max_attempts": 3,
            "retry_policy": {"max_retries": 2},
        },
    )()

    assert evaluator.should_retry(task, "oom") is False


@pytest.mark.asyncio
async def test_scheduler_requeues_failed_run_when_retry_policy_matches(
    db_session,
    monkeypatch,
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
        backend=FailingBackend(),
        session_factory=session_factory,
        queue=queue,
    )
    run = await _seed_run(
        db_session,
        config={
            "params": {"outdir": "results"},
            "policy": {
                "retry": {
                    "max_retries": 2,
                    "delay_seconds": 3600,
                    "retry_on": ["137"],
                }
            },
        },
    )

    await scheduler.start()
    try:
        task = await scheduler.enqueue(run.run_id)
        for _ in range(100):
            await db_session.refresh(run)
            retried = await queue.get(task.id)
            if (
                retried is not None
                and retried.state == TaskState.QUEUED.value
                and retried.attempt == 2
                and getattr(run.status, "value", run.status) == RunStatus.QUEUED.value
            ):
                break
            await asyncio.sleep(0.02)
        else:
            raise AssertionError("run was not re-enqueued for retry")
    finally:
        await scheduler.stop()

    assert retried is not None
    assert retried.delay_until is not None
    delay_until = retried.delay_until
    if delay_until.tzinfo is None:
        delay_until = delay_until.replace(tzinfo=timezone.utc)
    assert delay_until > datetime.now(timezone.utc)
    assert retried.error_message == "Executor killed with exit 137"
    assert getattr(run.status, "value", run.status) == RunStatus.QUEUED.value
