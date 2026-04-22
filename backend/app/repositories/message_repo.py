from __future__ import annotations

from sqlalchemy import case, select

from app.models.message import Message, MessageRole
from app.repositories.base import BaseRepository
from app.schemas.common import Pagination


class MessageRepository(BaseRepository[Message]):
    model = Message

    async def list(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        conversation_id: str | None = None,
    ) -> tuple[list[Message], Pagination]:
        filters = {"conversation_id": conversation_id}
        return await super().list(limit=limit, cursor=cursor, filters=filters)

    async def get_conversation_messages(self, conversation_id: str) -> list[Message]:
        stmt = (
            select(self.model)
            .where(self.model.conversation_id == conversation_id)
            .order_by(
                self.model.created_at,
                case((self.model.role == MessageRole.USER.value, 0), else_=1),
                self.model.id,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
