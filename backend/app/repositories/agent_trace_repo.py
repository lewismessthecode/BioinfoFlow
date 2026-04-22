from __future__ import annotations

from sqlalchemy import select

from app.models.agent_trace import AgentTrace
from app.repositories.base import BaseRepository


class AgentTraceRepository(BaseRepository[AgentTrace]):
    model = AgentTrace

    async def list_by_conversation(
        self,
        *,
        conversation_id: str,
        message_id: str | None = None,
        types: list[str] | None = None,
        limit: int = 200,
    ) -> list[AgentTrace]:
        stmt = select(self.model).where(self.model.conversation_id == conversation_id)
        if message_id:
            stmt = stmt.where(self.model.message_id == message_id)
        if types:
            stmt = stmt.where(self.model.type.in_(types))
        stmt = stmt.order_by(self.model.created_at, self.model.id)
        result = await self.session.execute(stmt.limit(limit))
        return list(result.scalars().all())
