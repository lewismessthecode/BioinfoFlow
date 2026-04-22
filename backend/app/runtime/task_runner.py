from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Awaitable, Callable

from app.utils.logging import get_logger

logger = get_logger(__name__)


class TaskRunner:
    def __init__(self, max_concurrency: int = 2) -> None:
        self.queue: (
            asyncio.Queue[tuple[Callable[..., Awaitable], tuple, dict]] | None
        ) = None
        self.max_concurrency = max_concurrency
        self._workers: list[asyncio.Task] = []
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self.queue = asyncio.Queue()
        self._started = True
        for _ in range(self.max_concurrency):
            self._workers.append(asyncio.create_task(self._worker()))

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        for worker in self._workers:
            with suppress(asyncio.CancelledError):
                await worker
        self._workers = []
        self._started = False
        self.queue = None

    def submit(self, func: Callable[..., Awaitable], *args, **kwargs) -> None:
        if self.queue is None:
            self.queue = asyncio.Queue()
        self.queue.put_nowait((func, args, kwargs))

    async def _worker(self) -> None:
        while True:
            if self.queue is None:
                await asyncio.sleep(0)
                continue
            func, args, kwargs = await self.queue.get()
            try:
                await func(*args, **kwargs)
            except Exception:
                logger.exception(
                    "task_runner.worker.error",
                    func=getattr(func, "__name__", str(func)),
                    args=args,
                )
            finally:
                self.queue.task_done()


task_runner = TaskRunner()
