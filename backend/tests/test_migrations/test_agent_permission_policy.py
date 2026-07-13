from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

from app.database import get_alembic_head_revision


BACKEND_DIR = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "0043_llm_provider_insecure_http_opt_in"


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={"DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_permission_policy_migration_defaults_existing_sessions_and_actions(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "permission-policy.db"
    previous = _run_alembic(db_path, "upgrade", PREVIOUS_REVISION)
    assert previous.returncode == 0, previous.stderr

    with sqlite3.connect(db_path) as connection:
        workspace_id = "00000000-0000-0000-0000-000000000011"
        session_id = "00000000-0000-0000-0000-000000000002"
        turn_id = "00000000-0000-0000-0000-000000000003"
        action_id = "00000000-0000-0000-0000-000000000004"
        connection.execute(
            "INSERT INTO workspaces (id, name, slug, created_at, updated_at) "
            "VALUES (?, 'Permission audit', 'permission-audit', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
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
            "created_at, updated_at) VALUES (?, ?, ?, 'dev', 'test', 'queued', 0, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (turn_id, session_id, workspace_id),
        )
        connection.execute(
            "INSERT INTO agent_actions "
            "(id, session_id, turn_id, kind, name, input, risk_level, status, "
            "requires_resume, created_at, updated_at) "
            "VALUES (?, ?, ?, 'tool', 'test.high', '{}', 'act_high', 'requested', 0, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (action_id, session_id, turn_id),
        )
        connection.commit()

    upgraded = _run_alembic(db_path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    with sqlite3.connect(db_path) as connection:
        session_row = connection.execute(
            "SELECT permission_policy_version FROM agent_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        action_row = connection.execute(
            "SELECT evaluated_policy_version, permission_context_snapshot "
            "FROM agent_actions WHERE id = ?",
            (action_id,),
        ).fetchone()
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()

    assert session_row == (1,)
    assert action_row == (None, None)
    assert revision == (get_alembic_head_revision(),)
