from __future__ import annotations

from datetime import datetime
from typing import Any

from app.repositories.agent_trace_repo import AgentModelTraceRepository
from app.services.model_runtime.exchange import ModelExchangeObserver


class ModelExchangeRecorder(ModelExchangeObserver):
    """Persist model exchanges without coupling the Model Gateway to the Harness."""

    def __init__(self, repository: AgentModelTraceRepository):
        self.repository = repository

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
    ) -> str:
        trace = await self.repository.start(
            session_id=session_id,
            run_id=run_id,
            iteration=iteration,
            attempt=attempt,
            context_through_sequence=context_through_sequence,
            provider=provider,
            model=model,
            wire_protocol=wire_protocol,
            context_snapshot=context_snapshot,
        )
        return str(trace.id)

    async def request_prepared(
        self,
        exchange_id: str,
        payload: dict | list,
        *,
        prepared_at: datetime,
    ) -> None:
        await self.repository.record_request(
            exchange_id,
            payload,
            prepared_at=prepared_at,
        )

    async def first_byte_received(
        self,
        exchange_id: str,
        *,
        occurred_at: datetime,
    ) -> None:
        await self.repository.record_first_byte(
            exchange_id,
            occurred_at=occurred_at,
        )

    async def response_received(self, exchange_id: str, payload: dict | list) -> None:
        await self.repository.record_response(exchange_id, payload)

    async def complete(
        self,
        exchange_id: str,
        *,
        usage: dict[str, Any] | None,
        provider_response_id: str | None,
        finish_reason: str | None,
    ) -> None:
        trace = await self.repository.get(exchange_id)
        if trace is None:
            return
        await self.repository.complete(
            exchange_id,
            response_payload=trace.response_payload,
            usage=usage,
            provider_response_id=provider_response_id,
            finish_reason=finish_reason,
        )

    async def fail(
        self,
        exchange_id: str,
        *,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        trace = await self.repository.get(exchange_id)
        if trace is None:
            return
        await self.repository.fail(
            exchange_id,
            error={"code": code, "message": message, **(details or {})},
            response_payload=trace.response_payload,
        )

    async def recover_after_failure(self) -> None:
        await self.repository.db.rollback()


__all__ = ["ModelExchangeRecorder"]
