from __future__ import annotations

import posixpath
import shlex
import uuid
from collections.abc import Callable
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_core_repo import AgentSessionRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.remote_connection_repo import RemoteConnectionRepository
from app.services.authorization_service import AuthorizationService
from app.services.agent_core.execution_target import (
    execution_scope_allows_remote,
    execution_scope_mode,
    selected_remote_connection_ids_from_policy,
)
from app.services.agent_core.permissions.remote_boundary import RemoteBoundaryResolver
from app.services.agent_core.permissions.command_risk import (
    CommandRiskAssessment,
    CommandTargetProfile,
    assess_command_risk,
    protected_resources_for_paths,
)
from app.services.agent_core.permissions.risk import RiskAssessment
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.remote_connection_service import remote_connection_config_from_model
from app.services.remote_execution import (
    RemoteCommandResult,
    RemoteConnectionConfig,
    RemoteExecutor,
    SshRemoteExecutor,
)
from app.utils.exceptions import BadRequestError, NotFoundError, PermissionDeniedError


ResolverFactory = Callable[[AsyncSession], "RemoteConnectionResolver"]


class RemoteConnectionResolver(Protocol):
    async def list(
        self,
        *,
        workspace_id: str,
        user_id: str,
        session_id: str | None = None,
    ) -> list[RemoteConnectionConfig]:
        """List remote connections visible to the current agent context."""

    async def get(
        self,
        connection_id: str,
        *,
        workspace_id: str,
        user_id: str,
        session_id: str | None = None,
    ) -> RemoteConnectionConfig:
        """Resolve one remote connection visible to the current agent context."""


class StaticRemoteConnectionResolver:
    def __init__(self, connections: list[RemoteConnectionConfig]) -> None:
        self.connections = connections

    async def list(
        self,
        *,
        workspace_id: str,
        user_id: str,
        session_id: str | None = None,
    ) -> list[RemoteConnectionConfig]:
        del workspace_id, user_id, session_id
        return list(self.connections)

    async def get(
        self,
        connection_id: str,
        *,
        workspace_id: str,
        user_id: str,
        session_id: str | None = None,
    ) -> RemoteConnectionConfig:
        del workspace_id, user_id, session_id
        for connection in self.connections:
            if connection.id == connection_id:
                return connection
        raise NotFoundError("Remote connection not found")


class DatabaseRemoteConnectionResolver:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(
        self,
        *,
        workspace_id: str,
        user_id: str,
        session_id: str | None = None,
    ) -> list[RemoteConnectionConfig]:
        allowed_ids = await _selected_remote_connection_ids(
            self.db,
            workspace_id=workspace_id,
            user_id=user_id,
            session_id=session_id,
        )
        if not allowed_ids:
            return []

        repo = RemoteConnectionRepository(self.db)
        connections: list[RemoteConnectionConfig] = []
        for connection_id in allowed_ids:
            connection = await repo.get_for_workspace(
                connection_id,
                workspace_id=workspace_id,
            )
            if connection is not None:
                connections.append(remote_connection_config_from_model(connection))
        return connections

    async def get(
        self,
        connection_id: str,
        *,
        workspace_id: str,
        user_id: str,
        session_id: str | None = None,
    ) -> RemoteConnectionConfig:
        for connection in await self.list(
            workspace_id=workspace_id,
            user_id=user_id,
            session_id=session_id,
        ):
            if connection.id == connection_id:
                return connection
        raise NotFoundError("Remote connection not found")


SessionMetadataRemoteConnectionResolver = DatabaseRemoteConnectionResolver


class RemoteConnectionsListTool:
    spec = AgentToolSpec(
        name="remote.connections.list",
        description=(
            "List SSH-backed remote connections available in the current workspace. "
            "In auto target mode, call this before choosing a machine, then copy the "
            "returned opaque connection_id exactly into a remote operation. In manual "
            "mode, only user-selected connections are returned."
        ),
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
                "connections": {"type": "array"},
                "total_count": {"type": "integer"},
            },
            "required": ["connections", "total_count"],
        },
        risk_level="read",
        read_scope=["remote_connections"],
        audit="List remote connections visible to the agent.",
    )

    def __init__(self, resolver_factory: ResolverFactory | None = None) -> None:
        self.resolver_factory = (
            resolver_factory or SessionMetadataRemoteConnectionResolver
        )

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        resolver = self.resolver_factory(context.db)
        connections = await resolver.list(
            workspace_id=context.workspace_id,
            user_id=context.user_id,
            session_id=context.session_id,
        )
        search = str(input.get("search") or "").casefold()
        if search:
            connections = [
                connection
                for connection in connections
                if _connection_matches(connection, search)
            ]
        limit = int(input.get("limit") or 50)
        return {
            "connections": [connection.summary() for connection in connections[:limit]],
            "total_count": len(connections),
        }


class RemoteExecTool:
    spec = AgentToolSpec(
        name="remote.exec",
        description=(
            "Run a bounded SSH command on a selected remote connection. In auto mode, "
            "first use remote.connections.list and copy its opaque connection_id; in "
            "manual mode, stay within the user-selected target fence."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "minLength": 1},
                "command": {"type": "string", "minLength": 1, "maxLength": 4000},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 60},
                "output_limit": {"type": "integer", "minimum": 100, "maximum": 50000},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "connection": {"type": "object"},
                "command": {"type": "string"},
                "result": {"type": "object"},
            },
            "required": ["connection", "command", "result"],
        },
        risk_level="act_high",
        read_scope=["remote_connections"],
        write_scope=["remote_shell"],
        audit="Run a bounded diagnostic command over SSH.",
        rollback_hint="Inspect the command and remote shell history; undo any remote changes manually.",
        timeout_seconds=70,
        artifact_policy={"stdout": True, "stderr": True, "type": "remote_command"},
    )

    def __init__(
        self,
        *,
        resolver_factory: ResolverFactory | None = None,
        executor: RemoteExecutor | None = None,
    ) -> None:
        self.resolver_factory = (
            resolver_factory or SessionMetadataRemoteConnectionResolver
        )
        self.executor = executor or SshRemoteExecutor()

    def assess_risk(
        self,
        input: dict[str, Any],
        *,
        target: CommandTargetProfile | None = None,
    ) -> CommandRiskAssessment | None:
        command = input.get("command")
        if not isinstance(command, str) or not command.strip() or target is None:
            return None
        connection_id = input.get("connection_id")
        return assess_command_risk(
            command,
            target=target,
            requested_connection_id=(
                connection_id.strip()
                if isinstance(connection_id, str) and connection_id.strip()
                else None
            ),
        )

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        await _require_remote_operation_access(context)
        connection, working_directory = await _resolve_claimed_remote_target(
            input, context, self.resolver_factory
        )
        command = _required_string(input, "command")
        remote_command = _command_in_remote_working_directory(
            command, working_directory
        )
        result = await self.executor.run(
            connection,
            remote_command,
            timeout_seconds=int(input.get("timeout_seconds") or 15),
            output_limit=int(input.get("output_limit") or 12000),
        )
        return {
            "connection": connection.summary(),
            "command": command,
            "working_directory": working_directory,
            "result": result.observation(),
        }


class RemoteReadFileTool:
    spec = AgentToolSpec(
        name="remote.read_file",
        description=(
            "Read bounded text from a file on a selected SSH remote connection. "
            "Copy an opaque connection_id from remote.connections.list in auto mode; "
            "manual mode permits only user-selected targets. Output is capped."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "minLength": 1},
                "path": {"type": "string", "minLength": 1},
                "max_bytes": {"type": "integer", "minimum": 1, "maximum": 65536},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 30},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "connection": {"type": "object"},
                "path": {"type": "string"},
                "content": {"type": "string"},
                "result": {"type": "object"},
            },
            "required": ["connection", "path", "content", "result"],
        },
        risk_level="read",
        read_scope=["remote_connections", "remote_files"],
        audit="Read bounded remote file content over SSH.",
        timeout_seconds=40,
        artifact_policy={"stdout": True, "stderr": True, "type": "remote_file"},
    )

    def __init__(
        self,
        *,
        resolver_factory: ResolverFactory | None = None,
        executor: RemoteExecutor | None = None,
    ) -> None:
        self.resolver_factory = (
            resolver_factory or SessionMetadataRemoteConnectionResolver
        )
        self.executor = executor or SshRemoteExecutor()

    def assess_risk(
        self,
        input: dict[str, Any],
        *,
        target: CommandTargetProfile | None = None,
    ) -> RiskAssessment | None:
        return _assess_structured_remote_path(input, target=target)

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        await _require_remote_operation_access(context)
        connection, working_directory = await _resolve_claimed_remote_target(
            input, context, self.resolver_factory
        )
        path = _remote_path_for_context(
            _required_string(input, "path"),
            working_directory,
            allow_outside_root=_action_allows_remote_outside_root(context),
        )
        max_bytes = int(input.get("max_bytes") or 16000)
        result = await self.executor.run(
            connection,
            _read_file_command(
                path,
                max_bytes,
                working_directory
                if _remote_path_within_root(path, working_directory)
                else None,
            ),
            timeout_seconds=int(input.get("timeout_seconds") or 10),
            output_limit=max_bytes + 1,
        )
        content_truncated = len(result.stdout) > max_bytes
        content = result.stdout[:max_bytes]
        observation = _result_observation(
            result,
            force_truncated=content_truncated,
            stdout=content,
        )
        return {
            "connection": connection.summary(),
            "path": path,
            "working_directory": working_directory,
            "content": content,
            "result": observation,
        }


class RemoteListDirTool:
    spec = AgentToolSpec(
        name="remote.list_dir",
        description=(
            "List a remote directory on a selected SSH connection. Returns a bounded "
            "set of entries. Copy the opaque connection_id from remote.connections.list "
            "in auto mode; manual mode permits only user-selected targets."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "minLength": 1},
                "path": {"type": "string", "minLength": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 30},
                "output_limit": {"type": "integer", "minimum": 100, "maximum": 50000},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "connection": {"type": "object"},
                "path": {"type": "string"},
                "entries": {"type": "array"},
                "result": {"type": "object"},
            },
            "required": ["connection", "path", "entries", "result"],
        },
        risk_level="read",
        read_scope=["remote_connections", "remote_files"],
        audit="List bounded remote directory entries over SSH.",
        timeout_seconds=40,
        artifact_policy={"stdout": True, "stderr": True, "type": "remote_directory"},
    )

    def __init__(
        self,
        *,
        resolver_factory: ResolverFactory | None = None,
        executor: RemoteExecutor | None = None,
    ) -> None:
        self.resolver_factory = (
            resolver_factory or SessionMetadataRemoteConnectionResolver
        )
        self.executor = executor or SshRemoteExecutor()

    def assess_risk(
        self,
        input: dict[str, Any],
        *,
        target: CommandTargetProfile | None = None,
    ) -> RiskAssessment | None:
        return _assess_structured_remote_path(input, target=target)

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        await _require_remote_operation_access(context)
        connection, working_directory = await _resolve_claimed_remote_target(
            input, context, self.resolver_factory
        )
        path = _remote_path_for_context(
            _required_string(input, "path"),
            working_directory,
            allow_outside_root=_action_allows_remote_outside_root(context),
        )
        limit = int(input.get("limit") or 50)
        result = await self.executor.run(
            connection,
            _list_dir_command(
                path,
                limit,
                working_directory
                if _remote_path_within_root(path, working_directory)
                else None,
            ),
            timeout_seconds=int(input.get("timeout_seconds") or 10),
            output_limit=int(input.get("output_limit") or 20000),
        )
        entries = _parse_find_entries(result.stdout)
        entries_truncated = len(entries) > limit
        return {
            "connection": connection.summary(),
            "path": path,
            "working_directory": working_directory,
            "entries": entries[:limit],
            "result": _result_observation(result, force_truncated=entries_truncated),
        }


async def _resolve_connection(
    input: dict[str, Any],
    context: AgentToolContext,
    resolver_factory: ResolverFactory,
) -> RemoteConnectionConfig:
    resolver = resolver_factory(context.db)
    connection_id = input.get("connection_id")
    if isinstance(connection_id, str) and connection_id.strip():
        return await resolver.get(
            connection_id.strip(),
            workspace_id=context.workspace_id,
            user_id=context.user_id,
            session_id=context.session_id,
        )
    connections = await resolver.list(
        workspace_id=context.workspace_id,
        user_id=context.user_id,
        session_id=context.session_id,
    )
    if len(connections) == 1:
        return connections[0]
    if not connections:
        raise NotFoundError("Remote connection not found")
    raise BadRequestError(
        "connection_id is required when multiple remote connections are selected"
    )


async def _resolve_claimed_remote_target(
    input: dict[str, Any],
    context: AgentToolContext,
    resolver_factory: ResolverFactory,
) -> tuple[RemoteConnectionConfig, str | None]:
    snapshot = context.permission_context_snapshot
    if not isinstance(snapshot, dict):
        connection = await _resolve_connection(input, context, resolver_factory)
        return connection, await _remote_working_directory(context, connection.id)

    execution_target = snapshot.get("execution_target")
    execution_scope = snapshot.get("execution_scope")
    if (
        isinstance(execution_scope, dict)
        and execution_scope_allows_remote(execution_scope)
        and (
            not isinstance(execution_target, dict)
            or execution_target.get("type") != "remote_ssh"
        )
    ):
        claimed_connection_id = str(snapshot.get("scope_remote_connection_id") or "")
        if claimed_connection_id:
            requested_connection_id = input.get("connection_id")
            if (
                isinstance(requested_connection_id, str)
                and requested_connection_id.strip()
                and requested_connection_id.strip() != claimed_connection_id
            ):
                raise PermissionDeniedError(
                    "Remote connection differs from the authorized target"
                )
            resolver = resolver_factory(context.db)
            try:
                connection = await resolver.get(
                    claimed_connection_id,
                    workspace_id=context.workspace_id,
                    user_id=context.user_id,
                    session_id=context.session_id,
                )
            except NotFoundError as exc:
                raise PermissionDeniedError(
                    "Remote connection changed after the action was authorized"
                ) from exc
        else:
            connection = await _resolve_connection(input, context, resolver_factory)
        agent_session = await AgentSessionRepository(context.db).get_fresh(
            context.session_id
        )
        if agent_session is None:
            raise PermissionDeniedError("Agent session is not accessible")
        if (
            str(agent_session.workspace_id) != context.workspace_id
            or str(agent_session.user_id) != context.user_id
        ):
            raise PermissionDeniedError("Agent session is not accessible")
        if int(agent_session.permission_policy_version) != int(
            snapshot.get("policy_version") or 0
        ):
            raise PermissionDeniedError(
                "Remote target changed after the action was authorized"
            )
        if claimed_connection_id:
            boundary = await RemoteBoundaryResolver(context.db).resolve(
                agent_session=agent_session,
                connection_id=claimed_connection_id,
            )
            claimed_roots = snapshot.get("effective_roots")
            claimed_root = (
                str(claimed_roots[0])
                if isinstance(claimed_roots, list) and claimed_roots
                else None
            )
            if (
                snapshot.get("remote_identity") != boundary.remote_identity
                or snapshot.get("resource_revisions") != boundary.resource_revisions
                or claimed_root != boundary.effective_root
            ):
                raise PermissionDeniedError(
                    "Remote target changed after the action was authorized"
                )
            return connection, claimed_root
        return connection, await _remote_working_directory(context, connection.id)

    if (
        not isinstance(execution_target, dict)
        or execution_target.get("type") != "remote_ssh"
    ):
        raise PermissionDeniedError("Authorized remote execution target is unavailable")
    claimed_connection_id = str(execution_target.get("connection_id") or "")
    if not claimed_connection_id:
        raise PermissionDeniedError("Authorized remote connection is unavailable")
    requested_connection_id = input.get("connection_id")
    if (
        isinstance(requested_connection_id, str)
        and requested_connection_id.strip()
        and requested_connection_id.strip() != claimed_connection_id
    ):
        raise PermissionDeniedError(
            "Remote connection differs from the authorized target"
        )

    resolver = resolver_factory(context.db)
    try:
        connection = await resolver.get(
            claimed_connection_id,
            workspace_id=context.workspace_id,
            user_id=context.user_id,
            session_id=context.session_id,
        )
    except NotFoundError as exc:
        raise PermissionDeniedError(
            "Remote connection changed after the action was authorized"
        ) from exc

    agent_session = await AgentSessionRepository(context.db).get_fresh(
        context.session_id
    )
    if agent_session is None:
        raise PermissionDeniedError("Agent session is not accessible")
    if (
        str(agent_session.workspace_id) != context.workspace_id
        or str(agent_session.user_id) != context.user_id
    ):
        raise PermissionDeniedError("Agent session is not accessible")
    boundary = await RemoteBoundaryResolver(context.db).resolve(
        agent_session=agent_session,
        connection_id=claimed_connection_id,
    )
    claimed_roots = snapshot.get("effective_roots")
    claimed_root = (
        str(claimed_roots[0])
        if isinstance(claimed_roots, list) and claimed_roots
        else None
    )
    current_identity = boundary.remote_identity
    current_revisions = boundary.resource_revisions
    if (
        int(agent_session.permission_policy_version)
        != int(snapshot.get("policy_version") or 0)
        or snapshot.get("remote_identity") != current_identity
        or snapshot.get("resource_revisions") != current_revisions
        or claimed_root != boundary.effective_root
    ):
        raise PermissionDeniedError(
            "Remote target changed after the action was authorized"
        )
    return connection, claimed_root


async def _require_remote_operation_access(context: AgentToolContext) -> None:
    await AuthorizationService(context.db).require_destructive_business_access(
        workspace_id=context.workspace_id,
        user_id=context.user_id,
    )


async def _selected_remote_connection_ids(
    db: AsyncSession,
    *,
    workspace_id: str,
    user_id: str,
    session_id: str | None,
) -> list[str]:
    if not session_id:
        return []
    try:
        uuid.UUID(str(session_id))
    except (TypeError, ValueError):
        return []
    session = await AgentSessionRepository(db).get(session_id)
    if session is None:
        return []
    if str(session.workspace_id) != workspace_id or str(session.user_id) != user_id:
        return []
    metadata = getattr(session, "session_metadata", None)
    scope_mode = (
        execution_scope_mode(metadata.get("execution_scope"))
        if isinstance(metadata, dict)
        else None
    )
    if scope_mode == "manual":
        return _selected_remote_connection_ids_from_policies(metadata)
    if scope_mode == "auto":
        return await _all_remote_connection_ids_for_workspace(
            db=db,
            workspace_id=workspace_id,
        )

    project_connection_id = await _session_remote_project_connection_id(db, session)
    if project_connection_id:
        return [project_connection_id]

    return _selected_remote_connection_ids_from_policies(
        metadata,
        getattr(session, "context_policy", None),
        getattr(session, "toolset_policy", None),
    )


async def _all_remote_connection_ids_for_workspace(
    *,
    db: AsyncSession,
    workspace_id: str,
) -> list[str]:
    repo = RemoteConnectionRepository(db)
    selected: list[str] = []
    cursor: str | None = None
    while True:
        connections, pagination = await repo.list_for_workspace(
            workspace_id=workspace_id,
            limit=100,
            cursor=cursor,
        )
        selected.extend(str(connection.id) for connection in connections)
        if not pagination.has_more or not pagination.next_cursor:
            break
        cursor = pagination.next_cursor
    return selected


def _selected_remote_connection_ids_from_policies(*policies: Any) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for policy in policies:
        for connection_id in _selected_ids_from_policy(policy):
            if not _is_uuid_string(connection_id):
                continue
            if connection_id in seen:
                continue
            seen.add(connection_id)
            selected.append(connection_id)
    return selected


async def _session_remote_project_connection_id(
    db: AsyncSession, session
) -> str | None:
    project = await _session_remote_project(db, session)
    if not project:
        return None
    connection_id = getattr(project, "remote_connection_id", None)
    return str(connection_id) if connection_id else None


async def _session_remote_project(db: AsyncSession, session):
    project_id = getattr(session, "project_id", None)
    if not project_id:
        return None
    project = await ProjectRepository(db).get_fresh(str(project_id))
    if not project or getattr(project, "storage_mode", None) != "remote":
        return None
    return project


async def _remote_working_directory(
    context: AgentToolContext,
    connection_id: str,
) -> str | None:
    session_id = context.session_id
    if not session_id or not _is_uuid_string(str(session_id)):
        return None
    session = await AgentSessionRepository(context.db).get_fresh(str(session_id))
    if session is None:
        return None
    if (
        str(session.workspace_id) != context.workspace_id
        or str(session.user_id) != context.user_id
    ):
        return None
    boundary = await RemoteBoundaryResolver(context.db).resolve(
        agent_session=session,
        connection_id=connection_id,
    )
    return boundary.effective_root


def _command_in_remote_working_directory(
    command: str, working_directory: str | None
) -> str:
    if not working_directory:
        return command
    return f"cd {shlex.quote(working_directory)} && {command}"


def _remote_path_for_context(
    path: str,
    working_directory: str | None,
    *,
    allow_outside_root: bool = False,
) -> str:
    if not working_directory:
        return path
    normalized = str(path or "").strip().replace("\\", "/")
    if "\x00" in normalized:
        raise BadRequestError("remote path contains an invalid character")
    if "$" in normalized or "`" in normalized:
        raise BadRequestError("remote path contains dynamic shell syntax")
    root = posixpath.normpath(working_directory)
    if normalized.startswith("~"):
        raise BadRequestError("home-relative paths are outside the remote project")
    if normalized.startswith("/"):
        absolute = posixpath.normpath(normalized)
        if absolute == root or absolute.startswith(f"{root.rstrip('/')}/"):
            return absolute
        if allow_outside_root and not _structured_remote_path_requires_explicit(
            absolute
        ):
            return absolute
        raise BadRequestError("absolute remote path is outside the remote project")
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise BadRequestError("relative remote path cannot escape the remote project")
    relative = posixpath.normpath("/".join(parts)) if parts else "."
    if relative == ".":
        return root
    return f"{root.rstrip('/')}/{relative}"


def _remote_path_within_root(path: str, working_directory: str | None) -> bool:
    if not working_directory:
        return False
    normalized = posixpath.normpath(path)
    root = posixpath.normpath(working_directory)
    return normalized == root or normalized.startswith(f"{root.rstrip('/')}/")


def _action_allows_remote_outside_root(context: AgentToolContext) -> bool:
    snapshot = context.permission_context_snapshot
    if not isinstance(snapshot, dict):
        return False
    decision = snapshot.get("action_permission_decision")
    if not isinstance(decision, dict):
        return False
    return decision.get("decision") in {"allow", "approve", "modify"}


def _assess_structured_remote_path(
    input: dict[str, Any],
    *,
    target: CommandTargetProfile | None,
) -> RiskAssessment | None:
    path = input.get("path")
    if not isinstance(path, str) or not path.strip():
        return None
    normalized = path.strip().replace("\\", "/")
    if target is None or target.kind != "remote_ssh":
        return RiskAssessment(
            level="act_high",
            reasons=[
                "structured remote path is not bounded by an effective project root",
                "explicit approval is required when the remote target is selected at runtime",
            ],
            affected_resources=[{"type": "path", "id": normalized[:1000]}],
            requires_explicit_approval=True,
        )
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    dynamic_or_traversal = (
        normalized.startswith(("~", "$"))
        or "$" in normalized
        or "`" in normalized
        or any(part == ".." for part in parts)
    )
    protected = _structured_remote_path_requires_explicit(normalized)
    outside_root = False
    if target.read_roots and normalized.startswith("/"):
        absolute = posixpath.normpath(normalized)
        outside_root = not any(
            absolute == posixpath.normpath(root)
            or absolute.startswith(f"{posixpath.normpath(root).rstrip('/')}/")
            for root in target.read_roots
        )
    absolute_path = normalized.startswith("/")
    unbounded_relative = not absolute_path and (
        not target.read_roots or not target.working_directory
    )
    requires_explicit = unbounded_relative or dynamic_or_traversal or protected
    if requires_explicit:
        return RiskAssessment(
            level="act_high",
            reasons=[
                "structured remote path is not bounded by an effective project root",
                "explicit approval is required for sensitive, home, variable, or traversal paths",
            ],
            affected_resources=[{"type": "path", "id": normalized[:1000]}],
            requires_explicit_approval=True,
        )
    if outside_root or (absolute_path and not target.read_roots):
        return RiskAssessment(
            level="act_high",
            reasons=[
                "structured remote path is outside the effective project root",
                "full access may read non-sensitive absolute remote data paths",
            ],
            affected_resources=[{"type": "path", "id": normalized[:1000]}],
        )
    return RiskAssessment(
        level="read",
        reasons=["structured remote path is a bounded relative read"],
        affected_resources=[{"type": "path", "id": normalized[:1000]}],
    )


def _structured_remote_path_requires_explicit(path: str) -> bool:
    if protected_resources_for_paths([path]):
        return True
    if path.startswith(("~", "$")) or "$" in path or "`" in path:
        return True
    normalized = posixpath.normpath(path)
    lowered = normalized.casefold()
    return lowered == "/etc" or lowered.startswith(
        (
            "/etc/",
            "/root/",
            "/proc/",
            "/sys/",
            "/dev/",
            "/private/etc/",
        )
    )


def _selected_ids_from_policy(policy: Any) -> list[str]:
    return selected_remote_connection_ids_from_policy(policy)


def _is_uuid_string(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (TypeError, ValueError):
        return False
    return True


def _connection_matches(connection: RemoteConnectionConfig, search: str) -> bool:
    haystack = " ".join(
        value
        for value in (
            connection.id,
            connection.name,
            connection.host,
            connection.username,
            connection.status,
            connection.skill_summary,
        )
        if value
    ).casefold()
    return search in haystack


def _required_string(input: dict[str, Any], key: str) -> str:
    value = input.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BadRequestError(f"{key} must be a non-empty string")
    return value


def _remote_scope_guard_command(path: str, working_directory: str | None) -> str:
    if not working_directory:
        return ""
    quoted_root = shlex.quote(working_directory)
    quoted_path = shlex.quote(path)
    return (
        f"root={quoted_root}; target={quoted_path}; "
        'root_real=$(realpath -- "$root") || exit 23; '
        'target_real=$(realpath -- "$target") || exit 23; '
        'case "$target_real" in "$root_real"|"$root_real"/*) ;; '
        "*) printf '%s\\n' 'remote path is outside the remote project' >&2; exit 23;; "
        "esac; "
    )


def _read_file_command(
    path: str,
    max_bytes: int,
    working_directory: str | None = None,
) -> str:
    scope_guard = _remote_scope_guard_command(path, working_directory)
    quoted_path = shlex.quote(path)
    read_bytes = max_bytes + 1
    return (
        scope_guard + f"if [ -d {quoted_path} ]; then "
        "printf '%s\\n' 'remote path is a directory' >&2; exit 21; "
        f"fi; head -c {read_bytes} -- {quoted_path}"
    )


def _list_dir_command(
    path: str,
    limit: int,
    working_directory: str | None = None,
) -> str:
    scope_guard = _remote_scope_guard_command(path, working_directory)
    quoted_path = shlex.quote(path)
    line_limit = limit + 1
    return (
        scope_guard + f"dir={quoted_path}; "
        'if [ ! -d "$dir" ]; then '
        "printf '%s\\n' 'remote path is not a directory' >&2; exit 22; "
        "fi; "
        'for child in "$dir"/* "$dir"/.[!.]* "$dir"/..?*; do '
        '[ -e "$child" ] || [ -L "$child" ] || continue; '
        "name=${child##*/}; "
        'if [ "$name" = . ] || [ "$name" = .. ]; then continue; fi; '
        'if [ -d "$child" ]; then kind=d; '
        'elif [ -L "$child" ]; then kind=l; '
        'elif [ -f "$child" ]; then kind=f; '
        "else kind=o; fi; "
        'if [ "$kind" = f ]; then '
        'size=$(wc -c < "$child" 2>/dev/null || printf 0); '
        "size=${size##* }; else size=0; fi; "
        'printf "%s\\t%s\\t%s\\n" "$kind" "$name" "$size"; '
        f"done | sort | head -n {line_limit}"
    )


def _parse_find_entries(stdout: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        kind_code, name, size = _parse_find_line(line)
        if kind_code is None:
            continue
        entries.append(
            {
                "kind": _find_kind(kind_code),
                "name": name,
                "size_bytes": size,
            }
        )
    return entries


def _parse_find_line(line: str) -> tuple[str | None, str, int]:
    parts = line.split("\t", 2)
    if len(parts) != 3:
        return None, "", 0
    try:
        size = int(parts[2])
    except ValueError:
        size = 0
    return parts[0], parts[1], size


def _find_kind(code: str) -> str:
    return {
        "f": "file",
        "d": "directory",
        "l": "symlink",
    }.get(code, "other")


def _result_observation(
    result: RemoteCommandResult,
    *,
    force_truncated: bool = False,
    stdout: str | None = None,
) -> dict[str, int | str | bool]:
    observation = result.observation()
    if stdout is not None:
        observation["stdout"] = stdout
    if force_truncated:
        observation["truncated"] = True
        observation["stdout_truncated"] = True
    return observation
