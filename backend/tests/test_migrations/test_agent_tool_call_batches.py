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
    previous = _run_alembic(db_path, "upgrade", "0046_agent_permission_policy")
    assert previous.returncode == 0, previous.stderr

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO workspaces (id, name, slug, created_at, updated_at) "
            "VALUES ('legacy-workspace', 'Legacy', 'legacy-batch', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO agent_sessions "
            "(id, workspace_id, user_id, role_profile, permission_mode, automation_mode, "
            "permission_policy_version, runtime_mode, status, created_at, updated_at) "
            "VALUES ('legacy-session', 'legacy-workspace', 'dev', 'bioinformatician', "
            "'guarded_auto', 'assisted', 1, 'api', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO agent_turns "
            "(id, session_id, workspace_id, user_id, input_text, status, iteration_count, "
            "created_at, updated_at) VALUES ('legacy-turn', 'legacy-session', "
            "'legacy-workspace', 'dev', 'legacy', 'waiting_approval', 0, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO agent_actions "
            "(id, session_id, turn_id, kind, name, tool_call_id, input, risk_level, status, "
            "requires_resume, created_at, updated_at) VALUES ('legacy-action', "
            "'legacy-session', 'legacy-turn', 'tool', 'bash', 'legacy-call', '{}', "
            "'act_high', 'waiting_decision', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.commit()

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
        batch_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(agent_tool_call_batches)")
        }
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(agent_actions)")
        }
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        legacy_action = connection.execute(
            "SELECT tool_batch_id, tool_call_ordinal FROM agent_actions WHERE id = 'legacy-action'"
        ).fetchone()

    assert "agent_tool_call_batches" in tables
    assert {"tool_batch_id", "tool_call_ordinal"} <= action_columns
    assert "batch_ordinal" in batch_columns
    assert "sqlite_autoindex_agent_actions_1" in indexes
    assert legacy_action == (None, None)
    assert revision == (get_alembic_head_revision(),)
