from __future__ import annotations

import pytest

from app.api.deps import get_current_user
from app.auth.session import AuthUser
from app.models.workspace import Workspace
from app.workspace import DEFAULT_WORKSPACE_ID


SECOND_WORKSPACE_ID = "00000000-0000-0000-0000-000000000002"


def _user(user_id: str, workspace_id: str = DEFAULT_WORKSPACE_ID) -> AuthUser:
    return AuthUser(
        id=user_id,
        name=f"User {user_id}",
        email=f"{user_id}@bioinfoflow.test",
        role="member",
        workspace_id=workspace_id,
    )


@pytest.mark.asyncio
async def test_agent_settings_api_round_trips_trimmed_custom_instructions(
    async_client,
) -> None:
    initial = await async_client.get("/api/v1/agent/settings")

    assert initial.status_code == 200
    assert initial.json()["data"] == {"custom_instructions": ""}

    updated = await async_client.put(
        "/api/v1/agent/settings",
        json={"custom_instructions": "  Prefer validated references.  "},
    )
    loaded = await async_client.get("/api/v1/agent/settings")

    assert updated.status_code == 200
    assert updated.json()["data"] == {
        "custom_instructions": "Prefer validated references."
    }
    assert loaded.json()["data"] == updated.json()["data"]


@pytest.mark.asyncio
async def test_agent_settings_are_isolated_by_workspace_and_user(
    app,
    async_client,
    db_session,
) -> None:
    db_session.add(
        Workspace(id=SECOND_WORKSPACE_ID, name="Second workspace", slug="second")
    )
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: _user("user-a")
    await async_client.put(
        "/api/v1/agent/settings",
        json={"custom_instructions": "User A workspace one"},
    )

    app.dependency_overrides[get_current_user] = lambda: _user("user-b")
    other_user = await async_client.get("/api/v1/agent/settings")
    assert other_user.json()["data"] == {"custom_instructions": ""}
    await async_client.put(
        "/api/v1/agent/settings",
        json={"custom_instructions": "User B workspace one"},
    )

    app.dependency_overrides[get_current_user] = lambda: _user(
        "user-a", SECOND_WORKSPACE_ID
    )
    other_workspace = await async_client.get("/api/v1/agent/settings")
    assert other_workspace.json()["data"] == {"custom_instructions": ""}

    app.dependency_overrides[get_current_user] = lambda: _user("user-a")
    original = await async_client.get("/api/v1/agent/settings")
    assert original.json()["data"] == {"custom_instructions": "User A workspace one"}

    app.dependency_overrides[get_current_user] = lambda: _user("user-b")
    second_user = await async_client.get("/api/v1/agent/settings")
    assert second_user.json()["data"] == {"custom_instructions": "User B workspace one"}
