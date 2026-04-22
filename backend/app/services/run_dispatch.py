from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Protocol

import app.database as app_database
from app.repositories.run_repo import RunRepository
from app.schemas.run import RunStatus
from app.runtime.events import publish_run_status
from app.utils.logging import get_logger


logger = get_logger(__name__)

if TYPE_CHECKING:
    from app.scheduler.scheduler import RunScheduler


_run_dispatcher: "RunDispatcher | None" = None
_run_scheduler: "RunScheduler | None" = None


class RunDispatcher(Protocol):
    def dispatch(self, run_id: str, *, priority: str = "normal") -> None:
        """Submit a run for execution."""

class SchedulerDispatcher:
    """Submit runs to the persistent RunScheduler."""

    def __init__(self, scheduler: "RunScheduler") -> None:
        self._scheduler = scheduler

    def dispatch(self, run_id: str, *, priority: str = "normal") -> None:
        task = asyncio.create_task(
            _enqueue_or_mark_failed(self._scheduler, run_id, priority=priority)
        )
        task.add_done_callback(_log_dispatch_result)


def get_run_dispatcher() -> RunDispatcher:
    if _run_dispatcher is None:
        raise RuntimeError("Run dispatcher is not configured")
    return _run_dispatcher


def set_run_dispatcher(dispatcher: RunDispatcher | None) -> None:
    global _run_dispatcher
    _run_dispatcher = dispatcher


def get_run_scheduler() -> "RunScheduler | None":
    return _run_scheduler


def set_run_scheduler(scheduler: "RunScheduler | None") -> None:
    global _run_scheduler
    _run_scheduler = scheduler


def _log_dispatch_result(task: asyncio.Task) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        exc = task.exception()
        if exc is not None:
            logger.exception("scheduler.dispatch.failed", error=str(exc))


async def _enqueue_or_mark_failed(
    scheduler: "RunScheduler",
    run_id: str,
    *,
    priority: str,
) -> None:
    try:
        await scheduler.enqueue(run_id, priority=priority)
    except Exception as exc:  # noqa: BLE001
        if await _run_is_terminal(run_id):
            logger.info("scheduler.dispatch.skipped_terminal", run_id=run_id)
            return
        await _mark_run_failed(run_id, str(exc))
        logger.exception("scheduler.dispatch.failed", run_id=run_id)


async def _mark_run_failed(run_id: str, message: str) -> None:
    async with app_database.async_session_maker() as session:
        repo = RunRepository(session)
        run = await repo.mark_failed(run_id, message)
        if run:
            await publish_run_status(run, message="Run failed")


async def _run_is_terminal(run_id: str) -> bool:
    async with app_database.async_session_maker() as session:
        run = await RunRepository(session).get_by_run_id(run_id)
        if run is None:
            return False
        return run.status in {
            RunStatus.CANCELLED.value,
            RunStatus.COMPLETED.value,
            RunStatus.FAILED.value,
        }
