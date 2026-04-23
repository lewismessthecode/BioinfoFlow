from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.workflow import WorkflowEngine, WorkflowSource
from app.services.project_workflow_service import ProjectWorkflowService
from tests.support.path_contract import bind_workflow, create_project, create_workflow


@pytest.mark.asyncio
async def test_list_project_workflows_groups_versions_and_respects_explicit_pin(db_session):
    project = await create_project(db_session, name=f"Project {uuid4()}")
    shared_name = f"wf-{uuid4()}"
    older = await create_workflow(
        db_session,
        name=shared_name,
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0",
    )
    newer = await create_workflow(
        db_session,
        name=shared_name,
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="2.0.0",
    )
    other = await create_workflow(
        db_session,
        name=f"other-{uuid4()}",
        source=WorkflowSource.GITHUB,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0",
    )

    service = ProjectWorkflowService(db_session)
    await service.bind_workflow(project_id=str(project.id), workflow_id=str(older.id))
    await service.bind_workflow(project_id=str(project.id), workflow_id=str(newer.id))
    await service.bind_workflow(project_id=str(project.id), workflow_id=str(other.id))

    base_time = datetime(2026, 4, 23, tzinfo=timezone.utc)
    older.created_at = base_time
    newer.created_at = base_time + timedelta(minutes=1)
    await db_session.commit()

    await service.set_pin(project_id=str(project.id), pinned_workflow_id=str(older.id))

    groups = await service.list_project_workflows(project_id=str(project.id))

    assert [(group["source"], group["name"]) for group in groups] == [
        ("github", other.name),
        ("local", shared_name),
    ]
    local_group = groups[1]
    assert str(local_group["pinned_workflow"].id) == str(older.id)
    assert [str(workflow.id) for workflow in local_group["versions"]] == [
        str(newer.id),
        str(older.id),
    ]


@pytest.mark.asyncio
async def test_unbind_workflow_removes_dangling_binding_when_workflow_row_is_missing(db_session):
    project = await create_project(db_session, name=f"Project {uuid4()}")
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0",
    )
    await bind_workflow(
        db_session,
        project_id=str(project.id),
        workflow_id=str(workflow.id),
    )

    service = ProjectWorkflowService(db_session)
    binding = await service.binding_repo.get_by_project_workflow(
        project_id=str(project.id),
        workflow_id=str(workflow.id),
    )
    assert binding is not None

    await service.workflow_repo.delete(workflow)

    await service.unbind_workflow(
        project_id=str(project.id),
        workflow_id=str(workflow.id),
    )

    assert (
        await service.binding_repo.get_by_project_workflow(
            project_id=str(project.id),
            workflow_id=str(workflow.id),
        )
        is None
    )
