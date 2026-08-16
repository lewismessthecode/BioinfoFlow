from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.remote_connection import RemoteConnection
from app.repositories.agent_harness_repo import AgentHarnessRepository
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

    run = await AgentHarnessRepository(db_session).create_run(session_id)
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
    assert (
        str(second.id)
        not in run.turn_execution_config["environment_scope"]["environment_ids"]
    )
