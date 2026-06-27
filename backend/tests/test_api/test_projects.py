from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_projects_crud(async_client):
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
    assert "workspace_path" not in data["data"]
    assert "data_roots" not in data["data"]

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

    delete_resp = await async_client.delete(f"/api/v1/projects/{project_id}")
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_default_project_endpoint_is_stable_and_not_deletable(async_client):
    first_resp = await async_client.get("/api/v1/projects/default")
    assert first_resp.status_code == 200
    first_data = first_resp.json()
    assert first_data["success"] is True
    assert first_data["data"]["is_default"] is True
    assert first_data["data"]["storage_mode"] == "managed"
    assert first_data["data"]["project_root"] == "asset://project"

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
async def test_create_remote_project_binds_connection_and_path(async_client):
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
