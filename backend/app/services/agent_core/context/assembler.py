from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent_core import AgentMemoryStatus
from app.path_layout import state_root
from app.repositories.agent_core_repo import AgentMemoryRepository
from app.repositories.image_repo import ImageRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.run_repo import RunRepository
from app.repositories.workflow_repo import WorkflowRepository
from app.services.agent_core.context.system_prompt import resolve_system_prompt_prefix
from app.services.agent_core.plugins import AgentPluginRegistry
from app.services.agent_core.sandbox import FilesystemPolicy
from app.services.agent_core.skills import AgentSkillRegistry
from app.services.agent_core.metrics import agent_metrics
from app.services.agent_core.transcript import (
    AgentTranscriptStore,
    provider_message_from_parts,
)


class AgentContextAssembler:
    def __init__(self, session: AsyncSession):
        self.db = session
        self.transcript = AgentTranscriptStore(session)
        self.memories = AgentMemoryRepository(session)

    async def provider_messages(
        self,
        *,
        agent_session,
        turn,
        exposed_tools=None,
    ) -> list[dict]:
        await self._compact_if_needed(agent_session=agent_session, turn=turn)
        # Stable, cache-friendly identity prefix comes first; everything that
        # changes per session/turn is appended after it.
        system_sections = [resolve_system_prompt_prefix(agent_session.prompt_snapshot)]
        environment_context = await self._environment_context(
            agent_session, exposed_tools
        )
        if environment_context:
            system_sections.append(environment_context)
        memory_context = await self._memory_context(agent_session)
        if memory_context:
            system_sections.append(memory_context)
        skills_context = self._skills_context()
        if skills_context:
            system_sections.append(skills_context)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": "\n\n".join(section for section in system_sections if section)}
        ]
        for message in await self.transcript.list_messages(str(agent_session.id)):
            if message.status != "committed":
                continue
            if message.role not in {"user", "assistant", "tool"}:
                continue
            messages.append(
                provider_message_from_parts(
                    message.role,
                    message.content_parts or [],
                    getattr(message, "message_metadata", None),
                )
            )
        return [
            message
            for message in messages
            if message.get("content") or message.get("tool_calls")
        ]

    async def _compact_if_needed(self, *, agent_session, turn) -> None:
        policy = getattr(agent_session, "compression_state", None) or {}
        if not bool(policy.get("enabled", False)):
            return
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

    async def _environment_context(self, agent_session, exposed_tools=None) -> str:
        """Dynamic per-turn environment, platform inventory, and tool list.

        This is the single biggest fix for the "what can you do / I can't do
        that" failure mode: the model sees its real working directory, the live
        platform state, and the exact tools it can call every turn. Ordering is
        deterministic so the preceding stable prefix stays cache-identical.
        """
        toolset = (getattr(agent_session, "toolset_policy", None) or {}).get("name") or "default"
        lines: list[str] = ["## Environment"]
        lines.append(f"- Working directory: {settings.repo_root}")
        allowed_roots = ", ".join(str(root) for root in FilesystemPolicy().allowed_roots)
        lines.append(f"- Allowed filesystem roots: {allowed_roots}")
        lines.append(f"- Workspace: {agent_session.workspace_id}")
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
        lines.append(f"- Role profile: {getattr(agent_session, 'role_profile', 'bioinformatician')}")
        lines.append(f"- Toolset policy: {toolset}")
        if toolset == "plan":
            lines.append(
                "- PLAN MODE: read and search tools only. Investigate, then call "
                "exit_plan_mode with a concrete plan to request approval to act."
            )

        inventory = await self._platform_inventory(agent_session)
        if inventory:
            lines.append("")
            lines.append("## Platform inventory")
            lines.extend(inventory)

        tool_lines = _exposed_tool_lines(exposed_tools)
        if tool_lines:
            lines.append("")
            lines.append("## Tools available this turn")
            lines.extend(tool_lines)

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

    async def _memory_context(self, agent_session) -> str | None:
        memories = await self.memories.list_for_workspace(
            workspace_id=str(agent_session.workspace_id),
            project_id=str(agent_session.project_id) if agent_session.project_id else None,
            status=AgentMemoryStatus.ACCEPTED,
        )
        if not memories:
            return None
        lines = ["Accepted durable Bioinfoflow memory:"]
        for memory in memories[:20]:
            lines.append(f"- {memory.scope}/{memory.type}: {memory.content}")
        return "\n".join(lines)

    def _skills_context(self) -> str | None:
        skills = AgentSkillRegistry.from_directory(state_root() / "agent_core" / "skills")
        plugins = AgentPluginRegistry.from_directory(state_root() / "agent_core" / "plugins")
        lines: list[str] = []
        if skills.list():
            lines.append("Available skills:")
            lines.extend(f"- {line}" for line in skills.describe_for_prompt().splitlines())
        enabled_plugins = plugins.list()
        if enabled_plugins:
            lines.append("Enabled plugins:")
            for plugin in enabled_plugins[:20]:
                lines.append(
                    f"- {plugin.id} ({plugin.version}): tools={plugin.tools}, skills={plugin.skills}"
                )
        return "\n".join(lines) if lines else None


def _exposed_tool_lines(exposed_tools) -> list[str]:
    if not exposed_tools:
        return []
    lines: list[str] = []
    for spec in sorted(exposed_tools, key=lambda spec: spec.name):
        summary = str(getattr(spec, "description", "") or "").strip()
        first_sentence = summary.split(". ")[0].rstrip(".")
        lines.append(f"- {spec.name}: {first_sentence}" if first_sentence else f"- {spec.name}")
    return lines
