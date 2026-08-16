from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.agent_ui.contracts import AgentUiContractBundle


def test_agent_ui_contract_bundle_generates_artifact_detail_shape() -> None:
    schema = AgentUiContractBundle.model_json_schema()

    assert "artifact" in schema["properties"]
    assert "StoredArtifactResourceView" in schema["$defs"]


@pytest.mark.asyncio
async def test_agent_ui_bootstrap_exposes_versioned_stable_slots(async_client) -> None:
    with patch(
        "app.services.agent_ui.bootstrap.resolve_model_snapshot",
        return_value={
            "model_id": "model-record-1",
            "capabilities": {"supports_tools": True},
            "target": {
                "provider_kind": "openai",
                "model_name": "gpt-5.6",
            },
        },
    ):
        response = await async_client.get(
            "/api/v1/agent/ui/bootstrap",
            params={"locale": "zh-CN"},
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["protocol_version"] == 1
    assert payload["model"] == {
        "catalog_model_id": "model-record-1",
        "provider": "openai",
        "model": "gpt-5.6",
        "display_name": "gpt-5.6",
        "supports_vision": False,
        "supports_reasoning": False,
        "supports_tools": True,
    }
    assert payload["permission_mode"] == "ask_dangerous"
    assert payload["capabilities"] == {
        "reasoning": True,
        "tool_activity": True,
        "approvals": True,
        "artifacts": True,
        "starter_prompts": True,
        "multi_target_execution": True,
        "retry": True,
        "edit_and_resend": True,
    }
    assert payload["execution_scope"] == {"mode": "auto", "target_ids": []}
    assert payload["execution_targets"] == [
        {
            "id": "local",
            "handle": "local",
            "alias": "Local",
            "kind": "local",
            "status": "online",
            "primary": True,
            "disabled_reason": None,
        }
    ]
    assert [item["id"] for item in payload["starter_prompts"]] == [
        "inspect-workspace",
        "plan-analysis",
        "review-failures",
    ]
    assert "技能" in payload["composer_hint"]


@pytest.mark.asyncio
async def test_agent_ui_bootstrap_only_enables_verified_remote_roots(
    async_client,
    monkeypatch,
) -> None:
    created = await async_client.post(
        "/api/v1/connections",
        json={
            "name": "Compute A",
            "host": "compute-a.example.org",
            "port": 22,
            "username": "alice",
            "auth_method": "agent",
        },
    )
    assert created.status_code == 201
    connection_id = created.json()["data"]["id"]

    before = await async_client.get("/api/v1/agent/ui/bootstrap")
    remote_before = next(
        target
        for target in before.json()["data"]["execution_targets"]
        if target["id"] == connection_id
    )
    assert remote_before["disabled_reason"] == "Verify this SSH connection before Agent use"

    from app.services.remote_connection_service import RemoteConnectionTestResult

    async def fake_test(self, connection):
        del self, connection
        return RemoteConnectionTestResult(
            status="online",
            verified_root_path="/home/alice",
        )

    monkeypatch.setattr(
        "app.services.remote_connection_service.SshRemoteConnectionTester.test",
        fake_test,
    )
    tested = await async_client.post(f"/api/v1/connections/{connection_id}/test")
    assert tested.status_code == 200

    after = await async_client.get("/api/v1/agent/ui/bootstrap")
    remote_after = next(
        target
        for target in after.json()["data"]["execution_targets"]
        if target["id"] == connection_id
    )
    assert remote_after["disabled_reason"] is None


@pytest.mark.asyncio
async def test_agent_ui_bootstrap_redacts_user_at_host_remote_labels(async_client) -> None:
    created = await async_client.post(
        "/api/v1/connections",
        json={
            "name": "alice@10.0.0.5",
            "host": "10.0.0.5",
            "port": 22,
            "username": "alice",
            "auth_method": "agent",
        },
    )
    assert created.status_code == 201
    connection_id = created.json()["data"]["id"]

    response = await async_client.get("/api/v1/agent/ui/bootstrap")

    remote = next(
        target
        for target in response.json()["data"]["execution_targets"]
        if target["id"] == connection_id
    )
    assert remote["alias"] == "Remote 1"
    assert "@" not in remote["handle"]


@pytest.mark.asyncio
async def test_agent_snapshot_and_events_publish_ui_protocol_version(async_client) -> None:
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        response = await async_client.post("/api/v1/agent/sessions", json={})

    assert response.status_code == 201
    snapshot = response.json()["data"]
    assert snapshot["protocol_version"] == 1
    assert snapshot["capabilities"]["multi_target_execution"] is True
