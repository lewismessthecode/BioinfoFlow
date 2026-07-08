from __future__ import annotations

import asyncio

import pytest
from uuid import uuid4

from app.config import settings
from app.services.terminal_service import terminal_manager
from tests.support.path_contract import create_project
from tests.support.auth import TEST_SESSION_COOKIE, create_better_auth_db


class _BlockingRemoteTerminalTransport:
    async def read(self, _max_bytes: int) -> bytes:
        await asyncio.Event().wait()
        return b""

    async def write(self, _data: bytes) -> None:
        return None

    async def resize(self, *, cols: int, rows: int) -> None:
        del cols, rows

    async def wait(self) -> int:
        return 0

    async def terminate(self) -> None:
        return None


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
async def test_terminal_session_api_returns_local_target_metadata(
    async_client, db_session
):
    project = await _create_project(
        db_session,
        name="Terminal Local Target Project",
    )

    response = await async_client.post(
        "/api/v1/terminal/sessions", json={"project_id": str(project.id)}
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["target_type"] == "local"
    assert data["target_label"] == "local"
    assert data["remote_connection_id"] is None


@pytest.mark.asyncio
async def test_terminal_session_api_returns_remote_target_without_local_fallback(
    async_client,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_remote_factory(**_kwargs):
        return _BlockingRemoteTerminalTransport()

    monkeypatch.setattr(
        terminal_manager,
        "_remote_terminal_factory",
        fake_remote_factory,
        raising=False,
    )

    connection_resp = await async_client.post(
        "/api/v1/connections",
        json={
            "name": "Phoenix login",
            "host": "login.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "agent",
        },
    )
    assert connection_resp.status_code == 201
    connection_id = connection_resp.json()["data"]["id"]

    project_resp = await async_client.post(
        "/api/v1/projects",
        json={
            "name": "Phoenix terminal",
            "remote_connection_id": connection_id,
            "remote_root_path": "/data/phoenix",
        },
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["data"]["id"]

    response = await async_client.post(
        "/api/v1/terminal/sessions", json={"project_id": project_id}
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["target_type"] == "remote"
    assert data["target_label"] == "remote · Phoenix login"
    assert data["remote_connection_id"] == connection_id
    assert data["cwd"] == "/data/phoenix"
    assert data["status"] == "running"


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
