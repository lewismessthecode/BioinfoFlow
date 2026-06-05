from __future__ import annotations

from typing import Any

from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.project_service import ProjectService


class ListProjectsTool:
    spec = AgentToolSpec(
        name="projects.list",
        description="List BioInfoFlow projects in the current workspace.",
        input_schema={
            "type": "object",
            "properties": {
                "search": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "projects": {"type": "array"},
                "total_count": {"type": "integer"},
            },
            "required": ["projects", "total_count"],
        },
        risk_level="read",
        read_scope=["projects"],
        audit="List projects in the current workspace.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        service = ProjectService(context.db)
        projects, pagination = await service.list_projects(
            workspace_id=context.workspace_id,
            limit=int(input.get("limit") or 20),
            search=input.get("search"),
        )
        return {
            "projects": [
                {
                    "id": str(project.id),
                    "name": project.name,
                    "description": project.description,
                    "storage_mode": project.storage_mode,
                    "project_root": project.project_root,
                    "is_default": bool(project.is_default),
                }
                for project in projects
            ],
            "total_count": pagination.total_count or 0,
        }
