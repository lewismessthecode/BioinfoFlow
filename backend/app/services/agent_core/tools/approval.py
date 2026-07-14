from __future__ import annotations

import json

from app.models.agent_core import AgentActionStatus


def action_requires_resume(status: str) -> bool:
    return status == AgentActionStatus.WAITING_DECISION


def action_matches_pending_observation(turn, action) -> bool:
    progress = ((getattr(turn, "loop_state", None) or {}).get("progress") or {})
    pending = progress.get("pending_observation")
    if not isinstance(pending, dict):
        return False
    for signature in pending.get("tool_results") or []:
        try:
            item = json.loads(signature)
        except (TypeError, ValueError):
            continue
        if (
            item.get("status") == "pending"
            and item.get("tool") == action.name
            and item.get("tool_call_id") == action.tool_call_id
        ):
            return True
    return False
