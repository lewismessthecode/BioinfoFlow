from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CHAR, MetaData, event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from sqlalchemy.types import TypeDecorator

from app.config import settings


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class DatabaseSchemaMismatchError(RuntimeError):
    """Raised when the connected database schema revision is behind the codebase."""


class Base(DeclarativeBase):
    metadata = metadata


class GUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses Postgres UUID when available; otherwise stores as CHAR(36).
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value: Any, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


SQLITE_BUSY_TIMEOUT_MS = 30000


def _is_sqlite_url(database_url: str) -> bool:
    return database_url.startswith(("sqlite+aiosqlite://", "sqlite://"))


def ensure_sqlite_database_parent(database_url: str) -> None:
    """Create the parent directory required by a file-backed SQLite URL."""
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return

    database = url.database
    if not database or database == ":memory:" or database.startswith("file:"):
        return

    Path(database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def create_state_engine(database_url: str, *, debug: bool) -> AsyncEngine:
    engine_kwargs: dict[str, Any] = {
        "echo": debug,
        "poolclass": NullPool,
    }
    if _is_sqlite_url(database_url):
        engine_kwargs["connect_args"] = {"timeout": SQLITE_BUSY_TIMEOUT_MS / 1000}

    next_engine = create_async_engine(database_url, **engine_kwargs)

    if _is_sqlite_url(database_url):

        @event.listens_for(next_engine.sync_engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

    return next_engine


engine = create_state_engine(settings.database_url, debug=settings.debug)

async_session_maker = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    config = Config(str(_backend_root() / "alembic.ini"))
    config.set_main_option("script_location", str(_backend_root() / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def get_alembic_head_revision() -> str:
    heads = ScriptDirectory.from_config(_alembic_config()).get_heads()
    if len(heads) != 1:
        raise DatabaseSchemaMismatchError(
            "Unable to determine a single Alembic head revision for startup checks"
        )
    return heads[0]


def _schema_mismatch_message(*, current_revision: str, expected_revision: str) -> str:
    return (
        "Database schema is out of date for this backend. "
        f"Current revision: {current_revision}. "
        f"Expected revision: {expected_revision}. "
        "Run `cd backend && uv run alembic upgrade head` and restart the server."
    )


async def stamp_database_revision(
    target_engine: AsyncEngine, revision: str | None = None
) -> None:
    revision = revision or get_alembic_head_revision()
    async with target_engine.begin() as conn:
        await conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(32) NOT NULL)"
        )
        await conn.exec_driver_sql("DELETE FROM alembic_version")
        await conn.exec_driver_sql(
            "INSERT INTO alembic_version (version_num) VALUES (:revision)",
            {"revision": revision},
        )


async def verify_database_schema_current(
    target_engine: AsyncEngine | None = None,
) -> None:
    current_engine = target_engine or engine
    expected_revision = get_alembic_head_revision()

    async with current_engine.connect() as conn:
        try:
            result = await conn.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            )
        except OperationalError as exc:
            if "no such table: alembic_version" not in str(exc).lower():
                raise
            raise DatabaseSchemaMismatchError(
                _schema_mismatch_message(
                    current_revision="unversioned",
                    expected_revision=expected_revision,
                )
            ) from exc

        revisions = [row[0] for row in result.fetchall() if row[0]]

    current_revision = ", ".join(revisions) if revisions else "unversioned"
    if expected_revision not in revisions or len(revisions) != 1:
        raise DatabaseSchemaMismatchError(
            _schema_mismatch_message(
                current_revision=current_revision,
                expected_revision=expected_revision,
            )
        )


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(lambda _: None)


async def close_db() -> None:
    await engine.dispose()
