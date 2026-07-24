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


@pytest.mark.asyncio
async def test_search_context_runs_is_server_paginated_and_project_ranked(db_session):
    current_project = await create_project(
        db_session,
        name=f"Current {uuid4()}",
        storage_mode="managed",
    )
    other_project = await create_project(
        db_session,
        name=f"Other {uuid4()}",
        storage_mode="managed",
    )
    workflow = await create_workflow(
        db_session,
        name="searchable-rnaseq",
        engine=WorkflowEngine.NEXTFLOW,
        content="workflow { }\n",
    )
    runs = [
        Run(
            run_id=f"search-run-{index:04d}",
            project_id=str(
                current_project.id if index % 10 == 0 else other_project.id
            ),
            workflow_id=str(workflow.id),
            status=RunStatus.COMPLETED.value,
            config={"label": f"cohort {index}"},
            samples_count=0,
            tasks_total=0,
            tasks_completed=0,
        )
        for index in range(1001)
    ]
    db_session.add_all(runs)
    await db_session.commit()
    repo = RunRepository(db_session)

    first, pagination = await repo.search_context(
        workspace_id=str(current_project.workspace_id),
        query="searchable-rnaseq",
        current_project_id=str(current_project.id),
        limit=20,
    )
    second, _ = await repo.search_context(
        workspace_id=str(current_project.workspace_id),
        query="searchable-rnaseq",
        current_project_id=str(current_project.id),
        limit=20,
        cursor=pagination.next_cursor,
    )

    assert len(first) == 20
    assert pagination.has_more is True
    assert pagination.next_cursor
    assert all(str(run.project_id) == str(current_project.id) for run in first)
    assert {run.run_id for run in first}.isdisjoint({run.run_id for run in second})
