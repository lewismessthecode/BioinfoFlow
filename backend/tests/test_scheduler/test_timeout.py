from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.project import Project
from app.models.run import Run, RunStatus
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource


class FakeScheduler:
    def __init__(self) -> None:
        self.cancel_calls: list[dict[str, str]] = []

    async def cancel(self, run_id: str, *, reason: str | None = None) -> bool:
        self.cancel_calls.append({"run_id": run_id, "reason": reason or ""})
        return True


async def _seed_run(
    db_session: AsyncSession,
    *,
    status: str = RunStatus.RUNNING.value,
    started_at: datetime | None = None,
    config: dict | None = None,
) -> Run:
    project = Project(
        name=f"Timeout Project {uuid4()}", storage_mode="managed", external_root_path=None, user_id="dev"
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
        run_id=f"run_timeout_{uuid4().hex[:10]}",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=status,
        started_at=started_at,
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
async def test_timeout_watcher_cancels_runs_past_configured_timeout(db_session):
    from app.scheduler.timeout import TimeoutWatcher

    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    scheduler = FakeScheduler()
    old_run = await _seed_run(
        db_session,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        config={"policy": {"timeout_seconds": 30}},
    )
    await _seed_run(
        db_session,
        started_at=datetime.now(timezone.utc) - timedelta(seconds=20),
        config={"policy": {"timeout_seconds": 300}},
    )

    watcher = TimeoutWatcher(
        scheduler=scheduler,
        session_factory=session_factory,
        check_interval=0.01,
    )

    await watcher._check_timeouts()

    assert scheduler.cancel_calls == [
        {
            "run_id": old_run.run_id,
            "reason": "Run exceeded timeout of 30 seconds",
        }
    ]


# --- Phase 2 Fix 13: Timeout watcher exception handling ---


@pytest.mark.asyncio
async def test_timeout_watcher_survives_check_exception(db_session, monkeypatch):
    """Watch loop should continue running after an exception in _check_timeouts."""
    import asyncio

    from app.scheduler.timeout import TimeoutWatcher

    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    scheduler = FakeScheduler()
    watcher = TimeoutWatcher(
        scheduler=scheduler,
        session_factory=session_factory,
        check_interval=0.01,
    )

    check_count = 0
    original_check = watcher._check_timeouts

    async def crashing_then_normal():
        nonlocal check_count
        check_count += 1
        if check_count == 1:
            raise RuntimeError("Simulated DB error")
        await original_check()

    monkeypatch.setattr(watcher, "_check_timeouts", crashing_then_normal)

    await watcher.start()
    try:
        # Wait enough time for multiple check cycles
        for _ in range(200):
            if check_count >= 3:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError(
                f"Watcher did not survive exception — only ran {check_count} checks"
            )
    finally:
        await watcher.stop()

    assert check_count >= 3
