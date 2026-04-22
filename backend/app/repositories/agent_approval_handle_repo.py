from __future__ import annotations

from sqlalchemy import desc, select

from app.models.agent_approval_handle import AgentApprovalHandle
from app.repositories.base import BaseRepository


class AgentApprovalHandleRepository(BaseRepository[AgentApprovalHandle]):
    model = AgentApprovalHandle

    async def get_latest_for_call(
        self, response_id: str, call_id: str
    ) -> AgentApprovalHandle | None:
        stmt = (
            select(self.model)
            .where(self.model.response_id == response_id)
            .where(self.model.call_id == call_id)
            .order_by(desc(self.model.created_at), desc(self.model.id))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_conversation(
        self,
        conversation_id: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ):
        return await self.list(
            limit=limit,
            cursor=cursor,
            filters={"conversation_id": conversation_id},
        )

    async def get_pending_for_conversation(
        self, conversation_id: str
    ) -> list[AgentApprovalHandle]:
        stmt = (
            select(self.model)
            .where(self.model.conversation_id == conversation_id)
            .where(self.model.status == "pending")
            .order_by(desc(self.model.created_at), desc(self.model.id))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_conversation(self, conversation_id: str) -> list[AgentApprovalHandle]:
        stmt = (
            select(self.model)
            .where(self.model.conversation_id == conversation_id)
            .order_by(self.model.created_at, self.model.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
