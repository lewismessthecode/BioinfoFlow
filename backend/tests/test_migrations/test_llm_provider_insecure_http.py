from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={
            **os.environ,
            "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
        },
        text=True,
        capture_output=True,
        check=False,
    )


def _provider_columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(llm_providers)")}


def test_insecure_http_opt_in_migration_defaults_existing_rows_and_downgrades(
    tmp_path: Path,
):
    db_path = tmp_path / "llm-provider-insecure-http.db"
    upgrade_to_previous = _run_alembic(
        db_path,
        "upgrade",
        "0042_remote_connection_stored_credentials",
    )
    assert upgrade_to_previous.returncode == 0, (
        upgrade_to_previous.stderr or upgrade_to_previous.stdout
    )

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO llm_providers (id, name, kind, scope, enabled)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("provider-existing", "Existing", "openai_compatible", "user", 1),
        )
        conn.commit()
    finally:
        conn.close()

    upgrade = _run_alembic(db_path, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr or upgrade.stdout

    conn = sqlite3.connect(db_path)
    try:
        assert "allow_insecure_http" in _provider_columns(conn)
        value = conn.execute(
            "SELECT allow_insecure_http FROM llm_providers WHERE id = ?",
            ("provider-existing",),
        ).fetchone()
        assert value == (0,)
    finally:
        conn.close()

    downgrade = _run_alembic(
        db_path,
        "downgrade",
        "0042_remote_connection_stored_credentials",
    )
    assert downgrade.returncode == 0, downgrade.stderr or downgrade.stdout

    conn = sqlite3.connect(db_path)
    try:
        assert "allow_insecure_http" not in _provider_columns(conn)
    finally:
        conn.close()
