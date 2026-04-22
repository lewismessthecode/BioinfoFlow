from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, select

from app.models.agent_response_handle import AgentResponseHandle, AgentResponseStatus
from app.repositories.base import BaseRepository


class AgentResponseHandleRepository(BaseRepository[AgentResponseHandle]):
    model = AgentResponseHandle

    async def get_latest_for_conversation(
        self, conversation_id: str
    ) -> AgentResponseHandle | None:
        stmt = (
            select(self.model)
            .where(self.model.conversation_id == conversation_id)
            .order_by(desc(self.model.created_at), desc(self.model.id))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_stale_in_flight(
        self, stale_before: datetime
    ) -> list[AgentResponseHandle]:
        """Return in-flight response handles whose updated_at predates the cutoff."""
        stmt = select(self.model).where(
            self.model.status.in_(
                [AgentResponseStatus.PENDING, AgentResponseStatus.RUNNING]
            ),
            self.model.updated_at < stale_before,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
