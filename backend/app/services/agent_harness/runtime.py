from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

import app.database as app_database
from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.services.agent_harness.contracts import (
    AgentCommand,
    AgentEvent,
    OpenSessionRequest,
    RunUpdatedEvent,
    SessionSnapshot,
    SnapshotEvent,
)
from app.services.agent_harness.events import AgentEventHub
from app.services.agent_harness.harness import AgentHarness
from app.services.agent_harness.projection import run_view
from app.utils.logging import get_logger


logger = get_logger(__name__)


HarnessFactory = Callable[..., AgentHarness]


class AgentRuntime:
    """Process-level owner of live Agent tasks, cancellation and event fan-out."""

    def __init__(
        self,
        session_factory: Callable[[], Any],
        *,
        harness_factory: HarnessFactory,
        cancel_poll_interval_seconds: float = 0.1,
        quiesce_timeout_seconds: float = 10.0,
    ) -> None:
        self._session_factory = session_factory
        self._harness_factory = harness_factory
        self.event_hub = AgentEventHub()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._finishing_runs: set[str] = set()
        self._cancellations: dict[str, asyncio.Event] = {}
        self._run_tokens: dict[str, str] = {}
        self._owner = f"process:{uuid4()}"
        self._cancel_poll_interval_seconds = max(cancel_poll_interval_seconds, 0.01)
        self._quiesce_timeout_seconds = max(quiesce_timeout_seconds, 0.01)
        self._shutting_down = False

    async def open_session(self, request: OpenSessionRequest) -> SessionSnapshot:
        async with self._session_factory() as db:
            return await self._harness(db).open_session(request)

    async def dispatch(self, session_id: str, command: AgentCommand) -> None:
        async with self._session_factory() as db:
            await self._harness(db).dispatch(session_id, command)

    async def snapshot(self, session_id: str) -> SessionSnapshot:
        async with self._session_factory() as db:
            return await self._harness(db).snapshot(session_id)

    async def publish_snapshot(
        self, session_id: str, snapshot: SessionSnapshot
    ) -> None:
        await self.event_hub.publish(session_id, SnapshotEvent(snapshot=snapshot))

    async def delete_session(self, session_id: str) -> None:
        async with self._session_factory() as db:
            await self._harness(db).delete_session(session_id)

    async def quiesce_session(self, session_id: str) -> None:
        """Stop and durably cancel active work before session files move."""

        async with self._session_factory() as db:
            harness = self._harness(db)
            current = await harness.repository.begin_session_closing(
                session_id,
                reason="session_deleted",
            )
            if harness.token_service is not None:
                await harness.token_service.revoke_session(session_id)
        if current is not None:
            run_id = str(current.id)
            cancellation = self._cancellations.get(run_id)
            if cancellation is not None:
                cancellation.set()
            task = self._tasks.get(run_id)
            if task is not None and not task.done():
                task.cancel()

        deadline = asyncio.get_running_loop().time() + self._quiesce_timeout_seconds
        while True:
            async with self._session_factory() as db:
                current = await AgentHarnessRepository(db).get_current_run(session_id)
                if current is None:
                    return
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(
                    "Agent session did not quiesce before the delete timeout"
                )
            await asyncio.sleep(min(self._cancel_poll_interval_seconds, remaining))

    def events(self, session_id: str) -> AsyncIterator[AgentEvent]:
        async def snapshot() -> SessionSnapshot:
            return await self.snapshot(session_id)

        return self.event_hub.stream(session_id, snapshot)

    async def recover(self) -> int:
        self._shutting_down = False
        async with self._session_factory() as db:
            return await self._harness(db).recover()

    async def shutdown(self) -> None:
        self._shutting_down = True
        scheduled = tuple(self._tasks.items())
        for run_id, task in scheduled:
            if run_id not in self._finishing_runs and not task.cancelling():
                task.cancel()
        if scheduled:
            await asyncio.gather(
                *(task for _, task in scheduled), return_exceptions=True
            )
        self._tasks.clear()
        self._finishing_runs.clear()
        self._cancellations.clear()
        self._run_tokens.clear()
        await self.event_hub.close()

    def _harness(self, db: AsyncSession) -> AgentHarness:
        return self._harness_factory(
            db,
            event_hub=self.event_hub,
            tasks=self._tasks,
            cancellations=self._cancellations,
            run_tokens=self._run_tokens,
            execution_scheduler=self._schedule,
            lease_owner=self._owner,
        )

    def _schedule(
        self,
        session_id: str,
        run_id: str,
        operation: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self._shutting_down:
            return
        existing = self._tasks.get(run_id)
        if existing is not None and not existing.done():
            if operation == "commands":
                cancellation = self._cancellations.get(run_id)
                if cancellation is not None and cancellation.is_set():
                    return

                def reschedule_commands(_completed: asyncio.Task[None]) -> None:
                    if self._shutting_down:
                        return
                    self._schedule(
                        session_id,
                        run_id,
                        operation,
                        payload,
                    )

                existing.add_done_callback(reschedule_commands)
            return

        async def execute() -> None:
            execution_task = asyncio.current_task()
            assert execution_task is not None
            cancellation = self._cancellations.setdefault(run_id, asyncio.Event())
            generation = await self._claim_when_available(run_id, cancellation)
            if generation is None:
                return
            heartbeat = asyncio.create_task(
                self._heartbeat(run_id, generation, cancellation),
                name=f"agent-lease:{run_id}",
            )
            cancel_watcher = asyncio.create_task(
                self._watch_persistent_cancellation(
                    run_id,
                    cancellation,
                    execution_task,
                ),
                name=f"agent-cancel-watch:{run_id}",
            )
            try:
                async with self._session_factory() as db:
                    harness = self._harness(db)
                    harness.bind_run_fence(
                        run_id,
                        owner=self._owner,
                        generation=generation,
                    )
                    try:
                        if operation == "run":
                            await harness.drive_run(session_id, run_id, claimed=True)
                        elif operation == "respond":
                            await harness.drive_response(
                                session_id, run_id, payload or {}, claimed=True
                            )
                        elif operation == "recover":
                            await harness.recover_run(run_id, claimed=True)
                        elif operation == "commands":
                            await harness.process_durable_commands(
                                session_id,
                                run_id,
                                claimed=True,
                            )
                        else:
                            raise ValueError(
                                f"unsupported Agent execution operation: {operation}"
                            )
                    except asyncio.CancelledError:
                        db.expire_all()
                        reason = await harness.repository.get_run_cancellation(run_id)
                        if reason is not None:
                            session = await harness.repository.get_session(session_id)
                            handled = bool(
                                session is not None
                                and session.status == "active"
                                and await harness.process_durable_commands(
                                    session_id,
                                    run_id,
                                    claimed=True,
                                )
                            )
                            if not handled:
                                await harness.repository.terminalize_run(
                                    run_id,
                                    status="cancelled",
                                    phase=None,
                                    termination_reason=reason,
                                )
                        raise
                    except Exception as exc:  # noqa: BLE001
                        await self._persist_runtime_failure(run_id, generation, exc)
                        logger.exception(
                            "agent_harness.task.failed",
                            session_id=session_id,
                            run_id=run_id,
                            operation=operation,
                            error=str(exc),
                        )
            finally:
                self._finishing_runs.add(run_id)
                try:
                    heartbeat.cancel()
                    cancel_watcher.cancel()
                    await asyncio.gather(
                        heartbeat,
                        cancel_watcher,
                        return_exceptions=True,
                    )
                    async with self._session_factory() as release_db:
                        await AgentHarnessRepository(release_db).release_run_lease(
                            run_id,
                            owner=self._owner,
                        )
                finally:
                    self._finishing_runs.discard(run_id)

        task = asyncio.create_task(execute(), name=f"agent-{operation}:{run_id}")
        self._tasks[run_id] = task

        def discard(completed: asyncio.Task[None]) -> None:
            if self._tasks.get(run_id) is completed:
                self._tasks.pop(run_id, None)
            if completed.cancelled():
                return
            error = completed.exception()
            if error is not None:
                logger.exception(
                    "agent_harness.task.unhandled",
                    run_id=run_id,
                    operation=operation,
                    error=str(error),
                )

        task.add_done_callback(discard)

    async def _persist_runtime_failure(
        self, run_id: str, generation: int, exc: Exception
    ) -> None:
        async with self._session_factory() as db:
            repository = AgentHarnessRepository(db)
            repository.bind_run_fence(run_id, owner=self._owner, generation=generation)
            run = await repository.get_run(run_id)
            if run is None or run.status in {"completed", "failed", "cancelled"}:
                return
            failed = await repository.update_run(
                run_id,
                status="failed",
                phase=None,
                termination_reason="runtime_failed",
                error={
                    "code": "runtime_failed",
                    "message": str(exc),
                    "type": type(exc).__name__,
                },
            )
            await self.event_hub.publish(
                str(failed.session_id),
                RunUpdatedEvent(run=run_view(failed)),
            )

    async def _claim_when_available(
        self, run_id: str, cancellation: asyncio.Event
    ) -> int | None:
        from app.config import settings

        lease_seconds = max(int(settings.agent_run_lease_seconds), 1)
        while not cancellation.is_set():
            async with self._session_factory() as db:
                repository = AgentHarnessRepository(db)
                generation = await repository.claim_run(
                    run_id,
                    owner=self._owner,
                    lease_expires_at=datetime.now(timezone.utc)
                    + timedelta(seconds=lease_seconds),
                )
                if generation is not None:
                    return generation
                run = await repository.get_run(run_id)
                if run is None or run.status in {"completed", "failed", "cancelled"}:
                    return None
                expires_at = run.lease_expires_at
            delay = 0.25
            if expires_at is not None:
                normalized = (
                    expires_at.replace(tzinfo=timezone.utc)
                    if expires_at.tzinfo is None
                    else expires_at
                )
                delay = max(
                    (normalized - datetime.now(timezone.utc)).total_seconds(), 0.25
                )
            try:
                await asyncio.wait_for(cancellation.wait(), timeout=min(delay, 30.0))
            except TimeoutError:
                pass
        return None

    async def _heartbeat(
        self, run_id: str, generation: int, cancellation: asyncio.Event
    ) -> None:
        from app.config import settings
        from app.repositories.agent_harness_repo import AgentHarnessRepository

        lease_seconds = max(int(settings.agent_run_lease_seconds), 1)
        interval = max(min(lease_seconds / 3, 30), 0.25)
        while not cancellation.is_set():
            await asyncio.sleep(interval)
            async with self._session_factory() as db:
                renewed = await AgentHarnessRepository(db).renew_run_lease(
                    run_id,
                    owner=self._owner,
                    generation=generation,
                    lease_expires_at=datetime.now(timezone.utc)
                    + timedelta(seconds=lease_seconds),
                )
            if not renewed:
                cancellation.set()
                return

    async def _watch_persistent_cancellation(
        self,
        run_id: str,
        cancellation: asyncio.Event,
        execution_task: asyncio.Task[None],
    ) -> None:
        while True:
            async with self._session_factory() as db:
                reason = await AgentHarnessRepository(db).get_run_cancellation(run_id)
            if reason is not None or cancellation.is_set():
                cancellation.set()
                done, _ = await asyncio.wait(
                    {execution_task},
                    timeout=self._cancel_poll_interval_seconds,
                )
                if execution_task not in done and not execution_task.cancelling():
                    execution_task.cancel()
                return
            try:
                await asyncio.wait_for(
                    cancellation.wait(),
                    timeout=self._cancel_poll_interval_seconds,
                )
            except TimeoutError:
                pass


def _database_session():
    return app_database.async_session_maker()


def _database_harness(db: AsyncSession, **runtime: Any) -> AgentHarness:
    from app.services.agent_harness.factory import harness_for_database

    return harness_for_database(db, **runtime)


agent_runtime = AgentRuntime(
    _database_session,
    harness_factory=_database_harness,
)


__all__ = ["AgentRuntime", "agent_runtime"]
