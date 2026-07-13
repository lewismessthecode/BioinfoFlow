from __future__ import annotations

import asyncio

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_core_repo import AgentEventRepository, AgentSessionRepository
from app.services.agent_core.execution_target import (
    ExecutionTargetChangedError,
    execution_target_from_session,
    normalize_execution_target,
)
from app.services.agent_core.observability import agent_event_log_fields
from app.utils.logging import get_logger


_session_seq_locks: dict[str, asyncio.Lock] = {}
logger = get_logger(__name__)


class AgentEventLedger:
    def __init__(self, session: AsyncSession):
        self.event_repo = AgentEventRepository(session)
        self.session_repo = AgentSessionRepository(session)

    async def append(
        self,
        *,
        session_id: str,
        turn_id: str | None,
        type: str,
        payload: dict | None = None,
        visibility: str = "user",
        schema_version: int = 1,
        expected_execution_target=None,
    ):
        lock = _session_seq_locks.setdefault(session_id, asyncio.Lock())
        for attempt in range(3):
            async with lock:
                session = await self.session_repo.lock_for_update(session_id)
                if session is None:
                    raise RuntimeError("Agent session disappeared before event append")
                if expected_execution_target is not None and (
                    execution_target_from_session(session)
                    != normalize_execution_target(expected_execution_target)
                ):
                    await self.event_repo.session.rollback()
                    raise ExecutionTargetChangedError
                seq = await self.event_repo.next_seq(session_id)
                try:
                    event = await self.event_repo.create(
                        session_id=session_id,
                        turn_id=turn_id,
                        seq=seq,
                        type=type,
                        payload=payload or {},
                        visibility=visibility,
                        schema_version=schema_version,
                    )
                    logger.debug(
                        "agent_core.event.appended",
                        **agent_event_log_fields(
                            session_id=session_id,
                            turn_id=turn_id,
                            seq=seq,
                            event_type=type,
                            payload=payload,
                        ),
                    )
                    return event
                except IntegrityError:
                    await self.event_repo.session.rollback()
                    if attempt == 2:
                        raise
                    continue
        raise RuntimeError("Unable to allocate agent event sequence")


__all__ = ["AgentEventLedger"]
