from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_core import AgentMemoryStatus
from app.path_layout import state_root
from app.repositories.agent_core_repo import AgentMemoryRepository
from app.services.agent_core.context.system_prompt import default_system_prompt_snapshot
from app.services.agent_core.plugins import AgentPluginRegistry
from app.services.agent_core.skills import AgentSkillRegistry
from app.services.agent_core.metrics import agent_metrics
from app.services.agent_core.transcript import (
    AgentTranscriptStore,
    provider_message_from_parts,
)


class AgentContextAssembler:
    def __init__(self, session: AsyncSession):
        self.transcript = AgentTranscriptStore(session)
        self.memories = AgentMemoryRepository(session)

    async def provider_messages(self, *, agent_session, turn) -> list[dict]:
        await self._compact_if_needed(agent_session=agent_session, turn=turn)
        snapshot = agent_session.prompt_snapshot or default_system_prompt_snapshot().as_dict()
        messages: list[dict[str, str]] = [
            {"role": "system", "content": str(snapshot.get("content") or "")}
        ]
        session_context = self._session_context(agent_session)
        if session_context:
            messages.append({"role": "system", "content": session_context})
        memory_context = await self._memory_context(agent_session)
        if memory_context:
            messages.append({"role": "system", "content": memory_context})
        skills_context = self._skills_context()
        if skills_context:
            messages.append({"role": "system", "content": skills_context})
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

    def _session_context(self, agent_session) -> str:
        toolset = (getattr(agent_session, "toolset_policy", None) or {}).get("name") or "default"
        prompt_snapshot = getattr(agent_session, "prompt_snapshot", None) or {}
        return "\n".join(
            [
                f"Prompt snapshot: {prompt_snapshot.get('id') or default_system_prompt_snapshot().id}",
                f"Runtime mode: {getattr(agent_session, 'runtime_mode', 'api')}",
                f"Role profile: {getattr(agent_session, 'role_profile', 'bioinformatician')}",
                f"Permission mode: {getattr(agent_session, 'permission_mode', 'guarded_auto')}",
                f"Automation mode: {getattr(agent_session, 'automation_mode', 'assisted')}",
                f"Toolset policy: {toolset}",
                "Protect continuity across long sessions: use summaries and recent transcript state instead of re-asking for prior context.",
            ]
        )

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
