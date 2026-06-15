from __future__ import annotations

from typing import Any

from app.schemas.run import RunCreate
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.run_compiler import RunCompiler
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


class SubmitRunTool:
    spec = AgentToolSpec(
        name="runs.submit",
        description=(
            "Launch a workflow run. Provide project_id, workflow_id, and values "
            "keyed by the workflow's form-spec field ids. Creates a queued run."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "workflow_id": {"type": "string"},
                "values": {"type": "object"},
                "options": {"type": "object"},
            },
            "required": ["project_id", "workflow_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"run": {"type": "object"}},
            "required": ["run"],
        },
        risk_level="act_high",
        read_scope=["runs", "projects", "workflows"],
        write_scope=["runs"],
        audit="Submit a workflow run.",
        rollback_hint="Cancel the run with runs.cancel if it was submitted in error.",
        artifact_policy={"type": "run"},
        timeout_seconds=120,
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        payload = RunCreate.model_validate(
            {
                "project_id": str(input["project_id"]),
                "workflow_id": str(input["workflow_id"]),
                "values": input.get("values") or {},
                "options": input.get("options"),
            }
        )
        run = await RunCompiler(context.db).create_run(
            payload,
            user_id=context.user_id,
            workspace_id=context.workspace_id,
        )
        return {"run": _run_payload(run)}


class CancelRunTool:
    spec = AgentToolSpec(
        name="runs.cancel",
        description="Cancel an in-flight or queued workflow run.",
        input_schema={
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"run": {"type": "object"}},
            "required": ["run"],
        },
        risk_level="act_high",
        read_scope=["runs"],
        write_scope=["runs"],
        audit="Cancel a workflow run.",
        rollback_hint="Retry the run with runs.retry if cancelled by mistake.",
        artifact_policy={"type": "run"},
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        run = await RunService(context.db).cancel_run(
            str(input["run_id"]),
            user_id=context.user_id,
            workspace_id=context.workspace_id,
        )
        return {"run": _run_payload(run)}


class RetryRunTool:
    spec = AgentToolSpec(
        name="runs.retry",
        description="Retry a failed or cancelled workflow run, creating a new run.",
        input_schema={
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"run": {"type": "object"}},
            "required": ["run"],
        },
        risk_level="act_high",
        read_scope=["runs"],
        write_scope=["runs"],
        audit="Retry a workflow run.",
        rollback_hint="Cancel the new run with runs.cancel if it was retried in error.",
        artifact_policy={"type": "run"},
        timeout_seconds=120,
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        run = await RunService(context.db).retry_run(
            str(input["run_id"]),
            user_id=context.user_id,
            workspace_id=context.workspace_id,
        )
        return {"run": _run_payload(run)}


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
