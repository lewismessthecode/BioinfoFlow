from __future__ import annotations

from typing import Any

from app.models.agent_core import AgentActionStatus
from app.repositories.agent_core_repo import AgentActionRepository
from app.services.agent_core.transcript.store import AgentTranscriptStore


TERMINAL_ACTION_STATUSES = frozenset(
    {
        AgentActionStatus.COMPLETED,
        AgentActionStatus.FAILED,
        AgentActionStatus.CANCELLED,
        AgentActionStatus.REJECTED,
    }
)


async def ordered_tool_call_batch(
    *,
    action_repo: AgentActionRepository,
    transcript: AgentTranscriptStore,
    action: Any,
) -> list[Any]:
    call_ids = await transcript.tool_call_batch_ids(
        session_id=str(action.session_id),
        turn_id=str(action.turn_id),
        tool_call_id=action.tool_call_id,
    )
    turn_actions = await action_repo.list_for_turn(str(action.turn_id))
    actions_by_call_id = {
        item.tool_call_id: item
        for item in turn_actions
        if item.kind == "tool" and item.tool_call_id
    }
    batch = [
        sibling
        for call_id in call_ids
        if (sibling := actions_by_call_id.get(call_id)) is not None
    ]
    if all(str(sibling.id) != str(action.id) for sibling in batch):
        batch.append(action)
    return batch
