"""Platform tools — first-class adapters for Bioinfoflow CLI actions.

Every tool in this module wraps a backend service method directly. The agent
used to reach these operations by shelling out to `bif`, which forced us to
build a permission layer on top of string-parsed commands. That path is dead.

Design rules (s02-style: one loop, one dispatch map, handlers own their edges):

1. **One tool = one action.** Listing runs, showing a run, submitting a run
   are distinct tools — the LLM's dispatch is done at tool-name level.
2. **Risk is a class attribute.** READ tools auto-allow; ACT_HIGH tools always
   prompt. No per-invocation resolvers. What the tool *is* determines its risk,
   not what arguments it was called with.
3. **Auth scoping comes from the tool's own context.** `self.user_id` and
   `self.workspace_id` are threaded in by `BaseTool.__init__` and forwarded to
   every service call — the LLM never chooses the auth scope.
4. **Return structured data.** Use existing Pydantic schemas
   (`RunRead`/`WorkflowRead`/`ProjectRead`) so the LLM sees the same envelope
   the API already serves.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.repositories.workflow_repo import WorkflowRepository
from app.schemas.project import ProjectRead
from app.schemas.run import RunCreate, RunRead
from app.schemas.workflow import WorkflowRead
from app.services.agent.tools import register_tool
from app.services.agent.tools.base import BaseTool, RiskLevel, ToolResult
from app.services.project_service import ProjectService
from app.services.project_workflow_service import ProjectWorkflowService
from app.services.run_archive import RunArchiveService
from app.services.run_compiler import RunCompiler
from app.services.run_service import RunService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_run(run: Any) -> dict[str, Any]:
    return RunRead.model_validate(run, from_attributes=True).model_dump(
        mode="json", by_alias=True
    )


def _serialize_workflow(workflow: Any) -> dict[str, Any]:
    return WorkflowRead.model_validate(workflow, from_attributes=True).model_dump(
        mode="json", by_alias=True
    )


def _serialize_project(project: Any) -> dict[str, Any]:
    return ProjectRead.model_validate(project, from_attributes=True).model_dump(
        mode="json", by_alias=True
    )


# ---------------------------------------------------------------------------
# Base for platform tools — shared service wiring
# ---------------------------------------------------------------------------


class _PlatformToolBase(BaseTool):
    """Shared setup for platform_* tools — eagerly constructs the services.

    Kept tiny on purpose: every concrete tool only needs to implement
    `get_schema` and `execute`. Auth scoping (`user_id`, `workspace_id`,
    `project_id`) comes from BaseTool.__init__ already.
    """

    def __init__(
        self,
        session: "AsyncSession",
        *,
        project_id: str,
        workspace_root: Path | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> None:
        super().__init__(
            session,
            project_id=project_id,
            workspace_root=workspace_root,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        self._run_service: RunService | None = None
        self._project_service: ProjectService | None = None
        self._project_workflow_service: ProjectWorkflowService | None = None
        self._workflow_repo: WorkflowRepository | None = None
        self._archive_service: RunArchiveService | None = None

    @property
    def run_service(self) -> RunService:
        if self._run_service is None:
            self._run_service = RunService(self.session)
        return self._run_service

    @property
    def project_service(self) -> ProjectService:
        if self._project_service is None:
            self._project_service = ProjectService(self.session)
        return self._project_service

    @property
    def project_workflow_service(self) -> ProjectWorkflowService:
        if self._project_workflow_service is None:
            self._project_workflow_service = ProjectWorkflowService(self.session)
        return self._project_workflow_service

    @property
    def workflow_repo(self) -> WorkflowRepository:
        if self._workflow_repo is None:
            self._workflow_repo = WorkflowRepository(self.session)
        return self._workflow_repo

    @property
    def archive_service(self) -> RunArchiveService:
        if self._archive_service is None:
            self._archive_service = RunArchiveService(self.session)
        return self._archive_service


# ---------------------------------------------------------------------------
# READ tools
# ---------------------------------------------------------------------------


@register_tool
class PlatformProjectListTool(_PlatformToolBase):
    name = "platform_project_list"
    description = (
        "List Bioinfoflow projects in the current workspace. "
        "Returns id, name, description, storage_mode, project_root, is_default, "
        "created_at, updated_at."
    )
    risk_level = RiskLevel.READ

    def get_schema(self) -> dict[str, Any]:
        return {
            "limit": {"type": "integer", "description": "Max results (default 20).", "required": False},
            "cursor": {"type": "string", "description": "Pagination cursor from previous call.", "required": False},
            "search": {"type": "string", "description": "Substring match on project name.", "required": False},
        }

    async def execute(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        search: str | None = None,
    ) -> ToolResult:
        if not self.workspace_id:
            return ToolResult(success=False, error="workspace_id missing from tool context")
        projects, pagination = await self.project_service.list_projects(
            workspace_id=self.workspace_id,
            limit=limit,
            cursor=cursor,
            search=search,
        )
        return ToolResult(
            success=True,
            data={
                "projects": [_serialize_project(p) for p in projects],
                "pagination": pagination.model_dump(mode="json") if pagination else None,
            },
        )


@register_tool
class PlatformProjectShowTool(_PlatformToolBase):
    name = "platform_project_show"
    description = "Show one project's full record by id."
    risk_level = RiskLevel.READ

    def get_schema(self) -> dict[str, Any]:
        return {
            "project_id": {"type": "string", "description": "Project id (UUID).", "required": True},
        }

    async def execute(self, *, project_id: str) -> ToolResult:
        project = await self.project_service.get_project(
            project_id, workspace_id=self.workspace_id
        )
        if project is None:
            return ToolResult(success=False, error=f"project not found: {project_id}")
        return ToolResult(success=True, data={"project": _serialize_project(project)})


@register_tool
class PlatformWorkflowListTool(_PlatformToolBase):
    name = "platform_workflow_list"
    description = (
        "List available workflows in the registry. Filter by name, source "
        "(nf-core / github / local), or pagination cursor."
    )
    risk_level = RiskLevel.READ

    def get_schema(self) -> dict[str, Any]:
        return {
            "limit": {"type": "integer", "description": "Max results (default 20).", "required": False},
            "cursor": {"type": "string", "description": "Pagination cursor.", "required": False},
            "search": {"type": "string", "description": "Substring match on workflow name/description.", "required": False},
            "source": {"type": "string", "description": "Filter by source: nf-core, github, or local.", "required": False},
        }

    async def execute(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        search: str | None = None,
        source: str | None = None,
    ) -> ToolResult:
        workflows, pagination = await self.workflow_repo.list(
            limit=limit, cursor=cursor, search=search, source=source
        )
        return ToolResult(
            success=True,
            data={
                "workflows": [_serialize_workflow(w) for w in workflows],
                "pagination": pagination.model_dump(mode="json") if pagination else None,
            },
        )


@register_tool
class PlatformWorkflowShowTool(_PlatformToolBase):
    name = "platform_workflow_show"
    description = "Show one workflow's full record (schema, form_spec, metadata) by id."
    risk_level = RiskLevel.READ

    def get_schema(self) -> dict[str, Any]:
        return {
            "workflow_id": {"type": "string", "description": "Workflow id (UUID).", "required": True},
        }

    async def execute(self, *, workflow_id: str) -> ToolResult:
        workflow = await self.workflow_repo.get(workflow_id)
        if workflow is None:
            return ToolResult(success=False, error=f"workflow not found: {workflow_id}")
        return ToolResult(success=True, data={"workflow": _serialize_workflow(workflow)})


@register_tool
class PlatformWorkflowProjectListTool(_PlatformToolBase):
    name = "platform_workflow_project_list"
    description = (
        "List workflows bound to the current project, grouped by source and "
        "version, with the pinned version marked."
    )
    risk_level = RiskLevel.READ

    def get_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self) -> ToolResult:
        entries = await self.project_workflow_service.list_project_workflows(
            project_id=self.project_id
        )
        return ToolResult(success=True, data={"workflows": entries})


@register_tool
class PlatformRunListTool(_PlatformToolBase):
    name = "platform_run_list"
    description = (
        "List runs. Defaults to the current project. Supports filtering by "
        "workflow, status, and pagination."
    )
    risk_level = RiskLevel.READ

    def get_schema(self) -> dict[str, Any]:
        return {
            "workflow_id": {"type": "string", "description": "Filter by workflow id.", "required": False},
            "status": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter by status values (queued/running/succeeded/failed/cancelled).",
                "required": False,
            },
            "limit": {"type": "integer", "description": "Max results (default 20).", "required": False},
            "cursor": {"type": "string", "description": "Pagination cursor.", "required": False},
            "all_projects": {
                "type": "boolean",
                "description": "If true, list runs across the whole workspace instead of the current project.",
                "required": False,
            },
        }

    async def execute(
        self,
        *,
        workflow_id: str | None = None,
        status: list[str] | None = None,
        limit: int = 20,
        cursor: str | None = None,
        all_projects: bool = False,
    ) -> ToolResult:
        runs, pagination = await self.run_service.list_runs(
            limit=limit,
            cursor=cursor,
            project_id=None if all_projects else self.project_id,
            workflow_id=workflow_id,
            status=status,
            user_id=self.user_id,
            workspace_id=self.workspace_id,
        )
        return ToolResult(
            success=True,
            data={
                "runs": [_serialize_run(r) for r in runs],
                "pagination": pagination.model_dump(mode="json") if pagination else None,
            },
        )


@register_tool
class PlatformRunShowTool(_PlatformToolBase):
    name = "platform_run_show"
    description = "Show one run's full record, including config and current status."
    risk_level = RiskLevel.READ

    def get_schema(self) -> dict[str, Any]:
        return {
            "run_id": {"type": "string", "description": "Run identifier (e.g. r-abc123).", "required": True},
        }

    async def execute(self, *, run_id: str) -> ToolResult:
        run = await self.run_service.get_run(
            run_id, user_id=self.user_id, workspace_id=self.workspace_id
        )
        return ToolResult(success=True, data={"run": _serialize_run(run)})


@register_tool
class PlatformRunLogsTool(_PlatformToolBase):
    name = "platform_run_logs"
    description = (
        "Return tail of a run's logs. Optionally filter to a single task. "
        "Use this instead of shell `cat` / `tail` on run log files."
    )
    risk_level = RiskLevel.READ

    def get_schema(self) -> dict[str, Any]:
        return {
            "run_id": {"type": "string", "description": "Run identifier.", "required": True},
            "tail": {"type": "integer", "description": "How many lines to return (default 100).", "required": False},
            "task": {"type": "string", "description": "Filter to a specific task name.", "required": False},
        }

    async def execute(
        self,
        *,
        run_id: str,
        tail: int = 100,
        task: str | None = None,
    ) -> ToolResult:
        logs = await self.run_service.get_logs(
            run_id,
            tail=tail,
            task=task,
            user_id=self.user_id,
            workspace_id=self.workspace_id,
        )
        return ToolResult(success=True, data=logs)


@register_tool
class PlatformRunDagTool(_PlatformToolBase):
    name = "platform_run_dag"
    description = "Return the live DAG for a run — nodes, edges, and per-node status."
    risk_level = RiskLevel.READ

    def get_schema(self) -> dict[str, Any]:
        return {
            "run_id": {"type": "string", "description": "Run identifier.", "required": True},
        }

    async def execute(self, *, run_id: str) -> ToolResult:
        dag = await self.run_service.get_dag(
            run_id, user_id=self.user_id, workspace_id=self.workspace_id
        )
        return ToolResult(success=True, data={"dag": dag})


@register_tool
class PlatformRunOutputsTool(_PlatformToolBase):
    name = "platform_run_outputs"
    description = (
        "List output artifacts produced by a run — name, relative path, "
        "size, type. Prefer this over shell `ls` inside the results dir."
    )
    risk_level = RiskLevel.READ

    def get_schema(self) -> dict[str, Any]:
        return {
            "run_id": {"type": "string", "description": "Run identifier.", "required": True},
        }

    async def execute(self, *, run_id: str) -> ToolResult:
        run = await self.run_service.get_run(
            run_id, user_id=self.user_id, workspace_id=self.workspace_id
        )
        outputs = await self.archive_service.list_outputs(run)
        return ToolResult(success=True, data=outputs)


@register_tool
class PlatformRunPreviewTool(_PlatformToolBase):
    name = "platform_run_preview"
    description = (
        "Preview the current form spec for a workflow against the current "
        "project. Use this to inspect required fields before submission."
    )
    risk_level = RiskLevel.READ

    def get_schema(self) -> dict[str, Any]:
        return {
            "workflow_id": {"type": "string", "description": "Workflow id to preview.", "required": True},
        }

    async def execute(self, *, workflow_id: str) -> ToolResult:
        workflow = await self.workflow_repo.get(workflow_id)
        if workflow is None:
            return ToolResult(success=False, error=f"workflow not found: {workflow_id}")
        return ToolResult(
            success=True,
            data={
                "workflow": _serialize_workflow(workflow),
                "form_spec": workflow.form_spec or {"fields": []},
            },
        )


# ---------------------------------------------------------------------------
# ACT_HIGH tools (approval-gated)
# ---------------------------------------------------------------------------


@register_tool
class PlatformRunSubmitTool(_PlatformToolBase):
    name = "platform_run_submit"
    description = (
        "Submit a new run of a workflow in the current project. "
        "Provide form-field keyed `values` and optional `options`."
    )
    risk_level = RiskLevel.ACT_HIGH

    def get_schema(self) -> dict[str, Any]:
        return {
            "workflow_id": {"type": "string", "description": "Workflow id to submit.", "required": True},
            "values": {
                "type": "object",
                "description": "Workflow form values keyed by field id.",
                "required": False,
            },
            "options": {
                "type": "object",
                "description": "Optional run options such as profile or timeout_seconds.",
                "required": False,
            },
        }

    async def execute(
        self,
        *,
        workflow_id: str,
        values: dict | None = None,
        options: dict | None = None,
    ) -> ToolResult:
        payload = RunCreate.model_validate(
            {
                "project_id": self.project_id,
                "workflow_id": workflow_id,
                "values": values or {},
                "options": options,
            }
        )
        run = await RunCompiler(self.session).create_run(
            payload,
            user_id=self.user_id,
            workspace_id=self.workspace_id,
        )
        return ToolResult(success=True, data={"run": _serialize_run(run)})


@register_tool
class PlatformRunCancelTool(_PlatformToolBase):
    name = "platform_run_cancel"
    description = "Cancel a queued or running run."
    risk_level = RiskLevel.ACT_HIGH

    def get_schema(self) -> dict[str, Any]:
        return {
            "run_id": {"type": "string", "description": "Run identifier.", "required": True},
        }

    async def execute(self, *, run_id: str) -> ToolResult:
        run = await self.run_service.cancel_run(
            run_id, user_id=self.user_id, workspace_id=self.workspace_id
        )
        return ToolResult(success=True, data={"run": _serialize_run(run)})


@register_tool
class PlatformRunRetryTool(_PlatformToolBase):
    name = "platform_run_retry"
    description = (
        "Retry a failed run. Optionally override params / inputs / config. "
        "Creates a new run with the same lineage."
    )
    risk_level = RiskLevel.ACT_HIGH

    def get_schema(self) -> dict[str, Any]:
        return {
            "run_id": {"type": "string", "description": "Original (failed) run id.", "required": True},
            "params": {"type": "object", "description": "Param overrides.", "required": False},
            "inputs": {"type": "object", "description": "Input overrides.", "required": False},
            "config_overrides": {"type": "object", "description": "Config overrides.", "required": False},
        }

    async def execute(
        self,
        *,
        run_id: str,
        params: dict | None = None,
        inputs: dict | None = None,
        config_overrides: dict | None = None,
    ) -> ToolResult:
        run = await self.run_service.retry_run(
            run_id,
            params=params,
            inputs=inputs,
            config_overrides=config_overrides,
            user_id=self.user_id,
            workspace_id=self.workspace_id,
        )
        return ToolResult(success=True, data={"run": _serialize_run(run)})


@register_tool
class PlatformRunResumeTool(_PlatformToolBase):
    name = "platform_run_resume"
    description = "Resume a failed run from its last checkpoint (engine-specific)."
    risk_level = RiskLevel.ACT_HIGH

    def get_schema(self) -> dict[str, Any]:
        return {
            "run_id": {"type": "string", "description": "Original (failed) run id.", "required": True},
            "config_overrides": {"type": "object", "description": "Config overrides.", "required": False},
        }

    async def execute(
        self,
        *,
        run_id: str,
        config_overrides: dict | None = None,
    ) -> ToolResult:
        run = await self.run_service.resume_run(
            run_id,
            config_overrides=config_overrides,
            user_id=self.user_id,
            workspace_id=self.workspace_id,
        )
        return ToolResult(success=True, data={"run": _serialize_run(run)})


@register_tool
class PlatformWorkflowBindTool(_PlatformToolBase):
    name = "platform_workflow_bind"
    description = "Enable / bind a workflow to the current project."
    risk_level = RiskLevel.ACT_HIGH

    def get_schema(self) -> dict[str, Any]:
        return {
            "workflow_id": {"type": "string", "description": "Workflow id to bind.", "required": True},
        }

    async def execute(self, *, workflow_id: str) -> ToolResult:
        await self.project_workflow_service.bind_workflow(
            project_id=self.project_id, workflow_id=workflow_id
        )
        return ToolResult(success=True, data={"project_id": self.project_id, "workflow_id": workflow_id})


@register_tool
class PlatformWorkflowUnbindTool(_PlatformToolBase):
    name = "platform_workflow_unbind"
    description = "Unbind (disable) a workflow from the current project."
    risk_level = RiskLevel.ACT_HIGH

    def get_schema(self) -> dict[str, Any]:
        return {
            "workflow_id": {"type": "string", "description": "Workflow id to unbind.", "required": True},
        }

    async def execute(self, *, workflow_id: str) -> ToolResult:
        await self.project_workflow_service.unbind_workflow(
            project_id=self.project_id, workflow_id=workflow_id
        )
        return ToolResult(success=True, data={"project_id": self.project_id, "workflow_id": workflow_id})


# Silence unused-import warnings when UUID isn't referenced in annotations.
_ = UUID
