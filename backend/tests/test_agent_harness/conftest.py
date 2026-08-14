from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import create_state_engine
from app.models.base import Base
from app.models.workspace import Workspace
from app.workspace import DEFAULT_WORKSPACE_ID
import app.models  # noqa: F401


@pytest_asyncio.fixture
async def harness_db(tmp_path):
    engine = create_state_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'harness.db'}", debug=False
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        session.add(
            Workspace(
                id=DEFAULT_WORKSPACE_ID,
                name="Default",
                slug="default",
                is_default=True,
            )
        )
        session.add(
            Workspace(
                id="30000000-0000-0000-0000-000000000001",
                name="Harness",
                slug="harness",
                is_default=False,
            )
        )
        await session.commit()
        yield session
    await engine.dispose()
