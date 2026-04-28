from __future__ import annotations

import pytest

from app.database import create_state_engine


@pytest.mark.asyncio
async def test_sqlite_state_engine_uses_wal_and_busy_timeout(tmp_path):
    db_path = tmp_path / "state.db"
    engine = create_state_engine(f"sqlite+aiosqlite:///{db_path}", debug=False)
    try:
        async with engine.connect() as conn:
            journal_mode = (
                await conn.exec_driver_sql("PRAGMA journal_mode")
            ).scalar_one()
            busy_timeout = (
                await conn.exec_driver_sql("PRAGMA busy_timeout")
            ).scalar_one()

        assert journal_mode == "wal"
        assert busy_timeout >= 30000
    finally:
        await engine.dispose()
