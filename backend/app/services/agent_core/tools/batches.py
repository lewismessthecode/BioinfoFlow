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

    async def create(self, *, session_id: str, turn_id: str, tool_call_count: int):
        return await self.batches.create(
            session_id=session_id,
            turn_id=turn_id,
            status=AgentToolCallBatchStatus.EVALUATING,
            tool_call_count=tool_call_count,
        )

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
        if batch.status != status:
            await self.batches.update_all(batch, status=status)
        return state

    async def claim_continuation(self, batch_id: str) -> bool:
        batch = await self.batches.get(batch_id)
        if batch is None or batch.status not in {
            AgentToolCallBatchStatus.READY,
            AgentToolCallBatchStatus.WAITING,
        }:
            return False
        if await self.batches.continuation_state(batch_id) != "ready":
            return False
        await self.batches.update_all(
            batch,
            status=AgentToolCallBatchStatus.CONTINUING,
            continuation_claimed_at=datetime.now(timezone.utc),
        )
        return True

    async def mark_terminal(self, batch_id: str) -> None:
        batch = await self.batches.get(batch_id)
        if batch is not None:
            await self.batches.update_all(
                batch,
                status=AgentToolCallBatchStatus.TERMINAL,
                completed_at=datetime.now(timezone.utc),
            )
