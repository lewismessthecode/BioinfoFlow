"""System resource snapshot for the /scheduler/resources display API.

The resource estimation, checking, and safety margin classes that
previously lived here have been removed in favor of slot-based
admission control (see slots.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SystemResources:
    cpu_count: int
    cpu_available: float
    memory_total_gb: float
    memory_available_gb: float
    disk_total_gb: float
    disk_available_gb: float
    gpu_count: int = 0
    gpu_memory_gb: float = 0.0
    sampled_at: datetime | str | None = None
