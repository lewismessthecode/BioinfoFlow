from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class SchedulerConfig:
    total_slots: int = 0  # 0 = auto-detect (cpu_count or max_concurrency)
    max_workers: int = 0  # 0 = same as effective_total_slots
    max_concurrency: int = 4  # legacy: kept for backward compat
    max_queue_depth: int = 500
    poll_interval_seconds: float = 1.0
    stale_timeout_minutes: int = 30
    resource_check_enabled: bool = False
    resource_sample_interval: float = 30.0
    safety_cpu: int = 2
    safety_memory_gb: float = 2.0
    safety_disk_gb: float = 10.0
    resource_workspace_path: str = "/"
    worker_heartbeat_grace_seconds: int = 90

    def effective_total_slots(self) -> int:
        if self.total_slots > 0:
            return self.total_slots
        if self.max_concurrency > 0:
            return self.max_concurrency
        return os.cpu_count() or 4

    def effective_max_workers(self) -> int:
        if self.max_workers > 0:
            return self.max_workers
        return self.effective_total_slots()

    @classmethod
    def from_settings(cls, settings) -> "SchedulerConfig":
        # resource_workspace_path defaults to "/" only as a last resort;
        # point it at the actual projects root so disk-usage readings
        # reflect the volume real runs consume.
        workspace_path = "/"
        try:
            projects_root = getattr(settings, "projects_root", None)
            if projects_root is not None:
                workspace_path = str(projects_root)
        except Exception:
            workspace_path = "/"
        return cls(
            total_slots=getattr(settings, "scheduler_total_slots", 0),
            max_workers=getattr(settings, "scheduler_max_workers", 0),
            max_concurrency=settings.scheduler_max_concurrency,
            max_queue_depth=settings.scheduler_max_queue_depth,
            poll_interval_seconds=settings.scheduler_poll_interval,
            stale_timeout_minutes=settings.scheduler_stale_timeout_minutes,
            resource_check_enabled=settings.scheduler_resource_check_enabled,
            resource_sample_interval=settings.scheduler_resource_sample_interval,
            safety_cpu=settings.scheduler_safety_cpu,
            safety_memory_gb=settings.scheduler_safety_memory_gb,
            safety_disk_gb=settings.scheduler_safety_disk_gb,
            resource_workspace_path=workspace_path,
            worker_heartbeat_grace_seconds=settings.scheduler_worker_heartbeat_grace_seconds,
        )
