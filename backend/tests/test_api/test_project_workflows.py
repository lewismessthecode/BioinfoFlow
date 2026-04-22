from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.workflow import WorkflowEngine, WorkflowSource
from tests.support.path_contract import create_project, create_workflow


@pytest.mark.asyncio
async def test_project_workflows_bind_list_pin_unbind(
    async_client, db_session
):
    project = await create_project(db_session, name="PW Project")
    name = f"wf-{uuid4()}"
    wf_v1 = await create_workflow(
        db_session,
        name=name,
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0",
    )
    wf_v2 = await create_workflow(
        db_session,
        name=name,
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="2.0.0",
    )

    # No bindings yet
    empty = await async_client.get(f"/api/v1/projects/{project.id}/workflows")
    assert empty.status_code == 200
    assert empty.json()["data"] == []

    bind1 = await async_client.post(
        f"/api/v1/projects/{project.id}/workflows/{wf_v1.id}:bind"
    )
    assert bind1.status_code == 201

    listed = await async_client.get(f"/api/v1/projects/{project.id}/workflows")
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1
    group = listed.json()["data"][0]
    assert group["name"] == name
    assert group["pinned_workflow"]["id"] == str(wf_v1.id)
    assert len(group["versions"]) == 1

    bind2 = await async_client.post(
        f"/api/v1/projects/{project.id}/workflows/{wf_v2.id}:bind"
    )
    assert bind2.status_code == 201

    listed2 = await async_client.get(f"/api/v1/projects/{project.id}/workflows")
    group2 = listed2.json()["data"][0]
    assert len(group2["versions"]) == 2

    pin = await async_client.post(
        f"/api/v1/projects/{project.id}/workflow-pins",
        json={"pinned_workflow_id": str(wf_v2.id)},
    )
    assert pin.status_code == 201

    listed3 = await async_client.get(f"/api/v1/projects/{project.id}/workflows")
    group3 = listed3.json()["data"][0]
    assert group3["pinned_workflow"]["id"] == str(wf_v2.id)

    unbind1 = await async_client.delete(
        f"/api/v1/projects/{project.id}/workflows/{wf_v1.id}:unbind"
    )
    assert unbind1.status_code == 204

    listed4 = await async_client.get(f"/api/v1/projects/{project.id}/workflows")
    group4 = listed4.json()["data"][0]
    assert len(group4["versions"]) == 1
    assert group4["pinned_workflow"]["id"] == str(wf_v2.id)

    unbind2 = await async_client.delete(
        f"/api/v1/projects/{project.id}/workflows/{wf_v2.id}:unbind"
    )
    assert unbind2.status_code == 204

    listed5 = await async_client.get(f"/api/v1/projects/{project.id}/workflows")
    assert listed5.status_code == 200
    assert listed5.json()["data"] == []


@pytest.mark.asyncio
async def test_project_workflows_duplicate_bind_is_idempotent(
    async_client, db_session
):
    project = await create_project(db_session, name="PW Duplicate")
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0",
    )

    first_bind = await async_client.post(
        f"/api/v1/projects/{project.id}/workflows/{workflow.id}:bind"
    )
    second_bind = await async_client.post(
        f"/api/v1/projects/{project.id}/workflows/{workflow.id}:bind"
    )

    assert first_bind.status_code == 201
    assert second_bind.status_code == 201

    listed = await async_client.get(f"/api/v1/projects/{project.id}/workflows")
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1
    assert len(listed.json()["data"][0]["versions"]) == 1


@pytest.mark.asyncio
async def test_project_workflows_unbind_missing_workflow_returns_not_found(
    async_client, db_session
):
    project = await create_project(db_session, name="PW Missing")

    resp = await async_client.delete(
        f"/api/v1/projects/{project.id}/workflows/{uuid4()}:unbind"
    )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_project_workflows_pin_requires_bound_workflow(
    async_client, db_session
):
    project = await create_project(db_session, name="PW Pin")
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0",
    )

    resp = await async_client.post(
        f"/api/v1/projects/{project.id}/workflow-pins",
        json={"pinned_workflow_id": str(workflow.id)},
    )

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "WORKFLOW_NOT_ENABLED_FOR_PROJECT"


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["project", "workflow"])
async def test_project_workflows_pin_missing_resources_return_not_found(
    async_client, db_session, missing
):
    project = await create_project(db_session, name="PW Missing Pin")
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0",
    )

    project_id = str(uuid4()) if missing == "project" else str(project.id)
    workflow_id = str(uuid4()) if missing == "workflow" else str(workflow.id)

    resp = await async_client.post(
        f"/api/v1/projects/{project_id}/workflow-pins",
        json={"pinned_workflow_id": workflow_id},
    )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_project_workflows_pin_invalid_workflow_payload_returns_validation_error(
    async_client, db_session
):
    project = await create_project(db_session, name="PW Invalid")
    workflow = await create_workflow(
        db_session,
        name="",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0",
    )

    bind_resp = await async_client.post(
        f"/api/v1/projects/{project.id}/workflows/{workflow.id}:bind"
    )
    assert bind_resp.status_code == 201

    resp = await async_client.post(
        f"/api/v1/projects/{project.id}/workflow-pins",
        json={"pinned_workflow_id": str(workflow.id)},
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
