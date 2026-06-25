from __future__ import annotations

import shlex
from collections.abc import Callable
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_core_repo import AgentSessionRepository
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.remote_execution import (
    RemoteCommandResult,
    RemoteConnectionConfig,
    RemoteExecutor,
    SshRemoteExecutor,
)
from app.utils.exceptions import BadRequestError, NotFoundError


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


class SessionMetadataRemoteConnectionResolver:
    """Temporary resolver until the canonical remote connection service lands.

    Integration point for Agent A: replace this resolver factory with the
    workspace connection repository/service, preserving the public tool input
    and output shape.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(
        self,
        *,
        workspace_id: str,
        user_id: str,
        session_id: str | None = None,
    ) -> list[RemoteConnectionConfig]:
        if not session_id:
            return []
        session = await AgentSessionRepository(self.db).get(session_id)
        if session is None:
            return []
        if str(session.workspace_id) != workspace_id or str(session.user_id) != user_id:
            return []
        return _connections_from_session_policy(session)

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


class RemoteConnectionsListTool:
    spec = AgentToolSpec(
        name="remote.connections.list",
        description=(
            "List SSH-backed remote connections available in the current workspace. "
            "Returns ids, host/user details, status, and skill guidance."
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
        self.resolver_factory = resolver_factory or SessionMetadataRemoteConnectionResolver

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        resolver = self.resolver_factory(context.db)
        connections = await resolver.list(
            workspace_id=context.workspace_id,
            user_id=context.user_id,
            session_id=context.session_id,
        )
        search = str(input.get("search") or "").casefold()
        if search:
            connections = [
                connection for connection in connections if _connection_matches(connection, search)
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
            "Run a short SSH diagnostic command on a selected remote connection. "
            "Use for commands such as hostname, uname, df, module avail, or nextflow -version."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "minLength": 1},
                "command": {"type": "string", "minLength": 1, "maxLength": 4000},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 60},
                "output_limit": {"type": "integer", "minimum": 100, "maximum": 50000},
            },
            "required": ["connection_id", "command"],
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
        self.resolver_factory = resolver_factory or SessionMetadataRemoteConnectionResolver
        self.executor = executor or SshRemoteExecutor()

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        connection = await _resolve_connection(input, context, self.resolver_factory)
        command = _required_string(input, "command")
        result = await self.executor.run(
            connection,
            command,
            timeout_seconds=int(input.get("timeout_seconds") or 15),
            output_limit=int(input.get("output_limit") or 12000),
        )
        return {
            "connection": connection.summary(),
            "command": command,
            "result": result.observation(),
        }


class RemoteReadFileTool:
    spec = AgentToolSpec(
        name="remote.read_file",
        description=(
            "Read bounded text from a file on a selected SSH remote connection. "
            "The path is shell-quoted and output is capped."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "minLength": 1},
                "path": {"type": "string", "minLength": 1},
                "max_bytes": {"type": "integer", "minimum": 1, "maximum": 65536},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 30},
            },
            "required": ["connection_id", "path"],
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
        self.resolver_factory = resolver_factory or SessionMetadataRemoteConnectionResolver
        self.executor = executor or SshRemoteExecutor()

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        connection = await _resolve_connection(input, context, self.resolver_factory)
        path = _required_string(input, "path")
        max_bytes = int(input.get("max_bytes") or 16000)
        result = await self.executor.run(
            connection,
            _read_file_command(path, max_bytes),
            timeout_seconds=int(input.get("timeout_seconds") or 10),
            output_limit=max_bytes + 1,
        )
        content_truncated = len(result.stdout) > max_bytes
        observation = _result_observation(
            result,
            force_truncated=content_truncated,
        )
        return {
            "connection": connection.summary(),
            "path": path,
            "content": result.stdout[:max_bytes],
            "result": observation,
        }


class RemoteListDirTool:
    spec = AgentToolSpec(
        name="remote.list_dir",
        description=(
            "List a remote directory on a selected SSH connection. Returns a bounded "
            "set of parsed entries plus the command observation."
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
            "required": ["connection_id", "path"],
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
        self.resolver_factory = resolver_factory or SessionMetadataRemoteConnectionResolver
        self.executor = executor or SshRemoteExecutor()

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        connection = await _resolve_connection(input, context, self.resolver_factory)
        path = _required_string(input, "path")
        limit = int(input.get("limit") or 50)
        result = await self.executor.run(
            connection,
            _list_dir_command(path, limit),
            timeout_seconds=int(input.get("timeout_seconds") or 10),
            output_limit=int(input.get("output_limit") or 20000),
        )
        entries = _parse_find_entries(result.stdout)
        entries_truncated = len(entries) > limit
        return {
            "connection": connection.summary(),
            "path": path,
            "entries": entries[:limit],
            "result": _result_observation(result, force_truncated=entries_truncated),
        }


async def _resolve_connection(
    input: dict[str, Any],
    context: AgentToolContext,
    resolver_factory: ResolverFactory,
) -> RemoteConnectionConfig:
    resolver = resolver_factory(context.db)
    return await resolver.get(
        _required_string(input, "connection_id"),
        workspace_id=context.workspace_id,
        user_id=context.user_id,
        session_id=context.session_id,
    )


def _connections_from_session_policy(agent_session) -> list[RemoteConnectionConfig]:
    raw_connections: list[Any] = []
    for policy in (
        getattr(agent_session, "session_metadata", None),
        getattr(agent_session, "context_policy", None),
        getattr(agent_session, "toolset_policy", None),
    ):
        if not isinstance(policy, dict):
            continue
        collection = policy.get("remote_connections")
        if isinstance(collection, list):
            raw_connections.extend(collection)
        single = policy.get("remote_connection")
        if isinstance(single, dict):
            raw_connections.append(single)

    connections: list[RemoteConnectionConfig] = []
    seen: set[str] = set()
    for raw in raw_connections:
        connection = _coerce_connection(raw)
        if connection is None or connection.id in seen:
            continue
        seen.add(connection.id)
        connections.append(connection)
    return connections


def _coerce_connection(raw: Any) -> RemoteConnectionConfig | None:
    if not isinstance(raw, dict):
        return None
    connection_id = raw.get("id") or raw.get("connection_id")
    host = raw.get("host") or raw.get("hostname") or raw.get("ssh_host")
    if not connection_id or not host:
        return None
    port = raw.get("port")
    try:
        normalized_port = int(port) if port is not None else None
    except (TypeError, ValueError):
        normalized_port = None
    return RemoteConnectionConfig(
        id=str(connection_id),
        name=str(raw.get("name") or connection_id),
        host=str(host),
        username=_optional_string(raw.get("username") or raw.get("user")),
        port=normalized_port,
        ssh_alias=_optional_string(raw.get("ssh_alias") or raw.get("alias")),
        key_path=_optional_string(raw.get("key_path") or raw.get("identity_file")),
        ssh_config_path=_optional_string(raw.get("ssh_config_path") or raw.get("config_path")),
        status=str(raw.get("status") or "unknown"),
        skill_summary=_optional_string(
            raw.get("skill_summary") or raw.get("skillSummary") or raw.get("instructions")
        ),
    )


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


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _read_file_command(path: str, max_bytes: int) -> str:
    quoted_path = shlex.quote(path)
    read_bytes = max_bytes + 1
    return (
        f"if [ -d {quoted_path} ]; then "
        "printf '%s\\n' 'remote path is a directory' >&2; exit 21; "
        f"fi; head -c {read_bytes} -- {quoted_path}"
    )


def _list_dir_command(path: str, limit: int) -> str:
    quoted_path = shlex.quote(path)
    line_limit = limit + 1
    return (
        f"if [ ! -d {quoted_path} ]; then "
        "printf '%s\\n' 'remote path is not a directory' >&2; exit 22; "
        "fi; "
        f"find {quoted_path} -maxdepth 1 -mindepth 1 "
        "-printf '%y\\t%f\\t%s\\n' | sort | "
        f"head -n {line_limit}"
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
) -> dict[str, int | str | bool]:
    observation = result.observation()
    if force_truncated:
        observation["truncated"] = True
        observation["stdout_truncated"] = True
    return observation
