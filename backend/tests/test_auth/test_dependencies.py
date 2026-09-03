from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.config import settings
from app.database import Base, stamp_database_revision
from app.main import app as fastapi_app
import app.database as app_database
import app.models  # noqa: F401
from app.auth.agent_tokens import AgentTokenService
from app.models.agent_harness import AgentHarnessRun, AgentHarnessSession
from app.models.project import Project
from app.models.remote_connection import RemoteConnection
from app.models.run import Run
from app.repositories.agent_harness_repo import RunFence
from app.workspace import DEFAULT_WORKSPACE_ID


def _create_better_auth_db(db_path: Path) -> None:
    """Create a minimal Better Auth SQLite DB with session and user tables."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE user (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            emailVerified INTEGER NOT NULL,
            image TEXT,
            createdAt date NOT NULL,
            updatedAt date NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE session (
            id TEXT PRIMARY KEY,
            expiresAt date NOT NULL,
            token TEXT NOT NULL UNIQUE,
            createdAt date NOT NULL,
            updatedAt date NOT NULL,
            ipAddress TEXT,
            userAgent TEXT,
            userId TEXT NOT NULL,
            FOREIGN KEY (userId) REFERENCES user(id)
        )
        """
    )
    conn.commit()
    conn.close()


def _seed_auth_db(db_path: Path) -> None:
    """Insert a test user and valid session into the Better Auth DB."""
    now_iso = _iso_utc(datetime.now(timezone.utc))
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO user (id, name, email, emailVerified, image, createdAt, updatedAt)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("test-user-1", "Test User", "test@example.com", 1, None, now_iso, now_iso),
    )
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    conn.execute(
        """
        INSERT INTO session (id, expiresAt, token, createdAt, updatedAt, ipAddress, userAgent, userId)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "sess-1",
            _iso_utc(future),
            "valid-session-token",
            now_iso,
            now_iso,
            None,
            None,
            "test-user-1",
        ),
    )
    conn.commit()
    conn.close()


def _iso_utc(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _active_test_fence() -> RunFence:
    return RunFence(owner="auth-test-worker", generation=1)


@pytest_asyncio.fixture
async def auth_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Client with auth enabled and a valid Better Auth DB."""
    db_path = tmp_path / "better-auth.db"
    _create_better_auth_db(db_path)
    _seed_auth_db(db_path)

    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "better_auth_db_path", str(db_path))

    state_db_path = tmp_path / "bioinfoflow.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{state_db_path}",
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await stamp_database_revision(engine)

    session_maker = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
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
        async with fastapi_app.router.lifespan_context(fastapi_app):
            transport = ASGITransport(app=fastapi_app)
            async with AsyncClient(
                transport=transport, base_url="http://localhost"
            ) as client:
                yield client
    finally:
        fastapi_app.dependency_overrides.clear()
        app_database.engine = original_engine
        app_database.async_session_maker = original_session_maker
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_current_user_no_cookie(auth_client: AsyncClient) -> None:
    """Request without session cookie should get 401."""
    response = await auth_client.get("/api/v1/projects")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_host_monitoring_endpoints_require_auth(
    auth_client: AsyncClient,
) -> None:
    for path in (
        "/api/v1/scheduler/status",
        "/api/v1/scheduler/resources",
        "/api/v1/system/gpu",
        "/api/v1/system/gpu/metrics",
        "/api/v1/system/readiness",
    ):
        response = await auth_client.get(path)
        assert response.status_code == 401, path

    assert (await auth_client.get("/api/v1/system/ping")).status_code == 200


@pytest.mark.asyncio
async def test_get_current_user_valid_cookie(auth_client: AsyncClient) -> None:
    """Request with valid session cookie should succeed."""
    auth_client.cookies.set("better-auth.session_token", "valid-session-token")
    response = await auth_client.get("/api/v1/projects")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_current_user_valid_agent_bearer(auth_client: AsyncClient) -> None:
    async with app_database.async_session_maker() as session:
        bound_project = Project(
            name="Bound",
            user_id="test-user-1",
            workspace_id=DEFAULT_WORKSPACE_ID,
        )
        other_project = Project(
            name="Other",
            user_id="test-user-1",
            workspace_id=DEFAULT_WORKSPACE_ID,
        )
        session.add_all((bound_project, other_project))
        await session.flush()
        session.add_all(
            (
                Run(
                    run_id="bound-run",
                    project_id=str(bound_project.id),
                    status="completed",
                    config={},
                ),
                Run(
                    run_id="other-run",
                    project_id=str(other_project.id),
                    status="completed",
                    config={},
                ),
            )
        )
        agent_session = AgentHarnessSession(
            user_id="test-user-1",
            workspace_id=DEFAULT_WORKSPACE_ID,
            project_id=str(bound_project.id),
            permission_mode="ask_dangerous",
            prompt_snapshot={"content": "test"},
            history_revision=0,
            command_queue=[],
            command_ids=[],
            status="active",
        )
        session.add(agent_session)
        await session.flush()
        agent_run = AgentHarnessRun(
            session_id=str(agent_session.id),
            status="running",
            lease_owner="auth-test-worker",
            lease_generation=1,
            lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            command_queue=[],
            command_ids=[],
        )
        session.add(agent_run)
        await session.commit()
        grant = await AgentTokenService(session).issue(
            user_id="test-user-1",
            workspace_id=DEFAULT_WORKSPACE_ID,
            session_id=str(agent_session.id),
            run_id=str(agent_run.id),
            fence=_active_test_fence(),
        )
        bound_project_id = str(bound_project.id)
        other_project_id = str(other_project.id)

    response = await auth_client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {grant.token}"},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["data"]] == [bound_project_id]

    outside = await auth_client.get(
        f"/api/v1/projects/{other_project_id}",
        headers={"Authorization": f"Bearer {grant.token}"},
    )
    assert outside.status_code == 403

    runs = await auth_client.get(
        "/api/v1/runs",
        headers={"Authorization": f"Bearer {grant.token}"},
    )
    assert runs.status_code == 200
    assert [item["run_id"] for item in runs.json()["data"]] == ["bound-run"]

    outside_run = await auth_client.get(
        "/api/v1/runs/other-run",
        headers={"Authorization": f"Bearer {grant.token}"},
    )
    assert outside_run.status_code == 403

    bound_files = await auth_client.get(
        "/api/v1/files",
        params={
            "project_id": bound_project_id,
            "path": "missing-agent-token-scope-check",
        },
        headers={"Authorization": f"Bearer {grant.token}"},
    )
    assert bound_files.status_code == 404

    outside_files = await auth_client.get(
        "/api/v1/files",
        params={"project_id": other_project_id},
        headers={"Authorization": f"Bearer {grant.token}"},
    )
    assert outside_files.status_code == 403

    undeclared = await auth_client.get(
        "/api/v1/llm/providers",
        headers={"Authorization": f"Bearer {grant.token}"},
    )
    assert undeclared.status_code == 403


@pytest.mark.asyncio
async def test_get_current_user_signed_cookie_value(auth_client: AsyncClient) -> None:
    """Signed Better Auth cookies should validate against the raw DB token."""
    auth_client.cookies.set(
        "better-auth.session_token", "valid-session-token.mock-signature"
    )
    response = await auth_client.get("/api/v1/projects")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_current_user_invalid_cookie(auth_client: AsyncClient) -> None:
    """Request with invalid session cookie should get 401."""
    auth_client.cookies.set("better-auth.session_token", "bad-token")
    response = await auth_client.get("/api/v1/projects")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_auth_disabled(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When auth_enabled=False, requests without cookie should succeed."""
    monkeypatch.setattr(settings, "auth_mode", "dev")
    monkeypatch.setattr(settings, "auth_enabled", True)
    response = await auth_client.get("/api/v1/projects")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_dev_auth_rejects_an_explicit_invalid_agent_bearer(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "dev")
    monkeypatch.setattr(settings, "auth_enabled", True)

    response = await auth_client.get(
        "/api/v1/projects",
        headers={"Authorization": "Bearer invalid"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_dev_auth_agent_bearer_requires_endpoint_opt_in(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "dev")
    monkeypatch.setattr(settings, "auth_enabled", True)
    async with app_database.async_session_maker() as session:
        agent_session = AgentHarnessSession(
            user_id="dev",
            workspace_id=DEFAULT_WORKSPACE_ID,
            permission_mode="ask_dangerous",
            prompt_snapshot={"content": "test"},
            history_revision=0,
            command_queue=[],
            command_ids=[],
            status="active",
        )
        session.add(agent_session)
        await session.flush()
        agent_run = AgentHarnessRun(
            session_id=str(agent_session.id),
            status="running",
            lease_owner="auth-test-worker",
            lease_generation=1,
            lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            command_queue=[],
            command_ids=[],
        )
        session.add(agent_run)
        await session.commit()
        grant = await AgentTokenService(session).issue(
            user_id="dev",
            workspace_id=DEFAULT_WORKSPACE_ID,
            session_id=str(agent_session.id),
            run_id=str(agent_run.id),
            fence=_active_test_fence(),
        )

    response = await auth_client.get(
        "/api/v1/llm/providers",
        headers={"Authorization": f"Bearer {grant.token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_dev_auth_agent_bearer_enforces_project_and_connection_scopes(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "dev")
    monkeypatch.setattr(settings, "auth_enabled", True)
    async with app_database.async_session_maker() as session:
        bound_connection = RemoteConnection(
            workspace_id=DEFAULT_WORKSPACE_ID,
            name="Bound connection",
            host="bound.example.com",
            port=22,
            username="agent",
            auth_method="agent",
        )
        other_connection = RemoteConnection(
            workspace_id=DEFAULT_WORKSPACE_ID,
            name="Other connection",
            host="other.example.com",
            port=22,
            username="agent",
            auth_method="agent",
        )
        session.add_all((bound_connection, other_connection))
        await session.flush()
        bound_project = Project(
            name="Bound",
            user_id="dev",
            workspace_id=DEFAULT_WORKSPACE_ID,
            storage_mode="remote",
            remote_connection_id=str(bound_connection.id),
            remote_root_path="/work/bound",
        )
        other_project = Project(
            name="Other",
            user_id="dev",
            workspace_id=DEFAULT_WORKSPACE_ID,
        )
        session.add_all((bound_project, other_project))
        await session.flush()
        agent_session = AgentHarnessSession(
            user_id="dev",
            workspace_id=DEFAULT_WORKSPACE_ID,
            project_id=str(bound_project.id),
            workspace_snapshot={"remote_connection": {"id": str(bound_connection.id)}},
            permission_mode="ask_dangerous",
            prompt_snapshot={"content": "test"},
            history_revision=0,
            command_queue=[],
            command_ids=[],
            status="active",
        )
        session.add(agent_session)
        await session.flush()
        agent_run = AgentHarnessRun(
            session_id=str(agent_session.id),
            status="running",
            lease_owner="auth-test-worker",
            lease_generation=1,
            lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            command_queue=[],
            command_ids=[],
        )
        session.add(agent_run)
        await session.commit()
        grant = await AgentTokenService(session).issue(
            user_id="dev",
            workspace_id=DEFAULT_WORKSPACE_ID,
            session_id=str(agent_session.id),
            run_id=str(agent_run.id),
            fence=_active_test_fence(),
        )
        bound_project_id = str(bound_project.id)
        other_project_id = str(other_project.id)
        bound_connection_id = str(bound_connection.id)
        other_connection_id = str(other_connection.id)

    headers = {"Authorization": f"Bearer {grant.token}"}
    assert (
        await auth_client.get(f"/api/v1/projects/{bound_project_id}", headers=headers)
    ).status_code == 200
    assert (
        await auth_client.get(f"/api/v1/projects/{other_project_id}", headers=headers)
    ).status_code == 403
    assert (
        await auth_client.get(
            f"/api/v1/connections/{bound_connection_id}", headers=headers
        )
    ).status_code == 200
    assert (
        await auth_client.get(
            f"/api/v1/connections/{other_connection_id}", headers=headers
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_public_route_no_auth_required(auth_client: AsyncClient) -> None:
    """System health check should not require auth."""
    response = await auth_client.get("/api/v1/system/health")
    # Should not be 401 — health check is public
    assert response.status_code != 401
