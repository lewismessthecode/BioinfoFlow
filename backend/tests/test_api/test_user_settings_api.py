from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_user_settings_get_update_and_models(async_client):
    initial = await async_client.get("/api/v1/user-settings")

    assert initial.status_code == 200
    assert initial.json()["data"] == {
        "provider_credentials": {},
        "selected_provider": "auto",
        "selected_model": "",
        "configured_providers": [],
    }

    update = await async_client.patch(
        "/api/v1/user-settings",
        json={
            "provider_credentials": {
                "openai": {
                    "api_key": "sk-test-openai-secret-value",
                    "base_url": "https://example.com/v1",
                }
            },
            "selected_provider": "openai",
            "selected_model": "gpt-5.4",
        },
    )

    assert update.status_code == 200
    payload = update.json()["data"]
    assert payload["selected_provider"] == "openai"
    assert payload["selected_model"] == "gpt-5.4"
    assert payload["configured_providers"] == ["openai"]
    assert payload["provider_credentials"]["openai"]["api_key"] != "sk-test-openai-secret-value"
    assert "..." in payload["provider_credentials"]["openai"]["api_key"]
    assert payload["provider_credentials"]["openai"]["base_url"] == "https://example.com/v1"

    models = await async_client.get("/api/v1/user-settings/models")

    assert models.status_code == 200
    models_by_provider = {
        entry["provider"]: entry for entry in models.json()["data"]
    }
    assert "openai" in models_by_provider
    assert models_by_provider["openai"]["label"] == "OpenAI"
    assert any(model["id"] == "gpt-5.4" for model in models_by_provider["openai"]["models"])


@pytest.mark.asyncio
async def test_user_settings_test_provider_surfaces_service_result(async_client):
    resp = await async_client.post("/api/v1/user-settings/test/anthropic")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider"] == "anthropic"
    assert data["success"] is False
    assert data["error"] == "No settings configured"


@pytest.mark.asyncio
async def test_user_settings_test_provider_rejects_unknown_provider(async_client):
    resp = await async_client.post("/api/v1/user-settings/test/not-a-provider")

    assert resp.status_code == 400
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_PROVIDER"
