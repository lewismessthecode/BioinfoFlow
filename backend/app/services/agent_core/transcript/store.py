from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_core_repo import AgentMessageRepository
from app.services.agent_core.transcript.messages import text_part


class AgentTranscriptStore:
    def __init__(self, session: AsyncSession):
        self.messages = AgentMessageRepository(session)

    async def append_text(
        self,
        *,
        session_id: str,
        turn_id: str | None,
        role: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ):
        return await self.append_parts(
            session_id=session_id,
            turn_id=turn_id,
            role=role,
            parts=[text_part(text)],
            metadata=metadata,
        )

    async def append_parts(
        self,
        *,
        session_id: str,
        turn_id: str | None,
        role: str,
        parts: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
        status: str = "committed",
    ):
        ordering_index = await self.messages.next_ordering_index(session_id)
        return await self.messages.create(
            session_id=session_id,
            turn_id=turn_id,
            role=role,
            content_parts=parts,
            message_metadata=metadata,
            status=status,
            ordering_index=ordering_index,
        )

    async def list_messages(self, session_id: str):
        return await self.messages.list_for_session(session_id)
