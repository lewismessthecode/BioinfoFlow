from __future__ import annotations

import pytest
from uuid import uuid4

from app.config import settings
from app.services.terminal_service import terminal_manager
from tests.support.path_contract import create_project
from tests.support.auth import TEST_SESSION_COOKIE, create_better_auth_db


async def _create_project(db_session, *, name: str):
    return await create_project(db_session, name=name)


@pytest.mark.asyncio
async def test_terminal_session_api_reuses_existing_project_session(
    async_client, db_session, tmp_path
):
    project = await _create_project(
        db_session,
        name="Terminal API Project",
    )

    first = await async_client.post(
        "/api/v1/terminal/sessions", json={"project_id": str(project.id)}
    )
    assert first.status_code == 201

    second = await async_client.post(
        "/api/v1/terminal/sessions", json={"project_id": str(project.id)}
    )
    assert second.status_code == 200
    assert second.json()["data"]["id"] == first.json()["data"]["id"]


@pytest.mark.asyncio
async def test_terminal_session_api_returns_not_found_for_unknown_project(async_client):
    response = await async_client.post(
        "/api/v1/terminal/sessions", json={"project_id": str(uuid4())}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_terminal_session_api_deletes_session(async_client, db_session, tmp_path):
    project = await _create_project(
        db_session,
        name="Terminal Delete Project",
    )

    created = await async_client.post(
        "/api/v1/terminal/sessions", json={"project_id": str(project.id)}
    )
    session_id = created.json()["data"]["id"]

    deleted = await async_client.delete(f"/api/v1/terminal/sessions/{session_id}")

    assert deleted.status_code == 200
    assert deleted.json()["data"]["closed"] is True


@pytest.mark.asyncio
async def test_terminal_session_api_hides_inaccessible_sessions(
    async_client, db_session, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    auth_db_path = tmp_path / "better-auth.db"
    create_better_auth_db(auth_db_path)
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_mode", "")
    monkeypatch.setattr(settings, "better_auth_db_path", str(auth_db_path))

    project = await create_project(db_session, name="System Project", user_id="system")
    session = await terminal_manager.create_or_get(
        project_id=str(project.id),
        root_path=tmp_path / "system-project",
    )

    async_client.cookies.set("better-auth.session_token", TEST_SESSION_COOKIE)
    deleted = await async_client.delete(
        f"/api/v1/terminal/sessions/{session.id}",
    )
    async_client.cookies.clear()

    assert deleted.status_code == 404
    assert deleted.json()["error"]["code"] == "NOT_FOUND"
    await terminal_manager.close_session(session.id)
