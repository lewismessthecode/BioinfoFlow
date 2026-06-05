from __future__ import annotations

from typing import Any

from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.workflow_service import WorkflowService


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


def _value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
