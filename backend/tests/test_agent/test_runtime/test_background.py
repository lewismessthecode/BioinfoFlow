"""Tests for runtime/background.py — BackgroundManager shell execution."""

from __future__ import annotations

import time
from pathlib import Path

from app.services.agent.runtime.background import BackgroundManager


class TestBackgroundSpawn:
    def test_spawn_and_drain(self, tmp_path: Path):
        mgr = BackgroundManager(workspace_root=tmp_path, timeout=10)
        task_id = mgr.spawn("echo hello")
        assert task_id.startswith("bg-")

        # Wait for completion
        time.sleep(1)
        results = mgr.drain_notifications()
        assert len(results) == 1
        assert results[0].task_id == task_id
        assert results[0].exit_code == 0
        assert "hello" in results[0].stdout

    def test_drain_empty(self):
        mgr = BackgroundManager()
        results = mgr.drain_notifications()
        assert results == []

    def test_active_count(self):
        mgr = BackgroundManager(timeout=10)
        assert mgr.active_count() == 0
        mgr.spawn("sleep 2")
        time.sleep(0.2)
        assert mgr.active_count() >= 1

    def test_multiple_jobs(self, tmp_path: Path):
        mgr = BackgroundManager(workspace_root=tmp_path, timeout=10)
        ids = [mgr.spawn(f"echo job{i}") for i in range(3)]
        assert len(set(ids)) == 3  # unique IDs

        time.sleep(1)
        results = mgr.drain_notifications()
        assert len(results) == 3
        assert all(r.exit_code == 0 for r in results)

    def test_timeout(self):
        mgr = BackgroundManager(timeout=1)
        mgr.spawn("sleep 10")
        time.sleep(3)
        results = mgr.drain_notifications()
        assert len(results) == 1
        assert results[0].exit_code == -1
        assert "timed out" in results[0].stderr.lower()

    def test_failed_command(self, tmp_path: Path):
        mgr = BackgroundManager(workspace_root=tmp_path, timeout=10)
        mgr.spawn("ls /nonexistent_path_that_does_not_exist")
        time.sleep(1)
        results = mgr.drain_notifications()
        assert len(results) == 1
        assert results[0].exit_code != 0


# --- Phase 2 Fix 15: BackgroundManager shutdown ---


class TestBackgroundShutdown:
    def test_shutdown_signals_workers_to_stop(self, tmp_path: Path):
        mgr = BackgroundManager(workspace_root=tmp_path, timeout=10)
        mgr.spawn("echo shutdown-test")
        time.sleep(0.5)

        mgr.shutdown(timeout=5)

        assert mgr._shutdown_event.is_set()

    def test_shutdown_drains_remaining_results(self, tmp_path: Path):
        mgr = BackgroundManager(workspace_root=tmp_path, timeout=10)
        mgr.spawn("echo draining")
        time.sleep(0.5)

        mgr.shutdown(timeout=5)

        # After shutdown, active count should be 0
        assert mgr.active_count() == 0

    def test_shutdown_is_idempotent(self, tmp_path: Path):
        mgr = BackgroundManager(workspace_root=tmp_path, timeout=10)
        mgr.shutdown(timeout=1)
        mgr.shutdown(timeout=1)  # Should not raise
