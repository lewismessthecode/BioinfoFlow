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
import app.runtime.jobs as runtime_jobs
import app.models  # noqa: F401


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
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@pytest_asyncio.fixture
async def auth_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Client with auth enabled and a valid Better Auth DB."""
    db_path = tmp_path / "better-auth.db"
    _create_better_auth_db(db_path)
    _seed_auth_db(db_path)

    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "better_auth_db_path", str(db_path))

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await stamp_database_revision(engine)

    session_maker = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
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
        async with fastapi_app.router.lifespan_context(fastapi_app):
            transport = ASGITransport(app=fastapi_app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                yield client
    finally:
        fastapi_app.dependency_overrides.clear()
        app_database.engine = original_engine
        app_database.async_session_maker = original_session_maker
        runtime_jobs.async_session_maker = original_jobs_session_maker
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_current_user_no_cookie(auth_client: AsyncClient) -> None:
    """Request without session cookie should get 401."""
    response = await auth_client.get("/api/v1/projects")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_valid_cookie(auth_client: AsyncClient) -> None:
    """Request with valid session cookie should succeed."""
    auth_client.cookies.set("better-auth.session_token", "valid-session-token")
    response = await auth_client.get("/api/v1/projects")
    assert response.status_code == 200


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
async def test_public_route_no_auth_required(auth_client: AsyncClient) -> None:
    """System health check should not require auth."""
    response = await auth_client.get("/api/v1/system/health")
    # Should not be 401 — health check is public
    assert response.status_code != 401
