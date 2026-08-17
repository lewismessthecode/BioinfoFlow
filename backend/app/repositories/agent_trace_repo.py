from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_trace import AgentModelTrace


class AgentModelTraceRepository:
    def __init__(self, session: AsyncSession):
        self.db = session

    async def start(
        self,
        *,
        session_id: str,
        run_id: str,
        iteration: int,
        attempt: int,
        context_through_sequence: int,
        provider: str,
        model: str,
        wire_protocol: str,
        context_snapshot: dict[str, Any],
    ) -> AgentModelTrace:
        trace = AgentModelTrace(
            session_id=session_id,
            run_id=run_id,
            iteration=iteration,
            attempt=attempt,
            context_through_sequence=context_through_sequence,
            provider=provider,
            model=model,
            wire_protocol=wire_protocol,
            schema_version=1,
            status="pending",
            context_snapshot=context_snapshot,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(trace)
        await self.db.commit()
        await self.db.refresh(trace)
        return trace

    async def record_request(
        self,
        trace_id: str,
        request_payload: dict | list,
        *,
        prepared_at: datetime | None = None,
    ) -> AgentModelTrace:
        trace = await self._required(trace_id)
        trace.request_payload = request_payload
        trace.request_prepared_at = prepared_at or datetime.now(timezone.utc)
        trace.status = "running"
        await self.db.commit()
        await self.db.refresh(trace)
        return trace

    async def record_first_byte(
        self,
        trace_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> AgentModelTrace:
        trace = await self._required(trace_id)
        if trace.first_byte_at is None:
            trace.first_byte_at = occurred_at or datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(trace)
        return trace

    async def complete(
        self,
        trace_id: str,
        *,
        response_payload: dict | list | None,
        usage: dict[str, Any] | None,
        provider_response_id: str | None,
        finish_reason: str | None,
        completed_at: datetime | None = None,
    ) -> AgentModelTrace:
        trace = await self._required(trace_id)
        trace.response_payload = response_payload
        trace.usage = usage
        trace.provider_response_id = provider_response_id
        trace.finish_reason = finish_reason
        trace.status = "completed"
        trace.completed_at = completed_at or datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(trace)
        return trace

    async def record_response(
        self, trace_id: str, response_payload: dict | list
    ) -> AgentModelTrace:
        trace = await self._required(trace_id)
        trace.response_payload = response_payload
        await self.db.commit()
        await self.db.refresh(trace)
        return trace

    async def fail(
        self,
        trace_id: str,
        *,
        error: dict[str, Any],
        response_payload: dict | list | None = None,
        completed_at: datetime | None = None,
    ) -> AgentModelTrace:
        trace = await self._required(trace_id)
        trace.response_payload = response_payload
        trace.error = error
        trace.status = "failed"
        trace.completed_at = completed_at or datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(trace)
        return trace

    async def get(
        self, trace_id: str, *, session_id: str | None = None
    ) -> AgentModelTrace | None:
        statement = select(AgentModelTrace).where(AgentModelTrace.id == trace_id)
        if session_id is not None:
            statement = statement.where(AgentModelTrace.session_id == session_id)
        return await self.db.scalar(statement)

    async def list_for_session(self, session_id: str) -> list[AgentModelTrace]:
        result = await self.db.execute(
            select(AgentModelTrace)
            .where(AgentModelTrace.session_id == session_id)
            .order_by(
                AgentModelTrace.started_at,
                AgentModelTrace.created_at,
                AgentModelTrace.id,
            )
        )
        return list(result.scalars().all())

    async def _required(self, trace_id: str) -> AgentModelTrace:
        trace = await self.db.get(AgentModelTrace, trace_id)
        if trace is None:
            raise LookupError(f"agent model trace not found: {trace_id}")
        return trace


__all__ = ["AgentModelTraceRepository"]
