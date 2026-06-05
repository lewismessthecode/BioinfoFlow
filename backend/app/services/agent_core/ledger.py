from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_core_repo import AgentEventRepository


class AgentEventLedger:
    def __init__(self, session: AsyncSession):
        self.event_repo = AgentEventRepository(session)

    async def append(
        self,
        *,
        session_id: str,
        turn_id: str,
        type: str,
        payload: dict | None = None,
        visibility: str = "user",
        schema_version: int = 1,
    ):
        seq = await self.event_repo.next_seq(turn_id)
        return await self.event_repo.create(
            session_id=session_id,
            turn_id=turn_id,
            seq=seq,
            type=type,
            payload=payload or {},
            visibility=visibility,
            schema_version=schema_version,
        )


__all__ = ["AgentEventLedger"]
