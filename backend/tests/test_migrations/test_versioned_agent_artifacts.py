from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "0064_agent_tool_outputs"
TARGET_REVISION = "0065_versioned_agent_artifacts"


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=os.environ | {"DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"},
        text=True,
        capture_output=True,
        check=False,
    )


def test_versioned_artifact_migration_backfills_legacy_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "artifacts.db"
    previous = _run_alembic(db_path, "upgrade", PREVIOUS_REVISION)
    assert previous.returncode == 0, previous.stderr
    legacy_id = "10000000-0000-0000-0000-000000000001"
    session_id = "20000000-0000-0000-0000-000000000001"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO agent_artifacts "
            "(id, session_id, type, title, payload, created_at, updated_at) "
            "VALUES (?, ?, 'published_file', 'Legacy report', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (legacy_id, session_id, '{"declaration_id":"tool:legacy"}'),
        )
        connection.commit()

    upgraded = _run_alembic(db_path, "upgrade", TARGET_REVISION)
    assert upgraded.returncode == 0, upgraded.stderr
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT artifact_id, version, declaration_id "
            "FROM agent_artifacts WHERE id = ?",
            (legacy_id,),
        ).fetchone()

    assert row == (legacy_id, 1, "tool:legacy")


def test_versioned_artifact_migration_refuses_downgrade_after_new_versions(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "new-versions.db"
    previous = _run_alembic(db_path, "upgrade", PREVIOUS_REVISION)
    assert previous.returncode == 0, previous.stderr
    artifact_id = "10000000-0000-0000-0000-000000000021"
    version_id = "10000000-0000-0000-0000-000000000022"
    session_id = "20000000-0000-0000-0000-000000000001"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO agent_artifacts "
            "(id, session_id, type, title, created_at, updated_at) "
            "VALUES (?, ?, 'published_file', 'Initial', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (artifact_id, session_id),
        )
        connection.commit()

    upgraded = _run_alembic(db_path, "upgrade", TARGET_REVISION)
    assert upgraded.returncode == 0, upgraded.stderr
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO agent_artifacts "
            "(id, artifact_id, version, session_id, type, title, created_at, updated_at) "
            "VALUES (?, ?, 2, ?, 'published_file', 'Updated', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (version_id, artifact_id, session_id),
        )
        connection.commit()

    refused = _run_alembic(db_path, "downgrade", PREVIOUS_REVISION)
    assert refused.returncode != 0
    assert "restore the pre-upgrade state snapshot" in refused.stderr
