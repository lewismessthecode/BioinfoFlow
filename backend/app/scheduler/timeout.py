from __future__ import annotations

import asyncio

import app.database as app_database
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.run import Run, RunStatus
from app.models.run_config import RunConfigHelper
from app.runtime.jobs import _duration_seconds, _now
from app.utils.logging import get_logger

DEFAULT_TIMEOUT_SECONDS = 24 * 60 * 60

logger = get_logger(__name__)


class TimeoutWatcher:
    def __init__(
        self,
        *,
        scheduler,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        check_interval: float = 60.0,
    ) -> None:
        self._scheduler = scheduler
        self._session_factory = session_factory or app_database.async_session_maker
        self._check_interval = check_interval
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _watch_loop(self) -> None:
        while self._running:
            try:
                await self._check_timeouts()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("timeout_watcher.check_error")
            await asyncio.sleep(self._check_interval)

    async def _check_timeouts(self) -> None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Run).where(
                    Run.status == RunStatus.RUNNING.value,
                    Run.started_at.is_not(None),
                )
            )
            running_runs = list(result.scalars().all())

        for run in running_runs:
            timeout = (
                RunConfigHelper(run.config).timeout_seconds or DEFAULT_TIMEOUT_SECONDS
            )
            elapsed = _duration_seconds(run.started_at, _now())
            if elapsed is None or elapsed <= timeout:
                continue
            # Route timeouts through handle_timeout so the retry policy
            # is honored. Scheduler.cancel() finalizes the run as
            # cancelled and never consults retry_policy, silently
            # defeating the user's retry-on-transient-failure intent.
            reason = f"Run exceeded timeout of {timeout} seconds"
            if hasattr(self._scheduler, "handle_timeout"):
                await self._scheduler.handle_timeout(run.run_id, reason=reason)
            else:
                await self._scheduler.cancel(run.run_id, reason=reason)
