from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.project import Project
from app.models.run import RunStatus
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.runtime.jobs import recover_stale_runs
from app.services.run_service import RunService


@pytest.mark.asyncio
async def test_recover_stale_runs_marks_queued_and_running_as_failed(
    db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project = Project(
        name="Recovery Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
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

    service = RunService(db_session)
    stale_started = datetime.now(timezone.utc) - timedelta(hours=2)
    stale_created = datetime.now(timezone.utc) - timedelta(hours=3)

    running = await service.repo.create(
        run_id="run_recover_running",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.RUNNING.value,
        config={"params": {}},
        started_at=stale_started,
        created_at=stale_created,
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    queued = await service.repo.create(
        run_id="run_recover_queued",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.QUEUED.value,
        config={"params": {}},
        created_at=stale_created,
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )

    recovered = await recover_stale_runs(session=db_session, stale_after_minutes=30)
    assert recovered == 2

    running_refreshed = await service.get_run(running.run_id)
    queued_refreshed = await service.get_run(queued.run_id)
    assert running_refreshed.status == RunStatus.FAILED.value
    assert queued_refreshed.status == RunStatus.FAILED.value
    assert running_refreshed.error_message.startswith("Run recovery:")
    assert queued_refreshed.error_message.startswith("Run recovery:")


@pytest.mark.asyncio
async def test_recover_stale_runs_skips_when_runs_table_missing(tmp_path):
    db_path = tmp_path / "empty.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_maker = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    try:
        async with session_maker() as session:
            recovered = await recover_stale_runs(
                session=session, stale_after_minutes=30
            )
        assert recovered == 0
    finally:
        await engine.dispose()
