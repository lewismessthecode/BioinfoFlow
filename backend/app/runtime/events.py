from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.utils.logging import get_logger

logger = get_logger(__name__)

EVENT_QUEUE_MAXSIZE = 200


class EventBus:
    def __init__(self, max_queue_size: int = EVENT_QUEUE_MAXSIZE) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._queue_maxsize = max_queue_size

    async def subscribe(self, project_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._queue_maxsize)
        self._subscribers[project_id].add(queue)
        return queue

    def unsubscribe(self, project_id: str, queue: asyncio.Queue) -> None:
        self._subscribers.get(project_id, set()).discard(queue)

    async def publish(self, event: dict[str, Any]) -> None:
        project_id = event.get("project_id")
        if not project_id:
            return
        for queue in list(self._subscribers.get(project_id, set())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Log when we drop an event due to full queue
                logger.warning(
                    "events.queue_full",
                    project_id=project_id,
                    event_type=event.get("event"),
                    run_id=event.get("run_id"),
                )
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with suppress(asyncio.QueueFull):
                    queue.put_nowait(event)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_event(
    *,
    event: str,
    project_id: str,
    data: dict[str, Any] | None = None,
    conversation_id: str | None = None,
    run_id: str | None = None,
    image_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid4()),
        "event": event,
        "project_id": project_id,
        "timestamp": _utc_timestamp(),
        "data": data or {},
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id
    if run_id:
        payload["run_id"] = run_id
    if image_id:
        payload["image_id"] = image_id
    return payload


events = EventBus()


async def publish_event(
    *,
    event: str,
    project_id: str,
    data: dict[str, Any] | None = None,
    conversation_id: str | None = None,
    run_id: str | None = None,
    image_id: str | None = None,
) -> None:
    envelope = build_event(
        event=event,
        project_id=project_id,
        data=data,
        conversation_id=conversation_id,
        run_id=run_id,
        image_id=image_id,
    )
    await events.publish(envelope)


async def publish_run_status(run, message: str | None = None) -> None:
    data = {
        "run_id": run.run_id,
        "status": getattr(run.status, "value", run.status),
        "current_task": run.current_task,
        "tasks_completed": run.tasks_completed,
        "tasks_total": run.tasks_total,
    }
    if message:
        data["message"] = message
    await publish_event(
        event="run.status",
        project_id=str(run.project_id),
        data=data,
        run_id=run.run_id,
    )


async def publish_run_log(
    *,
    project_id: str,
    run_id: str,
    message: str,
    level: str = "info",
    task: str | None = None,
) -> None:
    data = {
        "run_id": run_id,
        "level": level,
        "message": message,
        "task": task,
        "timestamp": _utc_timestamp(),
    }
    await publish_event(
        event="run.log",
        project_id=project_id,
        data=data,
        run_id=run_id,
    )


async def publish_image_progress(
    *,
    project_id: str,
    image_id: str,
    progress: int | None,
    status: str,
) -> None:
    data = {
        "image_id": image_id,
        "progress": progress,
        "status": status,
    }
    await publish_event(
        event="image.progress",
        project_id=project_id,
        data=data,
        image_id=image_id,
    )


async def publish_run_dag(run) -> None:
    """Publish DAG update event for a run.

    Args:
        run: Run model instance with config containing dag data
    """
    dag = {"nodes": [], "edges": []}
    if isinstance(run.config, dict):
        dag = run.config.get("dag", dag)
    await publish_event(
        event="run.dag",
        project_id=str(run.project_id),
        data={"run_id": run.run_id, "dag": dag},
        run_id=run.run_id,
    )


# ========== Agent approval events ==========


async def publish_approval_requested(
    *,
    project_id: str,
    conversation_id: str,
    approval_id: str,
    step_id: str,
    approval_type: str,
    tool: str,
    description: str,
    risk: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Publish an event when an approval is requested.

    Args:
        project_id: Project ID
        conversation_id: Conversation ID
        approval_id: Approval ID
        step_id: Plan step ID
        approval_type: Type of approval (run, file_diff, code_exec)
        tool: Tool name that requires approval
        description: Human-readable description of the step
        risk: Risk level of the tool
        payload: Additional context data
    """
    data = {
        "approval_id": approval_id,
        "step_id": step_id,
        "approval_type": approval_type,
        "tool": tool,
        "description": description,
        "risk": risk,
        "payload": payload or {},
    }
    await publish_event(
        event="agent.approval.requested",
        project_id=project_id,
        conversation_id=conversation_id,
        data=data,
    )


async def publish_approval_resolved(
    *,
    project_id: str,
    conversation_id: str,
    approval_id: str,
    step_id: str,
    status: str,
    resolved_by: str | None = None,
) -> None:
    """Publish an event when an approval is resolved.

    Args:
        project_id: Project ID
        conversation_id: Conversation ID
        approval_id: Approval ID
        step_id: Plan step ID
        status: Resolution status (approved, rejected)
        resolved_by: User or system that resolved
    """
    data = {
        "approval_id": approval_id,
        "step_id": step_id,
        "status": status,
        "resolved_by": resolved_by,
    }
    await publish_event(
        event="agent.approval.resolved",
        project_id=project_id,
        conversation_id=conversation_id,
        data=data,
    )
