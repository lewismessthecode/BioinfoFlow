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


@dataclass(frozen=True)
class SpawnAgentResult:
    child_session_id: str
    child_turn_id: str
    task_name: str
    status: AgentExternalStatus
    requested_model: str | None
    effective_model: str
    effective_model_id: str
    reasoning_effort: str | None
    model_fallback: bool
    fallback_reason: str | None


@dataclass(frozen=True)
class AgentListItem:
    agent_id: str
    task_name: str
    status: AgentExternalStatus
    current_turn_id: str | None
    requested_model: str | None = None
    effective_model: str | None = None
    model_fallback: bool = False
    fallback_reason: str | None = None
    final_text: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
