from __future__ import annotations

from typing import Any

from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.run_service import RunService


class ListRunsTool:
    spec = AgentToolSpec(
        name="runs.list",
        description="List workflow runs visible in the current workspace.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "workflow_id": {"type": "string"},
                "status": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "runs": {"type": "array"},
                "total_count": {"type": "integer"},
            },
            "required": ["runs", "total_count"],
        },
        risk_level="read",
        read_scope=["runs"],
        audit="List workflow runs.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        service = RunService(context.db)
        runs, pagination = await service.list_runs(
            limit=int(input.get("limit") or 20),
            project_id=input.get("project_id"),
            workflow_id=input.get("workflow_id"),
            status=input.get("status"),
            user_id=context.user_id,
            workspace_id=context.workspace_id,
        )
        return {
            "runs": [_run_payload(run) for run in runs],
            "total_count": pagination.total_count or 0,
        }


class GetRunLogsTool:
    spec = AgentToolSpec(
        name="runs.logs",
        description="Read a workflow run log tail.",
        input_schema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "tail": {"type": "integer", "minimum": 0, "maximum": 10000},
                "task": {"type": "string"},
            },
            "required": ["run_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"logs": {"type": "array"}},
            "required": ["logs"],
        },
        risk_level="read",
        read_scope=["runs", "logs"],
        audit="Read workflow run logs.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        service = RunService(context.db)
        return await service.get_logs(
            str(input["run_id"]),
            tail=int(input.get("tail", 100)),
            task=input.get("task"),
            user_id=context.user_id,
            workspace_id=context.workspace_id,
        )


def _run_payload(run) -> dict:
    return {
        "id": str(run.id),
        "run_id": run.run_id,
        "project_id": str(run.project_id),
        "workflow_id": str(run.workflow_id) if run.workflow_id else None,
        "status": _value(run.status),
        "samples_count": run.samples_count,
        "tasks_total": run.tasks_total,
        "tasks_completed": run.tasks_completed,
        "current_task": run.current_task,
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
