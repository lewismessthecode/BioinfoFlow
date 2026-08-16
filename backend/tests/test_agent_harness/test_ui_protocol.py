from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_agent_ui_bootstrap_exposes_versioned_stable_slots(async_client) -> None:
    response = await async_client.get(
        "/api/v1/agent/ui/bootstrap",
        params={"locale": "zh-CN"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["protocol_version"] == 1
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
