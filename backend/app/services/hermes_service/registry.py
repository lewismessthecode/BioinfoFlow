from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class RunningHermesResponse:
    response_id: str
    conversation_id: str
    project_id: str
    task: asyncio.Task | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_event_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cancelled: bool = False


class HermesResponseRegistry:
    _instance: "HermesResponseRegistry | None" = None
    _running: dict[str, RunningHermesResponse]
    _conversation_index: dict[str, str]
    _lock: asyncio.Lock | None
    _lock_loop: asyncio.AbstractEventLoop | None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._running = {}
            cls._instance._conversation_index = {}
            cls._instance._lock = None
            cls._instance._lock_loop = None
        return cls._instance

    def _get_lock(self) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    async def register(self, response_id: str, conversation_id: str, project_id: str) -> None:
        async with self._get_lock():
            self._running[response_id] = RunningHermesResponse(
                response_id=response_id,
                conversation_id=conversation_id,
                project_id=project_id,
            )
            self._conversation_index[conversation_id] = response_id

    async def set_task(self, response_id: str, task: asyncio.Task) -> None:
        async with self._get_lock():
            if response_id in self._running:
                self._running[response_id].task = task

    async def touch(self, response_id: str) -> None:
        async with self._get_lock():
            if response_id in self._running:
                self._running[response_id].last_event_at = datetime.now(timezone.utc)

    async def get(self, response_id: str) -> RunningHermesResponse | None:
        async with self._get_lock():
            return self._running.get(response_id)

    async def get_for_conversation(self, conversation_id: str) -> RunningHermesResponse | None:
        async with self._get_lock():
            response_id = self._conversation_index.get(conversation_id)
            if response_id is None:
                return None
            return self._running.get(response_id)

    async def cancel(self, response_id: str) -> bool:
        async with self._get_lock():
            entry = self._running.get(response_id)
            if not entry:
                return False
            entry.cancelled = True
            if entry.task and not entry.task.done():
                entry.task.cancel()
            return True

    async def unregister(self, response_id: str) -> None:
        async with self._get_lock():
            entry = self._running.pop(response_id, None)
            if entry and self._conversation_index.get(entry.conversation_id) == response_id:
                self._conversation_index.pop(entry.conversation_id, None)


hermes_response_registry = HermesResponseRegistry()
