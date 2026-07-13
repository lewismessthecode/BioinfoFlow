from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_core_repo import AgentSessionRepository
from app.repositories.remote_connection_repo import RemoteConnectionRepository
from app.models.agent_core import AgentSession
from app.services.agent_core.execution_target import execution_target_from_session
from app.services.agent_core.sandbox import FilesystemPolicy, SandboxRunner
from app.utils.exceptions import PermissionDeniedError


@dataclass(frozen=True)
class PermissionContext:
    session_id: str
    policy_version: int
    permission_mode: str
    automation_mode: str
    toolset_policy: Mapping[str, Any]
    role: str
    role_profile: str
    execution_target: Mapping[str, str]
    boundary: Mapping[str, Any]
    effective_roots: tuple[str, ...]
    remote_identity: Mapping[str, Any] | None

    def snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "policy_version": self.policy_version,
            "permission_mode": self.permission_mode,
            "automation_mode": self.automation_mode,
            "toolset_policy": _thaw(self.toolset_policy),
            "role": self.role,
            "role_profile": self.role_profile,
            "execution_target": _thaw(self.execution_target),
            "boundary": _thaw(self.boundary),
            "effective_roots": list(self.effective_roots),
            "remote_identity": _thaw(self.remote_identity),
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
        context, _agent_session = await self.resolve_with_session(
            session_id=session_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return context

    async def resolve_with_session(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
    ) -> tuple[PermissionContext, AgentSession]:
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
        remote_identity: dict[str, Any] | None = None
        if target_type == "remote_ssh":
            boundary: dict[str, Any] = {
                "kind": "remote_ssh",
                "enforcement": "remote_account",
                "sandboxed": False,
            }
            effective_roots: tuple[str, ...] = ()
            connection_id = execution_target.get("connection_id")
            if connection_id and _is_uuid(connection_id):
                connection = await RemoteConnectionRepository(
                    self.repository.session
                ).get_for_workspace(
                    connection_id,
                    workspace_id=str(agent_session.workspace_id),
                )
                if connection is not None:
                    remote_identity = {
                        "connection_id": str(connection.id),
                        "name": str(connection.name),
                        "host": str(connection.host),
                        "port": int(connection.port),
                        "username": str(connection.username),
                    }
        else:
            filesystem_policy = FilesystemPolicy()
            effective_roots = tuple(
                str(root)[:1000] for root in filesystem_policy.allowed_roots[:16]
            )
            runner = SandboxRunner.from_settings()
            adapter = runner.available_adapter() if runner.enabled else None
            sandboxed = adapter is not None
            boundary = {
                "kind": "local",
                "enforcement": "os_sandbox" if sandboxed else "none",
                "sandboxed": sandboxed,
                "sandbox_type": adapter.name if adapter is not None else "none",
                "filesystem_policy": "allowed_roots",
                "roots_enforced_by": "os_sandbox" if sandboxed else "application_policy",
                "network_allowed": runner.allow_network if sandboxed else True,
            }
        role_profile = str(agent_session.role_profile)
        context = PermissionContext(
            session_id=str(agent_session.id),
            policy_version=int(agent_session.permission_policy_version),
            permission_mode=str(agent_session.permission_mode),
            automation_mode=str(agent_session.automation_mode),
            toolset_policy=_freeze(_bounded_toolset(agent_session.toolset_policy)),
            role="worker" if role_profile == "worker" else "orchestrator",
            role_profile=role_profile,
            execution_target=_freeze(execution_target),
            boundary=_freeze(boundary),
            effective_roots=effective_roots,
            remote_identity=_freeze(remote_identity) if remote_identity else None,
        )
        return context, agent_session


def _bounded_toolset(policy: Any) -> dict[str, Any]:
    source = policy if isinstance(policy, dict) else {}
    name = str(source.get("name") or "default")[:40]
    bounded: dict[str, Any] = {"name": name}
    allowed_tools = source.get("allowed_tools")
    if isinstance(allowed_tools, list):
        bounded["allowed_tools"] = [
            str(tool_name)[:120]
            for tool_name in allowed_tools[:128]
            if isinstance(tool_name, str) and tool_name
        ]
    return bounded


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _is_uuid(value: str) -> bool:
    try:
        UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True
