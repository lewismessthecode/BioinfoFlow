from __future__ import annotations

from typing import Any

from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.authorization_service import AuthorizationService
from app.services.project_service import ProjectService
from app.utils.authorization import can_manage_external_roots
from app.utils.exceptions import NotFoundError, PermissionDeniedError


def _project_payload(project) -> dict[str, Any]:
    return {
        "id": str(project.id),
        "name": project.name,
        "description": project.description,
        "storage_mode": project.storage_mode,
        "external_root_path": getattr(project, "external_root_path", None),
        "remote_connection_id": getattr(project, "remote_connection_id", None),
        "remote_root_path": getattr(project, "remote_root_path", None),
        "project_root": project.project_root,
        "is_default": bool(project.is_default),
    }


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
                _project_payload(project)
                for project in projects
            ],
            "total_count": pagination.total_count or 0,
        }


class GetProjectTool:
    spec = AgentToolSpec(
        name="projects.get",
        description="Read a BioInfoFlow project by id.",
        input_schema={
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"project": {"type": "object"}},
            "required": ["project"],
        },
        risk_level="read",
        read_scope=["projects"],
        audit="Read project details.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        project = await ProjectService(context.db).get_project(
            str(input["project_id"]),
            workspace_id=context.workspace_id,
        )
        if project is None:
            raise NotFoundError("Project not found")
        return {"project": _project_payload(project)}


class CreateProjectTool:
    spec = AgentToolSpec(
        name="projects.create",
        description="Create a BioInfoFlow project in the current workspace.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "external_root_path": {"type": "string"},
                "remote_connection_id": {"type": "string"},
                "remote_root_path": {"type": "string"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"project": {"type": "object"}},
            "required": ["project"],
        },
        risk_level="act_high",
        read_scope=["projects"],
        write_scope=["projects"],
        audit="Create a project.",
        rollback_hint="Delete the project if it was created in error.",
        artifact_policy={"type": "project"},
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        payload = {key: value for key, value in input.items() if value is not None}
        if (
            payload.get("external_root_path")
            or payload.get("remote_connection_id")
            or payload.get("remote_root_path")
        ):
            role = await AuthorizationService(context.db).resolve_workspace_role(
                workspace_id=context.workspace_id,
                user_id=context.user_id,
            )
            if not can_manage_external_roots(role):
                raise PermissionDeniedError(
                    "External project roots are restricted to administrators"
                )
        payload["workspace_id"] = context.workspace_id
        project = await ProjectService(context.db).create_project(
            payload,
            user_id=context.user_id,
        )
        return {"project": _project_payload(project)}


class UpdateProjectTool:
    spec = AgentToolSpec(
        name="projects.update",
        description="Update project metadata or storage settings.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "external_root_path": {"type": "string"},
                "remote_connection_id": {"type": "string"},
                "remote_root_path": {"type": "string"},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"project": {"type": "object"}},
            "required": ["project"],
        },
        risk_level="act_high",
        read_scope=["projects"],
        write_scope=["projects"],
        audit="Update a project.",
        rollback_hint="Update the project again with the previous values if needed.",
        artifact_policy={"type": "project"},
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        service = ProjectService(context.db)
        project = await service.get_project(
            str(input["project_id"]),
            workspace_id=context.workspace_id,
        )
        if project is None:
            raise NotFoundError("Project not found")
        payload = {
            key: value
            for key, value in input.items()
            if key != "project_id" and value is not None
        }
        if (
            payload.get("external_root_path")
            or payload.get("remote_connection_id")
            or payload.get("remote_root_path")
        ):
            role = await AuthorizationService(context.db).resolve_workspace_role(
                workspace_id=context.workspace_id,
                user_id=context.user_id,
            )
            if not can_manage_external_roots(role):
                raise PermissionDeniedError(
                    "External project roots are restricted to administrators"
                )
        updated = await service.update_project(project, payload)
        return {"project": _project_payload(updated)}


class DeleteProjectTool:
    spec = AgentToolSpec(
        name="projects.delete",
        description="Delete a non-default project.",
        input_schema={
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "deleted": {"type": "boolean"},
            },
            "required": ["project_id", "deleted"],
        },
        risk_level="destructive",
        read_scope=["projects"],
        write_scope=["projects"],
        audit="Delete a project.",
        rollback_hint="Deleted project metadata cannot be restored automatically.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        project_id = str(input["project_id"])
        service = ProjectService(context.db)
        project = await service.get_project(project_id, workspace_id=context.workspace_id)
        if project is None:
            raise NotFoundError("Project not found")
        if project.is_default:
            raise PermissionDeniedError("Cannot delete the default project")
        await AuthorizationService(context.db).require_destructive_business_access(
            workspace_id=context.workspace_id,
            user_id=context.user_id,
        )
        await service.delete_project(project)
        return {"project_id": project_id, "deleted": True}
