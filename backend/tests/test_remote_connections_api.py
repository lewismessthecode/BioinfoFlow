from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.websockets import WebSocketDisconnect

import app.database as app_database
import app.models  # noqa: F401
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

    app_database.engine = engine
    app_database.async_session_maker = session_maker

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
async def test_remote_connection_accepts_and_redacts_password_auth(async_client):
    create_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(
            auth_method="password",
            key_path=None,
            password="super-secret",
        ),
    )
    assert create_resp.status_code == 201
    created = create_resp.json()["data"]
    assert created["auth_method"] == "password"
    assert "password" not in created
    assert "encrypted_password" not in created


@pytest.mark.asyncio
async def test_remote_connection_accepts_and_redacts_private_key_auth(async_client):
    create_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(
            auth_method="private_key",
            key_path=None,
            private_key="-----BEGIN OPENSSH PRIVATE KEY-----\nkey\n-----END OPENSSH PRIVATE KEY-----",
            passphrase="optional-passphrase",
        ),
    )
    assert create_resp.status_code == 201
    created = create_resp.json()["data"]
    assert created["auth_method"] == "private_key"
    assert "private_key" not in created
    assert "passphrase" not in created
    assert "encrypted_private_key" not in created


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

    password_without_secret = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(auth_method="password", key_path=None),
    )
    assert password_without_secret.status_code == 422

    private_key_without_secret = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(auth_method="private_key", key_path=None),
    )
    assert private_key_without_secret.status_code == 422


@pytest.mark.asyncio
async def test_remote_connection_creates_and_serializes_jump_auth(async_client):
    jump_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(name="Bastion", auth_method="agent", key_path=None),
    )
    assert jump_resp.status_code == 201
    jump_id = jump_resp.json()["data"]["id"]

    target_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(
            name="Internal HPC",
            host="internal.example.org",
            auth_method="jump",
            key_path=None,
            jump_connection_id=jump_id,
        ),
    )

    assert target_resp.status_code == 201
    target = target_resp.json()["data"]
    assert target["auth_method"] == "jump"
    assert target["jump_connection_id"] == jump_id


@pytest.mark.asyncio
async def test_remote_connection_jump_auth_requires_jump_id(async_client):
    response = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(auth_method="jump", key_path=None),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_remote_connection_direct_auth_rejects_jump_id(async_client):
    jump_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(name="Bastion", auth_method="agent", key_path=None),
    )
    jump_id = jump_resp.json()["data"]["id"]

    response = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(jump_connection_id=jump_id),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_remote_connection_direct_auth_patch_rejects_jump_id(async_client):
    jump_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(name="Bastion", auth_method="agent", key_path=None),
    )
    jump_id = jump_resp.json()["data"]["id"]
    direct_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(name="Direct Login"),
    )
    direct_id = direct_resp.json()["data"]["id"]

    response = await async_client.patch(
        f"/api/v1/connections/{direct_id}",
        json={"jump_connection_id": jump_id},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_remote_connection_jump_auth_rejects_direct_credentials(async_client):
    jump_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(name="Bastion", auth_method="agent", key_path=None),
    )
    jump_id = jump_resp.json()["data"]["id"]

    response = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(
            auth_method="jump",
            key_path=None,
            jump_connection_id=jump_id,
            password="must-not-be-used",
        ),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_remote_connection_rejects_self_jump_reference(async_client):
    connection_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(auth_method="agent", key_path=None),
    )
    connection_id = connection_resp.json()["data"]["id"]

    response = await async_client.patch(
        f"/api/v1/connections/{connection_id}",
        json={"auth_method": "jump", "jump_connection_id": connection_id},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_remote_connection_rejects_cross_workspace_jump_reference(
    async_client,
    app,
):
    _override_user(app, _auth_user(user_id="user-2", workspace_id=OTHER_WORKSPACE_ID))
    try:
        jump_resp = await async_client.post(
            "/api/v1/connections",
            json=_connection_payload(
                name="Other Bastion", auth_method="agent", key_path=None
            ),
        )
    finally:
        _clear_user_overrides(app)
    jump_id = jump_resp.json()["data"]["id"]

    response = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(
            auth_method="jump",
            key_path=None,
            jump_connection_id=jump_id,
        ),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_remote_connection_rejects_nested_jump_reference(async_client):
    direct_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(name="Bastion", auth_method="agent", key_path=None),
    )
    direct_id = direct_resp.json()["data"]["id"]
    jump_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(
            name="First Target",
            auth_method="jump",
            key_path=None,
            jump_connection_id=direct_id,
        ),
    )
    jump_id = jump_resp.json()["data"]["id"]

    response = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(
            name="Nested Target",
            auth_method="jump",
            key_path=None,
            jump_connection_id=jump_id,
        ),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_remote_connection_referenced_jump_host_cannot_be_deleted_or_converted(
    async_client,
):
    host_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(name="Bastion", auth_method="agent", key_path=None),
    )
    host_id = host_resp.json()["data"]["id"]
    alternate_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(name="Alternate", auth_method="agent", key_path=None),
    )
    alternate_id = alternate_resp.json()["data"]["id"]
    target_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(
            name="Internal HPC",
            auth_method="jump",
            key_path=None,
            jump_connection_id=host_id,
        ),
    )
    assert target_resp.status_code == 201

    edit_resp = await async_client.patch(
        f"/api/v1/connections/{host_id}",
        json={"name": "Bastion Updated"},
    )
    convert_resp = await async_client.patch(
        f"/api/v1/connections/{host_id}",
        json={"auth_method": "jump", "jump_connection_id": alternate_id},
    )
    delete_resp = await async_client.delete(f"/api/v1/connections/{host_id}")

    assert edit_resp.status_code == 200
    assert convert_resp.status_code == 422
    assert delete_resp.status_code == 409


@pytest.mark.asyncio
async def test_remote_connection_switching_jump_auth_clears_credentials_and_status(
    db_session,
):
    from app.services.remote_connection_service import RemoteConnectionService

    service = RemoteConnectionService(db_session)
    first_jump = await service.create_connection(
        _connection_payload(name="Bastion", auth_method="agent", key_path=None),
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    second_jump = await service.create_connection(
        _connection_payload(name="Alternate", auth_method="agent", key_path=None),
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    target = await service.create_connection(
        _connection_payload(
            name="Target",
            auth_method="private_key",
            key_path=None,
            private_key="private-key",
            passphrase="passphrase",
        ),
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    await service.repo.record_test_result(
        target,
        status="online",
        error=None,
        checked_at=target.created_at,
    )

    target = await service.update_connection(
        target,
        {"auth_method": "jump", "jump_connection_id": str(first_jump.id)},
    )
    assert target.encrypted_password is None
    assert target.encrypted_private_key is None
    assert target.encrypted_passphrase is None
    assert target.ssh_alias is None
    assert target.key_path is None
    assert target.last_status == "unknown"
    assert target.last_checked_at is None

    await service.repo.record_test_result(
        target,
        status="online",
        error=None,
        checked_at=target.updated_at,
    )
    target = await service.update_connection(
        target,
        {"jump_connection_id": str(second_jump.id)},
    )
    assert target.last_status == "unknown"
    assert target.last_checked_at is None
    assert str(target.jump_connection_id) == str(second_jump.id)

    target = await service.update_connection(target, {"auth_method": "agent"})
    assert target.jump_connection_id is None


@pytest.mark.asyncio
async def test_remote_connection_editing_jump_host_invalidates_dependent_status(
    db_session,
):
    from app.services.remote_connection_service import RemoteConnectionService

    service = RemoteConnectionService(db_session)
    jump_host = await service.create_connection(
        _connection_payload(name="Bastion", auth_method="agent", key_path=None),
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    target = await service.create_connection(
        _connection_payload(
            name="Target",
            auth_method="jump",
            key_path=None,
            jump_connection_id=str(jump_host.id),
        ),
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    await service.repo.record_test_result(
        target,
        status="online",
        error="previous error",
        checked_at=target.created_at,
    )

    await service.update_connection(jump_host, {"host": "new-bastion.example.org"})
    target = await service.get_connection(
        str(target.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
    )

    assert target is not None
    assert target.last_status == "unknown"
    assert target.last_error is None
    assert target.last_checked_at is None


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
async def test_remote_connection_service_resolves_jump_credentials_without_summary_leak(
    db_session,
):
    from app.services.remote_connection_service import RemoteConnectionService

    service = RemoteConnectionService(db_session)
    jump = await service.create_connection(
        _connection_payload(
            name="Bastion",
            host="bastion.example.org",
            auth_method="password",
            key_path=None,
            password="jump-secret",
        ),
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    target = await service.create_connection(
        _connection_payload(
            name="Phoenix",
            host="10.32.5.1",
            auth_method="jump",
            key_path=None,
            jump_connection_id=str(jump.id),
        ),
        workspace_id=DEFAULT_WORKSPACE_ID,
    )

    config = await service.resolve_connection_config(target)

    assert config.jump_connection is not None
    assert config.jump_connection.id == str(jump.id)
    assert config.jump_connection.password == "jump-secret"
    assert config.summary()["jump_connection_id"] == str(jump.id)
    assert config.summary()["jump_connection_name"] == "Bastion"
    assert "password" not in config.summary()
    assert "jump_connection" not in config.summary()


@pytest.mark.asyncio
async def test_remote_connection_resolver_rejects_persisted_nested_jump(db_session):
    from app.models.remote_connection import RemoteConnection
    from app.services.remote_connection_service import RemoteConnectionService

    service = RemoteConnectionService(db_session)
    outer_jump = await service.create_connection(
        _connection_payload(name="Outer Bastion", auth_method="agent", key_path=None),
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    referenced_jump = await service.create_connection(
        _connection_payload(
            name="Referenced Bastion", auth_method="agent", key_path=None
        ),
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    target = await service.create_connection(
        _connection_payload(
            name="Phoenix",
            auth_method="jump",
            key_path=None,
            jump_connection_id=str(referenced_jump.id),
        ),
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    await db_session.execute(
        update(RemoteConnection)
        .where(RemoteConnection.id == referenced_jump.id)
        .values(
            auth_method="jump",
            jump_connection_id=str(outer_jump.id),
        )
    )
    await db_session.commit()

    with pytest.raises(ValidationError, match="Nested jump"):
        await service.resolve_connection_config(target)


@pytest.mark.asyncio
async def test_remote_connection_resolver_rejects_direct_jump_with_route_residue(
    db_session,
):
    from app.models.remote_connection import RemoteConnection
    from app.services.remote_connection_service import RemoteConnectionService

    service = RemoteConnectionService(db_session)
    outer_jump = await service.create_connection(
        _connection_payload(name="Outer Bastion", auth_method="agent", key_path=None),
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    referenced_jump = await service.create_connection(
        _connection_payload(
            name="Referenced Bastion", auth_method="agent", key_path=None
        ),
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    target = await service.create_connection(
        _connection_payload(
            name="Phoenix",
            auth_method="jump",
            key_path=None,
            jump_connection_id=str(referenced_jump.id),
        ),
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    await db_session.execute(
        update(RemoteConnection)
        .where(RemoteConnection.id == referenced_jump.id)
        .values(jump_connection_id=str(outer_jump.id))
    )
    await db_session.commit()

    with pytest.raises(ValidationError, match="direct connection"):
        await service.resolve_connection_config(target)


@pytest.mark.asyncio
async def test_remote_connection_resolver_rejects_persisted_self_jump(db_session):
    from app.models.remote_connection import RemoteConnection
    from app.services.remote_connection_service import RemoteConnectionService

    service = RemoteConnectionService(db_session)
    target = await service.create_connection(
        _connection_payload(name="Phoenix", auth_method="agent", key_path=None),
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    await db_session.execute(
        update(RemoteConnection)
        .where(RemoteConnection.id == target.id)
        .values(auth_method="jump", jump_connection_id=str(target.id))
    )
    await db_session.commit()
    await db_session.refresh(target)

    with pytest.raises(ValidationError, match="itself"):
        await service.resolve_connection_config(target)


@pytest.mark.asyncio
async def test_jump_connection_test_and_browse_receive_resolved_config(
    async_client,
    monkeypatch,
):
    jump_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(name="Bastion", auth_method="agent", key_path=None),
    )
    jump_id = jump_resp.json()["data"]["id"]
    target_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(
            name="Phoenix",
            host="10.32.5.1",
            auth_method="jump",
            key_path=None,
            jump_connection_id=jump_id,
        ),
    )
    target_id = target_resp.json()["data"]["id"]
    calls = []

    from app.services.remote_execution import RemoteCommandResult

    async def fake_run(self, connection, command, *, timeout_seconds, output_limit):
        calls.append(connection)
        stdout = "bioinfoflow-ok" if command == "printf bioinfoflow-ok" else ""
        return RemoteCommandResult(
            exit_code=0,
            stdout=stdout,
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )

    monkeypatch.setattr("app.services.remote_execution.SshRemoteExecutor.run", fake_run)

    test_response = await async_client.post(f"/api/v1/connections/{target_id}/test")
    browse_response = await async_client.get(
        f"/api/v1/connections/{target_id}/directories"
    )

    assert test_response.status_code == 200
    assert browse_response.status_code == 200
    assert len(calls) == 2
    assert all(call.jump_connection is not None for call in calls)
    assert all(call.jump_connection.id == jump_id for call in calls)


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
async def test_remote_directory_browse_uses_bounded_ssh_command(
    async_client, monkeypatch
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


def test_remote_directory_command_does_not_block_on_fifo(tmp_path):
    from app.api.v1.connections import _remote_directory_command

    os.mkfifo(tmp_path / "named-pipe")

    result = subprocess.run(
        ["/bin/sh", "-c", _remote_directory_command(str(tmp_path), 20)],
        capture_output=True,
        text=True,
        timeout=1,
        check=False,
    )

    assert result.returncode == 0
    assert "named-pipe" in result.stdout


@pytest.mark.asyncio
async def test_remote_connection_delete_conflicts_when_used_by_remote_project(
    async_client,
):
    create_resp = await async_client.post(
        "/api/v1/connections",
        json=_connection_payload(auth_method="agent", key_path=None),
    )
    assert create_resp.status_code == 201
    connection_id = create_resp.json()["data"]["id"]

    project_resp = await async_client.post(
        "/api/v1/projects",
        json={
            "name": "Phoenix sample",
            "remote_connection_id": connection_id,
            "remote_root_path": "/inspurfsms102/B2C_RD1/project/sample_xxx",
        },
    )
    assert project_resp.status_code == 201

    delete_resp = await async_client.delete(f"/api/v1/connections/{connection_id}")

    assert delete_resp.status_code == 409
    assert delete_resp.json()["error"]["code"] == "CONFLICT"


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


def test_remote_connection_websocket_receives_resolved_jump_config(
    remote_connection_test_client,
    monkeypatch,
):
    client, session_maker = remote_connection_test_client

    async def create_connections():
        from app.services.remote_connection_service import RemoteConnectionService

        async with session_maker() as session:
            service = RemoteConnectionService(session)
            jump = await service.create_connection(
                _connection_payload(
                    name="Bastion",
                    auth_method="agent",
                    key_path=None,
                ),
                workspace_id=DEFAULT_WORKSPACE_ID,
            )
            target = await service.create_connection(
                _connection_payload(
                    name="Phoenix",
                    host="10.32.5.1",
                    auth_method="jump",
                    key_path=None,
                    jump_connection_id=str(jump.id),
                ),
                workspace_id=DEFAULT_WORKSPACE_ID,
            )
            return target, jump

    target, jump = asyncio.run(create_connections())
    calls = []

    async def fake_stream(
        self,
        connection,
        command,
        *,
        timeout_seconds,
        output_limit,
    ):
        from app.services.remote_execution import RemoteOutputFrame

        calls.append(connection)
        yield RemoteOutputFrame(type="exit", exit_code=0)

    monkeypatch.setattr(
        "app.services.remote_execution.SshRemoteExecutor.stream",
        fake_stream,
    )

    with client.websocket_connect(
        f"/api/v1/connections/{target.id}/exec/ws"
    ) as websocket:
        websocket.send_json({"command": "hostname"})
        assert websocket.receive_json()["exit_code"] == 0

    assert len(calls) == 1
    assert calls[0].jump_connection is not None
    assert calls[0].jump_connection.id == str(jump.id)
