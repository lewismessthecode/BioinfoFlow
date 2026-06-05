from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
VERSIONS_DIR = BACKEND_DIR / "alembic" / "versions"


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


def test_legacy_revision_file_exists_for_old_local_databases():
    revision_file = VERSIONS_DIR / "0005_workflow_launch_defaults.py"
    assert revision_file.exists()
    content = revision_file.read_text()
    assert 'revision = "0005_workflow_launch_defaults"' in content


def test_agent_core_cleanup_revision_drops_legacy_agent_tables():
    revision_file = VERSIONS_DIR / "0029_drop_legacy_agent_tables.py"
    assert revision_file.exists()
    content = revision_file.read_text()

    assert 'revision = "0029_drop_legacy_agent_tables"' in content
    for table_name in (
        "agent_approval_handles",
        "agent_response_handles",
        "agent_approvals",
        "agent_traces",
        "messages",
        "conversations",
    ):
        assert table_name in content


_LEGACY_DB = BACKEND_DIR / "bioinfoflow.db"


@pytest.mark.skipif(
    not _LEGACY_DB.exists(),
    reason="legacy bioinfoflow.db fixture not present (removed from git tracking)",
)
def test_old_local_database_can_upgrade_to_head(tmp_path: Path):
    from app.database import get_alembic_head_revision

    source_db = _LEGACY_DB
    db_copy = tmp_path / "legacy-copy.db"
    shutil.copy2(source_db, db_copy)

    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_copy}",
    }

    result = _run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    conn = sqlite3.connect(db_copy)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "scheduled_tasks" in tables
        assert "audit_logs" in tables
        assert "batches" in tables
        assert "batch_runs" in tables
        assert "notification_configs" in tables

        scheduled_task_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(scheduled_tasks)").fetchall()
        }
        assert "delay_until" in scheduled_task_columns
        assert "weight" in scheduled_task_columns

        workflow_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(workflows)").fetchall()
        }
        assert "weight" in workflow_columns

        project_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()
        }
        assert "user_id" in project_columns
        assert "created_by_user_id" in project_columns
        assert "workspace_id" in project_columns
        assert "is_default" in project_columns

        assert "conversations" not in tables
        assert "messages" not in tables
        assert "agent_traces" not in tables
        assert "agent_approvals" not in tables
        assert "agent_response_handles" not in tables
        assert "agent_approval_handles" not in tables

        assert "workspaces" in tables
        assert "workspace_memberships" in tables

        revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        assert revision is not None
        assert revision[0] == get_alembic_head_revision()
    finally:
        conn.close()
