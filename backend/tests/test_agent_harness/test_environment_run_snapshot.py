from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.remote_connection import RemoteConnection
from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.services.agent_harness.environment_runtime import (
    routed_workspace_runtime_for_session,
)
from app.services.agent_harness.turn_execution_config import (
    resolve_turn_execution_config,
)
from app.services.agent_harness.tools.specs import ToolCall
from app.services.agent_harness.turn_settings import effective_turn_session
from app.services.remote_execution import RemoteCommandResult
from app.workspace import DEFAULT_WORKSPACE_ID


@pytest.mark.asyncio
async def test_auto_environment_scope_resolves_once_when_run_is_created(
    async_client,
    db_session,
) -> None:
    first = RemoteConnection(
        workspace_id=DEFAULT_WORKSPACE_ID,
        name="First",
        host="first.internal",
        port=22,
        username="runner",
        auth_method="agent",
    )
    db_session.add(first)
    await db_session.commit()
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]

    repository = AgentHarnessRepository(db_session)
    session = await repository.get_session(session_id)
    assert session is not None
    run = await repository.create_run(
        session_id,
        turn_execution_config=await resolve_turn_execution_config(
            db_session,
            session,
        ),
    )
    second = RemoteConnection(
        workspace_id=DEFAULT_WORKSPACE_ID,
        name="Second",
        host="second.internal",
        port=22,
        username="runner",
        auth_method="agent",
    )
    db_session.add(second)
    await db_session.commit()
    await db_session.refresh(run)

    assert run.turn_execution_config["environment_scope"] == {
        "mode": "auto",
        "environment_ids": ["local", str(first.id)],
    }
    target = run.turn_execution_config["environment_targets"][str(first.id)]
    assert target == {
        "kind": "ssh",
        "display_name": "First",
        "host": "first.internal",
        "port": 22,
        "username": "runner",
        "configuration_revision": target["configuration_revision"],
    }
    assert len(target["configuration_revision"]) == 64
    assert "credential" not in repr(target).lower()
    assert (
        str(second.id)
        not in run.turn_execution_config["environment_scope"]["environment_ids"]
    )


@pytest.mark.asyncio
async def test_run_rejects_ssh_credential_drift_before_tool_execution(
    async_client,
    db_session,
) -> None:
    connection = RemoteConnection(
        workspace_id=DEFAULT_WORKSPACE_ID,
        name="Frozen target",
        host="before.internal",
        port=22,
        username="runner",
        auth_method="password",
        encrypted_password="cipher-before",
    )
    db_session.add(connection)
    await db_session.commit()
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post(
            "/api/v1/agent/sessions",
            json={
                "environment_scope": {
                    "mode": "manual",
                    "environment_ids": [str(connection.id)],
                }
            },
        )
    repository = AgentHarnessRepository(db_session)
    session_id = created.json()["data"]["session"]["id"]
    session = await repository.get_session(session_id)
    assert session is not None
    run = await repository.create_run(
        session_id,
        turn_execution_config=await resolve_turn_execution_config(
            db_session,
            session,
        ),
    )

    connection.encrypted_password = "cipher-after"
    await db_session.commit()

    class _RecordingExecutor:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def run(self, _connection, command, **_kwargs):
            self.calls.append(command)
            return RemoteCommandResult(
                exit_code=0,
                stdout="/srv/workspace\n",
                stderr="",
                timed_out=False,
                truncated=False,
                stdout_truncated=False,
                stderr_truncated=False,
            )

    executor = _RecordingExecutor()

    runtime = routed_workspace_runtime_for_session(
        db_session,
        effective_turn_session(session, run),
        remote_executor=executor,
    )
    descriptor = runtime.router.scope.require(str(connection.id))
    assert descriptor.display_name == "Frozen target"
    assert descriptor.description == "runner@before.internal:22"
    result = await runtime.execute(
        ToolCall(
            "read-1",
            "read",
            {"environment_id": str(connection.id), "path": "README.md"},
        )
    )

    assert result.status == "failed"
    assert result.output == {
        "code": "environment_unavailable",
        "environment_id": str(connection.id),
    }
    assert executor.calls == []
