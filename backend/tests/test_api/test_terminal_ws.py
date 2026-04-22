from __future__ import annotations

import asyncio
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.database as app_database
import app.models  # noqa: F401
import app.runtime.jobs as runtime_jobs
from app.config import settings
from app.api.deps import get_db
from app.database import Base, stamp_database_revision
from app.main import app as fastapi_app
from tests.support.path_contract import create_project
from tests.support.auth import TEST_SESSION_COOKIE, create_better_auth_db
from app.services.terminal_service import terminal_manager


async def _prepare_database(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await stamp_database_revision(engine)


async def _create_project(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    name: str,
    storage_mode: str = "external",
    external_root_path: str | None = None,
):
    async with session_maker() as session:
        return await create_project(
            name=name,
            session=session,
            storage_mode=storage_mode,
            external_root_path=external_root_path,
        )


def _receive_until(websocket, kind: str, *, contains: str | None = None) -> dict:
    for _ in range(32):
        message = websocket.receive_json()
        if message["type"] != kind:
            continue
        payload = message.get("data") or message.get("cwd") or message.get("message")
        if contains is None or contains in str(payload):
            return message
    raise AssertionError(f"Timed out waiting for websocket message: {kind}")


@pytest.fixture
def terminal_test_client(
    tmp_path: Path,
) -> Generator[tuple[TestClient, async_sessionmaker[AsyncSession]], None, None]:
    db_path = tmp_path / "terminal-ws.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    asyncio.run(_prepare_database(engine))

    session_maker = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    original_engine = app_database.engine
    original_session_maker = app_database.async_session_maker
    original_jobs_session_maker = runtime_jobs.async_session_maker

    app_database.engine = engine
    app_database.async_session_maker = session_maker
    runtime_jobs.async_session_maker = session_maker

    async def override_get_db():
        async with session_maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(fastapi_app) as client:
            yield client, session_maker
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(terminal_manager.shutdown())
        app_database.engine = original_engine
        app_database.async_session_maker = original_session_maker
        runtime_jobs.async_session_maker = original_jobs_session_maker
        asyncio.run(engine.dispose())


def test_terminal_websocket_streams_io_and_single_cwd_event(
    terminal_test_client,
    tmp_path: Path,
):
    client, session_maker = terminal_test_client
    workspace = tmp_path / "terminal-workspace"
    nested = workspace / "runs" / "run-1"
    nested.mkdir(parents=True)

    project = asyncio.run(
        _create_project(
            session_maker,
            name="Terminal WS Project",
            storage_mode="external", external_root_path=str(workspace),
        )
    )

    created = client.post(
        "/api/v1/terminal/sessions",
        json={"project_id": str(project.id)},
    )
    assert created.status_code == 201
    session_id = created.json()["data"]["id"]

    with client.websocket_connect(
        f"/api/v1/terminal/sessions/{session_id}/ws"
    ) as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready"
        assert ready["session"]["id"] == session_id

        initial_cwd = websocket.receive_json()
        assert initial_cwd == {"type": "cwd", "cwd": str(workspace.resolve())}

        websocket.send_json({"type": "input", "data": "printf 'hello-ws\\n'\n"})
        output = _receive_until(websocket, "output", contains="hello-ws")
        assert "hello-ws" in output["data"]

        websocket.send_json({"type": "chdir", "path": "runs/run-1"})
        websocket.send_json({"type": "ping"})

        cwd_count = 0
        while True:
            message = websocket.receive_json()
            if message["type"] == "cwd" and message["cwd"] == str(nested.resolve()):
                cwd_count += 1
            if message["type"] == "pong":
                break

        assert cwd_count == 1


def test_terminal_websocket_rejects_missing_session(terminal_test_client):
    client, _ = terminal_test_client

    with client.websocket_connect(
        f"/api/v1/terminal/sessions/{uuid4()}/ws"
    ) as websocket:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_json()

    assert exc_info.value.code == 4404


def test_terminal_websocket_requires_auth_when_enabled(
    terminal_test_client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client, session_maker = terminal_test_client
    workspace = tmp_path / "terminal-auth-workspace"
    workspace.mkdir(parents=True)

    auth_db_path = tmp_path / "better-auth.db"
    create_better_auth_db(auth_db_path)
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_mode", "")
    monkeypatch.setattr(settings, "better_auth_db_path", str(auth_db_path))

    project = asyncio.run(
        _create_project(
            session_maker,
            name="Terminal WS Auth Project",
            storage_mode="external",
            external_root_path=str(workspace),
        )
    )
    client.cookies.set("better-auth.session_token", TEST_SESSION_COOKIE)
    created = client.post(
        "/api/v1/terminal/sessions",
        json={"project_id": str(project.id)},
    )
    assert created.status_code == 201
    session_id = created.json()["data"]["id"]
    client.cookies.clear()

    with client.websocket_connect(
        f"/api/v1/terminal/sessions/{session_id}/ws"
    ) as websocket:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.send_json({"type": "ping"})
            websocket.receive_json()

    assert exc_info.value.code == 4401
