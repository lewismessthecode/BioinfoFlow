from __future__ import annotations

from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
REVISION = BACKEND_DIR / "alembic" / "versions" / "0041_run_module_invariants.py"


def test_run_module_invariants_migration_keeps_dispatched_duplicate_task():
    content = REVISION.read_text(encoding="utf-8")

    assert "CASE WHEN state = 'dispatched' THEN 0 ELSE 1 END" in content
    assert "uq_scheduled_tasks_active_run" in content
