"""Shared CLI constants — terminal states for runs and agent events."""

from __future__ import annotations

TERMINAL_RUN_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled"})

TERMINAL_AGENT_EVENTS: frozenset[str] = frozenset(
    {"agent.done", "agent.cancelled", "agent.error"}
)
