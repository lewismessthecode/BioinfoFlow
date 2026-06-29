from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_container_registry_crud_redacts_stored_credentials(async_client):
    create_resp = await async_client.post(
        "/api/v1/container-registries",
        json={
            "name": "Harbor Bio",
            "endpoint": "https://harbor.example.test",
            "namespace": "bio",
            "insecure": False,
            "is_default": True,
            "credential_source": "stored",
            "username": "robot-user",
            "password": "top-secret-value",
        },
    )

    assert create_resp.status_code == 201
    registry = create_resp.json()["data"]
    assert registry["name"] == "Harbor Bio"
    assert registry["endpoint"] == "https://harbor.example.test"
    assert registry["namespace"] == "bio"
    assert registry["insecure"] is False
    assert registry["is_default"] is True
    assert registry["credential_source"] == "stored"
    assert registry["username_hint"] == "robo...user"
    assert registry["password_hint"] == "top-...alue"
    assert registry["last_status"] == "untested"
    assert registry["last_error"] is None
    assert registry["last_checked_at"] is None
    assert "username" not in registry
    assert "password" not in registry
    assert "encrypted_username" not in registry
    assert "encrypted_password" not in registry

    list_resp = await async_client.get("/api/v1/container-registries")
    assert list_resp.status_code == 200
    assert [item["id"] for item in list_resp.json()["data"]] == [registry["id"]]

    update_resp = await async_client.patch(
        f"/api/v1/container-registries/{registry['id']}",
        json={"namespace": "bio-prod", "insecure": True},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()["data"]
    assert updated["namespace"] == "bio-prod"
    assert updated["insecure"] is True
    assert "password" not in updated
    assert "encrypted_password" not in updated

    delete_resp = await async_client.delete(
        f"/api/v1/container-registries/{registry['id']}"
    )
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_container_registry_default_is_global_singleton(async_client):
    first_resp = await async_client.post(
        "/api/v1/container-registries",
        json={
            "name": "GHCR",
            "endpoint": "https://ghcr.io",
            "is_default": True,
            "credential_source": "none",
        },
    )
    assert first_resp.status_code == 201
    first = first_resp.json()["data"]

    second_resp = await async_client.post(
        "/api/v1/container-registries",
        json={
            "name": "Quay",
            "endpoint": "https://quay.io",
            "is_default": True,
            "credential_source": "none",
        },
    )
    assert second_resp.status_code == 201
    second = second_resp.json()["data"]

    list_resp = await async_client.get("/api/v1/container-registries")
    assert list_resp.status_code == 200
    defaults = [
        item for item in list_resp.json()["data"] if item["is_default"]
    ]
    assert defaults == [second]

    get_first_resp = await async_client.get(
        f"/api/v1/container-registries/{first['id']}"
    )
    assert get_first_resp.status_code == 200
    assert get_first_resp.json()["data"]["is_default"] is False


@pytest.mark.asyncio
async def test_container_registry_test_uses_env_credential_availability(
    async_client,
    monkeypatch,
):
    monkeypatch.setenv("BIO_REGISTRY_USER", "robot")
    monkeypatch.setenv("BIO_REGISTRY_PASSWORD", "secret")
    create_resp = await async_client.post(
        "/api/v1/container-registries",
        json={
            "name": "Env registry",
            "endpoint": "https://registry.example.test",
            "credential_source": "env",
            "env_username_var": "BIO_REGISTRY_USER",
            "env_password_var": "BIO_REGISTRY_PASSWORD",
        },
    )
    assert create_resp.status_code == 201
    registry = create_resp.json()["data"]
    assert registry["username_hint"] == "env:BIO_REGISTRY_USER"
    assert registry["password_hint"] == "env:BIO_REGISTRY_PASSWORD"

    test_resp = await async_client.post(
        f"/api/v1/container-registries/{registry['id']}/test"
    )
    assert test_resp.status_code == 200
    result = test_resp.json()["data"]
    assert result["registry_id"] == registry["id"]
    assert result["success"] is True
    assert result["status"] == "ok"
    assert result["error"] is None
    assert result["checked_at"] is not None

    get_resp = await async_client.get(
        f"/api/v1/container-registries/{registry['id']}"
    )
    assert get_resp.status_code == 200
    refreshed = get_resp.json()["data"]
    assert refreshed["last_status"] == "ok"
    assert refreshed["last_error"] is None
    assert refreshed["last_checked_at"] == result["checked_at"]
