from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "0063_agent_session_project_delete_cascade"
TARGET_REVISION = "0064_agent_tool_outputs"


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ | {"DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_agent_tool_outputs_migration_upgrades_and_downgrades(tmp_path: Path) -> None:
    db_path = tmp_path / "platform.db"
    previous = _run_alembic(db_path, "upgrade", PREVIOUS_REVISION)
    assert previous.returncode == 0, previous.stderr
    legacy_id = "10000000-0000-0000-0000-000000000001"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO agent_artifacts "
            "(id, session_id, type, title, file_path, resource_ref, created_at, updated_at) "
            "VALUES (?, ?, 'command_output', 'pytest', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                legacy_id,
                "20000000-0000-0000-0000-000000000001",
                "20000000-0000-0000-0000-000000000001/legacy/command-output.json",
                '{"filename":"command-output.json","mime_type":"application/json"}',
            ),
        )
        connection.commit()

    upgraded = _run_alembic(db_path, "upgrade", TARGET_REVISION)
    assert upgraded.returncode == 0, upgraded.stderr
    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(agent_tool_outputs)")
        }
        assert {
            "id",
            "session_id",
            "run_id",
            "tool_call_id",
            "command",
            "cwd",
            "exit_code",
            "file_path",
            "resource_ref",
            "created_at",
            "updated_at",
        } <= columns
        moved = connection.execute(
            "SELECT id, tool_call_id, command FROM agent_tool_outputs WHERE id = ?",
            (legacy_id,),
        ).fetchone()
        hidden = connection.execute(
            "SELECT id FROM agent_artifacts WHERE id = ?", (legacy_id,)
        ).fetchone()
        assert moved == (legacy_id, f"legacy-artifact:{legacy_id}", "pytest")
        assert hidden is None

        current_id = "10000000-0000-0000-0000-000000000002"
        connection.execute(
            "INSERT INTO agent_tool_outputs "
            "(id, session_id, tool_call_id, command, file_path, resource_ref, created_at, updated_at) "
            "VALUES (?, ?, 'call-current', 'ruff check', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                current_id,
                "20000000-0000-0000-0000-000000000001",
                f"{current_id}/tool-output.json",
                '{"filename":"tool-output.json","mime_type":"application/json"}',
            ),
        )
        connection.commit()

    refused = _run_alembic(db_path, "downgrade", PREVIOUS_REVISION)
    assert refused.returncode != 0
    assert "restore the pre-upgrade state snapshot" in refused.stderr
    with sqlite3.connect(db_path) as connection:
        retained = connection.execute(
            "SELECT id FROM agent_tool_outputs WHERE id = ?", (current_id,)
        ).fetchone()
        assert retained == (current_id,)
        connection.execute("DELETE FROM agent_tool_outputs WHERE id = ?", (current_id,))
        connection.commit()

    downgraded = _run_alembic(db_path, "downgrade", PREVIOUS_REVISION)
    assert downgraded.returncode == 0, downgraded.stderr
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "agent_tool_outputs" not in tables
        restored = connection.execute(
            "SELECT id, type, title FROM agent_artifacts WHERE id = ?", (legacy_id,)
        ).fetchone()
        assert restored == (legacy_id, "command_output", "pytest")
