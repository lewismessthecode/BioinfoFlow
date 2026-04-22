"""Run orchestration tools for the agent.

Thin wrappers over the canonical run APIs. Submission goes through
``RunCompiler`` with the same ``{project_id, workflow_id, values, options}``
envelope as ``POST /runs``; read operations still use ``RunService``.

Risk levels:
* ``run_submit`` → ``act_high`` (triggers approval workflow)
* all others → ``read``
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.schemas.run import RunCreate, RunOptions
from app.services.agent.tools import register_tool
from app.services.agent.tools.base import BaseTool, RiskLevel, ToolResult
from app.services.run_compiler import (
    CompileError,
    RunCompiler,
    WorkflowNotEnabledError,
)
from app.services.run_service import RunService

@register_tool
class RunSubmitTool(BaseTool):
    """Submit a new workflow run using the v2 envelope."""

    name = "run_submit"
    description = (
        "Submit a new workflow run. Provide the workflow_id and a values dict "
        "keyed by form field ids (from GET /workflows/{id}/form-spec). "
        "Triggers approval because it starts real execution."
    )
    risk_level = RiskLevel.ACT_HIGH

    def get_schema(self) -> dict[str, Any]:
        return {
            "workflow_id": {
                "type": "string",
                "description": "Workflow UUID",
                "required": True,
            },
            "values": {
                "type": "object",
                "description": "Field id → value map matching the workflow's form-spec",
                "required": True,
            },
            "options": {
                "type": "object",
                "description": "Optional: profile, max_retries, timeout_seconds",
                "required": False,
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        workflow_id = kwargs.get("workflow_id")
        values = kwargs.get("values") or {}
        options = kwargs.get("options") or {}

        if not workflow_id or not isinstance(values, dict):
            return ToolResult(
                success=False,
                error="workflow_id and values (dict) are required",
            )

        try:
            payload = RunCreate(
                project_id=UUID(self.project_id),
                workflow_id=UUID(str(workflow_id)),
                values=values,
                options=RunOptions(**options) if options else None,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"invalid payload: {exc}")

        compiler = RunCompiler(self.session)
        try:
            run = await compiler.create_run(
                payload,
                user_id=self.user_id,
                workspace_id=self.workspace_id,
            )
        except FileNotFoundError as exc:
            return ToolResult(success=False, error=str(exc))
        except WorkflowNotEnabledError:
            return ToolResult(
                success=False,
                error="workflow not enabled for this project",
            )
        except CompileError as exc:
            return ToolResult(success=False, error=f"{exc.code}: {exc}")

        return ToolResult(
            success=True,
            data={
                "run_id": run.run_id,
                "status": getattr(run.status, "value", run.status),
            },
        )


@register_tool
class RunGetTool(BaseTool):
    """Fetch current status, current task, and structured error for a run."""

    name = "run_get"
    description = "Get a run's status, current task, and structured error (if any)."
    risk_level = RiskLevel.READ

    def get_schema(self) -> dict[str, Any]:
        return {
            "run_id": {"type": "string", "description": "Run ID", "required": True},
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        run_id = kwargs.get("run_id")
        if not run_id:
            return ToolResult(success=False, error="run_id is required")
        service = RunService(self.session)
        run = await service.get_run(str(run_id), user_id=None)
        if run is None:
            return ToolResult(success=False, error="run not found")
        return ToolResult(
            success=True,
            data={
                "run_id": run.run_id,
                "status": getattr(run.status, "value", run.status),
                "current_task": run.current_task,
                "tasks_total": run.tasks_total,
                "tasks_completed": run.tasks_completed,
                "error_message": run.error_message,
                "error": run.error_json,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            },
        )


@register_tool
class RunGetDagTool(BaseTool):
    """Get the live DAG snapshot for a run."""

    name = "run_get_dag"
    description = "Return the current DAG (nodes + edges) for a run."
    risk_level = RiskLevel.READ

    def get_schema(self) -> dict[str, Any]:
        return {
            "run_id": {"type": "string", "description": "Run ID", "required": True},
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        run_id = kwargs.get("run_id")
        if not run_id:
            return ToolResult(success=False, error="run_id is required")
        service = RunService(self.session)
        dag = await service.get_dag(str(run_id), user_id=None)
        return ToolResult(success=True, data=dag)


@register_tool
class RunGetResultsTool(BaseTool):
    """List output files produced by a completed run."""

    name = "run_get_results"
    description = "List output files (name, path, size, type) for a run."
    risk_level = RiskLevel.READ

    def get_schema(self) -> dict[str, Any]:
        return {
            "run_id": {"type": "string", "description": "Run ID", "required": True},
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        run_id = kwargs.get("run_id")
        if not run_id:
            return ToolResult(success=False, error="run_id is required")
        service = RunService(self.session)
        outputs = await service.list_outputs(str(run_id), user_id=None)
        return ToolResult(success=True, data=outputs)
