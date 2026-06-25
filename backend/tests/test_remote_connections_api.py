from __future__ import annotations

import pytest

from app.api.deps import get_current_user
from app.auth.session import AuthUser
from app.workspace import DEFAULT_WORKSPACE_ID


OTHER_WORKSPACE_ID = "00000000-0000-0000-0000-000000000002"


def _auth_user(
    *,
    user_id: str = "user-1",
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    role: str = "owner",
) -> AuthUser:
    return AuthUser(
        id=user_id,
        name=f"User {user_id}",
        email=f"{user_id}@bioinfoflow.test",
        role=role,
        workspace_id=workspace_id,
    )


def _connection_payload(**overrides):
    payload = {
        "name": "HPC Login",
        "host": "login.example.org",
        "port": 22,
        "username": "alice",
        "auth_method": "key_file",
        "key_path": "~/.ssh/id_ed25519",
        "skill_instructions": "Load the project module before launching workflows.",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_remote_connection_crud_is_scoped_to_workspace(async_client, app):
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="user-1",
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    try:
        create_resp = await async_client.post(
            "/api/v1/connections",
            json=_connection_payload(),
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert create_resp.status_code == 201
    created = create_resp.json()["data"]
    connection_id = created["id"]
    assert created["workspace_id"] == DEFAULT_WORKSPACE_ID
    assert created["last_status"] == "unknown"
    assert created["last_error"] is None
    assert created["last_checked_at"] is None
    assert "password" not in created
    assert "private_key" not in created

    list_resp = await async_client.get("/api/v1/connections")
    assert list_resp.status_code == 200
    assert [item["id"] for item in list_resp.json()["data"]] == [connection_id]

    update_resp = await async_client.patch(
        f"/api/v1/connections/{connection_id}",
        json={
            "name": "HPC Login Updated",
            "ssh_alias": "hpc-login",
            "key_path": None,
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()["data"]
    assert updated["name"] == "HPC Login Updated"
    assert updated["ssh_alias"] == "hpc-login"
    assert updated["key_path"] is None

    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="user-2",
        workspace_id=OTHER_WORKSPACE_ID,
    )
    try:
        other_list = await async_client.get("/api/v1/connections")
        other_get = await async_client.get(f"/api/v1/connections/{connection_id}")
        other_patch = await async_client.patch(
            f"/api/v1/connections/{connection_id}",
            json={"name": "Cross workspace edit"},
        )
        other_delete = await async_client.delete(f"/api/v1/connections/{connection_id}")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert other_list.status_code == 200
    assert other_list.json()["data"] == []
    assert other_get.status_code == 404
    assert other_patch.status_code == 404
    assert other_delete.status_code == 404

    delete_resp = await async_client.delete(f"/api/v1/connections/{connection_id}")
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_remote_connection_validation_rejects_secret_material(async_client):
    invalid_auth = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(auth_method="password"),
    )
    assert invalid_auth.status_code == 422
    assert invalid_auth.json()["error"]["code"] == "VALIDATION_ERROR"

    secret_payload = _connection_payload(
        auth_method="agent",
        key_path=None,
        password="super-secret",
        private_key="-----BEGIN OPENSSH PRIVATE KEY-----",
    )
    secret_resp = await async_client.post("/api/v1/connections", json=secret_payload)
    assert secret_resp.status_code == 422
    assert secret_resp.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_remote_connection_test_uses_mockable_tester_and_persists_status(
    async_client,
    monkeypatch,
):
    create_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(auth_method="agent", key_path=None),
    )
    assert create_resp.status_code == 201
    connection_id = create_resp.json()["data"]["id"]

    from app.services.remote_connection_service import RemoteConnectionTestResult

    async def fake_test(self, connection):
        assert connection.host == "login.example.org"
        return RemoteConnectionTestResult(status="online", error=None)

    monkeypatch.setattr(
        "app.services.remote_connection_service.UnavailableRemoteConnectionTester.test",
        fake_test,
    )

    test_resp = await async_client.post(f"/api/v1/connections/{connection_id}/test")
    assert test_resp.status_code == 200
    test_data = test_resp.json()["data"]
    assert test_data["status"] == "online"
    assert test_data["error"] is None
    assert test_data["checked_at"] is not None
    assert test_data["connection"]["last_status"] == "online"
    assert test_data["connection"]["last_error"] is None
    assert test_data["connection"]["last_checked_at"] == test_data["checked_at"]

    get_resp = await async_client.get(f"/api/v1/connections/{connection_id}")
    assert get_resp.status_code == 200
    persisted = get_resp.json()["data"]
    assert persisted["last_status"] == "online"
    assert persisted["last_error"] is None
    assert persisted["last_checked_at"] == test_data["checked_at"]
