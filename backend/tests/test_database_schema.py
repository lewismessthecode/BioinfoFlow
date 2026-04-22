from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.database as app_database
import app.runtime.jobs as runtime_jobs


def _create_stale_projects_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute(
            "INSERT INTO alembic_version (version_num) VALUES (?)",
            ("0015_provider_credentials_json",),
        )
        conn.execute(
            """
            CREATE TABLE projects (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                workspace_path VARCHAR(500) NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                user_id CHAR(36),
                data_roots JSON
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_verify_database_schema_current_raises_for_stale_revision(tmp_path: Path):
    from app.database import (
        DatabaseSchemaMismatchError,
        get_alembic_head_revision,
        verify_database_schema_current,
    )

    db_path = tmp_path / "stale.db"
    _create_stale_projects_db(db_path)

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    try:
        with pytest.raises(
            DatabaseSchemaMismatchError, match="uv run alembic upgrade head"
        ) as exc_info:
            await verify_database_schema_current(engine)
    finally:
        await engine.dispose()

    message = str(exc_info.value)
    assert "0015_provider_credentials_json" in message
    assert get_alembic_head_revision() in message


@pytest.mark.asyncio
async def test_app_lifespan_aborts_when_schema_is_stale(
    app,
    tmp_path: Path,
):
    from app.database import DatabaseSchemaMismatchError

    db_path = tmp_path / "lifespan-stale.db"
    _create_stale_projects_db(db_path)

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
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

    try:
        with pytest.raises(
            DatabaseSchemaMismatchError, match="0015_provider_credentials_json"
        ):
            async with app.router.lifespan_context(app):
                pass
    finally:
        app_database.engine = original_engine
        app_database.async_session_maker = original_session_maker
        runtime_jobs.async_session_maker = original_jobs_session_maker
        await engine.dispose()
