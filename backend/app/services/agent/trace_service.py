from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_trace_repo import AgentTraceRepository
from app.utils.exceptions import NotFoundError


class AgentTraceService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = AgentTraceRepository(session)

    async def list_trace(
        self,
        *,
        conversation_id: str,
        message_id: str | None = None,
        include_prompt: bool = False,
        limit: int = 200,
    ):
        if not conversation_id:
            raise NotFoundError("conversation not found")
        types = None
        if not include_prompt:
            types = ["agent.response", "agent.tool"]
        return await self.repo.list_by_conversation(
            conversation_id=conversation_id,
            message_id=message_id,
            types=types,
            limit=limit,
        )
