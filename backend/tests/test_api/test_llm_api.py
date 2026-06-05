from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_llm_provider_model_and_profile_contract(async_client):
    create_provider = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Local OpenAI Compatible",
            "kind": "openai_compatible",
            "base_url": "http://localhost:11434/v1",
            "api_key_ref": "env:LOCAL_MODEL_KEY",
            "metadata": {"purpose": "contract-test"},
        },
    )
    assert create_provider.status_code == 201
    provider = create_provider.json()["data"]
    assert provider["kind"] == "openai_compatible"
    assert provider["metadata"] == {"purpose": "contract-test"}

    list_providers = await async_client.get("/api/v1/llm/providers")
    assert list_providers.status_code == 200
    assert [item["id"] for item in list_providers.json()["data"]] == [provider["id"]]

    test_provider = await async_client.post(
        f"/api/v1/llm/providers/{provider['id']}/test"
    )
    assert test_provider.status_code == 200
    assert test_provider.json()["data"]["success"] is True

    create_model = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": provider["id"],
            "model_id": "local-bio-coder",
            "display_name": "Local Bio Coder",
            "context_length": 128000,
            "supports_tools": True,
            "supports_streaming": True,
            "supports_json_schema": True,
            "supports_reasoning": True,
        },
    )
    assert create_model.status_code == 201
    model = create_model.json()["data"]
    assert model["model_id"] == "local-bio-coder"
    assert model["supports_tools"] is True

    create_profile = await async_client.post(
        "/api/v1/llm/model-profiles",
        json={
            "name": "Bioinformatics agent default",
            "task_type": "agent_core",
            "primary_model_id": model["id"],
            "reasoning_budget": 4096,
            "max_tokens": 8192,
        },
    )
    assert create_profile.status_code == 201
    profile = create_profile.json()["data"]
    assert profile["task_type"] == "agent_core"
    assert profile["primary_model_id"] == model["id"]

    list_profiles = await async_client.get("/api/v1/llm/model-profiles")
    assert list_profiles.status_code == 200
    assert [item["id"] for item in list_profiles.json()["data"]] == [profile["id"]]
