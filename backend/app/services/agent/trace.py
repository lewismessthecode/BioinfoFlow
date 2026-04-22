from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.repositories.agent_trace_repo import AgentTraceRepository


class AgentTraceRecorder:
    """Records agent traces with batched writes to avoid race conditions.

    Tool traces are queued during parallel execution and flushed
    at the end of the agent turn to avoid UNIQUE constraint failures.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        project_id: str,
        conversation_id: str,
        message_id: str | None = None,
    ) -> None:
        self.repo = AgentTraceRepository(session)
        self.project_id = project_id
        self.conversation_id = conversation_id
        self.message_id = message_id
        self._pending_traces: list[dict[str, Any]] = []

    async def record_prompt(self, payload: dict[str, Any]) -> None:
        """Record a prompt trace immediately (not batched)."""
        await self._record("agent.prompt", payload)

    async def record_response(self, payload: dict[str, Any]) -> None:
        """Record a response trace immediately (not batched)."""
        await self._record("agent.response", payload)

    def queue_tool(self, payload: dict[str, Any]) -> None:
        """Queue a tool trace for batched write (avoids race conditions)."""
        if not settings.agent_observability:
            return
        truncated = self._truncate_payload(payload)
        self._pending_traces.append(
            {
                "project_id": self.project_id,
                "conversation_id": self.conversation_id,
                "message_id": self.message_id,
                "type": "agent.tool",
                "payload": truncated,
            }
        )

    async def record_tool(self, payload: dict[str, Any]) -> None:
        """Queue a tool trace (backwards compatible, calls queue_tool)."""
        self.queue_tool(payload)

    async def flush(self) -> None:
        """Flush all pending traces to the database in a single batch."""
        if not self._pending_traces:
            return
        await self.repo.bulk_create(self._pending_traces)
        self._pending_traces.clear()

    async def _record(self, event_type: str, payload: dict[str, Any]) -> None:
        if not settings.agent_observability:
            return
        truncated = self._truncate_payload(payload)
        await self.repo.create(
            project_id=self.project_id,
            conversation_id=self.conversation_id,
            message_id=self.message_id,
            type=event_type,
            payload=truncated,
        )

    def _truncate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            raw = json.dumps(payload)
        except TypeError:
            raw = json.dumps({"payload": str(payload)})
        if len(raw) <= settings.agent_log_truncate_chars:
            return payload
        return {"truncated": True, "payload": raw[: settings.agent_log_truncate_chars]}
