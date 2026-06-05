from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.append(str(Path(__file__).resolve().parents[1]))

import app.database as app_database
import app.runtime.jobs as runtime_jobs
from app.config import settings
from app.api.deps import get_db
from app.database import Base, stamp_database_revision
from app.main import app as fastapi_app
from app.services.run_dispatch import set_run_dispatcher, set_run_scheduler
import app.models  # noqa: F401


class _NoopDispatcher:
    def dispatch(self, run_id: str, *, priority: str = "normal") -> None:
        del run_id, priority


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def app():
    return fastapi_app


@pytest.fixture(autouse=True)
def _default_scheduler_mode(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "")
    monkeypatch.setattr(settings, "auth_enabled", False)
    set_run_dispatcher(_NoopDispatcher())
    set_run_scheduler(None)
    yield
    set_run_dispatcher(None)
    set_run_scheduler(None)


@pytest.fixture(autouse=True)
def _bioinfoflow_home(tmp_path, monkeypatch):
    home = tmp_path / "bioinfoflow-home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "bioinfoflow_home", str(home))


@pytest_asyncio.fixture
async def db_engine(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await stamp_database_revision(engine)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    session_maker = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def async_client(app, db_session):
    session_maker = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    original_engine = app_database.engine
    original_session_maker = app_database.async_session_maker
    original_jobs_session_maker = runtime_jobs.async_session_maker

    app_database.engine = db_session.bind
    app_database.async_session_maker = session_maker
    runtime_jobs.async_session_maker = session_maker

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                yield client
    finally:
        app.dependency_overrides.clear()
        app_database.engine = original_engine
        app_database.async_session_maker = original_session_maker
        runtime_jobs.async_session_maker = original_jobs_session_maker
