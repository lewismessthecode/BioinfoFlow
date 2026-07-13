from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

from app.database import get_alembic_head_revision


BACKEND_DIR = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "0047_agent_turn_tool_batch_sequence"


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={"DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_turn_lease_owner_migration_adds_nullable_owner_token(tmp_path: Path) -> None:
    db_path = tmp_path / "turn-lease-owner.db"
    previous = _run_alembic(db_path, "upgrade", PREVIOUS_REVISION)
    assert previous.returncode == 0, previous.stderr

    workspace_id = "00000000-0000-0000-0000-000000000011"
    session_id = "00000000-0000-0000-0000-000000000012"
    approved_turn_id = "00000000-0000-0000-0000-000000000013"
    waiting_turn_id = "00000000-0000-0000-0000-000000000014"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO workspaces (id, name, slug, created_at, updated_at) "
            "VALUES (?, 'Lease migration', 'lease-migration', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (workspace_id,),
        )
        connection.execute(
            "INSERT INTO agent_sessions "
            "(id, workspace_id, user_id, role_profile, permission_mode, automation_mode, "
            "permission_policy_version, runtime_mode, status, created_at, updated_at) "
            "VALUES (?, ?, 'dev', 'bioinformatician', 'guarded_auto', 'assisted', 1, "
            "'api', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (session_id, workspace_id),
        )
        for turn_id in (approved_turn_id, waiting_turn_id):
            connection.execute(
                "INSERT INTO agent_turns "
                "(id, session_id, workspace_id, user_id, input_text, status, "
                "iteration_count, tool_batch_sequence, created_at, updated_at) "
                "VALUES (?, ?, ?, 'dev', 'recover legacy approval', 'waiting_approval', "
                "0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (turn_id, session_id, workspace_id),
            )
        for action_id, turn_id, status in (
            (
                "00000000-0000-0000-0000-000000000015",
                approved_turn_id,
                "requested",
            ),
            (
                "00000000-0000-0000-0000-000000000016",
                waiting_turn_id,
                "waiting_decision",
            ),
        ):
            connection.execute(
                "INSERT INTO agent_actions "
                "(id, session_id, turn_id, kind, name, input, risk_level, status, "
                "requires_resume, created_at, updated_at) "
                "VALUES (?, ?, ?, 'tool', 'bash', '{}', 'act_high', ?, 1, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (action_id, session_id, turn_id, status),
            )
        connection.commit()

    upgraded = _run_alembic(db_path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(agent_turns)")
        }
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        turn_statuses = dict(
            connection.execute(
                "SELECT id, status FROM agent_turns WHERE id IN (?, ?)",
                (approved_turn_id, waiting_turn_id),
            )
        )

    assert columns["lease_owner_token"][2].upper() == "VARCHAR(64)"
    assert columns["lease_owner_token"][3] == 0
    assert turn_statuses == {
        approved_turn_id: "queued",
        waiting_turn_id: "waiting_approval",
    }
    assert revision == (get_alembic_head_revision(),)
