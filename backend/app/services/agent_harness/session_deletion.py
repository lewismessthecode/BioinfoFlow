from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.services.agent_harness.assets import stage_agent_session_files_for_delete
from app.services.agent_harness.runtime import AgentRuntime, agent_runtime
from app.utils.exceptions import ConflictError, NotFoundError


@dataclass
class _SessionMutationLockEntry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


_session_mutation_locks: dict[str, _SessionMutationLockEntry] = {}


@asynccontextmanager
async def session_mutation_lock(session_id: str):
    entry = _session_mutation_locks.setdefault(session_id, _SessionMutationLockEntry())
    entry.users += 1
    try:
        async with entry.lock:
            yield
    finally:
        entry.users -= 1
        if entry.users == 0 and _session_mutation_locks.get(session_id) is entry:
            _session_mutation_locks.pop(session_id, None)


async def delete_agent_session(
    session_id: str,
    *,
    db: AsyncSession,
    runtime: AgentRuntime = agent_runtime,
) -> None:
    """Delete one session through the complete runtime and file lifecycle."""

    repository = AgentHarnessRepository(db)
    async with session_mutation_lock(session_id):
        db.expire_all()
        if await repository.get_session(session_id) is None:
            raise NotFoundError("Agent session not found")
        try:
            await runtime.quiesce_session(session_id)
        except TimeoutError as exc:
            raise ConflictError(
                "Agent session is still stopping; retry deletion later"
            ) from exc
        tombstone = stage_agent_session_files_for_delete(session_id)
        try:
            await runtime.delete_session(session_id)
        except Exception:
            await db.rollback()
            db.expire_all()
            if await repository.get_session(session_id) is None:
                tombstone.purge()
            else:
                tombstone.restore()
            raise
        tombstone.purge_deleted_session_files()


__all__ = ["delete_agent_session", "session_mutation_lock"]
