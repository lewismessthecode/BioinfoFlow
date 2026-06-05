from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_core import AgentTurnStatus
from app.repositories.agent_core_repo import AgentTurnRepository
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger


class AgentCoreRuntime:
    def __init__(self, session: AsyncSession):
        self.turn_repo = AgentTurnRepository(session)
        self.ledger = AgentEventLedger(session)

    async def run_no_tool_turn(self, turn_id: str):
        turn = await self.turn_repo.get(turn_id)
        if turn is None:
            return None

        now = datetime.now(timezone.utc)
        turn = await self.turn_repo.update_all(
            turn,
            status=AgentTurnStatus.RUNNING,
            started_at=now,
        )
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_STARTED,
            payload={},
        )
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.ASSISTANT_THINKING_SUMMARY,
            payload={
                "summary": (
                    "AgentCore accepted the turn and recorded it in the event "
                    "ledger. Tool execution and model routing are enabled in "
                    "later phases."
                )
            },
        )
        final_text = (
            "AgentCore session is active. I recorded your request and the "
            "new event ledger is ready for model routing and tool execution."
        )
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.ASSISTANT_TEXT_COMPLETED,
            payload={"text": final_text},
        )
        completed_at = datetime.now(timezone.utc)
        turn = await self.turn_repo.update_all(
            turn,
            status=AgentTurnStatus.COMPLETED,
            final_text=final_text,
            completed_at=completed_at,
        )
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_COMPLETED,
            payload={"final_text": final_text},
        )
        return turn
