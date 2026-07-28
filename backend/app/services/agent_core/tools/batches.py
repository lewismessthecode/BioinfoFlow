from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_core import AgentToolCallBatchStatus
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentToolCallBatchRepository,
)
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.tools.toolsets import decode_provider_tool_name


class ToolCallBatchCoordinator:
    """Persisted source of truth for one assistant tool-call barrier."""

    def __init__(self, session: AsyncSession):
        self.actions = AgentActionRepository(session)
        self.batches = AgentToolCallBatchRepository(session)
        self.ledger = AgentEventLedger(session)

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
            "batch_ordinal": await self.batches.reserve_next_ordinal(turn_id),
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
        errors: list[dict[str, Any]] | None = None,
        results: list[dict[str, Any]] | None = None,
        commit: bool = True,
    ) -> None:
        if errors is not None and len(errors) != len(tool_calls):
            raise ValueError("Preparation repair errors must match tool call count")
        if results is not None and len(results) != len(tool_calls):
            raise ValueError("Preparation repair results must match tool call count")
        existing = {
            action.tool_call_ordinal: action
            for action in await self.actions.list_for_batch(batch_id)
        }
        for ordinal, tool_call in enumerate(tool_calls):
            action_error = (
                errors[ordinal]
                if errors is not None
                else {"type": error_type, "message": error_message}
            )
            action_result = results[ordinal] if results is not None else None
            canonical_name = decode_provider_tool_name(
                str(tool_call.get("name") or "unknown")
            )
            action = existing.get(ordinal)
            created = action is None
            if action is None:
                action = await self.actions.add(
                    session_id=session_id,
                    turn_id=turn_id,
                    tool_batch_id=batch_id,
                    tool_call_ordinal=ordinal,
                    tool_call_id=tool_call.get("id"),
                    kind="tool",
                    name=canonical_name,
                    input=tool_call.get("arguments") or {},
                    normalized_input=tool_call.get("arguments") or {},
                    risk_level="act_high",
                    status=action_status,
                    result=action_result,
                    error=action_error,
                    completed_at=datetime.now(timezone.utc),
                )
            elif action.status not in {"completed", "failed", "cancelled", "rejected"}:
                await self.actions.update_all_pending(
                    action,
                    status=action_status,
                    requires_resume=False,
                    result=action_result,
                    error=action_error,
                    completed_at=datetime.now(timezone.utc),
                )
            else:
                continue
            if created:
                await self.ledger.append(
                    session_id=session_id,
                    turn_id=turn_id,
                    type=AgentEventType.ACTION_REQUESTED,
                    payload={
                        "action_id": str(action.id),
                        "kind": "tool",
                        "name": canonical_name,
                        "evaluated_policy_version": getattr(
                            action, "evaluated_policy_version", None
                        ),
                    },
                    commit=False,
                )
            await self.ledger.append(
                session_id=session_id,
                turn_id=turn_id,
                type=(
                    AgentEventType.ACTION_CANCELLED
                    if action_status == "cancelled"
                    else AgentEventType.ACTION_FAILED
                ),
                payload={"action_id": str(action.id), "error": action_error},
                commit=False,
            )
        if commit:
            await self.batches.session.commit()
