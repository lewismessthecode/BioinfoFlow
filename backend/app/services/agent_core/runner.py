from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import app.database as app_database
from app.services.agent_core.runtime import AgentCoreRuntime
from app.utils.logging import get_logger


logger = get_logger(__name__)
_RUNNING_TURNS: dict[str, asyncio.Task] = {}
_PENDING_TURN_TASK_FACTORIES: dict[
    str, tuple[str | None, Callable[[], Awaitable[object]]]
] = {}


def enqueue_turn_run(turn_id: str, session_id: str | None = None) -> None:
    _register_turn_task(turn_id, session_id, lambda: run_turn_once(turn_id))


def enqueue_turn_resume(
    action_id: str, turn_id: str, session_id: str | None = None
) -> None:
    _register_turn_task(turn_id, session_id, lambda: resume_turn_once(action_id))


def cancel_turn_run(turn_id: str) -> bool:
    task = _RUNNING_TURNS.get(turn_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True


def is_turn_running(turn_id: str) -> bool:
    task = _RUNNING_TURNS.get(turn_id)
    return bool(task is not None and not task.done())


async def run_turn_once(turn_id: str):
    async with app_database.async_session_maker() as session:
        return await AgentCoreRuntime(session).run_turn(turn_id)


async def resume_turn_once(action_id: str):
    async with app_database.async_session_maker() as session:
        return await AgentCoreRuntime(session).resume_turn_after_action(action_id)


def _register_turn_task(
    turn_id: str,
    session_id: str | None,
    task_factory: Callable[[], Awaitable[object]],
) -> None:
    existing = _RUNNING_TURNS.get(turn_id)
    if existing is not None and not existing.done():
        _PENDING_TURN_TASK_FACTORIES[turn_id] = (session_id, task_factory)
        return
    _start_turn_task(turn_id, session_id, task_factory)


def _start_turn_task(
    turn_id: str,
    session_id: str | None,
    task_factory: Callable[[], Awaitable[object]],
) -> None:
    task = asyncio.create_task(task_factory())
    _RUNNING_TURNS[turn_id] = task
    task.add_done_callback(_build_done_callback(turn_id, session_id))


def _build_done_callback(
    turn_id: str, session_id: str | None
) -> Callable[[asyncio.Task], None]:
    def _done(task: asyncio.Task) -> None:
        current = _RUNNING_TURNS.get(turn_id)
        if current is task:
            _RUNNING_TURNS.pop(turn_id, None)
        _log_task_result(turn_id, session_id, task)
        pending = _PENDING_TURN_TASK_FACTORIES.pop(turn_id, None)
        if pending is not None:
            pending_session_id, pending_factory = pending
            _start_turn_task(turn_id, pending_session_id, pending_factory)

    return _done


def _log_task_result(turn_id: str, session_id: str | None, task: asyncio.Task) -> None:
    fields = {"turn_id": turn_id}
    if session_id:
        fields["session_id"] = session_id
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        logger.info("agent_core.runner.cancelled", **fields)
        return
    if exc is not None:
        logger.error(
            "agent_core.runner.failed",
            **fields,
            exception_type=type(exc).__name__,
        )
        return
    logger.info("agent_core.runner.completed", **fields)
