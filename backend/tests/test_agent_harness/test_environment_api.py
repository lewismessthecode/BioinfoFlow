from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.remote_connection import RemoteConnection
from app.workspace import DEFAULT_WORKSPACE_ID


@pytest.mark.asyncio
async def test_environment_list_exposes_local_and_safe_workspace_ssh_descriptors(
    async_client,
    db_session,
) -> None:
    connection = RemoteConnection(
        workspace_id=DEFAULT_WORKSPACE_ID,
        name="GPU cluster",
        host="gpu.internal",
        port=2202,
        username="runner",
        auth_method="agent",
        encrypted_password="must-not-leak",
        last_status="online",
    )
    db_session.add(connection)
    await db_session.commit()

    response = await async_client.get("/api/v1/agent/environments")

    assert response.status_code == 200
    assert response.json()["data"] == [
        {
            "id": "local",
            "kind": "local",
            "label": "Local",
            "description": "This machine",
            "status": "online",
        },
        {
            "id": str(connection.id),
            "kind": "ssh",
            "label": "GPU cluster",
            "description": "runner@gpu.internal:2202",
            "status": "online",
        },
    ]
    assert "must-not-leak" not in response.text


@pytest.mark.asyncio
async def test_session_create_and_patch_validate_and_publish_environment_scope(
    async_client,
    db_session,
) -> None:
    connection = RemoteConnection(
        workspace_id=DEFAULT_WORKSPACE_ID,
        name="GPU cluster",
        host="gpu.internal",
        port=22,
        username="runner",
        auth_method="agent",
    )
    db_session.add(connection)
    await db_session.commit()
    model = {"target": {"model_name": "fake"}}

    with patch("app.api.v1.agent.resolve_model_snapshot", return_value=model):
        created = await async_client.post(
            "/api/v1/agent/sessions",
            json={
                "environment_scope": {
                    "mode": "manual",
                    "environment_ids": ["local", str(connection.id)],
                }
            },
        )

    assert created.status_code == 201
    session_id = created.json()["data"]["session"]["id"]
    assert created.json()["data"]["session"]["environment_scope"] == {
        "mode": "manual",
        "environment_ids": ["local", str(connection.id)],
    }

    rejected = await async_client.patch(
        f"/api/v1/agent/sessions/{session_id}",
        json={
            "environment_scope": {
                "mode": "manual",
                "environment_ids": ["not-authorized"],
            }
        },
    )
    updated = await async_client.patch(
        f"/api/v1/agent/sessions/{session_id}",
        json={"environment_scope": {"mode": "auto"}},
    )

    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "BAD_REQUEST"
    assert updated.status_code == 200
    assert updated.json()["data"]["session"]["environment_scope"] == {
        "mode": "auto",
        "environment_ids": None,
    }
