from __future__ import annotations

import asyncio
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.websockets import WebSocketDisconnect

import app.database as app_database
import app.models  # noqa: F401
import app.runtime.jobs as runtime_jobs
from app.api.deps import get_current_user, get_db, require_admin
from app.auth.session import AuthUser
from app.config import settings
from app.database import Base, stamp_database_revision
from app.main import app as fastapi_app
from app.services.terminal_service import terminal_manager
from app.utils.exceptions import ValidationError
from app.workspace import DEFAULT_WORKSPACE_ID
from tests.support.auth import TEST_SESSION_COOKIE, create_better_auth_db


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


async def _prepare_database(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await stamp_database_revision(engine)


@pytest.fixture
def remote_connection_test_client(
    tmp_path: Path,
) -> Generator[tuple[TestClient, async_sessionmaker[AsyncSession]], None, None]:
    db_path = tmp_path / "remote-connection-ws.db"
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


def _override_user(app, user: AuthUser) -> None:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_admin] = lambda: user


def _clear_user_overrides(app) -> None:
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_admin, None)


@pytest.mark.asyncio
async def test_remote_connection_crud_is_scoped_to_workspace(async_client, app):
    _override_user(
        app,
        _auth_user(
            user_id="user-1",
            workspace_id=DEFAULT_WORKSPACE_ID,
        ),
    )
    try:
        create_resp = await async_client.post(
            "/api/v1/connections",
            json=_connection_payload(),
        )
    finally:
        _clear_user_overrides(app)

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
            "auth_method": "ssh_config",
            "ssh_alias": "hpc-login",
            "key_path": None,
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()["data"]
    assert updated["name"] == "HPC Login Updated"
    assert updated["ssh_alias"] == "hpc-login"
    assert updated["key_path"] is None

    _override_user(
        app,
        _auth_user(
            user_id="user-2",
            workspace_id=OTHER_WORKSPACE_ID,
        ),
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
        _clear_user_overrides(app)

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
async def test_remote_connection_validation_enforces_auth_method_fields(async_client):
    missing_key = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(auth_method="key_file", key_path=None),
    )
    assert missing_key.status_code == 422

    agent_with_key = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(auth_method="agent", key_path="~/.ssh/id_ed25519"),
    )
    assert agent_with_key.status_code == 422

    ssh_config_without_alias = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(
            auth_method="ssh_config",
            ssh_alias=None,
            key_path=None,
        ),
    )
    assert ssh_config_without_alias.status_code == 422


@pytest.mark.asyncio
async def test_remote_connection_service_enforces_auth_method_fields(db_session):
    from app.services.remote_connection_service import RemoteConnectionService

    service = RemoteConnectionService(db_session)

    with pytest.raises(ValidationError, match="key_path is required"):
        await service.create_connection(
            _connection_payload(auth_method="key_file", key_path=None),
            workspace_id=DEFAULT_WORKSPACE_ID,
        )


@pytest.mark.asyncio
async def test_remote_connection_routes_reject_malformed_ids(async_client):
    response = await async_client.get("/api/v1/connections/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


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
        "app.services.remote_connection_service.SshRemoteConnectionTester.test",
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

    skill_resp = await async_client.patch(
        f"/api/v1/connections/{connection_id}",
        json={"skill_instructions": "Use /data/project for runs."},
    )
    assert skill_resp.status_code == 200
    skill_updated = skill_resp.json()["data"]
    assert skill_updated["last_status"] == "online"
    assert skill_updated["last_error"] is None
    assert skill_updated["last_checked_at"] == test_data["checked_at"]

    target_resp = await async_client.patch(
        f"/api/v1/connections/{connection_id}",
        json={"host": "login-2.example.org"},
    )
    assert target_resp.status_code == 200
    target_updated = target_resp.json()["data"]
    assert target_updated["host"] == "login-2.example.org"
    assert target_updated["last_status"] == "unknown"
    assert target_updated["last_error"] is None
    assert target_updated["last_checked_at"] is None


@pytest.mark.asyncio
async def test_remote_connection_test_uses_ssh_executor_by_default(
    async_client,
    monkeypatch,
):
    create_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(auth_method="agent", key_path=None),
    )
    assert create_resp.status_code == 201
    connection_id = create_resp.json()["data"]["id"]

    from app.services.remote_execution import RemoteCommandResult

    calls = []

    async def fake_run(self, connection, command, *, timeout_seconds, output_limit):
        calls.append(
            {
                "connection": connection,
                "command": command,
                "timeout_seconds": timeout_seconds,
                "output_limit": output_limit,
            }
        )
        return RemoteCommandResult(
            exit_code=0,
            stdout="bioinfoflow-ok",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )

    monkeypatch.setattr(
        "app.services.remote_execution.SshRemoteExecutor.run",
        fake_run,
    )

    test_resp = await async_client.post(f"/api/v1/connections/{connection_id}/test")

    assert test_resp.status_code == 200
    assert test_resp.json()["data"]["status"] == "online"
    assert calls == [
        {
            "connection": calls[0]["connection"],
            "command": "printf bioinfoflow-ok",
            "timeout_seconds": 10,
            "output_limit": 2000,
        }
    ]
    assert calls[0]["connection"].host == "login.example.org"


@pytest.mark.asyncio
async def test_remote_directory_browse_uses_bounded_ssh_command(async_client, monkeypatch):
    create_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(auth_method="agent", key_path=None),
    )
    assert create_resp.status_code == 201
    connection_id = create_resp.json()["data"]["id"]

    from app.services.remote_execution import RemoteCommandResult

    calls = []

    async def fake_run(self, connection, command, *, timeout_seconds, output_limit):
        calls.append(
            {
                "connection": connection,
                "command": command,
                "timeout_seconds": timeout_seconds,
                "output_limit": output_limit,
            }
        )
        return RemoteCommandResult(
            exit_code=0,
            stdout="d\tresults\t0\nf\tinput.json\t42\n",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )

    monkeypatch.setattr(
        "app.services.remote_execution.SshRemoteExecutor.run",
        fake_run,
    )

    response = await async_client.get(
        f"/api/v1/connections/{connection_id}/directories",
        params={"path": "/scratch/run 1", "limit": 20},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["entries"] == [
        {
            "name": "results",
            "path": "/scratch/run 1/results",
            "type": "dir",
            "kind": "directory",
            "size": None,
        },
        {
            "name": "input.json",
            "path": "/scratch/run 1/input.json",
            "type": "file",
            "kind": "file",
            "size": 42,
        },
    ]
    assert "'/scratch/run 1'" in calls[0]["command"]
    assert "head -n 21" in calls[0]["command"]
    assert calls[0]["timeout_seconds"] == 10
    assert calls[0]["output_limit"] == 50000


@pytest.mark.asyncio
async def test_remote_connection_test_persists_executor_launch_errors(
    async_client,
    monkeypatch,
):
    create_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(auth_method="agent", key_path=None),
    )
    assert create_resp.status_code == 201
    connection_id = create_resp.json()["data"]["id"]

    async def fake_run(self, connection, command, *, timeout_seconds, output_limit):
        del self, connection, command, timeout_seconds, output_limit
        raise OSError("No such file or directory: 'ssh'")

    monkeypatch.setattr(
        "app.services.remote_execution.SshRemoteExecutor.run",
        fake_run,
    )

    test_resp = await async_client.post(f"/api/v1/connections/{connection_id}/test")

    assert test_resp.status_code == 200
    test_data = test_resp.json()["data"]
    assert test_data["status"] == "error"
    assert "No such file or directory" in test_data["error"]
    assert test_data["connection"]["last_status"] == "error"
    assert test_data["connection"]["last_error"] == test_data["error"]
    assert test_data["connection"]["last_checked_at"] == test_data["checked_at"]


@pytest.mark.asyncio
async def test_remote_connection_mutations_require_admin_in_team_mode(
    async_client,
    tmp_path,
    monkeypatch,
):
    auth_db_path = tmp_path / "better-auth-member.db"
    create_better_auth_db(auth_db_path)
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "better_auth_db_path", str(auth_db_path))

    async_client.cookies.set("better-auth.session_token", TEST_SESSION_COOKIE)
    create_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(),
    )

    assert create_resp.status_code == 403


def test_remote_connection_websocket_requires_admin_in_team_mode(
    remote_connection_test_client,
    tmp_path,
    monkeypatch,
):
    client, session_maker = remote_connection_test_client
    auth_db_path = tmp_path / "better-auth-member.db"
    create_better_auth_db(auth_db_path)
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "better_auth_db_path", str(auth_db_path))

    async def create_connection():
        from app.services.remote_connection_service import RemoteConnectionService

        async with session_maker() as session:
            return await RemoteConnectionService(session).create_connection(
                _connection_payload(),
                workspace_id=DEFAULT_WORKSPACE_ID,
            )

    connection = asyncio.run(create_connection())

    client.cookies.set("better-auth.session_token", TEST_SESSION_COOKIE)
    with client.websocket_connect(
        f"/api/v1/connections/{connection.id}/exec/ws"
    ) as websocket:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.send_json({"command": "hostname"})
            websocket.receive_json()

    assert exc_info.value.code == 4403
