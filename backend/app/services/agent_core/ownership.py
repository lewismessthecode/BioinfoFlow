from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.repositories.agent_core_repo import AgentTurnRepository


class TurnOwnershipLostError(RuntimeError):
    """The durable turn owner generation no longer belongs to this worker."""


def new_turn_owner_token() -> str:
    return str(uuid4())


class TurnOwnership:
    def __init__(
        self,
        *,
        bind: AsyncEngine,
        turn_id: str,
        owner_token: str,
        lease_duration: timedelta,
    ) -> None:
        self.turn_id = turn_id
        self.owner_token = owner_token
        self.lease_duration = lease_duration
        self._session_factory = async_sessionmaker(
            bind,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        self._lost = asyncio.Event()

    @property
    def lost(self) -> bool:
        return self._lost.is_set()

    async def ensure_current(self) -> None:
        if self._lost.is_set():
            raise TurnOwnershipLostError("Agent turn ownership was replaced")
        async with self._session_factory() as session:
            owned = await AgentTurnRepository(session).is_owned(
                self.turn_id,
                owner_token=self.owner_token,
            )
        if not owned:
            self._lost.set()
            raise TurnOwnershipLostError("Agent turn ownership was replaced")

    async def renew(self) -> None:
        if self._lost.is_set():
            raise TurnOwnershipLostError("Agent turn ownership was replaced")
        async with self._session_factory() as session:
            renewed = await AgentTurnRepository(session).renew_owned_lease(
                self.turn_id,
                owner_token=self.owner_token,
                lease_until=datetime.now(timezone.utc) + self.lease_duration,
            )
        if not renewed:
            self._lost.set()
            raise TurnOwnershipLostError("Agent turn ownership was replaced")

    @asynccontextmanager
    async def maintain(self):
        heartbeat = asyncio.create_task(self._heartbeat())
        try:
            yield self
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass

    async def _heartbeat(self) -> None:
        interval = max(min(self.lease_duration.total_seconds() / 3, 30.0), 0.1)
        while True:
            await asyncio.sleep(interval)
            try:
                await self.renew()
            except TurnOwnershipLostError:
                return


__all__ = [
    "TurnOwnership",
    "TurnOwnershipLostError",
    "new_turn_owner_token",
]
