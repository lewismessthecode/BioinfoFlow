from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.agent_core.context.remote import render_remote_connection_context
from app.services.agent_core.tools import build_default_tool_registry
from app.services.agent_core.tools.remote import (
    RemoteConnectionsListTool,
    RemoteExecTool,
    RemoteListDirTool,
    RemoteReadFileTool,
    StaticRemoteConnectionResolver,
)
from app.services.agent_core.tools.specs import AgentToolContext
from app.services.agent_core.tools.toolsets import ToolsetExposure
from app.services.remote_execution import RemoteCommandResult, RemoteConnectionConfig


def _tool_context(db_session) -> AgentToolContext:
    return AgentToolContext(
        db=db_session,
        workspace_id="workspace-1",
        user_id="user-1",
        session_id="session-1",
        turn_id="turn-1",
    )


def _connection() -> RemoteConnectionConfig:
    return RemoteConnectionConfig(
        id="conn-1",
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
    assert {
        "remote.connections.list",
        "remote.read_file",
        "remote.list_dir",
    }.issubset(exposure.exposed_names(policy={"name": "default"}))
    assert registry.get("remote.exec").spec.risk_level == "act_high"


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
