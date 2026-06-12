from __future__ import annotations

import json

from app.repositories.agent_core_repo import AgentSessionRepository, AgentTurnRepository
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.utils.exceptions import BadRequestError


class SubagentAnalyzeTool:
    spec = AgentToolSpec(
        name="subagent.analyze",
        description="Run a bounded read-only child agent turn and return its summary.",
        input_schema={
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "context": {"type": "object"},
                "allowed_tools": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["task"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "mode": {"type": "string"},
                "child_session_id": {"type": "string"},
                "child_turn_id": {"type": "string"},
                "status": {"type": "string"},
                "final_text": {"type": "string"},
                "allowed_tools": {"type": "array"},
                "artifact_ids": {"type": "array"},
            },
            "required": [
                "mode",
                "child_session_id",
                "child_turn_id",
                "status",
                "final_text",
                "allowed_tools",
                "artifact_ids",
            ],
        },
        risk_level="act_low",
        read_scope=["workspace"],
        write_scope=["agent_sessions", "agent_turns"],
        audit="Spawn a bounded read-only child agent turn.",
        rollback_hint="Delete the child session if the delegated run should not be retained.",
        timeout_seconds=120,
    )

    async def run(self, input: dict, context: AgentToolContext) -> dict:
        task = str(input["task"]).strip()
        if not task:
            raise BadRequestError("task must be non-empty")
        parent_session = await AgentSessionRepository(context.db).get(context.session_id)
        parent_turn = await AgentTurnRepository(context.db).get(context.turn_id)
        if parent_session is None or parent_turn is None:
            raise BadRequestError("parent agent context could not be loaded")

        from app.services.agent_core.service import AgentCoreService

        service = AgentCoreService(context.db)
        child_session = await service.create_session(
            project_id=str(parent_session.project_id) if parent_session.project_id else None,
            workspace_id=context.workspace_id,
            user_id=context.user_id,
            title=f"Subagent: {task[:80]}",
            role_profile="worker",
            permission_mode=parent_session.permission_mode,
            automation_mode=parent_session.automation_mode,
            default_model_profile_id=(
                str(parent_session.default_model_profile_id)
                if parent_session.default_model_profile_id
                else None
            ),
            metadata={
                "parent_session_id": context.session_id,
                "parent_turn_id": context.turn_id,
                "subagent_task": task,
            },
        )
        child_session = await service.session_repo.update_all(
            child_session,
            lineage={"parent_session_id": context.session_id, "parent_turn_id": context.turn_id},
            toolset_policy={"name": "default"},
        )
        child_turn = await service.create_turn_record(
            session_id=str(child_session.id),
            workspace_id=context.workspace_id,
            user_id=context.user_id,
            input_text=_build_subagent_prompt(
                task=task,
                task_context=input.get("context") or {},
                allowed_tools=input.get("allowed_tools") or [],
            ),
        )
        completed_turn = await service.runtime.run_turn(str(child_turn.id))
        artifacts = await service.list_artifacts_for_turn(
            turn_id=str(child_turn.id),
            workspace_id=context.workspace_id,
            user_id=context.user_id,
        )
        return {
            "mode": "delegated_read_only",
            "child_session_id": str(child_session.id),
            "child_turn_id": str(child_turn.id),
            "status": completed_turn.status,
            "final_text": completed_turn.final_text or "",
            "allowed_tools": input.get("allowed_tools") or [],
            "artifact_ids": [str(artifact.id) for artifact in artifacts],
        }


def _build_subagent_prompt(*, task: str, task_context: dict, allowed_tools: list[str]) -> str:
    sections = [f"Task: {task}"]
    if task_context:
        sections.append("Context:\n" + json.dumps(task_context, indent=2, sort_keys=True))
    if allowed_tools:
        sections.append("Allowed tools:\n" + "\n".join(f"- {tool}" for tool in allowed_tools))
    sections.append(
        "Work read-only, use only exposed read-only tools, and return a concise final answer for the parent agent."
    )
    return "\n\n".join(sections)
