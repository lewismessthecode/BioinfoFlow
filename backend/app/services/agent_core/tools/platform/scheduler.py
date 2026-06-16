from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.scheduler.scheduler import DEFAULT_STATE_COUNTS
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.run_dispatch import get_run_scheduler


class SchedulerStatusTool:
    spec = AgentToolSpec(
        name="scheduler.status",
        description="Read the persistent workflow scheduler status.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={
            "type": "object",
            "properties": {"status": {"type": "object"}},
            "required": ["status"],
        },
        risk_level="read",
        read_scope=["scheduler", "runs"],
        audit="Read scheduler status.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        scheduler = get_run_scheduler()
        if scheduler is None:
            return {
                "status": {
                    "mode": "persistent",
                    "effective_mode": "persistent",
                    "scheduler_available": False,
                    "resource_monitoring_enabled": False,
                    "workers": 0,
                    "queue_depth": 0,
                    "states": DEFAULT_STATE_COUNTS,
                    "total_slots": 0,
                    "used_slots": 0,
                    "available_slots": 0,
                    "active_runs": [],
                }
            }
        return {
            "status": {
                "mode": "persistent",
                "effective_mode": "persistent",
                "scheduler_available": True,
                **await scheduler.get_status(),
            }
        }


class SchedulerResourcesTool:
    spec = AgentToolSpec(
        name="scheduler.resources",
        description="Read the latest scheduler host resource snapshot.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={
            "type": "object",
            "properties": {"resources": {"type": "object"}},
            "required": ["resources"],
        },
        risk_level="read",
        read_scope=["scheduler"],
        audit="Read scheduler resources.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        scheduler = get_run_scheduler()
        snapshot = scheduler.get_resource_snapshot() if scheduler is not None else None
        return {"resources": _resource_payload(snapshot)}


def _resource_payload(snapshot) -> dict[str, object]:
    if snapshot is None:
        return {
            "enabled": False,
            "sampled_at": None,
            "cpu": {"total": None, "available": None},
            "memory": {"total_gb": None, "available_gb": None},
            "disk": {"total_gb": None, "available_gb": None},
            "gpu": {"count": 0, "memory_gb": 0.0},
        }

    sampled_at = snapshot.sampled_at
    if isinstance(sampled_at, datetime):
        sampled_at = sampled_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "enabled": True,
        "sampled_at": sampled_at,
        "cpu": {"total": snapshot.cpu_count, "available": snapshot.cpu_available},
        "memory": {
            "total_gb": snapshot.memory_total_gb,
            "available_gb": snapshot.memory_available_gb,
        },
        "disk": {
            "total_gb": snapshot.disk_total_gb,
            "available_gb": snapshot.disk_available_gb,
        },
        "gpu": {"count": snapshot.gpu_count, "memory_gb": snapshot.gpu_memory_gb},
    }
