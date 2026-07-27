from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "0055_merge_agent_heads"
REVISION = "0056_readable_project_directories"
INDEX_NAME = "uq_projects_directory_name"


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"},
        capture_output=True,
        text=True,
        check=False,
    )


def _columns(connection: sqlite3.Connection) -> set[str]:
    return {row[1] for row in connection.execute("PRAGMA table_info(projects)")}


def _indexes(connection: sqlite3.Connection) -> dict[str, tuple]:
    return {row[1]: row for row in connection.execute("PRAGMA index_list(projects)")}


def _insert_project(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    name: str,
    directory_name: str | None,
) -> None:
    connection.execute(
        "INSERT INTO projects (id, name, user_id, directory_name) VALUES (?, ?, ?, ?)",
        (project_id, name, "dev", directory_name),
    )


def test_readable_project_directories_migration_preserves_legacy_rows_and_downgrades(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "readable-project-directories.db"
    previous = _run_alembic(db_path, "upgrade", PREVIOUS_REVISION)
    assert previous.returncode == 0, previous.stderr or previous.stdout

    legacy_project_id = "00000000-0000-0000-0000-000000000101"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO projects (id, name, user_id) VALUES (?, ?, ?)",
            (legacy_project_id, "Legacy project", "dev"),
        )

    upgraded = _run_alembic(db_path, "upgrade", REVISION)
    assert upgraded.returncode == 0, upgraded.stderr or upgraded.stdout

    with sqlite3.connect(db_path) as connection:
        assert "directory_name" in _columns(connection)
        assert connection.execute(
            "SELECT directory_name FROM projects WHERE id = ?",
            (legacy_project_id,),
        ).fetchone() == (None,)

        indexes = _indexes(connection)
        assert INDEX_NAME in indexes
        assert indexes[INDEX_NAME][2] == 1
        assert [
            row[2] for row in connection.execute(f'PRAGMA index_info("{INDEX_NAME}")')
        ] == ["directory_name"]

        _insert_project(
            connection,
            project_id="00000000-0000-0000-0000-000000000102",
            name="Second legacy project",
            directory_name=None,
        )
        _insert_project(
            connection,
            project_id="00000000-0000-0000-0000-000000000103",
            name="Readable project",
            directory_name="ce-shi",
        )
        connection.commit()

        with pytest.raises(sqlite3.IntegrityError):
            _insert_project(
                connection,
                project_id="00000000-0000-0000-0000-000000000104",
                name="Duplicate readable project",
                directory_name="ce-shi",
            )
        connection.rollback()

    downgraded = _run_alembic(db_path, "downgrade", PREVIOUS_REVISION)
    assert downgraded.returncode == 0, downgraded.stderr or downgraded.stdout

    with sqlite3.connect(db_path) as connection:
        assert "directory_name" not in _columns(connection)
        assert INDEX_NAME not in _indexes(connection)
