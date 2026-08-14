from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import Request

from app.auth.agent_tokens import AgentTokenContext, AgentTokenService
from app.auth.dependencies import (
    require_agent_scope,
    resolve_current_user,
    resolve_optional_user,
)
from app.auth.session import AuthUser
from app.config import settings
from app.models.agent_token import AgentToken
from app.models.agent_harness import AgentHarnessRun, AgentHarnessSession
from app.repositories.agent_harness_repo import AgentHarnessRepository, RunFence


def _declare_agent_access(request: Request) -> Request:
    request.state.agent_token_access_declared = True
    return request


def test_request_scope_rejects_cross_project_session_run_and_connection() -> None:
    from fastapi import HTTPException

    request = Request({"type": "http", "headers": []})
    request.state.agent_token = AgentTokenContext(
        id="token-1",
        user_id="user-1",
        workspace_id="workspace-1",
        project_id="project-1",
        connection_id="connection-1",
        session_id="session-1",
        run_id="run-1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )

    assert (
        require_agent_scope(
            request,
            project_id="project-1",
            connection_id="connection-1",
            session_id="session-1",
            run_id="run-1",
        )
        is request.state.agent_token
    )

    for scope in (
        {"project_id": "project-2"},
        {"connection_id": "connection-2", "project_id": "project-1"},
        {"session_id": "session-2", "project_id": "project-1"},
        {"run_id": "run-2", "project_id": "project-1"},
    ):
        with pytest.raises(HTTPException) as exc_info:
            require_agent_scope(request, **scope)
        assert exc_info.value.status_code == 403


def _create_auth_user(db_path: Path, *, user_id: str, role: str = "member") -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE user (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                image TEXT,
                role TEXT,
                banned INTEGER,
                "banExpires" TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO user (id, name, email, image, role, banned, "banExpires")
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, "Agent User", "agent@example.com", None, role, 0, None),
        )
        connection.commit()
    finally:
        connection.close()


async def _create_bound_run(
    db_session,
    *,
    user_id: str,
    workspace_id: str = "00000000-0000-0000-0000-000000000001",
    project_id: str | None = None,
    lease_owner: str | None = "test-worker",
):
    session = AgentHarnessSession(
        user_id=user_id,
        workspace_id=workspace_id,
        project_id=project_id,
        permission_mode="ask_dangerous",
        prompt_snapshot={"content": "test"},
        history_revision=0,
        command_queue=[],
        command_ids=[],
        status="active",
    )
    db_session.add(session)
    await db_session.commit()
    run = AgentHarnessRun(
        session_id=str(session.id),
        status="running",
        lease_owner=lease_owner,
        lease_generation=1 if lease_owner is not None else 0,
        lease_expires_at=(
            datetime.now(timezone.utc) + timedelta(minutes=5)
            if lease_owner is not None
            else None
        ),
        command_queue=[],
        command_ids=[],
    )
    db_session.add(run)
    await db_session.commit()
    return session, run


def _fence(run: AgentHarnessRun) -> RunFence:
    assert run.lease_owner is not None
    return RunFence(owner=run.lease_owner, generation=run.lease_generation)


@pytest.mark.asyncio
async def test_agent_token_is_hashed_bound_and_expires(db_session) -> None:
    service = AgentTokenService(db_session)
    now = datetime.now(timezone.utc)
    session, run = await _create_bound_run(
        db_session,
        user_id="00000000-0000-0000-0000-000000000101",
        project_id="00000000-0000-0000-0000-000000000201",
    )
    grant = await service.issue(
        user_id="00000000-0000-0000-0000-000000000101",
        workspace_id="00000000-0000-0000-0000-000000000001",
        session_id=str(session.id),
        run_id=str(run.id),
        fence=_fence(run),
        ttl=timedelta(minutes=5),
        now=now,
    )

    stored = (await db_session.execute(select(AgentToken))).scalar_one()
    assert stored.token_hash != grant.token
    assert grant.token not in repr(stored)
    assert grant.token not in repr(grant)
    assert stored.user_id == "00000000-0000-0000-0000-000000000101"
    assert stored.workspace_id == "00000000-0000-0000-0000-000000000001"
    assert stored.session_id == grant.session_id
    assert stored.run_id == grant.run_id

    authenticated = await service.authenticate(grant.token, now=now)
    assert authenticated is not None
    assert authenticated.id == str(stored.id)
    assert authenticated.project_id == "00000000-0000-0000-0000-000000000201"
    assert (
        await service.authenticate(grant.token, now=now + timedelta(minutes=6)) is None
    )


@pytest.mark.asyncio
async def test_agent_token_issue_rejects_claims_outside_the_active_run_binding(
    db_session,
) -> None:
    service = AgentTokenService(db_session)
    session, run = await _create_bound_run(
        db_session,
        user_id="user-1",
        workspace_id="00000000-0000-0000-0000-000000000001",
        project_id="00000000-0000-0000-0000-000000000201",
    )
    valid = {
        "user_id": session.user_id,
        "workspace_id": str(session.workspace_id),
        "session_id": str(session.id),
        "run_id": str(run.id),
        "fence": _fence(run),
    }

    for override in (
        {"user_id": "user-2"},
        {"workspace_id": "00000000-0000-0000-0000-000000000002"},
        {"session_id": str(uuid4())},
        {"run_id": str(uuid4())},
    ):
        with pytest.raises(ValueError, match="active Agent run"):
            await service.issue(**{**valid, **override})

    run.status = "completed"
    await db_session.commit()
    with pytest.raises(ValueError, match="active Agent run"):
        await service.issue(**valid)


@pytest.mark.asyncio
async def test_agent_token_rejects_non_positive_or_long_lifetime(db_session) -> None:
    service = AgentTokenService(db_session)
    values = {
        "user_id": str(uuid4()),
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "session_id": str(uuid4()),
        "run_id": str(uuid4()),
        "fence": RunFence(owner="missing", generation=1),
    }

    with pytest.raises(ValueError):
        await service.issue(**values, ttl=timedelta(0))
    with pytest.raises(ValueError):
        await service.issue(**values, ttl=timedelta(hours=2))


@pytest.mark.asyncio
async def test_agent_token_can_be_revoked_by_run_or_session(db_session) -> None:
    service = AgentTokenService(db_session)
    now = datetime.now(timezone.utc)
    session_id = str(uuid4())

    first_session, first_run = await _create_bound_run(db_session, user_id=str(uuid4()))
    session_id = str(first_session.id)

    first = await service.issue(
        user_id=first_session.user_id,
        workspace_id="00000000-0000-0000-0000-000000000001",
        session_id=session_id,
        run_id=str(first_run.id),
        fence=_fence(first_run),
        now=now,
    )
    await service.revoke_run(first.run_id, now=now)
    assert await service.authenticate(first.token, now=now) is None

    second_session, second_run = await _create_bound_run(
        db_session, user_id=str(uuid4())
    )
    second = await service.issue(
        user_id=second_session.user_id,
        workspace_id="00000000-0000-0000-0000-000000000001",
        session_id=str(second_session.id),
        run_id=str(second_run.id),
        fence=_fence(second_run),
        now=now,
    )
    await service.revoke_session(str(second_session.id), now=now)
    assert await service.authenticate(second.token, now=now) is None


@pytest.mark.asyncio
async def test_agent_token_can_be_rotated_without_exposing_previous_secret(
    db_session,
) -> None:
    service = AgentTokenService(db_session)
    session, run = await _create_bound_run(db_session, user_id=str(uuid4()))
    values = {
        "user_id": session.user_id,
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "session_id": str(session.id),
        "run_id": str(run.id),
        "fence": _fence(run),
    }
    first = await service.issue(**values)
    second = await service.rotate(first.token, fence=_fence(run))

    assert second.token != first.token
    assert second.session_id == first.session_id
    assert second.run_id == first.run_id
    assert await service.authenticate(first.token) is None
    assert await service.authenticate(second.token) is not None


@pytest.mark.asyncio
async def test_issue_replaces_the_previous_active_token_for_the_same_run(
    db_session,
) -> None:
    service = AgentTokenService(db_session)
    session, run = await _create_bound_run(db_session, user_id=str(uuid4()))
    values = {
        "user_id": session.user_id,
        "workspace_id": str(session.workspace_id),
        "session_id": str(session.id),
        "run_id": str(run.id),
        "fence": _fence(run),
    }

    first = await service.issue(**values)
    second = await service.issue(**values)

    assert await service.authenticate(first.token) is None
    assert await service.authenticate(second.token) is not None
    active_count = await db_session.scalar(
        select(func.count())
        .select_from(AgentToken)
        .where(AgentToken.run_id == str(run.id), AgentToken.revoked_at.is_(None))
    )
    assert active_count == 1


@pytest.mark.asyncio
async def test_concurrent_issue_leaves_at_most_one_active_token(
    db_engine,
) -> None:
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as setup:
        session, run = await _create_bound_run(setup, user_id=str(uuid4()))
        values = {
            "user_id": session.user_id,
            "workspace_id": str(session.workspace_id),
            "session_id": str(session.id),
            "run_id": str(run.id),
            "fence": _fence(run),
        }

    async def issue_one():
        async with maker() as db:
            return await AgentTokenService(db).issue(**values)

    grants = await asyncio.gather(issue_one(), issue_one())

    async with maker() as verify:
        active_count = await verify.scalar(
            select(func.count())
            .select_from(AgentToken)
            .where(
                AgentToken.run_id == values["run_id"],
                AgentToken.revoked_at.is_(None),
            )
        )
        authenticated = [
            await AgentTokenService(verify).authenticate(grant.token)
            for grant in grants
        ]
    assert active_count == 1
    assert sum(item is not None for item in authenticated) == 1


@pytest.mark.asyncio
async def test_concurrent_rotation_of_one_token_only_succeeds_once(db_engine) -> None:
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as setup:
        session, run = await _create_bound_run(setup, user_id=str(uuid4()))
        fence = _fence(run)
        first = await AgentTokenService(setup).issue(
            user_id=session.user_id,
            workspace_id=str(session.workspace_id),
            session_id=str(session.id),
            run_id=str(run.id),
            fence=fence,
        )

    async def rotate_one():
        async with maker() as db:
            try:
                return await AgentTokenService(db).rotate(first.token, fence=fence)
            except ValueError:
                return None

    rotated = await asyncio.gather(rotate_one(), rotate_one())

    assert sum(item is not None for item in rotated) == 1
    async with maker() as verify:
        active_count = await verify.scalar(
            select(func.count())
            .select_from(AgentToken)
            .where(
                AgentToken.run_id == str(run.id),
                AgentToken.revoked_at.is_(None),
            )
        )
    assert active_count == 1


@pytest.mark.asyncio
async def test_stale_worker_cannot_replace_rotate_or_revoke_new_worker_token(
    db_engine,
) -> None:
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as setup:
        session, run = await _create_bound_run(
            setup,
            user_id=str(uuid4()),
            lease_owner=None,
        )
        values = {
            "user_id": session.user_id,
            "workspace_id": str(session.workspace_id),
            "session_id": str(session.id),
            "run_id": str(run.id),
        }
        repository = AgentHarnessRepository(setup)
        first_generation = await repository.claim_run(
            str(run.id),
            owner="worker-1",
            lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        assert first_generation == 1
        first_fence = RunFence(owner="worker-1", generation=first_generation)
        await AgentTokenService(setup).issue(**values, fence=first_fence)

    async with maker() as current_db:
        repository = AgentHarnessRepository(current_db)
        second_generation = await repository.claim_run(
            values["run_id"],
            owner="worker-2",
            lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        )
        assert second_generation == 2
        second_fence = RunFence(owner="worker-2", generation=second_generation)
        current = await AgentTokenService(current_db).issue(
            **values,
            fence=second_fence,
        )

    async with maker() as stale_db:
        stale = AgentTokenService(stale_db)
        with pytest.raises(ValueError, match="stale Agent run fence"):
            await stale.issue(**values, fence=first_fence)
        with pytest.raises(ValueError, match="stale Agent run fence"):
            await stale.rotate(current.token, fence=first_fence)
        with pytest.raises(ValueError, match="stale Agent run fence"):
            await stale.revoke_run(values["run_id"], fence=first_fence)

    async with maker() as verification_db:
        assert (
            await AgentTokenService(verification_db).authenticate(current.token)
            is not None
        )


@pytest.mark.asyncio
async def test_agent_token_is_invalid_when_bound_run_is_terminal(db_session) -> None:
    session, run = await _create_bound_run(db_session, user_id="user-1")

    service = AgentTokenService(db_session)
    grant = await service.issue(
        user_id=session.user_id,
        workspace_id=str(session.workspace_id),
        session_id=str(session.id),
        run_id=str(run.id),
        fence=_fence(run),
    )
    assert await service.authenticate(grant.token) is not None

    run.status = "cancelled"
    await db_session.commit()

    assert await service.authenticate(grant.token) is None


@pytest.mark.asyncio
async def test_bearer_agent_token_resolves_current_live_user(
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_db = tmp_path / "better-auth.db"
    user_id = str(uuid4())
    _create_auth_user(auth_db, user_id=user_id, role="admin")
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "better_auth_db_path", str(auth_db))

    session, run = await _create_bound_run(db_session, user_id=user_id)
    grant = await AgentTokenService(db_session).issue(
        user_id=user_id,
        workspace_id="00000000-0000-0000-0000-000000000001",
        session_id=str(session.id),
        run_id=str(run.id),
        fence=_fence(run),
    )
    request = _declare_agent_access(
        Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/projects",
                "headers": [
                    (b"authorization", f"Bearer {grant.token}".encode("ascii"))
                ],
            }
        )
    )

    user = await resolve_current_user(request, db_session)

    assert user == AuthUser(
        id=user_id,
        name="Agent User",
        email="agent@example.com",
        role="admin",
    )
    assert request.state.agent_token.session_id == grant.session_id
    assert request.state.agent_token.run_id == grant.run_id

    undeclared = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/unknown",
            "headers": [(b"authorization", f"Bearer {grant.token}".encode("ascii"))],
        }
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await resolve_current_user(undeclared, db_session)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_bearer_agent_token_overrides_cookie_identity(
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_db = tmp_path / "better-auth.db"
    user_id = str(uuid4())
    _create_auth_user(auth_db, user_id=user_id)
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "better_auth_db_path", str(auth_db))
    session, run = await _create_bound_run(db_session, user_id=user_id)
    grant = await AgentTokenService(db_session).issue(
        user_id=user_id,
        workspace_id="00000000-0000-0000-0000-000000000001",
        session_id=str(session.id),
        run_id=str(run.id),
        fence=_fence(run),
    )
    request = _declare_agent_access(
        Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/projects",
                "headers": [
                    (b"authorization", f"Bearer {grant.token}".encode("ascii")),
                    (b"cookie", b"better-auth.session_token=unrelated-cookie"),
                ],
            }
        )
    )

    user = await resolve_current_user(request, db_session)

    assert user.id == user_id


@pytest.mark.asyncio
async def test_optional_auth_accepts_agent_bearer_token(
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_db = tmp_path / "better-auth.db"
    user_id = str(uuid4())
    _create_auth_user(auth_db, user_id=user_id)
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "better_auth_db_path", str(auth_db))
    session, run = await _create_bound_run(db_session, user_id=user_id)
    grant = await AgentTokenService(db_session).issue(
        user_id=user_id,
        workspace_id="00000000-0000-0000-0000-000000000001",
        session_id=str(session.id),
        run_id=str(run.id),
        fence=_fence(run),
    )
    request = _declare_agent_access(
        Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/optional",
                "headers": [
                    (b"authorization", f"Bearer {grant.token}".encode("ascii"))
                ],
            }
        )
    )

    user = await resolve_optional_user(request, db_session)

    assert user is not None
    assert user.id == user_id


@pytest.mark.asyncio
async def test_invalid_bearer_does_not_fall_back_to_cookie(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/projects",
            "headers": [
                (b"authorization", b"Bearer invalid"),
                (b"cookie", b"better-auth.session_token=also-invalid"),
            ],
        }
    )

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await resolve_current_user(request, db_session)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_optional_auth_rejects_explicit_invalid_bearer(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/optional",
            "headers": [(b"authorization", b"Bearer invalid")],
        }
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await resolve_optional_user(request, db_session)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_dev_auth_rejects_an_explicit_stale_agent_token(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "dev")
    monkeypatch.setattr(settings, "auth_enabled", True)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/projects",
            "headers": [(b"authorization", b"Bearer stale")],
        }
    )

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await resolve_current_user(request, db_session)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_agent_token_rejects_disabled_user_and_workspace_mismatch(
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_db = tmp_path / "better-auth.db"
    user_id = str(uuid4())
    _create_auth_user(auth_db, user_id=user_id)
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "better_auth_db_path", str(auth_db))
    service = AgentTokenService(db_session)

    wrong_session, wrong_run = await _create_bound_run(
        db_session,
        user_id=user_id,
        workspace_id=str(uuid4()),
    )
    wrong_workspace = await service.issue(
        user_id=user_id,
        workspace_id=str(wrong_session.workspace_id),
        session_id=str(wrong_session.id),
        run_id=str(wrong_run.id),
        fence=_fence(wrong_run),
    )
    request = _declare_agent_access(
        Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/projects",
                "headers": [
                    (
                        b"authorization",
                        f"Bearer {wrong_workspace.token}".encode("ascii"),
                    )
                ],
            }
        )
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as mismatch:
        await resolve_current_user(request, db_session)
    assert mismatch.value.status_code == 401

    disabled_session, disabled_run = await _create_bound_run(
        db_session,
        user_id=user_id,
    )
    disabled = await service.issue(
        user_id=user_id,
        workspace_id=str(disabled_session.workspace_id),
        session_id=str(disabled_session.id),
        run_id=str(disabled_run.id),
        fence=_fence(disabled_run),
    )

    connection = sqlite3.connect(auth_db)
    try:
        connection.execute("UPDATE user SET banned = 1 WHERE id = ?", (user_id,))
        connection.commit()
    finally:
        connection.close()

    disabled_request = _declare_agent_access(
        Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/projects",
                "headers": [
                    (b"authorization", f"Bearer {disabled.token}".encode("ascii"))
                ],
            }
        )
    )
    with pytest.raises(HTTPException) as banned:
        await resolve_current_user(disabled_request, db_session)
    assert banned.value.status_code == 401
