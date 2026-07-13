from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_core_repo import AgentSessionRepository
from app.services.agent_core.execution_target import execution_target_from_session
from app.utils.exceptions import PermissionDeniedError


@dataclass(frozen=True)
class PermissionContext:
    session_id: str
    policy_version: int
    permission_mode: str
    automation_mode: str
    toolset_policy: dict[str, Any]
    role: str
    role_profile: str
    execution_target: dict[str, str]
    boundary: dict[str, Any]

    def snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "policy_version": self.policy_version,
            "permission_mode": self.permission_mode,
            "automation_mode": self.automation_mode,
            "toolset_policy": self.toolset_policy,
            "role": self.role,
            "role_profile": self.role_profile,
            "execution_target": self.execution_target,
            "boundary": self.boundary,
        }


class PermissionContextResolver:
    def __init__(self, session: AsyncSession):
        self.repository = AgentSessionRepository(session)

    async def resolve(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
    ) -> PermissionContext:
        agent_session = await self.repository.get_fresh(session_id)
        if agent_session is None:
            raise PermissionDeniedError("Agent session is not accessible")
        if (
            str(agent_session.workspace_id) != str(workspace_id)
            or str(agent_session.user_id) != str(user_id)
        ):
            raise PermissionDeniedError("Agent session is not accessible")

        execution_target = execution_target_from_session(agent_session)
        target_type = str(execution_target.get("type") or "local")
        boundary: dict[str, Any] = {
            "kind": "remote_ssh" if target_type == "remote_ssh" else "local",
            "enforcement": "remote_account" if target_type == "remote_ssh" else "workspace",
        }
        if execution_target.get("connection_id"):
            boundary["connection_id"] = execution_target["connection_id"]
        role_profile = str(agent_session.role_profile)
        return PermissionContext(
            session_id=str(agent_session.id),
            policy_version=int(agent_session.permission_policy_version),
            permission_mode=str(agent_session.permission_mode),
            automation_mode=str(agent_session.automation_mode),
            toolset_policy=dict(agent_session.toolset_policy or {"name": "default"}),
            role="worker" if role_profile == "worker" else "orchestrator",
            role_profile=role_profile,
            execution_target=execution_target,
            boundary=boundary,
        )
