from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "0043_llm_provider_insecure_http_opt_in"


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"},
        text=True,
        capture_output=True,
        check=False,
    )


def _provider_columns(conn: sqlite3.Connection) -> dict[str, tuple]:
    return {row[1]: row for row in conn.execute("PRAGMA table_info(llm_providers)")}


def test_wire_protocol_migration_defaults_existing_rows_constrains_values_and_downgrades(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "llm-provider-wire-protocol.db"
    previous = _run_alembic(db_path, "upgrade", PREVIOUS_REVISION)
    assert previous.returncode == 0, previous.stderr or previous.stdout

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
        columns = _provider_columns(conn)
        assert columns["wire_protocol"][3] == 1
        assert columns["wire_protocol"][4].strip("'\"") == "chat_completions"
        assert conn.execute(
            "SELECT wire_protocol FROM llm_providers WHERE id = ?",
            ("provider-existing",),
        ).fetchone() == ("chat_completions",)

        conn.execute(
            """
            INSERT INTO llm_providers (id, name, kind, scope, enabled, wire_protocol)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("provider-responses", "Responses", "openai", "user", 1, "responses"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO llm_providers (id, name, kind, scope, enabled, wire_protocol)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("provider-invalid", "Invalid", "openai", "user", 1, "guess"),
            )
    finally:
        conn.close()

    downgrade = _run_alembic(db_path, "downgrade", PREVIOUS_REVISION)
    assert downgrade.returncode == 0, downgrade.stderr or downgrade.stdout

    conn = sqlite3.connect(db_path)
    try:
        assert "wire_protocol" not in _provider_columns(conn)
    finally:
        conn.close()
