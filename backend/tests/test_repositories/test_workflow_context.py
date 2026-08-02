from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.project_workflow_binding import ProjectWorkflowBinding
from app.repositories.workflow_repo import WorkflowRepository
from tests.support.path_contract import create_project, create_workflow


@pytest.mark.asyncio
async def test_search_context_preserves_project_binding_and_order(db_session):
    project = await create_project(
        db_session,
        name="Context project",
        storage_mode="managed",
    )
    other_project = await create_project(
        db_session,
        name="Other project",
        storage_mode="managed",
    )
    older = await create_workflow(
        db_session,
        name="context-older",
        content="workflow { }\n",
    )
    newer = await create_workflow(
        db_session,
        name="context-newer",
        content="workflow { }\n",
    )
    unbound = await create_workflow(
        db_session,
        name="context-unbound",
        content="workflow { }\n",
    )
    other = await create_workflow(
        db_session,
        name="context-other-project",
        content="workflow { }\n",
    )
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    older.created_at = base_time
    newer.created_at = base_time + timedelta(minutes=1)
    db_session.add_all(
        [
            ProjectWorkflowBinding(
                project_id=str(project.id), workflow_id=str(older.id)
            ),
            ProjectWorkflowBinding(
                project_id=str(project.id), workflow_id=str(newer.id)
            ),
            ProjectWorkflowBinding(
                project_id=str(other_project.id), workflow_id=str(other.id)
            ),
        ]
    )
    await db_session.commit()

    workflows = await WorkflowRepository(db_session).search_context(
        query="context",
        project_id=str(project.id),
        limit=10,
    )

    assert [workflow.id for workflow in workflows] == [newer.id, older.id]
    assert unbound.id not in {workflow.id for workflow in workflows}
    assert other.id not in {workflow.id for workflow in workflows}
