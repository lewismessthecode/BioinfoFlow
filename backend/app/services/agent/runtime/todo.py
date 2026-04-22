"""TodoManager for tracking agent tasks within a session (s02 pattern).

In-memory only — lost on compaction or session end.
Registered as ``todo_write`` tool in the dispatch map.
The nag logic lives in loop.py: inject a reminder after 3 idle rounds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TodoItem:
    id: str
    text: str
    status: str = "pending"  # "pending" | "in_progress" | "completed"


class TodoManager:
    """Session-scoped todo list with at most one in_progress item."""

    def __init__(self) -> None:
        self.items: list[TodoItem] = []
        self.rounds_since_update: int = 0

    def update(self, items: list[dict[str, Any]]) -> str:
        """Replace the entire todo list.

        Enforces: at most 1 item may be ``in_progress``.

        Args:
            items: List of dicts with keys ``id``, ``text``, ``status``.

        Returns:
            Confirmation string for the tool result.
        """
        new_items: list[TodoItem] = []
        in_progress_count = 0

        for raw in items:
            status = raw.get("status", "pending")
            if status == "in_progress":
                in_progress_count += 1
            if in_progress_count > 1:
                status = "pending"
            new_items.append(
                TodoItem(
                    id=str(raw.get("id", len(new_items))),
                    text=str(raw.get("text", "")),
                    status=status,
                )
            )

        self.items = new_items
        self.rounds_since_update = 0

        counts = _count_statuses(self.items)
        return (
            f"Updated todo list: {counts['pending']} pending, "
            f"{counts['in_progress']} in progress, "
            f"{counts['completed']} completed."
        )

    def render(self) -> str:
        """Render the todo list in checkbox format for system prompt injection.

        Returns empty string if no items.
        """
        if not self.items:
            return ""

        lines: list[str] = []
        for item in self.items:
            if item.status == "completed":
                prefix = "[x]"
            elif item.status == "in_progress":
                prefix = "[>]"
            else:
                prefix = "[ ]"
            lines.append(f"{prefix} {item.text}")
        return "\n".join(lines)

    def has_incomplete(self) -> bool:
        """True if any items are pending or in_progress."""
        return any(item.status != "completed" for item in self.items)

    def tick_round(self) -> None:
        """Increment the idle-round counter (called each loop iteration)."""
        self.rounds_since_update += 1

    def should_nag(self, threshold: int = 3) -> bool:
        """True if we should inject a nag reminder."""
        return self.has_incomplete() and self.rounds_since_update >= threshold

    def nag_message(self) -> str:
        """Build the nag reminder content."""
        return (
            "<reminder>You have incomplete tasks in your todo list. "
            "Please review and update your progress using the todo_write tool.\n\n"
            f"{self.render()}</reminder>"
        )


def _count_statuses(items: list[TodoItem]) -> dict[str, int]:
    counts = {"pending": 0, "in_progress": 0, "completed": 0}
    for item in items:
        counts[item.status] += 1
    return counts
