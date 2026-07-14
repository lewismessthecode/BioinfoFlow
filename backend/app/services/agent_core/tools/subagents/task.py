from __future__ import annotations

from app.repositories.agent_core_repo import AgentSessionRepository, AgentTurnRepository
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.utils.exceptions import BadRequestError


class TaskTool:
    """Spawn a read-only ``worker`` sub-run to handle a delegated objective.

    Generalizes ``subagent.analyze``: instead of a fixed analysis contract it
    takes a free-form ``objective`` and returns the child agent's final text.
    The child runs with ``role_profile="worker"`` so it only sees concurrency-
    safe read tools (files.read, grep, glob, platform reads, …); any writes are
    handed back to the parent agent for approval.
    """

    spec = AgentToolSpec(
        name="task",
        description=(
            "Delegate a self-contained, read-only objective to a worker subagent "
            "and get back its findings. Use it to parallelize research or scope a "
            "large search without cluttering the main thread. The subagent cannot "
            "write or run side effects."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "objective": {"type": "string", "minLength": 1},
                "description": {"type": "string"},
            },
            "required": ["objective"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "child_session_id": {"type": "string"},
                "child_turn_id": {"type": "string"},
                "status": {"type": "string"},
                "final_text": {"type": "string"},
            },
            "required": ["child_session_id", "child_turn_id", "status", "final_text"],
        },
        risk_level="act_low",
        read_scope=["workspace"],
        write_scope=["agent_sessions", "agent_turns"],
        audit="Spawn a bounded read-only worker subagent.",
        rollback_hint="Delete the child session if the delegated run should not be retained.",
        timeout_seconds=180,
    )

    async def run(self, input: dict, context: AgentToolContext) -> dict:
        objective = str(input.get("objective") or "").strip()
        if not objective:
            raise BadRequestError("objective must be non-empty")
        description = str(input.get("description") or "").strip()

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
            title=f"Task: {objective[:80]}",
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
                "task_objective": objective,
            },
            lineage={"parent_session_id": context.session_id, "parent_turn_id": context.turn_id},
        )
        child_session = await service.session_repo.update_with_policy_version(
            child_session,
            increment_policy_version=True,
            toolset_policy={"name": "default"},
        )
        child_turn = await service.create_turn_record(
            session_id=str(child_session.id),
            workspace_id=context.workspace_id,
            user_id=context.user_id,
            input_text=_build_task_prompt(objective=objective, description=description),
        )
        completed_turn = await service.runtime.run_turn(str(child_turn.id))
        return {
            "child_session_id": str(child_session.id),
            "child_turn_id": str(child_turn.id),
            "status": completed_turn.status if completed_turn else "unknown",
            "final_text": (completed_turn.final_text if completed_turn else "") or "",
        }


def _build_task_prompt(*, objective: str, description: str) -> str:
    sections = [f"Objective: {objective}"]
    if description:
        sections.append(f"Details:\n{description}")
    sections.append(
        "You are a read-only worker subagent. Use only the exposed read tools "
        "(file reads, grep, glob, platform reads). Do not attempt to write files "
        "or run side effects. Return a concise, self-contained answer for the "
        "parent agent."
    )
    return "\n\n".join(sections)
