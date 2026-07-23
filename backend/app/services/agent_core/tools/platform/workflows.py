from __future__ import annotations

from typing import Any

from app.schemas.form_spec import to_read_projection
from app.services.agent_core.tools.result_budget import DEFAULT_TOOL_RESULT_LIMIT
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.authorization_service import AuthorizationService
from app.services.workflow_form_spec import effective_workflow_form_spec
from app.services.workflow_service import WorkflowService
from app.utils.dag_builder import build_dag_from_schema
from app.utils.exceptions import BadRequestError, NotFoundError

_WORKFLOW_SOURCE_DEFAULT_LINES = 400
_WORKFLOW_SOURCE_MAX_LINES = 2000
_WORKFLOW_SOURCE_CONTENT_LIMIT = DEFAULT_TOOL_RESULT_LIMIT


def workflow_payload(workflow) -> dict[str, Any]:
    return {
        "id": str(workflow.id),
        "name": workflow.name,
        "description": workflow.description,
        "source": _value(workflow.source),
        "engine": _value(workflow.engine),
        "version": workflow.version,
        "source_ref": workflow.source_ref,
        "entrypoint_relpath": workflow.entrypoint_relpath,
        "has_schema": getattr(workflow, "schema_json", None) is not None,
        "has_form_spec": getattr(workflow, "form_spec", None) is not None,
    }


class ListWorkflowsTool:
    spec = AgentToolSpec(
        name="workflows.list",
        description="List registered BioInfoFlow workflows.",
        input_schema={
            "type": "object",
            "properties": {
                "search": {"type": "string"},
                "source": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "workflows": {"type": "array"},
                "total_count": {"type": "integer"},
            },
            "required": ["workflows", "total_count"],
        },
        risk_level="read",
        read_scope=["workflows"],
        audit="List registered workflows.",
    )

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        service = WorkflowService(context.db)
        workflows, pagination = await service.list_workflows(
            limit=int(input.get("limit") or 20),
            search=input.get("search"),
            source=input.get("source"),
        )
        return {
            "workflows": [workflow_payload(workflow) for workflow in workflows],
            "total_count": pagination.total_count or 0,
        }


class GetWorkflowTool:
    spec = AgentToolSpec(
        name="workflows.get",
        description="Read a registered workflow by id.",
        input_schema={
            "type": "object",
            "properties": {"workflow_id": {"type": "string"}},
            "required": ["workflow_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"workflow": {"type": "object"}},
            "required": ["workflow"],
        },
        risk_level="read",
        read_scope=["workflows"],
        audit="Read workflow details.",
    )

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        workflow = await WorkflowService(context.db).get_workflow(
            str(input["workflow_id"])
        )
        if workflow is None:
            raise NotFoundError("Workflow not found")
        return {"workflow": workflow_payload(workflow)}


class CreateWorkflowTool:
    spec = AgentToolSpec(
        name="workflows.create",
        description=(
            "Register a workflow with the platform. Provide inline content for a "
            "local WDL/Nextflow file, a github source_ref, or an nf-core name. This "
            "is how you add a workflow you authored to the workflows module."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "source": {"type": "string", "enum": ["local", "github", "nf-core"]},
                "name": {"type": "string"},
                "version": {"type": "string"},
                "description": {"type": "string"},
                "engine": {"type": "string", "enum": ["nextflow", "wdl"]},
                "content": {"type": "string"},
                "file_name": {"type": "string"},
                "entrypoint_relpath": {"type": "string"},
                "source_ref": {"type": "string"},
                "estimated_time": {"type": "string"},
            },
            "required": ["source"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"workflow": {"type": "object"}},
            "required": ["workflow"],
        },
        risk_level="act_high",
        read_scope=["workflows"],
        write_scope=["workflows"],
        audit="Create a registered workflow.",
        rollback_hint="Delete the workflow from the workflows module if it was created in error.",
        artifact_policy={"type": "workflow"},
        timeout_seconds=120,
    )

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        await _require_workflow_mutation_access(context)
        service = WorkflowService(context.db)
        payload = {key: value for key, value in input.items() if value is not None}
        workflow = await service.create_workflow(payload)
        return {"workflow": workflow_payload(workflow)}


class UpdateWorkflowTool:
    spec = AgentToolSpec(
        name="workflows.update",
        description="Update workflow metadata or schema fields.",
        input_schema={
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "description": {"type": "string"},
                "estimated_time": {"type": "string"},
                "schema_json": {"type": "object"},
            },
            "required": ["workflow_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"workflow": {"type": "object"}},
            "required": ["workflow"],
        },
        risk_level="act_high",
        read_scope=["workflows"],
        write_scope=["workflows"],
        audit="Update workflow.",
        rollback_hint="Update the workflow again with previous values if needed.",
        artifact_policy={"type": "workflow"},
    )

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        await _require_workflow_mutation_access(context)
        service = WorkflowService(context.db)
        workflow = await service.get_workflow(str(input["workflow_id"]))
        if workflow is None:
            raise NotFoundError("Workflow not found")
        payload = {
            key: value
            for key, value in input.items()
            if key != "workflow_id" and value is not None
        }
        updated = await service.update_workflow(workflow, payload)
        return {"workflow": workflow_payload(updated)}


class DeleteWorkflowTool:
    spec = AgentToolSpec(
        name="workflows.delete",
        description="Delete a workflow registration.",
        input_schema={
            "type": "object",
            "properties": {"workflow_id": {"type": "string"}},
            "required": ["workflow_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "deleted": {"type": "boolean"},
            },
            "required": ["workflow_id", "deleted"],
        },
        risk_level="destructive",
        read_scope=["workflows"],
        write_scope=["workflows"],
        audit="Delete workflow.",
        rollback_hint="Recreate the workflow from its source if needed.",
    )

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        await _require_workflow_mutation_access(context)
        workflow_id = str(input["workflow_id"])
        service = WorkflowService(context.db)
        workflow = await service.get_workflow(workflow_id)
        if workflow is None:
            raise NotFoundError("Workflow not found")
        await service.delete_workflow(workflow)
        return {"workflow_id": workflow_id, "deleted": True}


class WorkflowFormSpecTool:
    spec = AgentToolSpec(
        name="workflows.form_spec",
        description="Read the workflow form spec used to submit runs.",
        input_schema={
            "type": "object",
            "properties": {"workflow_id": {"type": "string"}},
            "required": ["workflow_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"form_spec": {"type": "object"}},
            "required": ["form_spec"],
        },
        risk_level="read",
        read_scope=["workflows"],
        audit="Read workflow form spec.",
    )

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        service = WorkflowService(context.db)
        workflow = await service.get_workflow(str(input["workflow_id"]))
        if workflow is None:
            raise NotFoundError("Workflow not found")
        spec = effective_workflow_form_spec(workflow)
        return {"form_spec": to_read_projection(spec).model_dump(mode="json")}


class WorkflowDagTool:
    spec = AgentToolSpec(
        name="workflows.dag",
        description="Read workflow DAG data derived from the registered schema.",
        input_schema={
            "type": "object",
            "properties": {"workflow_id": {"type": "string"}},
            "required": ["workflow_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"dag": {"type": "object"}},
            "required": ["dag"],
        },
        risk_level="read",
        read_scope=["workflows"],
        audit="Read workflow DAG.",
    )

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        workflow = await WorkflowService(context.db).get_workflow(
            str(input["workflow_id"])
        )
        if workflow is None:
            raise NotFoundError("Workflow not found")
        if not workflow.schema_json:
            return {"dag": {"nodes": [], "edges": []}}
        return {"dag": build_dag_from_schema(workflow.schema_json)}


class WorkflowSourceTool:
    spec = AgentToolSpec(
        name="workflows.source",
        description="Read source code for a local workflow registration.",
        input_schema={
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": _WORKFLOW_SOURCE_MAX_LINES,
                },
            },
            "required": ["workflow_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"source": {"type": "object"}},
            "required": ["source"],
        },
        risk_level="read",
        read_scope=["workflows", "files"],
        audit="Read workflow source.",
    )

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        service = WorkflowService(context.db)
        workflow = await service.get_workflow(str(input["workflow_id"]))
        if workflow is None:
            raise NotFoundError("Workflow not found")
        if _value(workflow.source) != "local":
            raise BadRequestError("Source code is only available for local workflows")
        source_path = service.resolve_source_path(workflow)
        if not source_path.exists():
            raise NotFoundError("Workflow source file not found")
        content = source_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        offset = int(input.get("offset") or 0)
        limit = int(input.get("limit") or _WORKFLOW_SOURCE_DEFAULT_LINES)
        selected = "\n".join(lines[offset : offset + limit])
        capped_content = _truncate_source_content(selected)
        return {
            "source": {
                "path": str(source_path),
                "content": capped_content,
                "line_count": len(lines),
                "offset": offset,
                "limit": limit,
                "truncated": capped_content != selected or offset + limit < len(lines),
            }
        }


class InspectWorkflowTool:
    spec = AgentToolSpec(
        name="workflows.inspect",
        description=(
            "Inspect one workflow using a bounded summary, source, dag, or "
            "form_spec view. This is read-only and does not create, update, submit, "
            "or prove completion of a workflow run."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "view": {
                    "type": "string",
                    "enum": ["summary", "source", "dag", "form_spec"],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 2000},
            },
            "required": ["workflow_id", "view"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "view": {"type": "string"},
                "data": {"type": "object"},
            },
            "required": ["view", "data"],
        },
        risk_level="read",
        read_scope=["workflows"],
        audit="Inspect one workflow through a selected read-only view.",
        parallel_safe=True,
    )

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        view = str(input["view"])
        tools = {
            "summary": GetWorkflowTool,
            "source": WorkflowSourceTool,
            "dag": WorkflowDagTool,
            "form_spec": WorkflowFormSpecTool,
        }
        tool_type = tools.get(view)
        if tool_type is None:
            raise BadRequestError(f"Unsupported workflow inspection view: {view}")
        selected_input: dict[str, Any] = {"workflow_id": str(input["workflow_id"])}
        if view == "source" and "limit" in input:
            selected_input["limit"] = input["limit"]
        data = await tool_type().run(selected_input, context)
        return {"view": view, "data": data}


def _value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


async def _require_workflow_mutation_access(context: AgentToolContext) -> None:
    await AuthorizationService(context.db).require_destructive_business_access(
        workspace_id=context.workspace_id,
        user_id=context.user_id,
    )


def _truncate_source_content(content: str) -> str:
    if len(content) <= _WORKFLOW_SOURCE_CONTENT_LIMIT:
        return content
    return content[:_WORKFLOW_SOURCE_CONTENT_LIMIT] + "\n[truncated]"
