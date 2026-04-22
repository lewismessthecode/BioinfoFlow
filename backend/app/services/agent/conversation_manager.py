"""Manages running agent conversations for cancellation support."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RunningConversation:
    """Tracks a running conversation."""

    conversation_id: str
    project_id: str
    task: asyncio.Task | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_event_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    assistant_message_id: str | None = None
    cancelled: bool = False


class ConversationManager:
    """Singleton manager for tracking and cancelling running conversations.

    All methods that read or write the ``_running`` dict acquire ``_lock``
    to prevent race conditions between concurrent async tasks.

    The lock is lazily created per-event-loop to avoid issues when pytest
    creates new event loops across test functions.
    """

    _instance: ConversationManager | None = None
    _running: dict[str, RunningConversation]
    _lock: asyncio.Lock | None
    _lock_loop: asyncio.AbstractEventLoop | None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._running = {}
            cls._instance._lock = None
            cls._instance._lock_loop = None
        return cls._instance

    def _get_lock(self) -> asyncio.Lock:
        """Return the lock, recreating it if the event loop changed."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    async def register(
        self,
        conversation_id: str,
        project_id: str,
        *,
        assistant_message_id: str | None = None,
    ) -> RunningConversation:
        """Register a conversation as running."""
        entry = RunningConversation(
            conversation_id=conversation_id,
            project_id=project_id,
            assistant_message_id=assistant_message_id,
        )
        async with self._get_lock():
            self._running[conversation_id] = entry
        logger.info("conversation.registered", conversation_id=conversation_id)
        return entry

    async def set_task(self, conversation_id: str, task: asyncio.Task) -> None:
        """Associate an asyncio task with a conversation."""
        async with self._get_lock():
            if conversation_id in self._running:
                self._running[conversation_id].task = task

    async def touch(
        self,
        conversation_id: str,
        *,
        assistant_message_id: str | None = None,
    ) -> None:
        """Record activity for a conversation and optionally update draft message ID."""
        async with self._get_lock():
            entry = self._running.get(conversation_id)
            if not entry:
                return
            entry.last_event_at = datetime.now(timezone.utc)
            if assistant_message_id:
                entry.assistant_message_id = assistant_message_id

    async def get(self, conversation_id: str) -> RunningConversation | None:
        """Return the running conversation entry if present."""
        async with self._get_lock():
            return self._running.get(conversation_id)

    async def unregister(self, conversation_id: str) -> None:
        """Remove a conversation from tracking."""
        async with self._get_lock():
            if conversation_id in self._running:
                del self._running[conversation_id]
        logger.info("conversation.unregistered", conversation_id=conversation_id)

    async def is_running(self, conversation_id: str) -> bool:
        """Check if a conversation is currently running."""
        async with self._get_lock():
            return (
                conversation_id in self._running
                and not self._running[conversation_id].cancelled
            )

    async def is_cancelled(self, conversation_id: str) -> bool:
        """Check if a conversation has been cancelled."""
        async with self._get_lock():
            entry = self._running.get(conversation_id)
            return entry.cancelled if entry else False

    async def cancel(self, conversation_id: str) -> bool:
        """Cancel a running conversation."""
        async with self._get_lock():
            entry = self._running.get(conversation_id)
            if not entry:
                logger.warning(
                    "conversation.cancel_not_found", conversation_id=conversation_id
                )
                return False

            entry.cancelled = True
            if entry.task and not entry.task.done():
                entry.task.cancel()
                logger.info("conversation.cancelled", conversation_id=conversation_id)
                return True

        logger.info("conversation.cancel_no_task", conversation_id=conversation_id)
        return True

    async def get_running_count(self) -> int:
        """Get count of running conversations."""
        async with self._get_lock():
            return len(self._running)

    async def get_running_for_project(self, project_id: str) -> list[str]:
        """Get IDs of running conversations for a project."""
        async with self._get_lock():
            return [
                entry.conversation_id
                for entry in self._running.values()
                if entry.project_id == project_id and not entry.cancelled
            ]


# Singleton instance
conversation_manager = ConversationManager()
