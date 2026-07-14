from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent_core import AgentActionStatus, AgentMemoryStatus
from app.path_layout import state_root
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentMemoryRepository,
)
from app.repositories.image_repo import ImageRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.run_repo import RunRepository
from app.repositories.workflow_repo import WorkflowRepository
from app.services.agent_core.context.remote import (
    render_remote_connection_context,
    selected_remote_project,
)
from app.services.agent_core.context.instructions import ProjectInstructionResolver
from app.services.agent_core.context.system_prompt import resolve_system_prompt_prefix
from app.services.agent_core.execution_target import (
    execution_target_from_session,
    is_remote_ssh_execution_target,
)
from app.services.agent_core.plugins import AgentPluginRegistry
from app.services.agent_core.sandbox import FilesystemPolicy
from app.services.agent_core.skills import (
    ActiveSkillResolutionError,
    AgentSkillRegistry,
    SKILL_PROMPT_SUMMARY_BUDGET_CHARS,
    resolve_active_skills,
)
from app.services.agent_core.metrics import agent_metrics
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.transcript import (
    AgentTranscriptStore,
    provider_message_from_parts,
)
from app.services.agent_core.transcript.messages import model_input_parts_from_message
from app.services.model_runtime.contracts import InputPart


@dataclass(frozen=True)
class AgentModelContext:
    instructions: str
    input_items: tuple[InputPart, ...]
    compacted: bool = False


class AgentContextAssembler:
    def __init__(
        self,
        session: AsyncSession,
        *,
        owned_turn_id: str | None = None,
        expected_owner_token: str | None = None,
    ):
        self.db = session
        self.transcript = AgentTranscriptStore(
            session,
            owned_turn_id=owned_turn_id,
            expected_owner_token=expected_owner_token,
        )
        self.memories = AgentMemoryRepository(session)
        self.project_instructions = ProjectInstructionResolver(session)

    async def provider_messages(
        self,
        *,
        agent_session,
        turn,
        exposed_tools=None,
        skip_compaction: bool = False,
    ) -> list[dict]:
        await self._repair_incomplete_tool_groups(
            session_id=str(agent_session.id),
            turn_id=str(turn.id),
        )
        if not skip_compaction:
            await self._compact_if_needed(agent_session=agent_session, turn=turn)
        # Stable, cache-friendly identity prefix comes first; everything that
        # changes per session/turn is appended after it.
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": await self._instructions(
                    agent_session=agent_session,
                    turn=turn,
                    exposed_tools=exposed_tools,
                ),
            }
        ]
        transcript_messages = []
        for message in await self.transcript.list_messages(str(agent_session.id)):
            if message.status != "committed":
                continue
            if message.role not in {"user", "assistant", "tool"}:
                continue
            transcript_messages.append(
                provider_message_from_parts(
                    message.role,
                    message.content_parts or [],
                    getattr(message, "message_metadata", None),
                )
            )
        messages.extend(_complete_provider_groups(transcript_messages))
        return [
            message
            for message in messages
            if message.get("content") or message.get("tool_calls")
        ]

    async def _repair_incomplete_tool_groups(
        self,
        *,
        session_id: str,
        turn_id: str,
    ) -> None:
        messages = await self.transcript.list_messages(session_id)
        index = 0
        while index < len(messages):
            message = messages[index]
            if message.status != "committed" or message.role != "assistant":
                index += 1
                continue
            provider_message = provider_message_from_parts(
                message.role,
                message.content_parts or [],
                message.message_metadata,
            )
            tool_calls = provider_message.get("tool_calls") or []
            if not tool_calls:
                index += 1
                continue
            expected = [str(call["id"]) for call in tool_calls if call.get("id")]
            batch_id = (message.message_metadata or {}).get("tool_batch_id")
            group_turn_id = str(message.turn_id or turn_id)
            cursor = index + 1
            group_messages = []
            seen: list[str] = []
            while cursor < len(messages) and messages[cursor].role == "tool":
                if messages[cursor].status == "committed":
                    group_messages.append(messages[cursor])
                    metadata = messages[cursor].message_metadata or {}
                    if metadata.get("tool_call_id"):
                        seen.append(str(metadata["tool_call_id"]))
                cursor += 1
            missing = [
                tool_call_id for tool_call_id in expected if tool_call_id not in seen
            ]
            if missing or seen != expected:
                turn_actions = await AgentActionRepository(self.db).list_for_turn(
                    group_turn_id
                )
                if batch_id:
                    turn_actions = [
                        action
                        for action in turn_actions
                        if str(action.tool_batch_id) == str(batch_id)
                    ]
                actions_by_call_id = {}
                for action in turn_actions:
                    if not action.tool_call_id:
                        continue
                    call_id = str(action.tool_call_id)
                    if call_id in actions_by_call_id:
                        actions_by_call_id[call_id] = None
                    else:
                        actions_by_call_id[call_id] = action
                unresolved_ids = {
                    str(action.tool_call_id)
                    for action in turn_actions
                    if action.tool_call_id
                    and action.status
                    in {
                        AgentActionStatus.WAITING_DECISION,
                        AgentActionStatus.REQUESTED,
                        AgentActionStatus.RUNNING,
                    }
                }
                if any(tool_call_id in unresolved_ids for tool_call_id in missing):
                    index = cursor
                    continue
                existing_by_id = {
                    str((item.message_metadata or {}).get("tool_call_id")): item
                    for item in group_messages
                }
                insert_at = message.ordering_index + 1
                await self.transcript.messages.shift_ordering_indices(
                    session_id,
                    starting_at=insert_at,
                    delta=len(expected),
                )
                for offset, tool_call_id in enumerate(expected):
                    existing = existing_by_id.get(tool_call_id)
                    if existing is not None:
                        parts = existing.content_parts or []
                        metadata = {
                            **(existing.message_metadata or {}),
                            "tool_batch_id": batch_id,
                            "action_id": (
                                str(actions_by_call_id[tool_call_id].id)
                                if actions_by_call_id.get(tool_call_id) is not None
                                else (existing.message_metadata or {}).get("action_id")
                            ),
                            "transcript_repair": True,
                            "provider_message_id": str(message.id),
                            "original_message_id": str(existing.id),
                        }
                    else:
                        parts = [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {
                                        "status": "failed",
                                        "error": {
                                            "type": "TranscriptRepair",
                                            "message": (
                                                "Missing durable tool result was repaired."
                                            ),
                                        },
                                    },
                                    separators=(",", ":"),
                                ),
                            }
                        ]
                        metadata = {
                            "tool_call_id": tool_call_id,
                            "tool_batch_id": batch_id,
                            "action_id": (
                                str(actions_by_call_id[tool_call_id].id)
                                if actions_by_call_id.get(tool_call_id) is not None
                                else None
                            ),
                            "transcript_repair": True,
                            "provider_message_id": str(message.id),
                        }
                    await self.transcript.append_parts(
                        session_id=session_id,
                        turn_id=group_turn_id,
                        role="tool",
                        parts=parts,
                        metadata=metadata,
                        ordering_index=insert_at + offset,
                    )
                await self.transcript.messages.mark_superseded(
                    [str(item.id) for item in group_messages]
                )
                await AgentEventLedger(self.db).append(
                    session_id=session_id,
                    turn_id=group_turn_id,
                    type=AgentEventType.TRANSCRIPT_TOOL_GROUP_REPAIRED,
                    payload={
                        "provider_message_id": str(message.id),
                        "missing_tool_call_ids": missing,
                        "tool_batch_id": batch_id,
                    },
                    visibility="audit",
                )
                messages = await self.transcript.list_messages(session_id)
                index = 0
                continue
            index = cursor

    async def model_context(
        self,
        *,
        agent_session,
        turn,
        exposed_tools=None,
        skip_compaction: bool = False,
    ) -> AgentModelContext:
        await self._repair_incomplete_tool_groups(
            session_id=str(agent_session.id),
            turn_id=str(turn.id),
        )
        compacted = False
        if not skip_compaction:
            compacted = await self._compact_if_needed(
                agent_session=agent_session,
                turn=turn,
            )
        input_items: list[InputPart] = []
        for message in await self.transcript.list_messages(str(agent_session.id)):
            if message.status != "committed":
                continue
            if message.role not in {"user", "assistant", "tool"}:
                continue
            input_items.extend(
                model_input_parts_from_message(
                    message.role,
                    message.content_parts or [],
                    getattr(message, "message_metadata", None),
                )
            )
        return AgentModelContext(
            instructions=await self._instructions(
                agent_session=agent_session,
                turn=turn,
                exposed_tools=exposed_tools,
            ),
            input_items=tuple(input_items),
            compacted=compacted,
        )

    async def _compact_if_needed(self, *, agent_session, turn) -> bool:
        policy = getattr(agent_session, "compression_state", None) or {}
        if not bool(policy.get("enabled", False)):
            return False
        threshold_chars = int(policy.get("threshold_chars") or 12000)
        preserve_recent_messages = int(policy.get("preserve_recent_messages") or 12)
        compacted = await self.transcript.compact_session(
            session_id=str(agent_session.id),
            turn_id=str(turn.id),
            threshold_chars=threshold_chars,
            preserve_recent_messages=preserve_recent_messages,
        )
        if compacted is not None:
            agent_metrics.increment("transcript.compactions")
            return True
        return False

    async def _instructions(self, *, agent_session, turn, exposed_tools=None) -> str:
        del exposed_tools
        execution_target = execution_target_from_session(agent_session)
        system_sections = [resolve_system_prompt_prefix(agent_session.prompt_snapshot)]
        project_instruction_context = await self.project_instructions.resolve(
            agent_session,
            turn=turn,
            execution_target=execution_target,
        )
        if project_instruction_context:
            system_sections.append(project_instruction_context)
        environment_context = await self._environment_context(
            agent_session,
            execution_target=execution_target,
        )
        if environment_context:
            system_sections.append(environment_context)
        memory_context = await self._memory_context(
            agent_session,
            execution_target=execution_target,
        )
        if memory_context:
            system_sections.append(memory_context)
        skills_context = self._skills_context(turn)
        if skills_context:
            system_sections.append(skills_context)
        return "\n\n".join(section for section in system_sections if section)

    async def _environment_context(
        self,
        agent_session,
        *,
        execution_target: dict[str, str],
    ) -> str:
        """Render dynamic context without contradicting the current target."""
        toolset = (getattr(agent_session, "toolset_policy", None) or {}).get(
            "name"
        ) or "default"
        remote_target = is_remote_ssh_execution_target(execution_target)
        lines: list[str] = ["## Environment"]
        if not remote_target:
            lines.append(f"- Working directory: {settings.repo_root}")
            allowed_roots = ", ".join(
                str(root) for root in FilesystemPolicy().allowed_roots
            )
            lines.append(f"- Allowed filesystem roots: {allowed_roots}")
        lines.append(f"- Workspace: {agent_session.workspace_id}")
        if not remote_target:
            lines.append(
                f"- Active project: {agent_session.project_id or 'none (workspace scope)'}"
            )
        lines.append(
            "- Permission mode: "
            f"{getattr(agent_session, 'permission_mode', 'guarded_auto')} "
            f"(automation: {getattr(agent_session, 'automation_mode', 'assisted')}). "
            "Read and low-risk actions run automatically; elevated-risk actions pause "
            "for the user's approval."
        )
        lines.append(f"- Runtime mode: {getattr(agent_session, 'runtime_mode', 'api')}")
        lines.append(
            f"- Role profile: {getattr(agent_session, 'role_profile', 'bioinformatician')}"
        )
        lines.append(f"- Toolset policy: {toolset}")
        lines.append(f"- Execution target: {execution_target.get('type', 'local')}")
        if toolset == "plan":
            lines.append(
                "- PLAN MODE: read and search tools only. Investigate, then call "
                "exit_plan_mode with a concrete plan to request approval to act."
            )

        if remote_target:
            remote_context = await render_remote_connection_context(
                self.db,
                agent_session,
                execution_target=execution_target,
            )
            if remote_context:
                lines.append("")
                lines.append(remote_context)
        else:
            inventory = await self._platform_inventory(agent_session)
            if inventory:
                lines.append("")
                lines.append("## Platform inventory")
                lines.extend(inventory)
            lines.append("")
            lines.append(_local_platform_context())

        return "\n".join(lines)

    async def _platform_inventory(self, agent_session) -> list[str]:
        async def _count(coro) -> int | None:
            try:
                _items, pagination = await coro
                return int(pagination.total_count or 0)
            except Exception:  # noqa: BLE001 — inventory must never break a turn
                return None

        workspace_id = str(agent_session.workspace_id)
        workflows = await _count(WorkflowRepository(self.db).list(limit=1))
        images = await _count(ImageRepository(self.db).list(limit=1))
        runs = await _count(
            RunRepository(self.db).list(limit=1, workspace_id=workspace_id)
        )
        projects = await _count(
            ProjectRepository(self.db).list(limit=1, workspace_id=workspace_id)
        )
        lines: list[str] = []
        for label, value in (
            ("Workflows", workflows),
            ("Images", images),
            ("Runs", runs),
            ("Projects", projects),
        ):
            if value is not None:
                lines.append(f"- {label}: {value}")
        return lines

    async def _memory_context(
        self,
        agent_session,
        *,
        execution_target: dict[str, str],
    ) -> str | None:
        project_id = await self._memory_project_id(
            agent_session,
            execution_target=execution_target,
        )
        memories = await self.memories.list_for_workspace(
            workspace_id=str(agent_session.workspace_id),
            project_id=project_id,
            status=AgentMemoryStatus.ACCEPTED,
            scope="workspace" if project_id is None else None,
        )
        if not memories:
            return None
        lines = ["Accepted durable Bioinfoflow memory:"]
        for memory in memories[:20]:
            lines.append(f"- {memory.scope}/{memory.type}: {memory.content}")
        return "\n".join(lines)

    async def _memory_project_id(
        self,
        agent_session,
        *,
        execution_target: dict[str, str],
    ) -> str | None:
        project_id = getattr(agent_session, "project_id", None)
        if not project_id:
            return None
        if not is_remote_ssh_execution_target(execution_target):
            return str(project_id)
        remote_project = await selected_remote_project(self.db, agent_session)
        if remote_project is None:
            return None
        if str(remote_project.remote_connection_id) != execution_target.get(
            "connection_id"
        ):
            return None
        return str(project_id)

    def _skills_context(self, turn) -> str | None:
        skills = AgentSkillRegistry.from_default_roots()
        plugins = AgentPluginRegistry.from_directory(
            state_root() / "agent_core" / "plugins"
        )
        lines: list[str] = []
        if skills.list():
            lines.append("## Agent skills")
            lines.append(
                "Skill summaries are available every turn. Load full skill bodies only "
                "when the skill is relevant or explicitly requested."
            )
            summary = skills.describe_for_prompt(
                max_chars=SKILL_PROMPT_SUMMARY_BUDGET_CHARS
            )
            if summary:
                lines.extend(summary.splitlines())

        active_skill_names = _active_skill_names_for_turn(turn)
        if active_skill_names:
            lines.append("")
            lines.append("## Active skills for this turn")
            lines.append(
                "The user explicitly activated these skills for the current turn. "
                "Treat them as task guidance below system policy, tool schemas, "
                "permission policy, and the user's latest request."
            )
            try:
                active_skills = resolve_active_skills(skills, active_skill_names)
            except ActiveSkillResolutionError as exc:
                active_skills = []
                lines.append(f"Unavailable active skills: {', '.join(exc.missing)}")
            for skill in active_skills:
                lines.append("")
                lines.append(f"### {skill.name} ({skill.version})")
                lines.append(skill.body)

        enabled_plugins = plugins.list()
        if enabled_plugins:
            lines.append("Enabled plugins:")
            for plugin in enabled_plugins[:20]:
                lines.append(
                    f"- {plugin.id} ({plugin.version}): tools={plugin.tools}, skills={plugin.skills}"
                )
        return "\n".join(lines) if lines else None


def _active_skill_names_for_turn(turn) -> list[str]:
    snapshot = getattr(turn, "model_profile_snapshot", None) or {}
    metadata = snapshot.get("metadata") if isinstance(snapshot, dict) else None
    if not isinstance(metadata, dict):
        return []
    names = metadata.get("active_skill_names")
    if not isinstance(names, list):
        return []
    return [name for name in names if isinstance(name, str) and name.strip()]


def _complete_provider_groups(messages: list[dict]) -> list[dict]:
    """Exclude incomplete assistant/tool groups and orphan tool messages."""
    complete: list[dict] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        tool_calls = (
            message.get("tool_calls") if message.get("role") == "assistant" else None
        )
        if tool_calls:
            expected = [str(call.get("id")) for call in tool_calls if call.get("id")]
            group = [message]
            seen: list[str] = []
            cursor = index + 1
            while cursor < len(messages) and messages[cursor].get("role") == "tool":
                tool_message = messages[cursor]
                group.append(tool_message)
                if tool_message.get("tool_call_id"):
                    seen.append(str(tool_message["tool_call_id"]))
                cursor += 1
            if expected and len(seen) == len(expected) and set(seen) == set(expected):
                by_id = {str(item["tool_call_id"]): item for item in group[1:]}
                complete.append(message)
                complete.extend(by_id[tool_call_id] for tool_call_id in expected)
            index = cursor
            continue
        if message.get("role") != "tool":
            complete.append(message)
        index += 1
    return complete


def model_context_from_messages(messages: list[dict[str, Any]]) -> AgentModelContext:
    instruction_parts: list[str] = []
    input_items: list[InputPart] = []
    for message in messages:
        role = str(message.get("role") or "")
        text = message.get("content") if isinstance(message.get("content"), str) else ""
        if role == "system":
            if text:
                instruction_parts.append(text)
            continue
        parts: list[dict[str, Any]] = []
        if text:
            text_part: dict[str, Any] = {"type": "text", "text": text}
            phase = message.get("phase")
            if phase in {"commentary", "final_answer"}:
                text_part["phase"] = phase
            parts.append(text_part)
        raw_calls = message.get("tool_calls")
        if isinstance(raw_calls, list):
            parts.append({"type": "tool_calls", "tool_calls": raw_calls})
        input_items.extend(
            model_input_parts_from_message(
                role,
                parts,
                {
                    "tool_call_id": message.get("tool_call_id"),
                    "is_error": message.get("is_error", False),
                },
            )
        )
    return AgentModelContext(
        instructions="\n\n".join(instruction_parts),
        input_items=tuple(input_items),
    )


def _local_platform_context() -> str:
    return """\
## Bioinfoflow local platform
- Prefer dedicated Bioinfoflow tools for platform state. Use shell for repository
  work, tests, and operations with no dedicated platform tool.
- Before `runs.submit`, identify the exact project and workflow, confirm the
  project binding when relevant, and inspect `workflows.form_spec`. Copy its
  field keys exactly into the `runs.submit.values` object; do not infer keys
  from prose or filenames.
- Use lifecycle mutations only for the requested action: create or update the
  selected resource, submit/cancel/retry/resume the selected run, or perform the
  explicit cleanup/delete. Do not add registration or binding work unless the
  task requires it.
- After any mutation, use the matching get/list/status tool for read-back
  verification. For run diagnosis, gather the narrowest useful logs, outputs,
  DAG, audit, scheduler, or resource evidence before explaining the result.
"""
