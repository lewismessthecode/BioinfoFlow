from __future__ import annotations

import asyncio
import os
import subprocess
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.agent_core.context.remote import render_remote_connection_context
from app.services.agent_core.execution_target import (
    session_metadata_with_execution_target,
)
from app.services.agent_core.permissions.command_risk import CommandTargetProfile
from app.services.agent_core.permissions.policy import PermissionPolicy
from app.repositories.agent_core_repo import AgentSessionRepository
from app.services.agent_core.tools import (
    AgentToolDispatcher,
    build_default_tool_registry,
)
from app.services.agent_core.tools.executor import _artifact_descriptor
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
from app.utils.exceptions import BadRequestError, NotFoundError, PermissionDeniedError


def _tool_context(
    db_session, *, session_id: str | None = "session-1"
) -> AgentToolContext:
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
    permission_mode: str = "guarded_auto",
    session_metadata: dict | None = None,
):
    from app.models.agent_core import AgentSession, AgentSessionStatus

    if session_metadata is None and remote_connection_id:
        session_metadata = {"remote_connection_id": remote_connection_id}
    session = AgentSession(
        workspace_id="workspace-1",
        user_id="user-1",
        role_profile="bioinformatician",
        permission_mode=permission_mode,
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


async def _dispatch_remote_exec_while_target_drifts(db_session, drift: str):
    from app.repositories.project_repo import ProjectRepository
    from app.services.agent_core.service import AgentCoreService
    from app.services.project_service import ProjectService

    connection_service = RemoteConnectionService(db_session)
    first = await connection_service.create_connection(
        {
            "name": "Approved target",
            "host": "approved.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "agent",
        },
        workspace_id="workspace-1",
    )
    second = await connection_service.create_connection(
        {
            "name": "Replacement target",
            "host": "replacement.example.org",
            "port": 22,
            "username": "bob",
            "auth_method": "agent",
        },
        workspace_id="workspace-1",
    )
    project = None
    if drift == "project_root":
        project = await ProjectService(db_session).create_project(
            {
                "name": "Approved remote project",
                "workspace_id": "workspace-1",
                "remote_connection_id": str(first.id),
                "remote_root_path": "/approved/root",
            },
            user_id="user-1",
        )
    service = AgentCoreService(db_session)
    agent_session = await service.create_session(
        project_id=str(project.id) if project is not None else None,
        workspace_id="workspace-1",
        user_id="user-1",
        permission_mode="bypass",
        metadata=(
            None
            if project is not None
            else {
                "execution_target": {
                    "type": "remote_ssh",
                    "connection_id": str(first.id),
                }
            }
        ),
    )
    turn = await service.create_turn_record(
        session_id=str(agent_session.id),
        workspace_id="workspace-1",
        user_id="user-1",
        input_text="Run on the approved target only.",
    )
    remote_executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="ok\n",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    registry = build_default_tool_registry()
    remote_tool = registry.get("remote.exec")
    remote_tool.executor = remote_executor
    entered = asyncio.Event()
    release = asyncio.Event()
    original_run = remote_tool.run

    async def paused_run(input, context):
        entered.set()
        await release.wait()
        return await original_run(input, context)

    remote_tool.run = paused_run
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as worker, maker() as mutator:
        task = asyncio.create_task(
            AgentToolDispatcher(worker, registry).dispatch(
                tool_name="remote.exec",
                input={"command": "hostname"},
                context=AgentToolContext(
                    db=worker,
                    workspace_id="workspace-1",
                    user_id="user-1",
                    session_id=str(agent_session.id),
                    turn_id=str(turn.id),
                ),
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=1)
        if drift == "selected_target":
            session_repo = AgentSessionRepository(mutator)
            mutable_session = await session_repo.get_fresh(str(agent_session.id))
            await session_repo.update_all(
                mutable_session,
                session_metadata=session_metadata_with_execution_target(
                    mutable_session.session_metadata,
                    {
                        "type": "remote_ssh",
                        "connection_id": str(second.id),
                    },
                ),
            )
        elif drift == "host":
            current = await RemoteConnectionService(mutator).get_connection(
                str(first.id), workspace_id="workspace-1"
            )
            await RemoteConnectionService(mutator).update_connection(
                current, {"host": "changed.example.org"}
            )
        else:
            current_project = await ProjectRepository(mutator).get_fresh(
                str(project.id)
            )
            await ProjectRepository(mutator).update_all(
                current_project, remote_root_path="/changed/root"
            )
        release.set()
        result = await asyncio.wait_for(task, timeout=2)
    return result, remote_executor.calls


async def _resume_remote_exec_while_target_host_drifts(db_session):
    from app.services.agent_core.service import AgentCoreService

    connection_service = RemoteConnectionService(db_session)
    connection = await connection_service.create_connection(
        {
            "name": "Approved target",
            "host": "resume-approved.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "agent",
        },
        workspace_id="workspace-1",
    )
    service = AgentCoreService(db_session)
    agent_session = await service.create_session(
        project_id=None,
        workspace_id="workspace-1",
        user_id="user-1",
        permission_mode="ask_each_action",
        metadata={
            "execution_target": {
                "type": "remote_ssh",
                "connection_id": str(connection.id),
            }
        },
    )
    turn = await service.create_turn_record(
        session_id=str(agent_session.id),
        workspace_id="workspace-1",
        user_id="user-1",
        input_text="Ask before running on the approved target.",
    )
    remote_executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="ok\n",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    registry = build_default_tool_registry()
    remote_tool = registry.get("remote.exec")
    remote_tool.executor = remote_executor
    context = AgentToolContext(
        db=db_session,
        workspace_id="workspace-1",
        user_id="user-1",
        session_id=str(agent_session.id),
        turn_id=str(turn.id),
    )
    dispatcher = AgentToolDispatcher(db_session, registry)

    pending = await dispatcher.dispatch(
        tool_name="remote.exec",
        input={"command": "hostname"},
        context=context,
    )
    assert pending.status == "waiting_decision"
    assert remote_executor.calls == []

    await service.decide_action(
        action_id=pending.action_id,
        workspace_id="workspace-1",
        user_id="user-1",
        decision="approve",
    )
    current = await connection_service.get_connection(
        str(connection.id), workspace_id="workspace-1"
    )
    await connection_service.update_connection(
        current, {"host": "resume-changed.example.org"}
    )

    result = await dispatcher.resume_action(
        action_id=pending.action_id,
        context=context,
    )
    return result, remote_executor.calls


async def _dispatch_remote_exec_while_scope_target_host_drifts(db_session, mode: str):
    from app.services.agent_core.service import AgentCoreService

    connection_service = RemoteConnectionService(db_session)
    first = await connection_service.create_connection(
        {
            "name": "Scope target",
            "host": "scope-approved.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "agent",
        },
        workspace_id="workspace-1",
    )
    second = await connection_service.create_connection(
        {
            "name": "Second scope target",
            "host": "scope-second.example.org",
            "port": 22,
            "username": "bob",
            "auth_method": "agent",
        },
        workspace_id="workspace-1",
    )
    execution_scope = (
        {"mode": "auto"}
        if mode == "auto"
        else {
            "mode": "manual",
            "selected_targets": [
                {"type": "remote_ssh", "connection_id": str(first.id)},
                {"type": "remote_ssh", "connection_id": str(second.id)},
            ],
        }
    )
    service = AgentCoreService(db_session)
    agent_session = await service.create_session(
        project_id=None,
        workspace_id="workspace-1",
        user_id="user-1",
        permission_mode="bypass",
        execution_scope=execution_scope,
    )
    turn = await service.create_turn_record(
        session_id=str(agent_session.id),
        workspace_id="workspace-1",
        user_id="user-1",
        input_text="Run on the selected scope target only.",
    )
    remote_executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="ok\n",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    registry = build_default_tool_registry()
    remote_tool = registry.get("remote.exec")
    remote_tool.executor = remote_executor
    entered = asyncio.Event()
    release = asyncio.Event()
    original_run = remote_tool.run

    async def paused_run(input, context):
        entered.set()
        await release.wait()
        return await original_run(input, context)

    remote_tool.run = paused_run
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as worker, maker() as mutator:
        task = asyncio.create_task(
            AgentToolDispatcher(worker, registry).dispatch(
                tool_name="remote.exec",
                input={"connection_id": str(first.id), "command": "hostname"},
                context=AgentToolContext(
                    db=worker,
                    workspace_id="workspace-1",
                    user_id="user-1",
                    session_id=str(agent_session.id),
                    turn_id=str(turn.id),
                ),
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=1)
        current = await RemoteConnectionService(mutator).get_connection(
            str(first.id), workspace_id="workspace-1"
        )
        await RemoteConnectionService(mutator).update_connection(
            current, {"host": "scope-changed.example.org"}
        )
        release.set()
        result = await asyncio.wait_for(task, timeout=2)
    return result, remote_executor.calls


async def _dispatch_remote_exec_without_connection_id_while_scope_target_host_drifts(
    db_session, mode: str
):
    from app.services.agent_core.service import AgentCoreService

    connection_service = RemoteConnectionService(db_session)
    connection = await connection_service.create_connection(
        {
            "name": "Implicit scope target",
            "host": "implicit-approved.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "agent",
        },
        workspace_id="workspace-1",
    )
    execution_scope = (
        {"mode": "auto"}
        if mode == "auto"
        else {
            "mode": "manual",
            "selected_targets": [
                {"type": "local"},
                {"type": "remote_ssh", "connection_id": str(connection.id)},
            ],
        }
    )
    service = AgentCoreService(db_session)
    agent_session = await service.create_session(
        project_id=None,
        workspace_id="workspace-1",
        user_id="user-1",
        permission_mode="bypass",
        execution_scope=execution_scope,
    )
    turn = await service.create_turn_record(
        session_id=str(agent_session.id),
        workspace_id="workspace-1",
        user_id="user-1",
        input_text="Run on the only visible remote target.",
    )
    remote_executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="ok\n",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    registry = build_default_tool_registry()
    remote_tool = registry.get("remote.exec")
    remote_tool.executor = remote_executor
    entered = asyncio.Event()
    release = asyncio.Event()
    original_run = remote_tool.run

    async def paused_run(input, context):
        entered.set()
        await release.wait()
        return await original_run(input, context)

    remote_tool.run = paused_run
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as worker, maker() as mutator:
        task = asyncio.create_task(
            AgentToolDispatcher(worker, registry).dispatch(
                tool_name="remote.exec",
                input={"command": "hostname"},
                context=AgentToolContext(
                    db=worker,
                    workspace_id="workspace-1",
                    user_id="user-1",
                    session_id=str(agent_session.id),
                    turn_id=str(turn.id),
                ),
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=1)
        current = await RemoteConnectionService(mutator).get_connection(
            str(connection.id), workspace_id="workspace-1"
        )
        await RemoteConnectionService(mutator).update_connection(
            current, {"host": "implicit-changed.example.org"}
        )
        release.set()
        result = await asyncio.wait_for(task, timeout=2)
    return result, remote_executor.calls


async def _resume_remote_exec_after_scope_target_host_drifts(db_session, mode: str):
    from app.services.agent_core.service import AgentCoreService

    connection_service = RemoteConnectionService(db_session)
    first = await connection_service.create_connection(
        {
            "name": "Approved scope target",
            "host": "resume-approved.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "agent",
        },
        workspace_id="workspace-1",
    )
    second = await connection_service.create_connection(
        {
            "name": "Second approved scope target",
            "host": "resume-second.example.org",
            "port": 22,
            "username": "bob",
            "auth_method": "agent",
        },
        workspace_id="workspace-1",
    )
    execution_scope = (
        {"mode": "auto"}
        if mode == "auto"
        else {
            "mode": "manual",
            "selected_targets": [
                {"type": "remote_ssh", "connection_id": str(first.id)},
                {"type": "remote_ssh", "connection_id": str(second.id)},
            ],
        }
    )
    agent_service = AgentCoreService(db_session)
    agent_session = await agent_service.create_session(
        project_id=None,
        workspace_id="workspace-1",
        user_id="user-1",
        permission_mode="ask_each_action",
        execution_scope=execution_scope,
    )
    turn = await agent_service.create_turn_record(
        session_id=str(agent_session.id),
        workspace_id="workspace-1",
        user_id="user-1",
        input_text="Ask before running on the selected scope target.",
    )
    executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="ok\n",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    registry = build_default_tool_registry()
    remote_tool = registry.get("remote.exec")
    remote_tool.executor = executor
    context = AgentToolContext(
        db=db_session,
        workspace_id="workspace-1",
        user_id="user-1",
        session_id=str(agent_session.id),
        turn_id=str(turn.id),
    )
    dispatcher = AgentToolDispatcher(db_session, registry)

    pending = await dispatcher.dispatch(
        tool_name="remote.exec",
        input={"connection_id": str(first.id), "command": "hostname"},
        context=context,
    )
    assert pending.status == "waiting_decision"
    assert executor.calls == []

    await agent_service.decide_action(
        action_id=pending.action_id,
        workspace_id="workspace-1",
        user_id="user-1",
        decision="approve",
    )
    current = await connection_service.get_connection(
        str(first.id), workspace_id="workspace-1"
    )
    await connection_service.update_connection(
        current, {"host": "resume-changed.example.org"}
    )

    resumed = await dispatcher.resume_action(
        action_id=pending.action_id,
        context=context,
    )
    return resumed, executor.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["selected_target", "host", "project_root"])
async def test_remote_exec_fails_closed_when_claimed_target_drifts(db_session, drift):
    result, calls = await _dispatch_remote_exec_while_target_drifts(db_session, drift)

    assert result.status == "failed"
    assert result.error["type"] == "PermissionDeniedError"
    assert calls == []


@pytest.mark.asyncio
async def test_remote_exec_resume_fails_closed_when_claimed_target_drifts(db_session):
    result, calls = await _resume_remote_exec_while_target_host_drifts(db_session)

    assert result.status == "failed"
    assert result.error["type"] == "PermissionDeniedError"
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["manual_multi", "auto"])
async def test_remote_exec_fails_closed_when_scope_selected_target_drifts(
    db_session, mode
):
    result, calls = await _dispatch_remote_exec_while_scope_target_host_drifts(
        db_session, mode
    )

    assert result.status == "failed"
    assert result.error["type"] == "PermissionDeniedError"
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["manual_local_remote", "auto"])
async def test_remote_exec_without_connection_id_binds_only_visible_scope_target(
    db_session, mode
):
    (
        result,
        calls,
    ) = await _dispatch_remote_exec_without_connection_id_while_scope_target_host_drifts(
        db_session, mode
    )

    assert result.status == "failed"
    assert result.error["type"] == "PermissionDeniedError"
    assert calls == []


@pytest.mark.asyncio
async def test_remote_exec_runtime_scope_uses_remote_command_risk(db_session):
    from app.services.agent_core.service import AgentCoreService

    connection = await RemoteConnectionService(db_session).create_connection(
        {
            "name": "Runtime risk target",
            "host": "risk.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "agent",
        },
        workspace_id="workspace-1",
    )
    service = AgentCoreService(db_session)
    agent_session = await service.create_session(
        project_id=None,
        workspace_id="workspace-1",
        user_id="user-1",
        permission_mode="guarded_auto",
        execution_scope={"mode": "auto"},
    )
    turn = await service.create_turn_record(
        session_id=str(agent_session.id),
        workspace_id="workspace-1",
        user_id="user-1",
        input_text="Inspect a remote secret-like file only after approval.",
    )
    remote_executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="secret\n",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    registry = build_default_tool_registry()
    registry.get("remote.exec").executor = remote_executor

    result = await AgentToolDispatcher(db_session, registry).dispatch(
        tool_name="remote.exec",
        input={"command": "cat secrets.txt"},
        context=AgentToolContext(
            db=db_session,
            workspace_id="workspace-1",
            user_id="user-1",
            session_id=str(agent_session.id),
            turn_id=str(turn.id),
        ),
    )

    assert result.status == "waiting_decision"
    assert remote_executor.calls == []
    action = await service.get_action(
        action_id=result.action_id,
        workspace_id="workspace-1",
        user_id="user-1",
    )
    assert action.risk_level == "act_high"
    snapshot = action.permission_context_snapshot
    assert snapshot["scope_remote_connection_id"] == str(connection.id)
    assert snapshot["command_risk"]["target"]["kind"] == "remote_ssh"
    assert snapshot["command_risk"]["target"]["connection_id"] == str(connection.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["manual_multi", "auto"])
async def test_remote_exec_resume_fails_closed_when_scope_target_drifts(
    db_session, mode
):
    result, calls = await _resume_remote_exec_after_scope_target_host_drifts(
        db_session, mode
    )

    assert result.status == "failed"
    assert result.error["type"] == "PermissionDeniedError"
    assert calls == []


@pytest.mark.asyncio
async def test_remote_connections_list_returns_workspace_summaries(db_session):
    tool = RemoteConnectionsListTool(
        resolver_factory=_resolver_factory([_connection()])
    )

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

    result = await tool.run(
        {}, _tool_context(db_session, session_id=str(agent_session.id))
    )

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
async def test_database_remote_connection_resolver_stitches_selected_jump_connection(
    db_session,
):
    service = RemoteConnectionService(db_session)
    jump = await service.create_connection(
        {
            "name": "Bastion",
            "host": "bastion.example.org",
            "port": 22,
            "username": "jump-user",
            "auth_method": "password",
            "password": "jump-secret",
        },
        workspace_id="workspace-1",
    )
    target = await service.create_connection(
        {
            "name": "Phoenix",
            "host": "10.32.5.1",
            "port": 22,
            "username": "phoenix",
            "auth_method": "jump",
            "jump_connection_id": str(jump.id),
        },
        workspace_id="workspace-1",
    )
    agent_session = await _create_agent_session(
        db_session,
        remote_connection_id=str(target.id),
    )

    resolved = await DatabaseRemoteConnectionResolver(db_session).get(
        str(target.id),
        workspace_id="workspace-1",
        user_id="user-1",
        session_id=str(agent_session.id),
    )

    assert resolved.jump_connection is not None
    assert resolved.jump_connection.id == str(jump.id)
    assert resolved.jump_connection.password == "jump-secret"


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

    assert (
        await resolver.list(
            workspace_id="workspace-1",
            user_id="user-1",
            session_id=None,
        )
        == []
    )
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


@pytest.mark.asyncio
async def test_remote_exec_uses_single_execution_target_connection_when_omitted(
    db_session,
):
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
    agent_session = await _create_agent_session(
        db_session,
        session_metadata={
            "execution_target": {
                "type": "remote_ssh",
                "connection_id": str(selected.id),
            }
        },
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
        {"command": "hostname"},
        _tool_context(db_session, session_id=str(agent_session.id)),
    )

    assert result["connection"]["id"] == str(selected.id)
    assert executor.calls[0]["connection"].id == str(selected.id)


@pytest.mark.asyncio
async def test_remote_exec_bypass_runs_literal_inline_filter_pipeline_without_approval(
    db_session,
):
    from app.services.agent_core.service import AgentCoreService

    service = RemoteConnectionService(db_session)
    selected = await service.create_connection(
        {
            "name": "Phoenix login",
            "host": "phoenix-login.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "ssh_config",
            "ssh_alias": "phoenix-login",
        },
        workspace_id="workspace-1",
    )
    agent_service = AgentCoreService(db_session)
    agent_session = await agent_service.create_session(
        project_id=None,
        workspace_id="workspace-1",
        user_id="user-1",
        permission_mode="bypass",
        metadata={
            "execution_target": {
                "type": "remote_ssh",
                "connection_id": str(selected.id),
            },
            "remote_project_root": "/mnt/nas1/.bioinfoflow",
        },
    )
    turn = await agent_service.create_turn_record(
        session_id=str(agent_session.id),
        workspace_id="workspace-1",
        user_id="user-1",
        input_text="List tasks on the remote host.",
    )
    executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="[]\n",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    registry = build_default_tool_registry()
    remote_tool = registry.get("remote.exec")
    remote_tool.executor = executor
    command = (
        "phoenixcli --no-interactive task list --output json --page-size 100 "
        '2>&1 | python3 -c "import sys,json; '
        "data=json.load(sys.stdin); print(len(data.get('data', [])))\""
    )

    result = await AgentToolDispatcher(db_session, registry).dispatch(
        tool_name="remote.exec",
        input={"command": command},
        context=AgentToolContext(
            db=db_session,
            workspace_id="workspace-1",
            user_id="user-1",
            session_id=str(agent_session.id),
            turn_id=str(turn.id),
        ),
    )

    assert result.status == "completed"
    assert executor.calls[0]["connection"].id == str(selected.id)
    assert executor.calls[0]["command"].startswith("cd /mnt/nas1/.bioinfoflow && ")


@pytest.mark.asyncio
async def test_remote_exec_runs_with_manual_multi_scope_selected_connection(
    db_session,
):
    from app.services.agent_core.service import AgentCoreService

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
    stale = await service.create_connection(
        {
            "name": "Stale HPC",
            "host": "stale.cluster.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "ssh_config",
            "ssh_alias": "stale-hpc",
        },
        workspace_id="workspace-1",
    )
    core = AgentCoreService(db_session)
    agent_session = await core.create_session(
        project_id=None,
        workspace_id="workspace-1",
        user_id="user-1",
        permission_mode="bypass",
        metadata={
            "remote_connection_id": str(stale.id),
            "execution_target": {
                "type": "remote_ssh",
                "connection_id": str(stale.id),
            },
        },
        execution_scope={
            "mode": "manual",
            "selected_targets": [
                {"type": "local"},
                {"type": "remote_ssh", "connection_id": str(selected.id)},
            ],
        },
    )
    turn = await core.create_turn_record(
        session_id=str(agent_session.id),
        workspace_id="workspace-1",
        user_id="user-1",
        input_text="Run on the scoped target.",
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
    registry = build_default_tool_registry()
    remote_tool = registry.get("remote.exec")
    remote_tool.executor = executor

    result = await AgentToolDispatcher(db_session, registry).dispatch(
        tool_name="remote.exec",
        input={"connection_id": str(selected.id), "command": "hostname"},
        context=AgentToolContext(
            db=db_session,
            workspace_id="workspace-1",
            user_id="user-1",
            session_id=str(agent_session.id),
            turn_id=str(turn.id),
        ),
    )

    assert result.status == "completed", result.error
    assert result.result["connection"]["id"] == str(selected.id)
    assert executor.calls[0]["connection"].id == str(selected.id)


@pytest.mark.asyncio
async def test_manual_scope_overrides_remote_project_binding_for_resolver(db_session):
    from app.services.agent_core.service import AgentCoreService
    from app.services.project_service import ProjectService

    service = RemoteConnectionService(db_session)
    project_connection = await service.create_connection(
        {
            "name": "Project HPC",
            "host": "project.cluster.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "ssh_config",
            "ssh_alias": "project-hpc",
        },
        workspace_id="workspace-1",
    )
    selected = await service.create_connection(
        {
            "name": "Manually selected HPC",
            "host": "selected.cluster.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "ssh_config",
            "ssh_alias": "selected-hpc",
        },
        workspace_id="workspace-1",
    )
    project = await ProjectService(db_session).create_project(
        {
            "name": "Remote project",
            "workspace_id": "workspace-1",
            "remote_connection_id": str(project_connection.id),
            "remote_root_path": "/analysis/project",
        },
        user_id="user-1",
    )
    agent_session = await AgentCoreService(db_session).create_session(
        project_id=str(project.id),
        workspace_id="workspace-1",
        user_id="user-1",
        execution_scope={
            "mode": "manual",
            "selected_targets": [
                {"type": "remote_ssh", "connection_id": str(selected.id)}
            ],
        },
    )

    resolver = DatabaseRemoteConnectionResolver(db_session)
    connections = await resolver.list(
        workspace_id="workspace-1",
        user_id="user-1",
        session_id=str(agent_session.id),
    )

    assert [connection.id for connection in connections] == [str(selected.id)]
    with pytest.raises(NotFoundError):
        await resolver.get(
            str(project_connection.id),
            workspace_id="workspace-1",
            user_id="user-1",
            session_id=str(agent_session.id),
        )


@pytest.mark.asyncio
async def test_auto_scope_resolver_lists_more_than_first_page(db_session, monkeypatch):
    from app.schemas.common import Pagination
    from app.services.agent_core.tools.remote import resources as remote_resources

    created_ids = [f"connection-{index:03}" for index in range(101)]
    calls: list[str | None] = []

    async def list_for_workspace(self, *, workspace_id, limit=20, cursor=None):
        calls.append(cursor)
        page_ids = created_ids[:100] if cursor is None else created_ids[100:]
        return (
            [SimpleNamespace(id=connection_id) for connection_id in page_ids],
            Pagination(
                limit=limit,
                has_more=cursor is None,
                next_cursor="page-2" if cursor is None else None,
                total_count=len(created_ids),
            ),
        )

    monkeypatch.setattr(
        remote_resources.RemoteConnectionRepository,
        "list_for_workspace",
        list_for_workspace,
    )
    agent_session = await _create_agent_session(
        db_session,
        session_metadata={"execution_scope": {"mode": "auto"}},
    )

    returned_ids = await remote_resources._selected_remote_connection_ids(
        db_session,
        workspace_id="workspace-1",
        user_id="user-1",
        session_id=str(agent_session.id),
    )

    assert returned_ids == created_ids
    assert calls == [None, "page-2"]


@pytest.mark.asyncio
async def test_remote_read_file_bypass_runs_data_path_outside_root_without_approval(
    db_session,
):
    from app.services.agent_core.service import AgentCoreService

    service = RemoteConnectionService(db_session)
    selected = await service.create_connection(
        {
            "name": "Phoenix login",
            "host": "phoenix-login.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "ssh_config",
            "ssh_alias": "phoenix-login",
        },
        workspace_id="workspace-1",
    )
    agent_service = AgentCoreService(db_session)
    agent_session = await agent_service.create_session(
        project_id=None,
        workspace_id="workspace-1",
        user_id="user-1",
        permission_mode="bypass",
        metadata={
            "execution_target": {
                "type": "remote_ssh",
                "connection_id": str(selected.id),
            },
            "remote_project_root": "/mnt/nas1/.bioinfoflow",
        },
    )
    turn = await agent_service.create_turn_record(
        session_id=str(agent_session.id),
        workspace_id="workspace-1",
        user_id="user-1",
        input_text="Read a previous task input file.",
    )
    executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="sample-a\n",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    registry = build_default_tool_registry()
    remote_tool = registry.get("remote.read_file")
    remote_tool.executor = executor
    path = (
        "/mnt/nas1/phoenix-task/Deaf_20/"
        "sz01-Deaf_20-202607093417298900000001/input/sequence.list"
    )

    result = await AgentToolDispatcher(db_session, registry).dispatch(
        tool_name="remote.read_file",
        input={"path": path},
        context=AgentToolContext(
            db=db_session,
            workspace_id="workspace-1",
            user_id="user-1",
            session_id=str(agent_session.id),
            turn_id=str(turn.id),
        ),
    )

    assert result.status == "completed"
    assert result.result["path"] == path
    assert result.result["content"] == "sample-a\n"
    assert (
        "remote path is outside the remote project" not in executor.calls[0]["command"]
    )


@pytest.mark.asyncio
async def test_remote_read_file_approved_data_path_outside_root_resumes_successfully(
    db_session,
):
    from app.services.agent_core.service import AgentCoreService

    service = RemoteConnectionService(db_session)
    selected = await service.create_connection(
        {
            "name": "Phoenix login",
            "host": "phoenix-login.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "ssh_config",
            "ssh_alias": "phoenix-login",
        },
        workspace_id="workspace-1",
    )
    agent_service = AgentCoreService(db_session)
    agent_session = await agent_service.create_session(
        project_id=None,
        workspace_id="workspace-1",
        user_id="user-1",
        permission_mode="guarded_auto",
        metadata={
            "execution_target": {
                "type": "remote_ssh",
                "connection_id": str(selected.id),
            },
            "remote_project_root": "/mnt/nas1/.bioinfoflow",
        },
    )
    turn = await agent_service.create_turn_record(
        session_id=str(agent_session.id),
        workspace_id="workspace-1",
        user_id="user-1",
        input_text="Read a previous task input file after approval.",
    )
    executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="sample-a\n",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    registry = build_default_tool_registry()
    remote_tool = registry.get("remote.read_file")
    remote_tool.executor = executor
    context = AgentToolContext(
        db=db_session,
        workspace_id="workspace-1",
        user_id="user-1",
        session_id=str(agent_session.id),
        turn_id=str(turn.id),
    )
    path = (
        "/mnt/nas1/phoenix-task/Deaf_20/"
        "sz01-Deaf_20-202607093417298900000001/input/sequence.list"
    )
    dispatcher = AgentToolDispatcher(db_session, registry)

    pending = await dispatcher.dispatch(
        tool_name="remote.read_file",
        input={"path": path},
        context=context,
    )
    assert pending.status == "waiting_decision"
    assert executor.calls == []

    await agent_service.decide_action(
        action_id=pending.action_id,
        workspace_id="workspace-1",
        user_id="user-1",
        decision="approve",
    )
    resumed = await dispatcher.resume_action(
        action_id=pending.action_id,
        context=context,
    )

    assert resumed.status == "completed"
    assert resumed.result["path"] == path
    assert resumed.result["content"] == "sample-a\n"
    assert (
        "remote path is outside the remote project" not in executor.calls[0]["command"]
    )


@pytest.mark.asyncio
async def test_remote_exec_rejects_explicit_connection_outside_execution_target(
    db_session,
):
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
        session_metadata={
            "execution_target": {
                "type": "remote_ssh",
                "connection_id": str(selected.id),
            }
        },
    )
    executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="other.cluster.example.org\n",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    tool = RemoteExecTool(executor=executor)

    with pytest.raises(NotFoundError):
        await tool.run(
            {"connection_id": str(other.id), "command": "hostname"},
            _tool_context(db_session, session_id=str(agent_session.id)),
        )
    assert executor.calls == []


@pytest.mark.asyncio
async def test_remote_exec_ignores_stale_legacy_connection_when_target_is_canonical(
    db_session,
):
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
    stale = await service.create_connection(
        {
            "name": "Stale HPC",
            "host": "stale.cluster.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "ssh_config",
            "ssh_alias": "stale-hpc",
        },
        workspace_id="workspace-1",
    )
    agent_session = await _create_agent_session(
        db_session,
        session_metadata={
            "remote_connection_id": str(stale.id),
            "execution_target": {
                "type": "remote_ssh",
                "connection_id": str(selected.id),
            },
        },
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
        {"command": "hostname"},
        _tool_context(db_session, session_id=str(agent_session.id)),
    )

    assert result["connection"]["id"] == str(selected.id)
    assert executor.calls[0]["connection"].id == str(selected.id)
    with pytest.raises(NotFoundError):
        await tool.run(
            {"connection_id": str(stale.id), "command": "hostname"},
            _tool_context(db_session, session_id=str(agent_session.id)),
        )


@pytest.mark.asyncio
async def test_remote_project_session_sets_connection_and_working_directory(db_session):
    connection = await RemoteConnectionService(db_session).create_connection(
        {
            "name": "Phoenix login",
            "host": "phoenix-login.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "ssh_config",
            "ssh_alias": "phoenix-login",
        },
        workspace_id="workspace-1",
    )
    from app.services.agent_core.service import AgentCoreService
    from app.services.project_service import ProjectService

    project = await ProjectService(db_session).create_project(
        {
            "name": "Phoenix sample",
            "workspace_id": "workspace-1",
            "remote_connection_id": str(connection.id),
            "remote_root_path": "/inspurfsms102/B2C_RD1/sample",
        },
        user_id="user-1",
    )
    agent_session = await AgentCoreService(db_session).create_session(
        project_id=str(project.id),
        workspace_id="workspace-1",
        user_id="user-1",
    )
    executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="/inspurfsms102/B2C_RD1/sample\n",
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
            "connection_id": str(connection.id),
            "command": "pwd",
        },
        _tool_context(db_session, session_id=str(agent_session.id)),
    )

    assert agent_session.session_metadata["remote_connection_id"] == str(connection.id)
    assert result["working_directory"] == "/inspurfsms102/B2C_RD1/sample"
    assert executor.calls[0]["command"] == "cd /inspurfsms102/B2C_RD1/sample && pwd"


@pytest.mark.asyncio
async def test_metadata_remote_root_is_shared_by_snapshot_and_structured_tool_enforcement(
    db_session,
):
    from app.services.agent_core.permissions.context import PermissionContextResolver

    connection = await RemoteConnectionService(db_session).create_connection(
        {
            "name": "Metadata root login",
            "host": "metadata-root.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "agent",
        },
        workspace_id="workspace-1",
    )
    session = await _create_agent_session(
        db_session,
        session_metadata={
            "execution_target": {
                "type": "remote_ssh",
                "connection_id": str(connection.id),
            },
            "remote_project_root": "/metadata/project",
        },
    )
    snapshot = (
        await PermissionContextResolver(db_session).resolve(
            session_id=str(session.id),
            workspace_id="workspace-1",
            user_id="user-1",
        )
    ).snapshot()
    executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="ACGT\n",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    tool = RemoteReadFileTool(executor=executor)

    result = await tool.run(
        {"connection_id": str(connection.id), "path": "inputs/sample.txt"},
        _tool_context(db_session, session_id=str(session.id)),
    )

    assert snapshot["effective_roots"] == ["/metadata/project"]
    assert result["working_directory"] == "/metadata/project"
    command = executor.calls[0]["command"]
    assert "root_real=$(realpath" in command
    assert "/metadata/project/inputs/sample.txt" in command
    with pytest.raises(BadRequestError, match="cannot escape"):
        await tool.run(
            {"connection_id": str(connection.id), "path": "../secret.txt"},
            _tool_context(db_session, session_id=str(session.id)),
        )


@pytest.mark.asyncio
async def test_remote_project_session_ignores_metadata_connection_override(db_session):
    service = RemoteConnectionService(db_session)
    project_connection = await service.create_connection(
        {
            "name": "Phoenix login",
            "host": "phoenix-login.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "ssh_config",
            "ssh_alias": "phoenix-login",
        },
        workspace_id="workspace-1",
    )
    metadata_connection = await service.create_connection(
        {
            "name": "Metadata override",
            "host": "other-login.example.org",
            "port": 22,
            "username": "mallory",
            "auth_method": "ssh_config",
            "ssh_alias": "other-login",
        },
        workspace_id="workspace-1",
    )
    from app.services.agent_core.service import AgentCoreService
    from app.services.project_service import ProjectService

    project = await ProjectService(db_session).create_project(
        {
            "name": "Phoenix sample",
            "workspace_id": "workspace-1",
            "remote_connection_id": str(project_connection.id),
            "remote_root_path": "/inspurfsms102/B2C_RD1/sample",
        },
        user_id="user-1",
    )
    agent_session = await AgentCoreService(db_session).create_session(
        project_id=str(project.id),
        workspace_id="workspace-1",
        user_id="user-1",
        metadata={"remote_connection_id": str(metadata_connection.id)},
    )

    resolver = DatabaseRemoteConnectionResolver(db_session)
    connections = await resolver.list(
        workspace_id="workspace-1",
        user_id="user-1",
        session_id=str(agent_session.id),
    )

    assert agent_session.session_metadata["remote_connection_id"] == str(
        project_connection.id
    )
    assert [connection.id for connection in connections] == [str(project_connection.id)]
    with pytest.raises(NotFoundError):
        await resolver.get(
            str(metadata_connection.id),
            workspace_id="workspace-1",
            user_id="user-1",
            session_id=str(agent_session.id),
        )


@pytest.mark.asyncio
async def test_remote_project_resolver_ignores_metadata_added_after_session_create(
    db_session,
):
    service = RemoteConnectionService(db_session)
    project_connection = await service.create_connection(
        {
            "name": "Phoenix login",
            "host": "phoenix-login.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "ssh_config",
            "ssh_alias": "phoenix-login",
        },
        workspace_id="workspace-1",
    )
    metadata_connection = await service.create_connection(
        {
            "name": "Metadata override",
            "host": "other-login.example.org",
            "port": 22,
            "username": "mallory",
            "auth_method": "ssh_config",
            "ssh_alias": "other-login",
        },
        workspace_id="workspace-1",
    )
    from app.services.agent_core.service import AgentCoreService
    from app.services.project_service import ProjectService

    project = await ProjectService(db_session).create_project(
        {
            "name": "Phoenix sample",
            "workspace_id": "workspace-1",
            "remote_connection_id": str(project_connection.id),
            "remote_root_path": "/inspurfsms102/B2C_RD1/sample",
        },
        user_id="user-1",
    )
    agent_service = AgentCoreService(db_session)
    agent_session = await agent_service.create_session(
        project_id=str(project.id),
        workspace_id="workspace-1",
        user_id="user-1",
    )
    await agent_service.update_session(
        session_id=str(agent_session.id),
        workspace_id="workspace-1",
        user_id="user-1",
        updates={"metadata": {"remote_connection_id": str(metadata_connection.id)}},
    )

    resolver = DatabaseRemoteConnectionResolver(db_session)
    connections = await resolver.list(
        workspace_id="workspace-1",
        user_id="user-1",
        session_id=str(agent_session.id),
    )

    assert [connection.id for connection in connections] == [str(project_connection.id)]
    with pytest.raises(NotFoundError):
        await resolver.get(
            str(metadata_connection.id),
            workspace_id="workspace-1",
            user_id="user-1",
            session_id=str(agent_session.id),
        )


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

    assert (
        await resolver.list(
            workspace_id="workspace-1",
            user_id="user-1",
            session_id=str(agent_session.id),
        )
        == []
    )
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
    assert result["result"]["stdout"] == "hello remote"
    assert result["result"]["truncated"] is True


@pytest.mark.asyncio
async def test_remote_read_file_guards_remote_project_symlink_escape(db_session):
    connection = await RemoteConnectionService(db_session).create_connection(
        {
            "name": "Phoenix login",
            "host": "phoenix-login.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "ssh_config",
            "ssh_alias": "phoenix-login",
        },
        workspace_id="workspace-1",
    )
    from app.services.agent_core.service import AgentCoreService
    from app.services.project_service import ProjectService

    project = await ProjectService(db_session).create_project(
        {
            "name": "Phoenix sample",
            "workspace_id": "workspace-1",
            "remote_connection_id": str(connection.id),
            "remote_root_path": "/inspurfsms102/B2C_RD1/sample",
        },
        user_id="user-1",
    )
    agent_session = await AgentCoreService(db_session).create_session(
        project_id=str(project.id),
        workspace_id="workspace-1",
        user_id="user-1",
    )
    executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="secret",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    tool = RemoteReadFileTool(executor=executor)

    await tool.run(
        {
            "connection_id": str(connection.id),
            "path": "outside-link/secret.txt",
            "max_bytes": 100,
        },
        _tool_context(db_session, session_id=str(agent_session.id)),
    )

    command = executor.calls[0]["command"]
    assert "realpath --" in command
    assert "remote path is outside the remote project" in command


def test_remote_exec_nested_result_does_not_promote_command_artifact():
    descriptor = _artifact_descriptor(
        policy={"stdout": True, "stderr": True, "type": "remote_command"},
        tool_name="remote.exec",
        action_input={"connection_id": "conn-1", "command": "hostname"},
        result={
            "connection": {"id": "conn-1", "name": "HPC login"},
            "command": "hostname",
            "result": {
                "exit_code": 0,
                "stdout": "login.cluster.example.org\n",
                "stderr": "",
                "timed_out": False,
                "truncated": False,
            },
        },
    )

    assert descriptor is None


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


@pytest.mark.asyncio
async def test_remote_list_dir_guards_remote_project_symlink_escape(db_session):
    connection = await RemoteConnectionService(db_session).create_connection(
        {
            "name": "Phoenix login",
            "host": "phoenix-login.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "ssh_config",
            "ssh_alias": "phoenix-login",
        },
        workspace_id="workspace-1",
    )
    from app.services.agent_core.service import AgentCoreService
    from app.services.project_service import ProjectService

    project = await ProjectService(db_session).create_project(
        {
            "name": "Phoenix sample",
            "workspace_id": "workspace-1",
            "remote_connection_id": str(connection.id),
            "remote_root_path": "/inspurfsms102/B2C_RD1/sample",
        },
        user_id="user-1",
    )
    agent_session = await AgentCoreService(db_session).create_session(
        project_id=str(project.id),
        workspace_id="workspace-1",
        user_id="user-1",
    )
    executor = _FakeRemoteExecutor(
        RemoteCommandResult(
            exit_code=0,
            stdout="d\tresults\t0\n",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )
    )
    tool = RemoteListDirTool(executor=executor)

    await tool.run(
        {
            "connection_id": str(connection.id),
            "path": "outside-link",
        },
        _tool_context(db_session, session_id=str(agent_session.id)),
    )

    command = executor.calls[0]["command"]
    assert "realpath --" in command
    assert "remote path is outside the remote project" in command


def test_remote_list_dir_command_does_not_block_on_fifo(tmp_path):
    from app.services.agent_core.tools.remote.resources import _list_dir_command

    os.mkfifo(tmp_path / "named-pipe")

    result = subprocess.run(
        ["/bin/sh", "-c", _list_dir_command(str(tmp_path), 20)],
        capture_output=True,
        text=True,
        timeout=1,
        check=False,
    )

    assert result.returncode == 0
    assert "named-pipe" in result.stdout


def test_remote_project_paths_cannot_escape_working_directory():
    root = "/inspurfsms102/B2C_RD1/sample"
    from app.services.agent_core.tools.remote.resources import _remote_path_for_context

    with pytest.raises(BadRequestError):
        _remote_path_for_context("../outside.txt", root)
    with pytest.raises(BadRequestError):
        _remote_path_for_context("~/outside.txt", root)
    with pytest.raises(BadRequestError):
        _remote_path_for_context("/etc/passwd", root)


@pytest.mark.parametrize("tool", [RemoteReadFileTool(), RemoteListDirTool()])
@pytest.mark.parametrize(
    "path",
    ["/etc/passwd", "~/.ssh/config", "$HOME/.ssh/config", "../outside.txt"],
)
def test_unbounded_structured_remote_paths_require_explicit_approval(tool, path):
    target = CommandTargetProfile(
        kind="remote_ssh",
        trust_domain="cluster.example.org",
        identity="alice",
        sandbox_strength="none",
        connection_id="conn-1",
    )

    risk = tool.assess_risk({"path": path}, target=target)

    assert risk.level == "act_high"
    assert risk.requires_explicit_approval is True
    assert (
        PermissionPolicy()
        .decide(
            risk=risk,
            permission_mode="bypass",
            automation_mode="autonomous",
        )
        .decision
        == "ask"
    )


@pytest.mark.parametrize("tool", [RemoteReadFileTool(), RemoteListDirTool()])
def test_unbounded_structured_relative_path_requires_explicit_approval(tool):
    target = CommandTargetProfile(
        kind="remote_ssh",
        trust_domain="cluster.example.org",
        identity="alice",
        sandbox_strength="none",
        connection_id="conn-1",
    )

    risk = tool.assess_risk({"path": "results/run.log"}, target=target)

    assert risk.level == "act_high"
    assert risk.requires_explicit_approval is True
    assert (
        PermissionPolicy()
        .decide(
            risk=risk,
            permission_mode="bypass",
            automation_mode="autonomous",
        )
        .decision
        == "ask"
    )


@pytest.mark.parametrize("tool", [RemoteReadFileTool(), RemoteListDirTool()])
def test_runtime_selected_remote_path_requires_explicit_approval(tool):
    target = CommandTargetProfile(
        kind="local",
        trust_domain="local-machine",
        identity="local-user",
        sandbox_strength="none",
    )

    risk = tool.assess_risk({"path": "/etc/passwd"}, target=target)

    assert risk.level == "act_high"
    assert risk.requires_explicit_approval is True
    assert (
        PermissionPolicy()
        .decide(
            risk=risk,
            permission_mode="bypass",
            automation_mode="autonomous",
        )
        .decision
        == "ask"
    )


@pytest.mark.parametrize("tool", [RemoteReadFileTool(), RemoteListDirTool()])
@pytest.mark.parametrize(
    "path",
    ["/etc/passwd", "~/.ssh/config", "$HOME/.ssh/config", "../outside.txt"],
)
def test_bounded_structured_remote_paths_cannot_escape_root(tool, path):
    target = CommandTargetProfile(
        kind="remote_ssh",
        trust_domain="cluster.example.org",
        identity="alice",
        sandbox_strength="none",
        read_roots=("/analysis/project",),
        working_directory="/analysis/project",
        connection_id="conn-1",
    )

    risk = tool.assess_risk({"path": path}, target=target)

    assert risk.level == "act_high"
    assert risk.requires_explicit_approval is True


@pytest.mark.parametrize("tool", [RemoteReadFileTool(), RemoteListDirTool()])
def test_bounded_structured_remote_data_path_outside_root_is_full_access_safe(tool):
    target = CommandTargetProfile(
        kind="remote_ssh",
        trust_domain="cluster.example.org",
        identity="alice",
        sandbox_strength="none",
        read_roots=("/mnt/nas1/.bioinfoflow",),
        working_directory="/mnt/nas1/.bioinfoflow",
        connection_id="conn-1",
    )

    risk = tool.assess_risk(
        {
            "path": (
                "/mnt/nas1/phoenix-task/Deaf_20/"
                "sz01-Deaf_20-202607093417298900000001/input/sequence.list"
            )
        },
        target=target,
    )

    assert risk.level == "act_high"
    assert risk.requires_explicit_approval is False
    assert (
        PermissionPolicy()
        .decide(
            risk=risk,
            permission_mode="bypass",
            automation_mode="assisted",
        )
        .decision
        == "allow"
    )
    assert (
        PermissionPolicy()
        .decide(
            risk=risk,
            permission_mode="guarded_auto",
            automation_mode="assisted",
        )
        .decision
        == "ask"
    )


@pytest.mark.parametrize("tool", [RemoteReadFileTool(), RemoteListDirTool()])
def test_bounded_structured_remote_absolute_path_inside_root_is_read(tool):
    target = CommandTargetProfile(
        kind="remote_ssh",
        trust_domain="cluster.example.org",
        identity="alice",
        sandbox_strength="none",
        read_roots=("/analysis/project",),
        working_directory="/analysis/project",
        connection_id="conn-1",
    )

    risk = tool.assess_risk(
        {"path": "/analysis/project/input/sequence.list"},
        target=target,
    )

    assert risk.level == "read"


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
    assert "remote.connections.list" in exposure.exposed_names(
        policy={"name": "default"}
    )
    assert "remote.read_file" in exposure.exposed_names(policy={"name": "default"})
    assert "remote.list_dir" in exposure.exposed_names(policy={"name": "default"})
    assert registry.get("remote.exec").spec.risk_level == "act_high"
    assert registry.get("remote.read_file").spec.risk_level == "read"
    assert registry.get("remote.read_file").spec.write_scope == []
    assert registry.get("remote.list_dir").spec.risk_level == "read"
    assert registry.get("remote.list_dir").spec.write_scope == []


def test_remote_ssh_toolset_exposure_hides_local_and_platform_tools():
    registry = build_default_tool_registry()
    exposure = ToolsetExposure(registry)
    execution_target = {"type": "remote_ssh", "connection_id": "conn-1"}

    execution_tools = exposure.exposed_names(
        policy={"name": "execution"},
        execution_target=execution_target,
    )
    plan_tools = exposure.exposed_names(
        policy={"name": "plan"},
        execution_target=execution_target,
    )
    worker_tools = exposure.exposed_names(
        policy={"name": "execution"},
        role="worker",
        execution_target=execution_target,
    )

    hidden_prefixes = (
        "files.",
        "projects.",
        "workflows.",
        "runs.",
        "images.",
        "scheduler.",
    )
    assert "bash" not in execution_tools
    assert "grep" not in execution_tools
    assert "glob" not in execution_tools
    assert not any(name.startswith(hidden_prefixes) for name in execution_tools)
    assert {
        "remote.connections.list",
        "remote.exec",
        "remote.read_file",
        "remote.list_dir",
    } <= execution_tools
    assert {"skills.load", "web.search", "web.fetch"} <= execution_tools
    assert {"skills.list", "plugins.list"}.isdisjoint(execution_tools)
    assert {"todo_write", "ask_user"} <= execution_tools

    assert "remote.exec" not in plan_tools
    assert {
        "remote.read_file",
        "todo_write",
        "ask_user",
        "exit_plan_mode",
    } <= plan_tools
    assert "bash" not in plan_tools

    assert {
        "remote.connections.list",
        "remote.read_file",
        "remote.list_dir",
    } <= worker_tools
    assert "remote.exec" not in worker_tools
    assert "ask_user" not in worker_tools
    assert "todo_write" not in worker_tools
    assert "projects.list" not in worker_tools


def test_manual_scope_with_remote_exposes_remote_and_local_tools():
    registry = build_default_tool_registry()
    exposure = ToolsetExposure(registry)

    tools = exposure.exposed_names(
        policy={"name": "execution"},
        execution_target={"type": "local"},
        execution_scope={
            "mode": "manual",
            "selected_targets": [
                {"type": "local"},
                {"type": "remote_ssh", "connection_id": "conn-1"},
            ],
        },
    )

    assert "remote.exec" in tools
    assert "remote.read_file" in tools
    assert "bash" in tools


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
