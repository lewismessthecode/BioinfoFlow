from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]


def _run(
    cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_runtime_strategy_migration_is_idempotent_for_partially_applied_sqlite_db(
    tmp_path: Path,
):
    db_path = tmp_path / "partial-0033.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute(
            "INSERT INTO alembic_version (version_num) VALUES (?)",
            ("0032_seed_ollama_deepseek_r1",),
        )
        conn.execute(
            """
            CREATE TABLE llm_model_profiles (
              name VARCHAR(120) NOT NULL,
              task_type VARCHAR(80) NOT NULL,
              primary_model_id VARCHAR(36) NOT NULL,
              fallback_model_ids JSON,
              reasoning_budget INTEGER,
              max_tokens INTEGER,
              cost_ceiling VARCHAR(40),
              routing_policy JSON,
              permission_overrides JSON,
              scope VARCHAR(20) NOT NULL,
              workspace_id VARCHAR(36),
              user_id VARCHAR(36),
              enabled BOOLEAN NOT NULL,
              metadata JSON,
              id VARCHAR(36) NOT NULL PRIMARY KEY,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              prefer_streaming BOOLEAN NOT NULL DEFAULT 1,
              allow_thinking BOOLEAN NOT NULL DEFAULT 1,
              allow_tools BOOLEAN NOT NULL DEFAULT 1
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
    }
    result = _run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    conn = sqlite3.connect(db_path)
    try:
        revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        assert revision == ("0033_llm_profile_runtime_strategy",)

        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(llm_model_profiles)").fetchall()
        }
        assert {"prefer_streaming", "allow_thinking", "allow_tools"} <= columns
    finally:
        conn.close()
