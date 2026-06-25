from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.agent_core.context.remote import render_remote_connection_context
from app.services.agent_core.tools import build_default_tool_registry
from app.services.agent_core.tools.remote import (
    DatabaseRemoteConnectionResolver,
    RemoteConnectionsListTool,
    RemoteExecTool,
    RemoteListDirTool,
    RemoteReadFileTool,
    StaticRemoteConnectionResolver,
)
from app.services.agent_core.tools.specs import AgentToolContext
from app.services.agent_core.tools.toolsets import ToolsetExposure
from app.config import settings
from app.models.workspace import WorkspaceMembership
from app.services.remote_execution import RemoteCommandResult, RemoteConnectionConfig
from app.services.remote_connection_service import RemoteConnectionService
from app.utils.exceptions import NotFoundError, PermissionDeniedError


def _tool_context(db_session, *, session_id: str | None = "session-1") -> AgentToolContext:
    return AgentToolContext(
        db=db_session,
        workspace_id="workspace-1",
        user_id="user-1",
        session_id=session_id,
        turn_id="turn-1",
    )


def _tool_context_without_session(db_session) -> AgentToolContext:
    return AgentToolContext(
        db=db_session,
        workspace_id="workspace-1",
        user_id="user-1",
        session_id=None,
        turn_id="turn-1",
    )


async def _create_agent_session(
    db_session,
    *,
    remote_connection_id: str | None = None,
    session_metadata: dict | None = None,
):
    from app.models.agent_core import AgentSession, AgentSessionStatus

    if session_metadata is None and remote_connection_id:
        session_metadata = {"remote_connection_id": remote_connection_id}
    session = AgentSession(
        workspace_id="workspace-1",
        user_id="user-1",
        role_profile="bioinformatician",
        permission_mode="guarded_auto",
        automation_mode="assisted",
        runtime_mode="api",
        status=AgentSessionStatus.ACTIVE,
        session_metadata=session_metadata,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


def _connection(connection_id: str = "conn-1") -> RemoteConnectionConfig:
    return RemoteConnectionConfig(
        id=connection_id,
        name="HPC login",
        host="login.cluster.example.org",
        username="alice",
        status="ready",
        skill_summary="Use module load nextflow before launching workflows.",
        ssh_alias="bio-hpc",
    )


def _resolver_factory(connections: list[RemoteConnectionConfig]):
    def factory(_db):
        return StaticRemoteConnectionResolver(connections)

    return factory


class _FakeRemoteExecutor:
    def __init__(self, result: RemoteCommandResult):
        self.result = result
        self.calls: list[dict] = []

    async def run(
        self,
        connection: RemoteConnectionConfig,
        command: str,
        *,
        timeout_seconds: int,
        output_limit: int,
    ) -> RemoteCommandResult:
        self.calls.append(
            {
                "connection": connection,
                "command": command,
                "timeout_seconds": timeout_seconds,
                "output_limit": output_limit,
            }
        )
        return self.result


@pytest.mark.asyncio
async def test_remote_connections_list_returns_workspace_summaries(db_session):
    tool = RemoteConnectionsListTool(resolver_factory=_resolver_factory([_connection()]))

    result = await tool.run({}, _tool_context(db_session))

    assert result == {
        "connections": [
            {
                "id": "conn-1",
                "name": "HPC login",
                "host": "login.cluster.example.org",
                "username": "alice",
                "status": "ready",
                "skill_summary": "Use module load nextflow before launching workflows.",
            }
        ],
        "total_count": 1,
    }


@pytest.mark.asyncio
async def test_remote_connections_list_reads_workspace_database_connections(db_session):
    service = RemoteConnectionService(db_session)
    created = await service.create_connection(
        {
            "name": "DB HPC login",
            "host": "db-login.cluster.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "ssh_config",
            "ssh_alias": "db-hpc",
            "skill_instructions": "Use the shared module stack.",
        },
        workspace_id="workspace-1",
    )
    agent_session = await _create_agent_session(
        db_session,
        remote_connection_id=str(created.id),
    )
    tool = RemoteConnectionsListTool()

    result = await tool.run({}, _tool_context(db_session, session_id=str(agent_session.id)))

    assert result["connections"] == [
        {
            "id": str(created.id),
            "name": "DB HPC login",
            "host": "db-login.cluster.example.org",
            "username": "alice",
            "status": "unknown",
            "skill_summary": "Use the shared module stack.",
        }
    ]


@pytest.mark.asyncio
async def test_remote_tools_require_explicit_selected_connection(db_session):
    service = RemoteConnectionService(db_session)
    await service.create_connection(
        {
            "name": "DB HPC login",
            "host": "db-login.cluster.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "ssh_config",
            "ssh_alias": "db-hpc",
        },
        workspace_id="workspace-1",
    )

    resolver = DatabaseRemoteConnectionResolver(db_session)

    assert await resolver.list(
        workspace_id="workspace-1",
        user_id="user-1",
        session_id=None,
    ) == []
    with pytest.raises(NotFoundError):
        await resolver.get(
            "conn-1",
            workspace_id="workspace-1",
            user_id="user-1",
            session_id=None,
        )


@pytest.mark.asyncio
async def test_remote_tools_only_resolve_selected_workspace_connection(db_session):
    service = RemoteConnectionService(db_session)
    selected = await service.create_connection(
        {
            "name": "Selected HPC",
            "host": "selected.cluster.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "ssh_config",
            "ssh_alias": "selected-hpc",
        },
        workspace_id="workspace-1",
    )
    other = await service.create_connection(
        {
            "name": "Other HPC",
            "host": "other.cluster.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "ssh_config",
            "ssh_alias": "other-hpc",
        },
        workspace_id="workspace-1",
    )
    agent_session = await _create_agent_session(
        db_session,
        remote_connection_id=str(selected.id),
    )

    resolver = DatabaseRemoteConnectionResolver(db_session)
    connections = await resolver.list(
        workspace_id="workspace-1",
        user_id="user-1",
        session_id=str(agent_session.id),
    )

    assert [connection.id for connection in connections] == [str(selected.id)]
    assert (
        await resolver.get(
            str(selected.id),
            workspace_id="workspace-1",
            user_id="user-1",
            session_id=str(agent_session.id),
        )
    ).host == "selected.cluster.example.org"
    with pytest.raises(NotFoundError):
        await resolver.get(
            str(other.id),
            workspace_id="workspace-1",
            user_id="user-1",
            session_id=str(agent_session.id),
        )


@pytest.mark.asyncio
async def test_remote_exec_uses_persisted_selected_connection(db_session):
    service = RemoteConnectionService(db_session)
    selected = await service.create_connection(
        {
            "name": "Selected HPC",
            "host": "selected.cluster.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "ssh_config",
            "ssh_alias": "selected-hpc",
            "skill_instructions": "Use /scratch/project for outputs.",
        },
        workspace_id="workspace-1",
    )
    agent_session = await _create_agent_session(
        db_session,
        remote_connection_id=str(selected.id),
    )
    executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="selected.cluster.example.org\n",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    tool = RemoteExecTool(executor=executor)

    result = await tool.run(
        {
            "connection_id": str(selected.id),
            "command": "hostname",
        },
        _tool_context(db_session, session_id=str(agent_session.id)),
    )

    assert result["connection"]["id"] == str(selected.id)
    assert result["connection"]["skill_summary"] == "Use /scratch/project for outputs."
    assert result["result"]["stdout"] == "selected.cluster.example.org\n"
    assert executor.calls[0]["connection"].id == str(selected.id)
    assert executor.calls[0]["command"] == "hostname"


@pytest.mark.asyncio
async def test_remote_tools_ignore_inline_session_metadata_connection(db_session):
    agent_session = await _create_agent_session(
        db_session,
        session_metadata={
            "remote_connection_id": "evil",
            "remote_connection": {
                "id": "evil",
                "name": "Injected target",
                "host": "evil.example.org",
                "username": "mallory",
                "key_path": "/tmp/mallory",
            },
        },
    )
    resolver = DatabaseRemoteConnectionResolver(db_session)

    assert await resolver.list(
        workspace_id="workspace-1",
        user_id="user-1",
        session_id=str(agent_session.id),
    ) == []
    with pytest.raises(NotFoundError):
        await resolver.get(
            "evil",
            workspace_id="workspace-1",
            user_id="user-1",
            session_id=str(agent_session.id),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "payload"),
    [
        (RemoteExecTool, {"connection_id": "conn-1", "command": "hostname"}),
        (RemoteReadFileTool, {"connection_id": "conn-1", "path": "/etc/hosts"}),
        (RemoteListDirTool, {"connection_id": "conn-1", "path": "/scratch"}),
    ],
)
async def test_remote_operations_require_admin_role_in_team_mode(
    db_session,
    monkeypatch,
    tool,
    payload,
):
    monkeypatch.setattr(settings, "auth_mode", "team")
    db_session.add(
        WorkspaceMembership(
            workspace_id="workspace-1",
            user_id="user-1",
            role="member",
        )
    )
    await db_session.commit()

    executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="ok",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    instance = tool(
        resolver_factory=_resolver_factory([_connection()]),
        executor=executor,
    )

    with pytest.raises(PermissionDeniedError):
        await instance.run(payload, _tool_context(db_session))
    assert executor.calls == []


@pytest.mark.asyncio
async def test_remote_exec_allows_admin_role_in_team_mode(db_session, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "team")
    db_session.add(
        WorkspaceMembership(
            workspace_id="workspace-1",
            user_id="user-1",
            role="admin",
        )
    )
    await db_session.commit()
    executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="ok",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    tool = RemoteExecTool(
        resolver_factory=_resolver_factory([_connection()]),
        executor=executor,
    )

    result = await tool.run(
        {"connection_id": "conn-1", "command": "hostname"},
        _tool_context(db_session),
    )

    assert executor.calls[0]["command"] == "hostname"
    assert result["result"]["exit_code"] == 0


@pytest.mark.asyncio
async def test_remote_exec_returns_structured_observation(db_session):
    executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="Linux login 6.1\n",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    tool = RemoteExecTool(
        resolver_factory=_resolver_factory([_connection()]),
        executor=executor,
    )

    result = await tool.run(
        {
            "connection_id": "conn-1",
            "command": "uname -a",
            "timeout_seconds": 7,
            "output_limit": 500,
        },
        _tool_context(db_session),
    )

    assert executor.calls[0]["command"] == "uname -a"
    assert executor.calls[0]["timeout_seconds"] == 7
    assert executor.calls[0]["output_limit"] == 500
    assert result["connection"]["id"] == "conn-1"
    assert result["result"] == {
        "exit_code": 0,
        "stdout": "Linux login 6.1\n",
        "stderr": "",
        "timed_out": False,
        "truncated": False,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }


@pytest.mark.asyncio
async def test_remote_read_file_quotes_path_and_bounds_content(db_session):
    executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="hello remote file!",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    tool = RemoteReadFileTool(
        resolver_factory=_resolver_factory([_connection()]),
        executor=executor,
    )

    result = await tool.run(
        {
            "connection_id": "conn-1",
            "path": "/data/it's here.txt",
            "max_bytes": 12,
            "timeout_seconds": 4,
        },
        _tool_context(db_session),
    )

    assert "'/data/it'\"'\"'s here.txt'" in executor.calls[0]["command"]
    assert executor.calls[0]["output_limit"] == 13
    assert result["path"] == "/data/it's here.txt"
    assert result["content"] == "hello remote"
    assert result["result"]["truncated"] is True


@pytest.mark.asyncio
async def test_remote_list_dir_builds_bounded_command_and_parses_entries(db_session):
    executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="f\talpha.txt\t42\nd\tresults\t0\n",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    tool = RemoteListDirTool(
        resolver_factory=_resolver_factory([_connection()]),
        executor=executor,
    )

    result = await tool.run(
        {"connection_id": "conn-1", "path": "/scratch/alice/run 1", "limit": 20},
        _tool_context(db_session),
    )

    assert "'/scratch/alice/run 1'" in executor.calls[0]["command"]
    assert "head -n 21" in executor.calls[0]["command"]
    assert result["entries"] == [
        {"kind": "file", "name": "alpha.txt", "size_bytes": 42},
        {"kind": "directory", "name": "results", "size_bytes": 0},
    ]
    assert result["result"]["exit_code"] == 0


def test_default_registry_registers_remote_tools_with_expected_exposure():
    registry = build_default_tool_registry()
    names = registry.names()
    exposure = ToolsetExposure(registry)

    assert {
        "remote.connections.list",
        "remote.exec",
        "remote.read_file",
        "remote.list_dir",
    }.issubset(names)
    assert "remote.exec" not in exposure.exposed_names(policy={"name": "default"})
    assert "remote.connections.list" in exposure.exposed_names(policy={"name": "default"})
    assert "remote.read_file" in exposure.exposed_names(policy={"name": "default"})
    assert "remote.list_dir" in exposure.exposed_names(policy={"name": "default"})
    assert registry.get("remote.exec").spec.risk_level == "act_high"
    assert registry.get("remote.read_file").spec.risk_level == "read"
    assert registry.get("remote.read_file").spec.write_scope == []
    assert registry.get("remote.list_dir").spec.risk_level == "read"
    assert registry.get("remote.list_dir").spec.write_scope == []


@pytest.mark.asyncio
async def test_remote_connection_context_renders_selected_connection(db_session):
    agent_session = SimpleNamespace(
        workspace_id="workspace-1",
        user_id="user-1",
        session_metadata={"remote_connection_id": "conn-1"},
        context_policy=None,
        toolset_policy=None,
    )

    context = await render_remote_connection_context(
        db_session,
        agent_session,
        resolver_factory=_resolver_factory([_connection()]),
    )

    assert context is not None
    assert "Selected remote connection: HPC login (conn-1)" in context
    assert "alice@login.cluster.example.org" in context
    assert "Use module load nextflow before launching workflows." in context
