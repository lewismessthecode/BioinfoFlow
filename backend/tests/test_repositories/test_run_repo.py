from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.run import Run, RunStatus
from app.models.workflow import WorkflowEngine
from app.repositories.run_repo import RunRepository
from tests.support.path_contract import create_project, create_workflow


@pytest.mark.asyncio
async def test_mark_failed_does_not_overwrite_terminal_run(db_session):
    project = await create_project(
        db_session,
        name=f"Repo Project {uuid4()}",
        storage_mode="managed",
    )
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        engine=WorkflowEngine.NEXTFLOW,
        content="workflow { }\n",
    )
    run = Run(
        run_id=f"run_repo_terminal_{uuid4().hex[:10]}",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={"params": {"outdir": "results"}},
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    updated = await RunRepository(db_session).mark_failed(run.run_id, "late failure")
    await db_session.refresh(run)

    assert updated is None
    assert run.status == RunStatus.COMPLETED.value
    assert run.error_message is None
