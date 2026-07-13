from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

from app.database import get_alembic_head_revision


BACKEND_DIR = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "0047_agent_turn_tool_batch_sequence"


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={"DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_turn_lease_owner_migration_adds_nullable_owner_token(tmp_path: Path) -> None:
    db_path = tmp_path / "turn-lease-owner.db"
    previous = _run_alembic(db_path, "upgrade", PREVIOUS_REVISION)
    assert previous.returncode == 0, previous.stderr

    upgraded = _run_alembic(db_path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(agent_turns)")
        }
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()

    assert columns["lease_owner_token"][2].upper() == "VARCHAR(64)"
    assert columns["lease_owner_token"][3] == 0
    assert revision == (get_alembic_head_revision(),)
