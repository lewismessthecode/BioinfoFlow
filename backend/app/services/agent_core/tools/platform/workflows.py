from __future__ import annotations

from typing import Any

from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.workflow_service import WorkflowService


def _workflow_summary(workflow) -> dict[str, Any]:
    return {
        "id": str(workflow.id),
        "name": workflow.name,
        "description": workflow.description,
        "source": _value(workflow.source),
        "engine": _value(workflow.engine),
        "version": workflow.version,
        "source_ref": workflow.source_ref,
        "entrypoint_relpath": workflow.entrypoint_relpath,
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

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        service = WorkflowService(context.db)
        workflows, pagination = await service.list_workflows(
            limit=int(input.get("limit") or 20),
            search=input.get("search"),
            source=input.get("source"),
        )
        return {
            "workflows": [
                {
                    "id": str(workflow.id),
                    "name": workflow.name,
                    "description": workflow.description,
                    "source": _value(workflow.source),
                    "engine": _value(workflow.engine),
                    "version": workflow.version,
                    "source_ref": workflow.source_ref,
                    "entrypoint_relpath": workflow.entrypoint_relpath,
                    "has_schema": workflow.schema_json is not None,
                    "has_form_spec": workflow.form_spec is not None,
                }
                for workflow in workflows
            ],
            "total_count": pagination.total_count or 0,
        }


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
                "source": {"type": "string", "enum": ["local", "github", "nfcore"]},
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

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        service = WorkflowService(context.db)
        payload = {key: value for key, value in input.items() if value is not None}
        workflow = await service.create_workflow(payload)
        return {"workflow": _workflow_summary(workflow)}


def _value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
