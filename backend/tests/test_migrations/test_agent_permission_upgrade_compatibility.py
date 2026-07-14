from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from app.database import get_alembic_head_revision


BACKEND_DIR = Path(__file__).resolve().parents[2]
PR125_HEAD = "0045_agent_turn_owner_token"
EXPECTED_HEAD = "0050_agent_session_active_turn"


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"},
        capture_output=True,
        text=True,
        check=False,
    )


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def test_permission_migrations_upgrade_pr125_database_without_rewriting_turn(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "pr125-upgrade.db"
    previous = _run_alembic(db_path, "upgrade", PR125_HEAD)
    assert previous.returncode == 0, previous.stderr or previous.stdout

    workspace_id = "00000000-0000-0000-0000-000000000011"
    session_id = "00000000-0000-0000-0000-000000000012"
    turn_id = "00000000-0000-0000-0000-000000000013"
    owner_token = "00000000-0000-0000-0000-000000000014"
    resume_batch_token = "00000000-0000-0000-0000-000000000015"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO workspaces (id, name, slug, created_at, updated_at) "
            "VALUES (?, 'PR125 upgrade', 'pr125-upgrade', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (workspace_id,),
        )
        connection.execute(
            "INSERT INTO agent_sessions "
            "(id, workspace_id, user_id, role_profile, permission_mode, automation_mode, "
            "runtime_mode, status, created_at, updated_at) "
            "VALUES (?, ?, 'dev', 'bioinformatician', 'guarded_auto', 'assisted', "
            "'api', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (session_id, workspace_id),
        )
        connection.execute(
            "INSERT INTO agent_turns "
            "(id, session_id, workspace_id, user_id, input_text, status, iteration_count, "
            "owner_token, resume_batch_token, created_at, updated_at) "
            "VALUES (?, ?, ?, 'dev', 'preserve ownership', 'waiting_approval', 0, ?, ?, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (turn_id, session_id, workspace_id, owner_token, resume_batch_token),
        )
        connection.commit()

    upgraded = _run_alembic(db_path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr or upgraded.stdout

    with sqlite3.connect(db_path) as connection:
        turn = connection.execute(
            "SELECT status, owner_token, resume_batch_token, tool_batch_sequence "
            "FROM agent_turns WHERE id = ?",
            (turn_id,),
        ).fetchone()
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        session_columns = _columns(connection, "agent_sessions")
        action_columns = _columns(connection, "agent_actions")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert turn == ("waiting_approval", owner_token, resume_batch_token, 0)
    assert revision == (EXPECTED_HEAD,)
    assert "permission_policy_version" in session_columns
    assert {
        "tool_batch_id",
        "tool_call_ordinal",
        "evaluated_policy_version",
        "permission_context_snapshot",
    } <= action_columns
    assert "agent_tool_call_batches" in tables
    assert get_alembic_head_revision() == EXPECTED_HEAD


def test_permission_migrations_downgrade_preserves_pr125_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "pr125-downgrade.db"
    upgraded = _run_alembic(db_path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr or upgraded.stdout

    downgraded = _run_alembic(db_path, "downgrade", PR125_HEAD)
    assert downgraded.returncode == 0, downgraded.stderr or downgraded.stdout

    with sqlite3.connect(db_path) as connection:
        turn_columns = _columns(connection, "agent_turns")
        session_columns = _columns(connection, "agent_sessions")
        action_columns = _columns(connection, "agent_actions")
        provider_columns = _columns(connection, "llm_providers")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()

    assert {"owner_token", "resume_batch_token"} <= turn_columns
    assert "tool_batch_sequence" not in turn_columns
    assert "permission_policy_version" not in session_columns
    assert {
        "tool_batch_id",
        "tool_call_ordinal",
        "evaluated_policy_version",
        "permission_context_snapshot",
    }.isdisjoint(action_columns)
    assert "agent_tool_call_batches" not in tables
    assert "wire_protocol" in provider_columns
    assert revision == (PR125_HEAD,)
