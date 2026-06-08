from __future__ import annotations

import asyncio
import contextlib

import app.database as app_database
from app.services.agent_core.runtime import AgentCoreRuntime
from app.utils.logging import get_logger


logger = get_logger(__name__)


def enqueue_turn_run(turn_id: str) -> None:
    task = asyncio.create_task(run_turn_once(turn_id))
    task.add_done_callback(_log_task_result)


def enqueue_turn_resume(action_id: str) -> None:
    task = asyncio.create_task(resume_turn_once(action_id))
    task.add_done_callback(_log_task_result)


async def run_turn_once(turn_id: str):
    async with app_database.async_session_maker() as session:
        return await AgentCoreRuntime(session).run_turn(turn_id)


async def resume_turn_once(action_id: str):
    async with app_database.async_session_maker() as session:
        return await AgentCoreRuntime(session).resume_turn_after_action(action_id)


def _log_task_result(task: asyncio.Task) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        exc = task.exception()
        if exc is not None:
            logger.exception("agent_core.runner.failed", error=str(exc))
