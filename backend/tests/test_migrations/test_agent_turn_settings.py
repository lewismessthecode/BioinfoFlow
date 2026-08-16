from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "0060_agent_harness_public_revisions"
TARGET_REVISION = "0061_agent_turn_settings"


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={"DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_turn_settings_migration_snapshots_workspace_environments_for_existing_runs(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "agent-turn-settings.db"
    previous = _run_alembic(db_path, "upgrade", PREVIOUS_REVISION)
    assert previous.returncode == 0, previous.stderr

    workspace_a = "a0000000-0000-0000-0000-000000000001"
    workspace_b = "a0000000-0000-0000-0000-000000000002"
    session_a = "10000000-0000-0000-0000-000000000001"
    session_b = "10000000-0000-0000-0000-000000000002"
    run_a = "20000000-0000-0000-0000-000000000001"
    run_b = "20000000-0000-0000-0000-000000000002"
    remote_a_1 = "30000000-0000-0000-0000-000000000001"
    remote_a_2 = "30000000-0000-0000-0000-000000000002"
    remote_b = "30000000-0000-0000-0000-000000000003"

    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            "INSERT INTO workspaces (id, name, slug, created_at, updated_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                (workspace_a, "Workspace A", "workspace-a"),
                (workspace_b, "Workspace B", "workspace-b"),
            ),
        )
        connection.executemany(
            "INSERT INTO remote_connections "
            "(id, workspace_id, name, host, port, username, auth_method, "
            "last_status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'example.test', 22, 'agent', 'agent', 'online', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                (remote_a_2, workspace_a, "A second"),
                (remote_b, workspace_b, "B only"),
                (remote_a_1, workspace_a, "A first"),
            ),
        )
        for session_id, workspace_id in (
            (session_a, workspace_a),
            (session_b, workspace_b),
        ):
            connection.execute(
                "INSERT INTO agent_sessions "
                "(id, user_id, workspace_id, title, permission_mode, workspace_access, "
                "prompt_snapshot, history_revision, command_queue, command_ids, status, "
                "created_at, updated_at) "
                "VALUES (?, 'user-1', ?, 'Migrated', 'ask_dangerous', 'read_write', "
                "?, 0, '[]', '[]', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (session_id, workspace_id, json.dumps({"schema_version": 1})),
            )
        for run_id, session_id in ((run_a, session_a), (run_b, session_b)):
            connection.execute(
                "INSERT INTO agent_runs "
                "(id, session_id, status, revision, lease_generation, command_queue, "
                "command_ids, retry_count, created_at, updated_at) "
                "VALUES (?, ?, 'running', 0, 0, '[]', '[]', 0, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (run_id, session_id),
            )

    upgraded = _run_alembic(db_path, "upgrade", TARGET_REVISION)
    assert upgraded.returncode == 0, upgraded.stderr

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT id, turn_execution_config FROM agent_runs ORDER BY id"
        ).fetchall()

    configs = {run_id: json.loads(config) for run_id, config in rows}
    assert configs[run_a]["environment_scope"] == {
        "mode": "auto",
        "environment_ids": ["local", remote_a_1, remote_a_2],
    }
    assert configs[run_b]["environment_scope"] == {
        "mode": "auto",
        "environment_ids": ["local", remote_b],
    }
