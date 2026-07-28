from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
PREVIOUS_HEAD = "0057_merge_agent_heads"


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_remove_default_container_registry_preserves_registry_data(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "remove-default-container-registry.db"
    previous = _run_alembic(db_path, "upgrade", PREVIOUS_HEAD)
    assert previous.returncode == 0, previous.stderr or previous.stdout

    registry_id = "00000000-0000-0000-0000-000000000058"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO container_registries "
            "(id, name, endpoint, namespace, insecure, is_default, credential_source, "
            "last_status, created_at, updated_at) "
            "VALUES (?, 'Legacy Harbor', 'https://harbor.example.test', 'legacy', 0, 1, "
            "'none', 'untested', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (registry_id,),
        )
        connection.commit()

    upgraded = _run_alembic(db_path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr or upgraded.stdout

    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(container_registries)")
        }
        indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list(container_registries)")
        }
        registry = connection.execute(
            "SELECT id, name, endpoint, namespace, credential_source, last_status "
            "FROM container_registries WHERE id = ?",
            (registry_id,),
        ).fetchone()

    assert "is_default" not in columns
    assert "ix_container_registries_is_default" not in indexes
    assert "uq_container_registries_default_singleton" not in indexes
    assert registry == (
        registry_id,
        "Legacy Harbor",
        "https://harbor.example.test",
        "legacy",
        "none",
        "untested",
    )
