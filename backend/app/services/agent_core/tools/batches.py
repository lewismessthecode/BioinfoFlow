from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_core import AgentToolCallBatchStatus
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentToolCallBatchRepository,
)


class ToolCallBatchCoordinator:
    """Persisted source of truth for one assistant tool-call barrier."""

    def __init__(self, session: AsyncSession):
        self.actions = AgentActionRepository(session)
        self.batches = AgentToolCallBatchRepository(session)

    async def create(
        self,
        *,
        session_id: str,
        turn_id: str,
        tool_call_count: int,
        batch_id: str | None = None,
        commit: bool = True,
    ):
        create = self.batches.create if commit else self.batches.add
        values = {
            "session_id": session_id,
            "turn_id": turn_id,
            "status": AgentToolCallBatchStatus.EVALUATING,
            "tool_call_count": tool_call_count,
            "batch_ordinal": await self.batches.next_ordinal(turn_id),
        }
        if batch_id is not None:
            values["id"] = batch_id
        return await create(**values)

    async def settle(self, batch_id: str) -> str:
        batch = await self.batches.get(batch_id)
        if batch is None:
            return "missing"
        state = await self.batches.continuation_state(batch_id)
        status = (
            AgentToolCallBatchStatus.READY
            if state == "ready"
            else AgentToolCallBatchStatus.WAITING
        )
        if batch.status in {
            AgentToolCallBatchStatus.EVALUATING,
            AgentToolCallBatchStatus.WAITING,
        }:
            await self.batches.settle_unclaimed(batch_id, status=status)
        return state

    async def claim_continuation(self, batch_id: str) -> bool:
        if await self.batches.continuation_state(batch_id) != "ready":
            return False
        return await self.batches.claim_ready(batch_id)

    async def mark_terminal(self, batch_id: str) -> None:
        await self.batches.terminalize_continuing(
            batch_id, status=AgentToolCallBatchStatus.TERMINAL
        )
        await self.batches.get_fresh(batch_id)

    async def release_continuation(self, batch_id: str) -> bool:
        return await self.batches.release_continuing(batch_id)

    async def fail_continuation(self, batch_id: str) -> bool:
        return await self.batches.terminalize_continuing(batch_id, status="failed")

    async def cancel_continuation(self, batch_id: str) -> bool:
        return await self.batches.terminalize_continuing(batch_id, status="cancelled")

    async def repair_preparation_failure(
        self,
        *,
        batch_id: str,
        session_id: str,
        turn_id: str,
        tool_calls: list[dict],
        error_message: str,
        action_status: str = "failed",
        error_type: str = "BatchPreparationError",
        commit: bool = True,
    ) -> None:
        error = {"type": error_type, "message": error_message}
        existing = {
            action.tool_call_ordinal: action
            for action in await self.actions.list_for_batch(batch_id)
        }
        for ordinal, tool_call in enumerate(tool_calls):
            action = existing.get(ordinal)
            if action is None:
                create = self.actions.create if commit else self.actions.add
                action = await create(
                    session_id=session_id,
                    turn_id=turn_id,
                    tool_batch_id=batch_id,
                    tool_call_ordinal=ordinal,
                    tool_call_id=tool_call.get("id"),
                    kind="tool",
                    name=str(tool_call.get("name") or "unknown"),
                    input=tool_call.get("arguments") or {},
                    normalized_input=tool_call.get("arguments") or {},
                    risk_level="act_high",
                    status=action_status,
                    error=error,
                    completed_at=datetime.now(timezone.utc),
                )
            elif action.status not in {"completed", "failed", "cancelled", "rejected"}:
                update = self.actions.update_all if commit else self.actions.update_all_pending
                await update(
                    action,
                    status=action_status,
                    requires_resume=False,
                    error=error,
                    completed_at=datetime.now(timezone.utc),
                )
        if commit:
            await self.batches.session.commit()
