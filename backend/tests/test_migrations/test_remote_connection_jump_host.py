from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "0052_agent_user_custom_instructions"
JUMP_REVISION = "0053_remote_connection_jump_host"
WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"},
        text=True,
        capture_output=True,
        check=False,
    )


def _remote_connection_columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(remote_connections)")}


def test_jump_host_migration_upgrades_and_downgrades_populated_connections(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "remote-connection-jump-host.db"
    previous = _run_alembic(db_path, "upgrade", PREVIOUS_REVISION)
    assert previous.returncode == 0, previous.stderr or previous.stdout

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO remote_connections (
                id, workspace_id, name, host, port, username, auth_method, last_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "00000000-0000-0000-0000-000000000010",
                WORKSPACE_ID,
                "Bastion",
                "bastion.example.org",
                22,
                "alice",
                "agent",
                "online",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    upgrade = _run_alembic(db_path, "upgrade", JUMP_REVISION)
    assert upgrade.returncode == 0, upgrade.stderr or upgrade.stdout

    conn = sqlite3.connect(db_path)
    try:
        assert "jump_connection_id" in _remote_connection_columns(conn)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO remote_connections (
                id, workspace_id, name, host, port, username, auth_method,
                jump_connection_id, last_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "00000000-0000-0000-0000-000000000011",
                WORKSPACE_ID,
                "Target",
                "target.internal",
                22,
                "alice",
                "jump",
                "00000000-0000-0000-0000-000000000010",
                "online",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    downgrade = _run_alembic(db_path, "downgrade", PREVIOUS_REVISION)
    assert downgrade.returncode == 0, downgrade.stderr or downgrade.stdout

    conn = sqlite3.connect(db_path)
    try:
        assert "jump_connection_id" not in _remote_connection_columns(conn)
        rows = conn.execute(
            "SELECT id, auth_method FROM remote_connections ORDER BY id"
        ).fetchall()
        assert rows == [
            ("00000000-0000-0000-0000-000000000010", "agent"),
            ("00000000-0000-0000-0000-000000000011", "agent"),
        ]
    finally:
        conn.close()
