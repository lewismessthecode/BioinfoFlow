from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from app.services.agent_harness.contracts import (
    AgentEvent,
    SessionSnapshot,
    SnapshotEvent,
)


_SUBSCRIBER_QUEUE_CAPACITY = 256


class AgentEventHub:
    """Live event fan-out; durable truth always comes from the snapshot."""

    def __init__(self, *, liveness_interval_seconds: float = 15.0) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[AgentEvent]]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._liveness_interval_seconds = max(liveness_interval_seconds, 0.01)

    async def publish(self, session_id: str | UUID, event: AgentEvent) -> None:
        key = str(session_id)
        async with self._lock:
            subscribers = self._subscribers.get(key)
            if subscribers is None:
                return
            for queue in tuple(subscribers):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    subscribers.discard(queue)
                    _close_queue(queue)
            if not subscribers:
                self._subscribers.pop(key, None)

    async def stream(
        self,
        session_id: str | UUID,
        snapshot: Callable[[], Awaitable[SessionSnapshot]],
        exists: Callable[[], Awaitable[bool]] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        key = str(session_id)
        queue: asyncio.Queue[AgentEvent | _StreamClosed] = asyncio.Queue(
            maxsize=_SUBSCRIBER_QUEUE_CAPACITY
        )
        async with self._lock:
            self._subscribers[key].add(queue)
        try:
            yield SnapshotEvent(snapshot=await snapshot())
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=self._liveness_interval_seconds,
                    )
                except TimeoutError:
                    if exists is not None and not await exists():
                        return
                    continue
                if isinstance(event, _StreamClosed):
                    return
                yield event
        finally:
            async with self._lock:
                subscribers = self._subscribers.get(key)
                if subscribers is not None:
                    subscribers.discard(queue)
                    if not subscribers:
                        self._subscribers.pop(key, None)

    async def close(self) -> None:
        async with self._lock:
            queues = [
                queue for queues in self._subscribers.values() for queue in queues
            ]
            self._subscribers.clear()
        for queue in queues:
            _close_queue(queue)

    async def close_session(self, session_id: str | UUID) -> None:
        """End live streams for one deleted session without closing the hub."""

        async with self._lock:
            queues = tuple(self._subscribers.pop(str(session_id), ()))
        for queue in queues:
            _close_queue(queue)


@dataclass(frozen=True)
class _StreamClosed:
    pass


_STREAM_CLOSED = _StreamClosed()


def _close_queue(queue: asyncio.Queue[AgentEvent | _StreamClosed]) -> None:
    while True:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    queue.put_nowait(_STREAM_CLOSED)


__all__ = ["AgentEventHub"]
