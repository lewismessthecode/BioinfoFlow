from __future__ import annotations

import pytest

from app.repositories.project_repo import ProjectRepository
from app.repositories.workflow_repo import WorkflowRepository
from app.models.workflow import WorkflowEngine, WorkflowSource


@pytest.mark.asyncio
async def test_project_repository_crud(db_session):
    repo = ProjectRepository(db_session)
    project = await repo.create(
        name="Repo Project",
        description="desc",
        storage_mode="managed",
        external_root_path=None,
        user_id="dev",
    )
    fetched = await repo.get(project.id)
    assert fetched is not None
    items, pagination = await repo.list(limit=1)
    assert pagination.limit == 1
    assert len(items) == 1


@pytest.mark.asyncio
async def test_workflow_repository_unique(db_session):
    repo = WorkflowRepository(db_session)
    workflow = await repo.create(
        name="nf-core/viralrecon",
        description="desc",
        source=WorkflowSource.NFCORE.value,
        engine=WorkflowEngine.NEXTFLOW.value,
        source_ref="nf-core/viralrecon",
        entrypoint_relpath=None,
        bundle_kind="remote_ref",
        version="2.6.0",
        estimated_time=None,
        schema_json=None,
    )
    fetched = await repo.get_by_unique(
        source=WorkflowSource.NFCORE.value,
        name=workflow.name,
        version=workflow.version,
    )
    assert fetched is not None
