"""Tests for runtime/todo.py — TodoManager with nag reminder."""

from __future__ import annotations

from app.services.agent.runtime.todo import TodoManager


class TestTodoUpdate:
    def test_basic_update(self):
        mgr = TodoManager()
        result = mgr.update(
            [
                {"id": "1", "text": "Run pipeline", "status": "pending"},
                {"id": "2", "text": "Check results", "status": "pending"},
            ]
        )
        assert "2 pending" in result
        assert len(mgr.items) == 2

    def test_max_one_in_progress(self):
        mgr = TodoManager()
        mgr.update(
            [
                {"id": "1", "text": "Task A", "status": "in_progress"},
                {"id": "2", "text": "Task B", "status": "in_progress"},
            ]
        )
        in_progress = [i for i in mgr.items if i.status == "in_progress"]
        assert len(in_progress) == 1, "Only 1 item should be in_progress"

    def test_resets_round_counter(self):
        mgr = TodoManager()
        mgr.rounds_since_update = 5
        mgr.update([{"id": "1", "text": "Task", "status": "pending"}])
        assert mgr.rounds_since_update == 0

    def test_replaces_list(self):
        mgr = TodoManager()
        mgr.update([{"id": "1", "text": "Old", "status": "pending"}])
        mgr.update([{"id": "2", "text": "New", "status": "completed"}])
        assert len(mgr.items) == 1
        assert mgr.items[0].text == "New"


class TestTodoRender:
    def test_empty(self):
        mgr = TodoManager()
        assert mgr.render() == ""

    def test_mixed_statuses(self):
        mgr = TodoManager()
        mgr.update(
            [
                {"id": "1", "text": "Done task", "status": "completed"},
                {"id": "2", "text": "Active task", "status": "in_progress"},
                {"id": "3", "text": "Waiting task", "status": "pending"},
            ]
        )
        rendered = mgr.render()
        assert "[x] Done task" in rendered
        assert "[>] Active task" in rendered
        assert "[ ] Waiting task" in rendered


class TestTodoHasIncomplete:
    def test_all_completed(self):
        mgr = TodoManager()
        mgr.update([{"id": "1", "text": "Done", "status": "completed"}])
        assert not mgr.has_incomplete()

    def test_has_pending(self):
        mgr = TodoManager()
        mgr.update([{"id": "1", "text": "Pending", "status": "pending"}])
        assert mgr.has_incomplete()

    def test_empty_list(self):
        mgr = TodoManager()
        assert not mgr.has_incomplete()


class TestTodoNag:
    def test_nag_after_threshold(self):
        mgr = TodoManager()
        mgr.update([{"id": "1", "text": "Task", "status": "pending"}])
        for _ in range(3):
            mgr.tick_round()
        assert mgr.should_nag()

    def test_no_nag_when_updated_recently(self):
        mgr = TodoManager()
        mgr.update([{"id": "1", "text": "Task", "status": "pending"}])
        mgr.tick_round()
        assert not mgr.should_nag()

    def test_no_nag_when_all_completed(self):
        mgr = TodoManager()
        mgr.update([{"id": "1", "text": "Done", "status": "completed"}])
        for _ in range(5):
            mgr.tick_round()
        assert not mgr.should_nag()

    def test_nag_message_content(self):
        mgr = TodoManager()
        mgr.update([{"id": "1", "text": "Pending task", "status": "pending"}])
        msg = mgr.nag_message()
        assert "<reminder>" in msg
        assert "Pending task" in msg
