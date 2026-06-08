from __future__ import annotations

import asyncio

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_core_repo import AgentEventRepository


_session_seq_locks: dict[str, asyncio.Lock] = {}


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
    ):
        lock = _session_seq_locks.setdefault(session_id, asyncio.Lock())
        for attempt in range(3):
            async with lock:
                seq = await self.event_repo.next_seq(session_id)
                try:
                    return await self.event_repo.create(
                        session_id=session_id,
                        turn_id=turn_id,
                        seq=seq,
                        type=type,
                        payload=payload or {},
                        visibility=visibility,
                        schema_version=schema_version,
                    )
                except IntegrityError:
                    await self.event_repo.session.rollback()
                    if attempt == 2:
                        raise
                    continue
        raise RuntimeError("Unable to allocate agent event sequence")


__all__ = ["AgentEventLedger"]
