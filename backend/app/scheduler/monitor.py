from __future__ import annotations

import asyncio
import contextlib
import subprocess
from datetime import datetime, timezone

import psutil

from app.scheduler.resources import SystemResources
from app.utils.logging import get_logger


logger = get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ResourceMonitor:
    def __init__(
        self,
        sample_interval: float = 30.0,
        workspace_path: str = "/",
    ) -> None:
        self._interval = sample_interval
        self._workspace_path = workspace_path
        self._latest: SystemResources | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        try:
            self._latest = await self._sample()
        except Exception:  # noqa: BLE001
            logger.exception("scheduler.resource_monitor.start_sample_failed")
        self._task = asyncio.create_task(self._sample_loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    def current(self) -> SystemResources:
        if self._latest is None:
            self._latest = self._sample_sync()
        return self._latest

    async def _sample_loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                self._latest = await self._sample()
            except Exception:  # noqa: BLE001
                logger.exception("scheduler.resource_monitor.sample_failed")

    async def _sample(self) -> SystemResources:
        return await asyncio.to_thread(self._sample_sync)

    def _sample_sync(self) -> SystemResources:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(self._workspace_path)
        cpu_count = psutil.cpu_count(logical=True) or 1
        try:
            load_avg = psutil.getloadavg()[0]
        except (AttributeError, OSError):
            load_avg = 0.0
        cpu_available = max(0.0, float(cpu_count) - float(load_avg))
        gpu_count, gpu_memory_gb = self._detect_gpu()
        gib = 1024**3
        return SystemResources(
            cpu_count=cpu_count,
            cpu_available=round(cpu_available, 1),
            memory_total_gb=round(mem.total / gib, 1),
            memory_available_gb=round(mem.available / gib, 1),
            disk_total_gb=round(disk.total / gib, 1),
            disk_available_gb=round(disk.free / gib, 1),
            gpu_count=gpu_count,
            gpu_memory_gb=round(gpu_memory_gb, 1),
            sampled_at=_utc_now(),
        )

    def _detect_gpu(self) -> tuple[int, float]:
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.free",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return 0, 0.0
        if result.returncode != 0:
            return 0, 0.0
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            return 0, 0.0
        # nvidia-smi sometimes emits non-numeric rows like "N/A" when a
        # GPU is offline or a driver query fails. Skip those rather
        # than letting ValueError escape _sample_sync and stale out
        # the entire resource snapshot for sample_interval seconds.
        total_free_mb = 0.0
        parsed = 0
        for line in lines:
            try:
                total_free_mb += float(line)
                parsed += 1
            except ValueError:
                continue
        return parsed, total_free_mb / 1024.0
