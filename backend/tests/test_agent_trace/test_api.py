from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_trace_endpoints_expose_timeline_and_lazy_detail(async_client) -> None:
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={
            "target": {
                "provider_kind": "openai",
                "model_name": "gpt-5",
                "wire_protocol": "responses",
            }
        },
    ):
        created = await async_client.post(
            "/api/v1/agent/sessions",
            json={"title": "Trace session"},
        )
    assert created.status_code == 201
    session_id = created.json()["data"]["session"]["id"]

    timeline = await async_client.get(f"/api/v1/agent/sessions/{session_id}/trace")

    assert timeline.status_code == 200
    data = timeline.json()["data"]
    assert data["protocol"] == "bioinfoflow.agent.trace"
    assert data["protocol_version"] == 1
    assert data["session"]["id"] == session_id
    assert data["events"][0]["id"] == f"system:{session_id}"
    assert "payload" not in data["events"][0]

    detail = await async_client.get(
        f"/api/v1/agent/sessions/{session_id}/trace/events/system:{session_id}"
    )

    assert detail.status_code == 200
    detail_data = detail.json()["data"]
    assert detail_data["event_id"] == f"system:{session_id}"
    assert detail_data["payload"]["schema_version"] == 1
    assert "schema" in detail_data


@pytest.mark.asyncio
async def test_trace_detail_returns_not_found_for_unknown_event(async_client) -> None:
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={
            "target": {
                "provider_kind": "openai",
                "model_name": "gpt-5",
                "wire_protocol": "responses",
            }
        },
    ):
        created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]

    response = await async_client.get(
        f"/api/v1/agent/sessions/{session_id}/trace/events/model:missing"
    )

    assert response.status_code == 404
