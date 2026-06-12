from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


TurnTerminationReason = Literal[
    "assistant_final",
    "waiting_approval",
    "interrupted",
    "cancelled",
    "budget_exhausted",
    "model_failed",
    "no_progress",
]


@dataclass(frozen=True)
class LoopResult:
    termination_reason: TurnTerminationReason
    final_text: str | None
    iteration_count: int
    token_usage: dict | None = None
    error_code: str | None = None
    error_message: str | None = None
