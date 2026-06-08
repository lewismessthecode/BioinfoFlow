from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_core import AgentMemoryStatus
from app.repositories.agent_core_repo import AgentMemoryRepository
from app.services.agent_core.context.system_prompt import default_system_prompt_snapshot
from app.services.agent_core.transcript import (
    AgentTranscriptStore,
    provider_message_from_parts,
)


class AgentContextAssembler:
    def __init__(self, session: AsyncSession):
        self.transcript = AgentTranscriptStore(session)
        self.memories = AgentMemoryRepository(session)

    async def provider_messages(self, *, agent_session, turn) -> list[dict]:
        snapshot = agent_session.prompt_snapshot or default_system_prompt_snapshot().as_dict()
        messages: list[dict[str, str]] = [
            {"role": "system", "content": str(snapshot.get("content") or "")}
        ]
        memory_context = await self._memory_context(agent_session)
        if memory_context:
            messages.append({"role": "system", "content": memory_context})
        for message in await self.transcript.list_messages(str(agent_session.id)):
            if message.status != "committed":
                continue
            if message.role not in {"user", "assistant", "tool"}:
                continue
            messages.append(
                provider_message_from_parts(
                    message.role,
                    message.content_parts or [],
                    getattr(message, "message_metadata", None),
                )
            )
        return [
            message
            for message in messages
            if message.get("content") or message.get("tool_calls")
        ]

    async def _memory_context(self, agent_session) -> str | None:
        memories = await self.memories.list_for_workspace(
            workspace_id=str(agent_session.workspace_id),
            project_id=str(agent_session.project_id) if agent_session.project_id else None,
            status=AgentMemoryStatus.ACCEPTED,
        )
        if not memories:
            return None
        lines = ["Accepted durable Bioinfoflow memory:"]
        for memory in memories[:20]:
            lines.append(f"- {memory.scope}/{memory.type}: {memory.content}")
        return "\n".join(lines)
