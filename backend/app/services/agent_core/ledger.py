from __future__ import annotations

import asyncio

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_core_repo import AgentEventRepository
from app.services.agent_core.observability import agent_event_log_fields
from app.utils.logging import get_logger


_session_seq_locks: dict[str, asyncio.Lock] = {}
logger = get_logger(__name__)


class AgentEventLedger:
    def __init__(self, session: AsyncSession):
        self.event_repo = AgentEventRepository(session)

    async def append(
        self,
        *,
        session_id: str,
        turn_id: str | None,
        type: str,
        payload: dict | None = None,
        visibility: str = "user",
        schema_version: int = 1,
        commit: bool = True,
    ):
        lock = _session_seq_locks.setdefault(session_id, asyncio.Lock())
        for attempt in range(3):
            async with lock:
                seq = await self.event_repo.next_seq(session_id)
                try:
                    values = {
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "seq": seq,
                        "type": type,
                        "payload": payload or {},
                        "visibility": visibility,
                        "schema_version": schema_version,
                    }
                    if commit:
                        event = await self.event_repo.create(**values)
                    else:
                        # A savepoint lets a cross-process sequence collision
                        # retry without rolling back the caller's surrounding
                        # CAS/update transaction.
                        async with self.event_repo.session.begin_nested():
                            event = await self.event_repo.add(**values)
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
                    if commit:
                        await self.event_repo.session.rollback()
                    if attempt == 2:
                        raise
                    continue
        raise RuntimeError("Unable to allocate agent event sequence")


__all__ = ["AgentEventLedger"]
