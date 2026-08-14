from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "0055_merge_agent_heads"
TARGET_REVISION = "0056_agent_collaboration_tree"


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={"DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"},
        capture_output=True,
        text=True,
        check=False,
    )


def _agent_session_schema(db_path: Path) -> tuple[set[str], set[str]]:
    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(agent_sessions)")
        }
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(agent_sessions)")
        }
    return columns, indexes


def test_agent_collaboration_migration_keeps_legacy_sessions_nullable_and_enforces_names(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "agent-collaboration.db"
    previous = _run_alembic(db_path, "upgrade", PREVIOUS_REVISION)
    assert previous.returncode == 0, previous.stderr

    workspace_id = "00000000-0000-0000-0000-000000000011"
    root_id = "00000000-0000-0000-0000-000000000012"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO workspaces (id, name, slug, created_at, updated_at) "
            "VALUES (?, 'Collaboration', 'collaboration', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (workspace_id,),
        )
        connection.execute(
            "INSERT INTO agent_sessions "
            "(id, workspace_id, user_id, role_profile, permission_mode, automation_mode, "
            "runtime_mode, status, created_at, updated_at) "
            "VALUES (?, ?, 'dev', 'bioinformatician', 'guarded_auto', 'assisted', "
            "'api', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (root_id, workspace_id),
        )
        connection.commit()

    upgraded = _run_alembic(db_path, "upgrade", TARGET_REVISION)
    assert upgraded.returncode == 0, upgraded.stderr

    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1]: row
            for row in connection.execute("PRAGMA table_info(agent_sessions)")
        }
        legacy = connection.execute(
            "SELECT parent_session_id, root_session_id, agent_name, collaboration_slot, "
            "spawned_by_turn_id FROM agent_sessions WHERE id = ?",
            (root_id,),
        ).fetchone()
        indexes = {
            row[1]: row
            for row in connection.execute("PRAGMA index_list(agent_sessions)")
        }

        child_columns = (
            "id, workspace_id, user_id, role_profile, permission_mode, automation_mode, "
            "runtime_mode, status, parent_session_id, root_session_id, agent_name, "
            "created_at, updated_at"
        )
        child_values = (
            "?, ?, 'dev', 'bioinformatician', 'guarded_auto', 'assisted', 'api', "
            "'active', ?, ?, 'reader', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
        )
        connection.execute(
            f"INSERT INTO agent_sessions ({child_columns}) VALUES ({child_values})",
            ("00000000-0000-0000-0000-000000000013", workspace_id, root_id, root_id),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                f"INSERT INTO agent_sessions ({child_columns}) VALUES ({child_values})",
                (
                    "00000000-0000-0000-0000-000000000014",
                    workspace_id,
                    root_id,
                    root_id,
                ),
            )

    expected_columns = {
        "parent_session_id",
        "root_session_id",
        "agent_name",
        "collaboration_slot",
        "spawned_by_turn_id",
    }
    assert expected_columns <= columns.keys()
    assert all(columns[name][3] == 0 for name in expected_columns)
    assert legacy == (None, None, None, None, None)
    assert {
        "uq_agent_sessions_parent_agent_name",
        "uq_agent_sessions_root_collaboration_slot",
        "ix_agent_sessions_root_status",
        "ix_agent_sessions_root_active_turn",
        "ix_agent_sessions_parent_session_id",
        "ix_agent_sessions_spawned_by_turn_id",
    } <= indexes.keys()

    downgraded = _run_alembic(db_path, "downgrade", PREVIOUS_REVISION)
    assert downgraded.returncode == 0, downgraded.stderr
    downgraded_columns, downgraded_indexes = _agent_session_schema(db_path)
    assert expected_columns.isdisjoint(downgraded_columns)
    assert {
        "uq_agent_sessions_parent_agent_name",
        "uq_agent_sessions_root_collaboration_slot",
        "ix_agent_sessions_root_status",
        "ix_agent_sessions_root_active_turn",
        "ix_agent_sessions_parent_session_id",
        "ix_agent_sessions_spawned_by_turn_id",
    }.isdisjoint(downgraded_indexes)

    reupgraded = _run_alembic(db_path, "upgrade", TARGET_REVISION)
    assert reupgraded.returncode == 0, reupgraded.stderr
    reupgraded_columns, reupgraded_indexes = _agent_session_schema(db_path)
    assert expected_columns <= reupgraded_columns
    assert {
        "uq_agent_sessions_parent_agent_name",
        "uq_agent_sessions_root_collaboration_slot",
        "ix_agent_sessions_root_status",
        "ix_agent_sessions_root_active_turn",
        "ix_agent_sessions_parent_session_id",
        "ix_agent_sessions_spawned_by_turn_id",
    } <= reupgraded_indexes
