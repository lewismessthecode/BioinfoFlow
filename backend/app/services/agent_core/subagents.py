from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_core_repo import AgentSessionRepository, AgentTurnRepository
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.utils.exceptions import PermissionDeniedError


class ReadOnlySubagentRunner:
    def __init__(self, registry: AgentToolRegistry, db: AsyncSession | None = None):
        self.registry = registry
        self.db = db

    async def analyze(
        self,
        *,
        task: str,
        context: dict | None = None,
        allowed_tools: list[str] | None = None,
    ) -> dict:
        tool_names = allowed_tools or self._default_read_only_tools()
        for tool_name in tool_names:
            tool = self.registry.get(tool_name)
            if tool.spec.write_scope or tool.spec.risk_level != "read":
                raise PermissionDeniedError(
                    f"Read-only subagent cannot use write-capable tool: {tool_name}"
                )

        if self.db is None or not _has_runtime_context(context):
            return {
                "mode": "read_only",
                "task": task,
                "context": context or {},
                "allowed_tools": tool_names,
                "write_handoff_required": True,
                "handoff_contract": {
                    "write_operations": "return_to_main_agent_action_ledger",
                    "artifacts": "return_as_summary_or_file_refs",
                },
            }

        runtime_context = context or {}
        parent_session = await AgentSessionRepository(self.db).get(runtime_context["session_id"])
        parent_turn = await AgentTurnRepository(self.db).get(runtime_context["turn_id"])
        if parent_session is None or parent_turn is None:
            raise PermissionDeniedError("Subagent parent context could not be loaded")

        from app.services.agent_core.service import AgentCoreService

        service = AgentCoreService(self.db)
        child_session = await service.create_session(
            project_id=str(parent_session.project_id) if parent_session.project_id else None,
            workspace_id=runtime_context["workspace_id"],
            user_id=runtime_context["user_id"],
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
                "parent_session_id": runtime_context["session_id"],
                "parent_turn_id": runtime_context["turn_id"],
                "subagent_task": task,
            },
            lineage={
                "parent_session_id": runtime_context["session_id"],
                "parent_turn_id": runtime_context["turn_id"],
            },
        )
        child_session = await service.session_repo.update_all(
            child_session,
            toolset_policy={"name": "default", "allowed_tools": tool_names},
        )
        child_turn = await service.create_turn_record(
            session_id=str(child_session.id),
            workspace_id=runtime_context["workspace_id"],
            user_id=runtime_context["user_id"],
            input_text=_build_subagent_prompt(task=task, context=runtime_context, allowed_tools=tool_names),
        )
        completed_turn = await service.runtime.run_turn(str(child_turn.id))
        artifacts = await service.list_artifacts_for_turn(
            turn_id=str(child_turn.id),
            workspace_id=runtime_context["workspace_id"],
            user_id=runtime_context["user_id"],
        )
        return {
            "mode": "delegated_read_only",
            "task": task,
            "context": runtime_context,
            "allowed_tools": tool_names,
            "child_session_id": str(child_session.id),
            "child_turn_id": str(child_turn.id),
            "status": completed_turn.status,
            "final_text": completed_turn.final_text or "",
            "artifact_ids": [str(artifact.id) for artifact in artifacts],
            "write_handoff_required": True,
        }

    def _default_read_only_tools(self) -> list[str]:
        return [
            spec.name
            for spec in self.registry.list_specs()
            if not spec.write_scope and spec.risk_level == "read"
        ]


def _has_runtime_context(context: dict | None) -> bool:
    if not isinstance(context, dict):
        return False
    return all(
        isinstance(context.get(key), str) and context.get(key)
        for key in ("workspace_id", "user_id", "session_id", "turn_id")
    )


def _build_subagent_prompt(*, task: str, context: dict, allowed_tools: list[str]) -> str:
    payload = {k: v for k, v in context.items() if k not in {"workspace_id", "user_id", "session_id", "turn_id"}}
    sections = [f"Task: {task}"]
    if payload:
        sections.append("Context:\n" + json.dumps(payload, indent=2, sort_keys=True))
    if allowed_tools:
        sections.append("Allowed tools:\n" + "\n".join(f"- {tool}" for tool in allowed_tools))
    sections.append(
        "Work read-only, use only exposed read-only tools, and return a concise final answer for the parent agent."
    )
    return "\n\n".join(sections)
