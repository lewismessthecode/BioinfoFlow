from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


AgentExternalStatus = Literal[
    "pending_init",
    "running",
    "completed",
    "errored",
    "interrupted",
    "not_found",
]


@dataclass(frozen=True)
class AgentModelChoice:
    requested_model: str | None
    effective_model: str
    effective_model_id: str
    reasoning_effort: str | None
    fallback: bool
    fallback_reason: str | None


@dataclass(frozen=True)
class AgentStatusView:
    status: AgentExternalStatus
    final_text: str | None = None
    error_code: str | None = None
    error_message: str | None = None
