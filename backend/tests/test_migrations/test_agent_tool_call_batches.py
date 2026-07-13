from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

from app.database import get_alembic_head_revision


BACKEND_DIR = Path(__file__).resolve().parents[2]


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={"DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_agent_tool_call_batch_migration_adds_durable_barrier_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "tool-call-batches.db"
    previous = _run_alembic(db_path, "upgrade", "0044_agent_permission_policy")
    assert previous.returncode == 0, previous.stderr

    upgraded = _run_alembic(db_path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        action_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(agent_actions)")
        }
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(agent_actions)")
        }
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()

    assert "agent_tool_call_batches" in tables
    assert {"tool_batch_id", "tool_call_ordinal"} <= action_columns
    assert "sqlite_autoindex_agent_actions_1" in indexes
    assert revision == (get_alembic_head_revision(),)
