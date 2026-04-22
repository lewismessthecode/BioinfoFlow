"""Per-session state container for the agent runtime.

Holds all mutable state that persists across rounds within a single
agent invocation: messages, todo list, round counter, and workspace context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.services.agent.runtime.todo import TodoManager

if TYPE_CHECKING:
    from app.services.agent.runtime.background import BackgroundManager
    from app.services.agent.runtime.tasks import TaskManager


@dataclass
class SessionState:
    """Mutable state for a single agent session (one send_message call)."""

    project_id: str
    conversation_id: str
    workspace_root: Path | None = None

    # Message history (plain dicts, Anthropic format)
    messages: list[dict[str, Any]] = field(default_factory=list)

    # Round counter (incremented each LLM call)
    current_round: int = 0

    # Todo manager (session-scoped)
    todo: TodoManager = field(default_factory=TodoManager)

    # Transcript directory for compaction saves
    transcript_dir: Path | None = None

    # Phase 2: task DAG manager (persistent)
    task_manager: "TaskManager | None" = None

    # Phase 2: background command manager
    background_manager: "BackgroundManager | None" = None

    # Token usage tracking (accumulated across rounds)
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    def increment_round(self) -> None:
        """Advance the round counter and tick the todo nag timer."""
        self.current_round += 1
        self.todo.tick_round()

    def accumulate_usage(self, usage: dict[str, int]) -> None:
        """Add token usage from an LLM response."""
        self.total_input_tokens += usage.get("input_tokens", 0) + usage.get("prompt_tokens", 0)
        self.total_output_tokens += usage.get("output_tokens", 0) + usage.get("completion_tokens", 0)
