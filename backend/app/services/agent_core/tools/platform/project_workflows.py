from __future__ import annotations

from typing import Any

from app.services.agent_core.tools.platform.workflows import workflow_payload
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.project_workflow_service import ProjectWorkflowService
from app.services.project_service import ProjectService
from app.utils.exceptions import NotFoundError


async def _require_project_in_workspace(
    input: dict[str, Any], context: AgentToolContext
) -> str:
    project_id = str(input["project_id"])
    project = await ProjectService(context.db).get_project(
        project_id,
        workspace_id=context.workspace_id,
    )
    if project is None:
        raise NotFoundError("Project not found")
    return project_id


class ListProjectWorkflowsTool:
    spec = AgentToolSpec(
        name="projects.workflows.list",
        description="List workflows enabled for a project, grouped by source/name.",
        input_schema={
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"groups": {"type": "array"}},
            "required": ["groups"],
        },
        risk_level="read",
        read_scope=["projects", "workflows"],
        audit="List project workflow bindings.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        project_id = await _require_project_in_workspace(input, context)
        groups = await ProjectWorkflowService(context.db).list_project_workflows(
            project_id=project_id
        )
        return {
            "groups": [
                {
                    "source": group["source"],
                    "name": group["name"],
                    "pinned_workflow": workflow_payload(group["pinned_workflow"]),
                    "versions": [workflow_payload(workflow) for workflow in group["versions"]],
                }
                for group in groups
            ]
        }


class BindProjectWorkflowTool:
    spec = AgentToolSpec(
        name="projects.workflows.bind",
        description="Enable a workflow for a project.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "workflow_id": {"type": "string"},
            },
            "required": ["project_id", "workflow_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "workflow_id": {"type": "string"},
                "bound": {"type": "boolean"},
            },
            "required": ["project_id", "workflow_id", "bound"],
        },
        risk_level="act_high",
        read_scope=["projects", "workflows"],
        write_scope=["projects", "workflows"],
        audit="Bind workflow to project.",
        rollback_hint="Unbind the workflow from the project if it was enabled in error.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        project_id = await _require_project_in_workspace(input, context)
        workflow_id = str(input["workflow_id"])
        await ProjectWorkflowService(context.db).bind_workflow(
            project_id=project_id,
            workflow_id=workflow_id,
        )
        return {"project_id": project_id, "workflow_id": workflow_id, "bound": True}


class UnbindProjectWorkflowTool:
    spec = AgentToolSpec(
        name="projects.workflows.unbind",
        description="Disable a workflow for a project.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "workflow_id": {"type": "string"},
            },
            "required": ["project_id", "workflow_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "workflow_id": {"type": "string"},
                "unbound": {"type": "boolean"},
            },
            "required": ["project_id", "workflow_id", "unbound"],
        },
        risk_level="act_high",
        read_scope=["projects", "workflows"],
        write_scope=["projects", "workflows"],
        audit="Unbind workflow from project.",
        rollback_hint="Bind the workflow to the project again if needed.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        project_id = await _require_project_in_workspace(input, context)
        workflow_id = str(input["workflow_id"])
        await ProjectWorkflowService(context.db).unbind_workflow(
            project_id=project_id,
            workflow_id=workflow_id,
        )
        return {"project_id": project_id, "workflow_id": workflow_id, "unbound": True}


class PinProjectWorkflowTool:
    spec = AgentToolSpec(
        name="projects.workflows.pin",
        description="Pin a specific enabled workflow version for a project.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "workflow_id": {"type": "string"},
            },
            "required": ["project_id", "workflow_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "pinned_workflow_id": {"type": "string"},
            },
            "required": ["project_id", "pinned_workflow_id"],
        },
        risk_level="act_high",
        read_scope=["projects", "workflows"],
        write_scope=["projects", "workflows"],
        audit="Pin project workflow version.",
        rollback_hint="Pin the previous workflow version again if needed.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        project_id = await _require_project_in_workspace(input, context)
        workflow_id = str(input["workflow_id"])
        await ProjectWorkflowService(context.db).set_pin(
            project_id=project_id,
            pinned_workflow_id=workflow_id,
        )
        return {"project_id": project_id, "pinned_workflow_id": workflow_id}
