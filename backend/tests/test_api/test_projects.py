from __future__ import annotations

import pytest

from app.models.project import Project
from app.path_layout import project_data_root, project_home, project_runs_root


@pytest.mark.asyncio
async def test_projects_crud(async_client, db_session):
    payload = {
        "name": "API Project",
        "description": "Test project",
    }
    create_resp = await async_client.post("/api/v1/projects", json=payload)
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["success"] is True
    project_id = data["data"]["id"]
    assert data["data"]["storage_mode"] == "managed"
    assert data["data"]["project_root"] == "asset://project"
    assert "directory_name" not in data["data"]
    assert "workspace_path" not in data["data"]
    assert "data_roots" not in data["data"]
    project = await db_session.get(Project, project_id)
    assert project is not None
    assert project.directory_name == "api-project"
    original_home = project_home(project)
    assert project_data_root(project).is_dir()
    assert project_runs_root(project).is_dir()

    list_resp = await async_client.get("/api/v1/projects")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert "pagination" in list_data["meta"]
    assert list_data["data"][0]["project_root"] == "asset://project"

    get_resp = await async_client.get(f"/api/v1/projects/{project_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["storage_mode"] == "managed"

    update_resp = await async_client.patch(
        f"/api/v1/projects/{project_id}", json={"name": "API Project Updated"}
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["data"]["name"] == "API Project Updated"
    await db_session.refresh(project)
    assert project.directory_name == "api-project"
    assert project_home(project) == original_home

    delete_resp = await async_client.delete(f"/api/v1/projects/{project_id}")
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_projects_api_suffixes_duplicate_managed_names(async_client, db_session):
    first = await async_client.post("/api/v1/projects", json={"name": "API Project"})
    second = await async_client.post("/api/v1/projects", json={"name": "API Project"})

    assert first.status_code == 201
    assert second.status_code == 201
    first_project = await db_session.get(Project, first.json()["data"]["id"])
    second_project = await db_session.get(Project, second.json()["data"]["id"])
    assert first_project is not None and second_project is not None
    assert first_project.directory_name == "api-project"
    assert second_project.directory_name == "api-project-2"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["post", "patch"])
async def test_projects_api_rejects_directory_name_input(async_client, method):
    if method == "post":
        response = await async_client.post(
            "/api/v1/projects",
            json={"name": "Injected", "directory_name": "chosen-by-client"},
        )
    else:
        created = await async_client.post(
            "/api/v1/projects",
            json={"name": "Update target"},
        )
        response = await async_client.patch(
            f"/api/v1/projects/{created.json()['data']['id']}",
            json={"directory_name": "chosen-by-client"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_default_project_endpoint_is_stable_and_not_deletable(
    async_client, db_session
):
    first_resp = await async_client.get("/api/v1/projects/default")
    assert first_resp.status_code == 200
    first_data = first_resp.json()
    assert first_data["success"] is True
    assert first_data["data"]["is_default"] is True
    assert first_data["data"]["storage_mode"] == "managed"
    assert first_data["data"]["project_root"] == "asset://project"
    assert "directory_name" not in first_data["data"]
    project = await db_session.get(Project, first_data["data"]["id"])
    assert project is not None
    assert project.directory_name == "recent"
    assert project_home(project).name == "recent"

    second_resp = await async_client.get("/api/v1/projects/default")
    assert second_resp.status_code == 200
    second_data = second_resp.json()
    assert second_data["data"]["id"] == first_data["data"]["id"]

    delete_resp = await async_client.delete(
        f"/api/v1/projects/{first_data['data']['id']}"
    )
    assert delete_resp.status_code == 403
    assert delete_resp.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_default_project_endpoint_preserves_legacy_uuid_directory(
    async_client, db_session
):
    legacy = Project(
        name="Recent",
        storage_mode="managed",
        user_id="dev",
        workspace_id="00000000-0000-0000-0000-000000000001",
        is_default=True,
    )
    db_session.add(legacy)
    await db_session.commit()

    response = await async_client.get("/api/v1/projects/default")

    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(legacy.id)
    await db_session.refresh(legacy)
    assert legacy.directory_name is None
    assert project_home(legacy).name == str(legacy.id)


@pytest.mark.asyncio
async def test_create_remote_project_binds_connection_and_path(
    async_client, db_session
):
    connection_resp = await async_client.post(
        "/api/v1/connections",
        json={
            "name": "Phoenix login",
            "host": "login.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "agent",
            "skill_instructions": "Use phoenixcli for platform jobs.",
        },
    )
    assert connection_resp.status_code == 201
    connection_id = connection_resp.json()["data"]["id"]

    create_resp = await async_client.post(
        "/api/v1/projects",
        json={
            "name": "Phoenix sample",
            "description": "Remote shared-storage project",
            "remote_connection_id": connection_id,
            "remote_root_path": "/inspurfsms102/B2C_RD1/project/sample_xxx/",
        },
    )

    assert create_resp.status_code == 201
    data = create_resp.json()["data"]
    assert data["storage_mode"] == "remote"
    assert data["remote_connection_id"] == connection_id
    assert data["remote_root_path"] == "/inspurfsms102/B2C_RD1/project/sample_xxx"
    assert data["project_root"] == (
        f"ssh://{connection_id}/inspurfsms102/B2C_RD1/project/sample_xxx"
    )
    project = await db_session.get(Project, data["id"])
    assert project is not None
    assert project.directory_name is None


@pytest.mark.asyncio
async def test_create_remote_project_requires_workspace_connection(async_client):
    create_resp = await async_client.post(
        "/api/v1/projects",
        json={
            "name": "Missing remote",
            "remote_connection_id": "00000000-0000-0000-0000-000000000099",
            "remote_root_path": "/data/project",
        },
    )

    assert create_resp.status_code == 404
    assert create_resp.json()["error"]["code"] == "NOT_FOUND"
