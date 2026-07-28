from __future__ import annotations

from app.models.agent_core import AgentActionStatus


def action_requires_resume(status: str) -> bool:
    return status == AgentActionStatus.WAITING_DECISION
