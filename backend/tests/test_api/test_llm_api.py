from __future__ import annotations

import pytest

from app.api.deps import get_current_user
from app.auth.session import AuthUser
from app.config import settings
from app.models.llm import LlmModel, LlmModelProfile, LlmProvider
from app.workspace import DEFAULT_WORKSPACE_ID


OTHER_WORKSPACE_ID = "00000000-0000-0000-0000-000000000002"
OTHER_PROVIDER_ID = "00000000-0000-0000-0000-00000000aa01"
OTHER_MODEL_ID = "00000000-0000-0000-0000-00000000bb01"
OTHER_PROFILE_ID = "00000000-0000-0000-0000-00000000cc01"


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


async def _create_provider(
    db_session,
    *,
    name: str,
    scope: str = "user",
    workspace_id: str | None = DEFAULT_WORKSPACE_ID,
    user_id: str | None = "user-1",
) -> LlmProvider:
    provider = LlmProvider(
        name=name,
        kind="openai_compatible",
        base_url="http://localhost:11434/v1",
        api_key_ref="env:TEST_KEY",
        scope=scope,
        workspace_id=workspace_id,
        user_id=user_id,
        enabled=True,
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    return provider


async def _create_model(
    db_session,
    *,
    provider_id: str,
    model_id: str,
    display_name: str,
) -> LlmModel:
    model = LlmModel(
        provider_id=provider_id,
        model_id=model_id,
        display_name=display_name,
        supports_tools=True,
        supports_streaming=True,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


async def _create_profile(
    db_session,
    *,
    name: str,
    primary_model_id: str,
    scope: str = "user",
    workspace_id: str | None = DEFAULT_WORKSPACE_ID,
    user_id: str | None = "user-1",
) -> LlmModelProfile:
    profile = LlmModelProfile(
        name=name,
        task_type="agent_core",
        primary_model_id=primary_model_id,
        scope=scope,
        workspace_id=workspace_id,
        user_id=user_id,
        enabled=True,
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    return profile

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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("post", "/api/v1/llm/providers", {"name": "p", "kind": "openai"}),
        ("patch", f"/api/v1/llm/providers/{OTHER_PROVIDER_ID}", {"name": "p"}),
        ("post", f"/api/v1/llm/providers/{OTHER_PROVIDER_ID}/test", None),
        (
            "post",
            "/api/v1/llm/models",
            {
                "provider_id": OTHER_PROVIDER_ID,
                "model_id": "gpt-test",
                "display_name": "GPT Test",
            },
        ),
        ("patch", f"/api/v1/llm/models/{OTHER_MODEL_ID}", {"display_name": "GPT Test"}),
        (
            "post",
            "/api/v1/llm/model-profiles",
            {
                "name": "Agent profile",
                "task_type": "agent_core",
                "primary_model_id": OTHER_MODEL_ID,
            },
        ),
        ("patch", f"/api/v1/llm/model-profiles/{OTHER_PROFILE_ID}", {"name": "Agent profile"}),
    ],
)
async def test_llm_mutations_require_authenticated_user(
    async_client,
    monkeypatch,
    method: str,
    path: str,
    json_body: dict | None,
):
    monkeypatch.setattr(settings, "auth_mode", "personal")
    monkeypatch.setattr(settings, "auth_enabled", True)

    response = await getattr(async_client, method)(path, json=json_body)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_provider_derives_tenant_fields_from_session(
    async_client,
    app,
    db_session,
):
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="user-1",
        workspace_id=DEFAULT_WORKSPACE_ID,
        role="owner",
    )
    try:
        response = await async_client.post(
            "/api/v1/llm/providers",
            json={
                "name": "Tenant forced provider",
                "kind": "openai_compatible",
                "scope": "user",
                "workspace_id": OTHER_WORKSPACE_ID,
                "user_id": "other-user",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 201
    provider = response.json()["data"]
    assert provider["workspace_id"] == DEFAULT_WORKSPACE_ID
    assert provider["user_id"] == "user-1"

    persisted = await db_session.get(LlmProvider, provider["id"])
    assert persisted is not None
    assert str(persisted.workspace_id) == DEFAULT_WORKSPACE_ID
    assert persisted.user_id == "user-1"


@pytest.mark.asyncio
async def test_create_model_profile_derives_tenant_fields_from_session(
    async_client,
    app,
    db_session,
):
    provider = await _create_provider(db_session, name="Profile tenant provider")
    model = await _create_model(
        db_session,
        provider_id=str(provider.id),
        model_id="tenant-model",
        display_name="Tenant Model",
    )
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="user-1",
        workspace_id=DEFAULT_WORKSPACE_ID,
        role="owner",
    )
    try:
        response = await async_client.post(
            "/api/v1/llm/model-profiles",
            json={
                "name": "Tenant forced profile",
                "task_type": "agent_core",
                "primary_model_id": str(model.id),
                "scope": "user",
                "workspace_id": OTHER_WORKSPACE_ID,
                "user_id": "other-user",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 201
    profile = response.json()["data"]
    assert profile["workspace_id"] == DEFAULT_WORKSPACE_ID
    assert profile["user_id"] == "user-1"

    persisted = await db_session.get(LlmModelProfile, profile["id"])
    assert persisted is not None
    assert str(persisted.workspace_id) == DEFAULT_WORKSPACE_ID
    assert persisted.user_id == "user-1"


@pytest.mark.asyncio
async def test_team_member_cannot_write_workspace_or_global_llm_scope(
    async_client,
    app,
    monkeypatch,
):
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="member-1",
        role="member",
    )
    try:
        workspace_response = await async_client.post(
            "/api/v1/llm/providers",
            json={
                "name": "Workspace provider",
                "kind": "openai_compatible",
                "scope": "workspace",
            },
        )
        global_response = await async_client.post(
            "/api/v1/llm/providers",
            json={
                "name": "Global provider",
                "kind": "openai_compatible",
                "scope": "global",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert workspace_response.status_code == 403
    assert global_response.status_code == 403


@pytest.mark.asyncio
async def test_user_cannot_update_or_test_another_users_provider(
    async_client,
    app,
    db_session,
):
    other_provider = await _create_provider(
        db_session,
        name="Other user provider",
        user_id="other-user",
    )
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="user-1",
        role="owner",
    )
    try:
        update_response = await async_client.patch(
            f"/api/v1/llm/providers/{other_provider.id}",
            json={"name": "Compromised"},
        )
        test_response = await async_client.post(
            f"/api/v1/llm/providers/{other_provider.id}/test",
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert update_response.status_code == 403
    assert test_response.status_code == 403


@pytest.mark.asyncio
async def test_models_are_limited_to_visible_providers(async_client, app, db_session):
    own_provider = await _create_provider(db_session, name="Own provider")
    own_model = await _create_model(
        db_session,
        provider_id=str(own_provider.id),
        model_id="own-model",
        display_name="Own Model",
    )
    other_provider = await _create_provider(
        db_session,
        name="Other provider",
        user_id="other-user",
    )
    other_model = await _create_model(
        db_session,
        provider_id=str(other_provider.id),
        model_id="other-model",
        display_name="Other Model",
    )

    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="user-1",
        role="owner",
    )
    try:
        list_response = await async_client.get("/api/v1/llm/models")
        filtered_response = await async_client.get(
            "/api/v1/llm/models",
            params={"provider_id": str(other_provider.id)},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert list_response.status_code == 200
    model_ids = [item["id"] for item in list_response.json()["data"]]
    assert str(own_model.id) in model_ids
    assert str(other_model.id) not in model_ids
    assert filtered_response.status_code == 403


@pytest.mark.asyncio
async def test_model_and_profile_writes_reject_invisible_dependencies(
    async_client,
    app,
    db_session,
):
    own_provider = await _create_provider(db_session, name="Own dependency provider")
    own_model = await _create_model(
        db_session,
        provider_id=str(own_provider.id),
        model_id="own-dependency-model",
        display_name="Own Dependency Model",
    )
    profile = await _create_profile(
        db_session,
        name="Own profile",
        primary_model_id=str(own_model.id),
    )
    other_provider = await _create_provider(
        db_session,
        name="Other dependency provider",
        user_id="other-user",
    )
    other_model = await _create_model(
        db_session,
        provider_id=str(other_provider.id),
        model_id="other-dependency-model",
        display_name="Other Dependency Model",
    )

    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="user-1",
        role="owner",
    )
    try:
        create_model_response = await async_client.post(
            "/api/v1/llm/models",
            json={
                "provider_id": str(other_provider.id),
                "model_id": "bad-model",
                "display_name": "Bad Model",
            },
        )
        create_profile_response = await async_client.post(
            "/api/v1/llm/model-profiles",
            json={
                "name": "Bad profile",
                "task_type": "agent_core",
                "primary_model_id": str(other_model.id),
            },
        )
        update_profile_response = await async_client.patch(
            f"/api/v1/llm/model-profiles/{profile.id}",
            json={"primary_model_id": str(other_model.id)},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert create_model_response.status_code == 403
    assert create_profile_response.status_code == 403
    assert update_profile_response.status_code == 403
