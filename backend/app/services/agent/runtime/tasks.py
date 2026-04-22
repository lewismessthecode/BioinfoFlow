"""Persistent task DAG system (s07 pattern).

Provides a lightweight task tracker with blocking/dependency relationships,
persisted as individual JSON files in a ``.tasks/`` directory within the
agent workspace.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Task:
    """A single task in the DAG."""

    id: str
    subject: str
    description: str = ""
    status: str = "pending"  # pending | in_progress | completed
    blocked_by: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    owner: str = ""


class TaskManager:
    """Manages a persistent task DAG stored as JSON files."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace = workspace_root
        self._tasks_dir = workspace_root / ".tasks"
        self._tasks: dict[str, Task] = {}
        self._next_id = 1
        self._load_existing()

    def _load_existing(self) -> None:
        """Load any previously persisted tasks from disk."""
        if not self._tasks_dir.is_dir():
            return
        max_id = 0
        for fp in sorted(self._tasks_dir.glob("task_*.json")):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                task = Task(**data)
                self._tasks[task.id] = task
                try:
                    max_id = max(max_id, int(task.id))
                except ValueError:
                    pass
            except Exception as exc:
                logger.warning("tasks.load_error", file=str(fp), error=str(exc))
        self._next_id = max_id + 1

    def _persist(self, task: Task) -> None:
        """Write a single task to disk."""
        self._tasks_dir.mkdir(parents=True, exist_ok=True)
        fp = self._tasks_dir / f"task_{task.id}.json"
        fp.write_text(
            json.dumps(asdict(task), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def create(self, *, subject: str, description: str = "") -> str:
        """Create a new task and return a JSON confirmation."""
        task_id = str(self._next_id)
        self._next_id += 1
        task = Task(id=task_id, subject=subject, description=description)
        self._tasks[task_id] = task
        self._persist(task)
        logger.info("tasks.created", task_id=task_id, subject=subject)
        return json.dumps({"created": task_id, "subject": subject})

    def update(
        self,
        *,
        task_id: str,
        status: str | None = None,
        subject: str | None = None,
        description: str | None = None,
        add_blocked_by: list[str] | None = None,
        add_blocks: list[str] | None = None,
        owner: str | None = None,
    ) -> str:
        """Update task fields and return a JSON confirmation."""
        task = self._tasks.get(task_id)
        if task is None:
            return json.dumps({"error": f"Task {task_id} not found"})

        if subject is not None:
            task.subject = subject
        if description is not None:
            task.description = description
        if owner is not None:
            task.owner = owner
        if status is not None:
            task.status = status
            if status == "completed":
                self._auto_unlock(task_id)

        if add_blocked_by:
            for dep_id in add_blocked_by:
                if dep_id not in task.blocked_by:
                    task.blocked_by.append(dep_id)
                # Also update the reverse relationship
                dep_task = self._tasks.get(dep_id)
                if dep_task and task_id not in dep_task.blocks:
                    dep_task.blocks.append(task_id)
                    self._persist(dep_task)

        if add_blocks:
            for dep_id in add_blocks:
                if dep_id not in task.blocks:
                    task.blocks.append(dep_id)
                dep_task = self._tasks.get(dep_id)
                if dep_task and task_id not in dep_task.blocked_by:
                    dep_task.blocked_by.append(task_id)
                    self._persist(dep_task)

        self._persist(task)
        return json.dumps({"updated": task_id, "status": task.status})

    def get(self, task_id: str) -> str:
        """Return full task detail as JSON."""
        task = self._tasks.get(task_id)
        if task is None:
            return json.dumps({"error": f"Task {task_id} not found"})
        return json.dumps(asdict(task), ensure_ascii=False)

    def list_all(self) -> str:
        """Return summary of all tasks as JSON."""
        summary = []
        for task in self._tasks.values():
            # Only include open blocked_by IDs (tasks that aren't completed)
            open_blocked = [
                bid
                for bid in task.blocked_by
                if bid in self._tasks and self._tasks[bid].status != "completed"
            ]
            summary.append(
                {
                    "id": task.id,
                    "subject": task.subject,
                    "status": task.status,
                    "owner": task.owner,
                    "blockedBy": open_blocked,
                }
            )
        return json.dumps(summary, ensure_ascii=False)

    def render(self) -> str:
        """Render active tasks for system prompt injection."""
        active = [t for t in self._tasks.values() if t.status != "completed"]
        if not active:
            return ""
        lines = []
        for t in active:
            prefix = "[>]" if t.status == "in_progress" else "[ ]"
            blocked = (
                f" (blocked by: {', '.join(t.blocked_by)})" if t.blocked_by else ""
            )
            lines.append(f"{prefix} #{t.id} {t.subject}{blocked}")
        return "\n".join(lines)

    def _auto_unlock(self, completed_id: str) -> None:
        """Remove completed_id from all other tasks' blocked_by lists."""
        for task in self._tasks.values():
            if completed_id in task.blocked_by:
                task.blocked_by.remove(completed_id)
                self._persist(task)
