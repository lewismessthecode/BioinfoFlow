"""Shared CLI constants for terminal workflow-run states."""

from __future__ import annotations

TERMINAL_RUN_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled"})
