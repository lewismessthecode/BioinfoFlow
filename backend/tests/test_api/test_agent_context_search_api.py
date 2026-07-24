from __future__ import annotations

import pytest

from app.models.project_workflow_binding import ProjectWorkflowBinding
from app.models.run import Run, RunStatus
from app.path_layout import project_home
from tests.support.path_contract import create_project, create_workflow


@pytest.mark.asyncio
async def test_context_search_api_returns_balanced_results(async_client, db_session) -> None:
    project = await create_project(
        db_session,
        name="API context project",
        storage_mode="managed",
    )
    root = project_home(project)
    root.mkdir(parents=True, exist_ok=True)
    for index in range(6):
        (root / f"api-match-{index}.txt").write_text("content", encoding="utf-8")
    for index in range(3):
        workflow = await create_workflow(
            db_session,
            name=f"api-match-workflow-{index}",
            content="workflow { }\n",
        )
        db_session.add(
            ProjectWorkflowBinding(
                project_id=str(project.id), workflow_id=str(workflow.id)
            )
        )
        db_session.add(
            Run(
                run_id=f"api-match-run-{index}",
                project_id=str(project.id),
                workflow_id=str(workflow.id),
                status=RunStatus.COMPLETED.value,
                config={},
                samples_count=0,
                tasks_total=0,
                tasks_completed=0,
            )
        )
    await db_session.commit()

    response = await async_client.get(
        "/api/v1/agent/context/search",
        params={"q": "api-match", "scope": "mixed", "project_id": str(project.id)},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["counts"] == {"file": 4, "workflow": 2, "run": 2}
    assert len(data["results"]) == 8


@pytest.mark.asyncio
async def test_only_run_scope_accepts_cursor(async_client) -> None:
    response = await async_client.get(
        "/api/v1/agent/context/search",
        params={"q": "", "scope": "mixed", "cursor": "opaque"},
    )
    assert response.status_code == 400
