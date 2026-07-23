from __future__ import annotations

import pytest

from app.models.workspace import Workspace
from app.repositories.agent_user_settings_repo import AgentUserSettingsRepository
from app.services.agent_core import AgentCoreService
from app.workspace import DEFAULT_WORKSPACE_ID


async def _workspace(db_session, *, workspace_id: str, slug: str) -> Workspace:
    workspace = Workspace(id=workspace_id, name=slug.title(), slug=slug)
    db_session.add(workspace)
    await db_session.commit()
    return workspace


@pytest.mark.asyncio
async def test_settings_are_scoped_by_workspace_and_user(db_session) -> None:
    await _workspace(db_session, workspace_id="workspace-a", slug="workspace-a")
    await _workspace(db_session, workspace_id="workspace-b", slug="workspace-b")
    repository = AgentUserSettingsRepository(db_session)

    await repository.upsert(
        workspace_id="workspace-a",
        user_id="user-a",
        custom_instructions="A",
    )
    await repository.upsert(
        workspace_id="workspace-a",
        user_id="user-b",
        custom_instructions="B",
    )
    await repository.upsert(
        workspace_id="workspace-b",
        user_id="user-a",
        custom_instructions="C",
    )

    assert (await repository.get("workspace-a", "user-a")).custom_instructions == "A"
    assert (await repository.get("workspace-a", "user-b")).custom_instructions == "B"
    assert (await repository.get("workspace-b", "user-a")).custom_instructions == "C"


@pytest.mark.asyncio
async def test_settings_api_trims_and_clears_custom_instructions(async_client) -> None:
    initial = await async_client.get("/api/v1/agent/settings")
    assert initial.status_code == 200
    assert initial.json()["data"] == {"custom_instructions": ""}

    updated = await async_client.put(
        "/api/v1/agent/settings",
        json={"custom_instructions": "  Always use concise bullets.  "},
    )
    assert updated.status_code == 200
    assert updated.json()["data"] == {
        "custom_instructions": "Always use concise bullets."
    }

    cleared = await async_client.put(
        "/api/v1/agent/settings", json={"custom_instructions": "   "}
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"] == {"custom_instructions": ""}


@pytest.mark.asyncio
async def test_settings_api_rejects_custom_instructions_over_20k(async_client) -> None:
    response = await async_client.put(
        "/api/v1/agent/settings",
        json={"custom_instructions": "x" * 20_001},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_new_sessions_freeze_current_custom_instructions(async_client) -> None:
    first_instructions = "Prefer explicit verification."
    await async_client.put(
        "/api/v1/agent/settings",
        json={"custom_instructions": first_instructions},
    )

    first = await async_client.post("/api/v1/agent/sessions", json={})
    assert first.status_code == 201
    first_session = first.json()["data"]
    assert first_instructions in first_session["prompt_snapshot"]["content"]

    next_instructions = "Use short final answers."
    await async_client.put(
        "/api/v1/agent/settings",
        json={"custom_instructions": next_instructions},
    )

    existing = await async_client.get(f"/api/v1/agent/sessions/{first_session['id']}")
    assert existing.status_code == 200
    assert first_instructions in existing.json()["data"]["prompt_snapshot"]["content"]
    assert next_instructions not in existing.json()["data"]["prompt_snapshot"]["content"]

    second = await async_client.post("/api/v1/agent/sessions", json={})
    assert second.status_code == 201
    assert next_instructions in second.json()["data"]["prompt_snapshot"]["content"]
    assert first_instructions not in second.json()["data"]["prompt_snapshot"]["content"]


@pytest.mark.asyncio
async def test_explicit_session_prompt_snapshot_overrides_user_settings(db_session) -> None:
    await _workspace(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        slug="team",
    )
    await AgentUserSettingsRepository(db_session).upsert(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        custom_instructions="Current user setting",
    )

    explicit_snapshot = {"id": "explicit", "content": "Frozen explicit prompt"}
    session = await AgentCoreService(db_session).create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        prompt_snapshot=explicit_snapshot,
    )

    assert session.prompt_snapshot == explicit_snapshot
