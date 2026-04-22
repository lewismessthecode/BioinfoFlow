"""Tests for runtime/tasks.py — TaskManager with persistent DAG."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.agent.runtime.tasks import TaskManager


class TestTaskCreate:
    def test_creates_task(self, tmp_path: Path):
        mgr = TaskManager(tmp_path)
        result = json.loads(mgr.create(subject="Build feature"))
        assert result["created"] == "1"
        assert result["subject"] == "Build feature"

    def test_increments_ids(self, tmp_path: Path):
        mgr = TaskManager(tmp_path)
        r1 = json.loads(mgr.create(subject="First"))
        r2 = json.loads(mgr.create(subject="Second"))
        assert r1["created"] == "1"
        assert r2["created"] == "2"


class TestTaskUpdate:
    def test_update_status(self, tmp_path: Path):
        mgr = TaskManager(tmp_path)
        mgr.create(subject="Task A")
        result = json.loads(mgr.update(task_id="1", status="in_progress"))
        assert result["status"] == "in_progress"

    def test_update_nonexistent(self, tmp_path: Path):
        mgr = TaskManager(tmp_path)
        result = json.loads(mgr.update(task_id="999", status="completed"))
        assert "error" in result

    def test_auto_unlock_on_complete(self, tmp_path: Path):
        mgr = TaskManager(tmp_path)
        mgr.create(subject="Blocker")
        mgr.create(subject="Blocked task")
        mgr.update(task_id="2", add_blocked_by=["1"])

        # Verify blocked
        task2 = json.loads(mgr.get("2"))
        assert "1" in task2["blocked_by"]

        # Complete the blocker
        mgr.update(task_id="1", status="completed")

        # Verify unblocked
        task2 = json.loads(mgr.get("2"))
        assert "1" not in task2["blocked_by"]

    def test_add_blocks_reverse_relationship(self, tmp_path: Path):
        mgr = TaskManager(tmp_path)
        mgr.create(subject="Task A")
        mgr.create(subject="Task B")
        mgr.update(task_id="1", add_blocks=["2"])

        task1 = json.loads(mgr.get("1"))
        task2 = json.loads(mgr.get("2"))
        assert "2" in task1["blocks"]
        assert "1" in task2["blocked_by"]


class TestTaskGet:
    def test_get_full_detail(self, tmp_path: Path):
        mgr = TaskManager(tmp_path)
        mgr.create(subject="My task", description="Do the thing")
        data = json.loads(mgr.get("1"))
        assert data["subject"] == "My task"
        assert data["description"] == "Do the thing"
        assert data["status"] == "pending"

    def test_get_nonexistent(self, tmp_path: Path):
        mgr = TaskManager(tmp_path)
        result = json.loads(mgr.get("999"))
        assert "error" in result


class TestTaskList:
    def test_list_summary(self, tmp_path: Path):
        mgr = TaskManager(tmp_path)
        mgr.create(subject="Task A")
        mgr.create(subject="Task B")
        data = json.loads(mgr.list_all())
        assert len(data) == 2
        assert data[0]["id"] == "1"
        assert "subject" in data[0]


class TestTaskPersistence:
    def test_loads_from_disk(self, tmp_path: Path):
        mgr1 = TaskManager(tmp_path)
        mgr1.create(subject="Persisted task")
        mgr1.update(task_id="1", status="in_progress")

        # Create new manager from same dir
        mgr2 = TaskManager(tmp_path)
        data = json.loads(mgr2.get("1"))
        assert data["subject"] == "Persisted task"
        assert data["status"] == "in_progress"

    def test_id_continues_after_reload(self, tmp_path: Path):
        mgr1 = TaskManager(tmp_path)
        mgr1.create(subject="First")
        mgr1.create(subject="Second")

        mgr2 = TaskManager(tmp_path)
        result = json.loads(mgr2.create(subject="Third"))
        assert result["created"] == "3"


class TestTaskRender:
    def test_renders_active_tasks(self, tmp_path: Path):
        mgr = TaskManager(tmp_path)
        mgr.create(subject="Active task")
        mgr.update(task_id="1", status="in_progress")
        rendered = mgr.render()
        assert "[>] #1 Active task" in rendered

    def test_empty_when_all_completed(self, tmp_path: Path):
        mgr = TaskManager(tmp_path)
        mgr.create(subject="Done task")
        mgr.update(task_id="1", status="completed")
        assert mgr.render() == ""
