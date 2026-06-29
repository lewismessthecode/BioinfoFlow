from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.project import Project
from app.models.run import Run, RunStatus
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.scheduler.models import ScheduledTask, TaskState


async def _seed_project_and_workflow(db_session) -> tuple[Project, Workflow]:
    project = Project(
        name=f"Project {uuid4()}",
        storage_mode="managed",
        external_root_path=None,
        user_id="dev",
    )
    workflow = Workflow(
        name=f"Workflow {uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.WDL,
        version=str(uuid4()),
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)
    return project, workflow


def _run(
    *,
    run_id: str,
    project: Project,
    workflow: Workflow,
    status: str = RunStatus.QUEUED.value,
    source_run_id: str | None = None,
    replay_kind: str | None = None,
    replay_idempotency_key: str | None = None,
    attempt_number: int = 1,
) -> Run:
    payload = {
        "run_id": run_id,
        "project_id": str(project.id),
        "workflow_id": str(workflow.id),
        "status": status,
        "config": {"config_schema_version": 1, "request": {"values": {}}},
        "samples_count": 0,
        "tasks_total": 0,
        "tasks_completed": 0,
    }
    if source_run_id is not None:
        payload["source_run_id"] = source_run_id
    if replay_kind is not None:
        payload["replay_kind"] = replay_kind
    if replay_idempotency_key is not None:
        payload["replay_idempotency_key"] = replay_idempotency_key
    if attempt_number != 1:
        payload["attempt_number"] = attempt_number
    return Run(**payload)


@pytest.mark.asyncio
async def test_run_status_is_database_constrained(db_session):
    project, workflow = await _seed_project_and_workflow(db_session)
    db_session.add(
        _run(
            run_id="run_invalid_status",
            project=project,
            workflow=workflow,
            status="typoed",
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_scheduled_task_has_one_active_row_per_run(db_session):
    project, workflow = await _seed_project_and_workflow(db_session)
    run = _run(run_id="run_active_task_unique", project=project, workflow=workflow)
    db_session.add(run)
    await db_session.commit()

    db_session.add_all(
        [
            ScheduledTask(run_id=run.run_id, state=TaskState.QUEUED.value),
            ScheduledTask(run_id=run.run_id, state=TaskState.DISPATCHED.value),
        ]
    )

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_active_replay_idempotency_is_database_constrained(db_session):
    project, workflow = await _seed_project_and_workflow(db_session)
    source = _run(
        run_id="run_source_for_replay_unique",
        project=project,
        workflow=workflow,
        status=RunStatus.FAILED.value,
    )
    first = _run(
        run_id="run_replay_first",
        project=project,
        workflow=workflow,
        source_run_id=source.run_id,
        replay_kind="retry",
        replay_idempotency_key="same-intent",
        attempt_number=2,
    )
    second = _run(
        run_id="run_replay_second",
        project=project,
        workflow=workflow,
        source_run_id=source.run_id,
        replay_kind="retry",
        replay_idempotency_key="same-intent",
        attempt_number=2,
    )
    db_session.add_all([source, first, second])

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_replay_lineage_fields_are_all_or_none(db_session):
    project, workflow = await _seed_project_and_workflow(db_session)
    source = _run(
        run_id="run_source_for_partial_lineage",
        project=project,
        workflow=workflow,
        status=RunStatus.FAILED.value,
    )
    partial = _run(
        run_id="run_partial_lineage",
        project=project,
        workflow=workflow,
        source_run_id=source.run_id,
        attempt_number=2,
    )
    db_session.add_all([source, partial])

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_original_run_attempt_number_is_one(db_session):
    project, workflow = await _seed_project_and_workflow(db_session)
    db_session.add(
        _run(
            run_id="run_original_attempt_two",
            project=project,
            workflow=workflow,
            attempt_number=2,
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_replay_run_cannot_source_itself(db_session):
    project, workflow = await _seed_project_and_workflow(db_session)
    db_session.add(
        _run(
            run_id="run_self_source",
            project=project,
            workflow=workflow,
            source_run_id="run_self_source",
            replay_kind="retry",
            replay_idempotency_key="self-source",
            attempt_number=2,
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_replay_idempotency_is_database_constrained_after_terminal(db_session):
    project, workflow = await _seed_project_and_workflow(db_session)
    source = _run(
        run_id="run_source_for_later_replay",
        project=project,
        workflow=workflow,
        status=RunStatus.FAILED.value,
    )
    first = _run(
        run_id="run_terminal_replay",
        project=project,
        workflow=workflow,
        status=RunStatus.FAILED.value,
        source_run_id=source.run_id,
        replay_kind="retry",
        replay_idempotency_key="same-intent-after-terminal",
        attempt_number=2,
    )
    second = _run(
        run_id="run_later_replay",
        project=project,
        workflow=workflow,
        status=RunStatus.QUEUED.value,
        source_run_id=source.run_id,
        replay_kind="retry",
        replay_idempotency_key="same-intent-after-terminal",
        attempt_number=2,
    )
    db_session.add_all([source, first, second])

    with pytest.raises(IntegrityError):
        await db_session.commit()
