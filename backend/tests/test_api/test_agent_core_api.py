from __future__ import annotations

import asyncio

import pytest


async def _create_project(async_client) -> str:
    resp = await async_client.post(
        "/api/v1/projects",
        json={
            "name": "AgentCore API Project",
            "description": "Contract test project",
        },
    )
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


async def _wait_for_turn(async_client, turn_id: str) -> dict:
    for _ in range(40):
        resp = await async_client.get(f"/api/v1/agent/turns/{turn_id}")
        assert resp.status_code == 200
        turn = resp.json()["data"]
        if turn["status"] in {"completed", "failed", "cancelled", "waiting_approval"}:
            return turn
        await asyncio.sleep(0.05)
    raise AssertionError("agent turn did not reach a terminal or waiting state")


@pytest.mark.asyncio
async def test_agent_core_session_turn_event_and_artifact_contract(async_client, monkeypatch):
    async def fake_completion(*args, **kwargs):
        class FakeUsage:
            def model_dump(self):
                return {"prompt_tokens": 6, "completion_tokens": 10, "total_tokens": 16}

        class FakeMessage:
            content = "Mocked model reply."

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = FakeUsage()

        return FakeResponse()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)

    project_id = await _create_project(async_client)

    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "WGS triage",
            "permission_mode": "guarded_auto",
            "automation_mode": "assisted",
            "model_selection": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
            },
            "metadata": {"batch": "b001"},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]
    assert session["title"] == "WGS triage"
    assert session["metadata"] == {
        "batch": "b001",
        "model_selection": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
        },
    }
    assert session["model_selection"] == {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
    }
    assert session["permission_mode"] == "guarded_auto"

    list_sessions = await async_client.get("/api/v1/agent/sessions")
    assert list_sessions.status_code == 200
    assert list_sessions.json()["data"][0]["id"] == session["id"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={
            "input_text": "Check the FASTQ files before running alignment.",
            "input_parts": [{"type": "text", "text": "preflight"}],
        },
    )
    assert create_turn.status_code == 202
    turn = create_turn.json()["data"]
    assert turn["session_id"] == session["id"]
    assert turn["status"] == "queued"

    turn = await _wait_for_turn(async_client, turn["id"])
    assert turn["status"] == "completed"
    assert turn["final_text"] == "Mocked model reply."
    assert turn["model_selection"] == {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
    }
    assert turn["model_profile_snapshot"]["resolved_model_selection"] == {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
    }
    assert turn["model_profile_snapshot"]["resolved_model_source"] == "session"

    list_turns = await async_client.get(
        f"/api/v1/agent/sessions/{session['id']}/turns"
    )
    assert list_turns.status_code == 200
    assert [item["id"] for item in list_turns.json()["data"]] == [turn["id"]]

    events = await async_client.get(f"/api/v1/agent/turns/{turn['id']}/events")
    assert events.status_code == 200
    assert [item["type"] for item in events.json()["data"]] == [
        "turn.created",
        "turn.started",
        "model.selected",
        "assistant.thinking.summary",
        "assistant.text.completed",
        "turn.completed",
    ]

    stream_lines: list[str] = []
    async with async_client.stream(
        "GET",
        f"/api/v1/agent/sessions/{session['id']}/stream?follow=false",
    ) as stream:
        assert stream.status_code == 200
        async for line in stream.aiter_lines():
            stream_lines.append(line)
            if line == "event: ready":
                break
    assert "event: turn.created" in stream_lines
    assert "event: ready" in stream_lines

    artifacts = await async_client.get(
        f"/api/v1/agent/sessions/{session['id']}/artifacts"
    )
    assert artifacts.status_code == 200
    assert artifacts.json()["data"] == []

    cancel = await async_client.post(f"/api/v1/agent/turns/{turn['id']}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["data"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_legacy_agent_message_endpoint_is_removed(async_client):
    project_id = await _create_project(async_client)

    resp = await async_client.post(
        "/api/v1/agent/message",
        json={"project_id": project_id, "content": "old endpoint"},
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_agent_core_memory_contract(async_client):
    project_id = await _create_project(async_client)

    proposal = await async_client.post(
        "/api/v1/agent/memories/proposals",
        json={
            "project_id": project_id,
            "scope": "project",
            "type": "project_convention",
            "content": {"reference_genome": "hg38"},
            "source": {"kind": "user_confirmed"},
            "confidence": 95,
        },
    )
    assert proposal.status_code == 201
    memory = proposal.json()["data"]
    assert memory["status"] == "proposed"
    assert memory["content"] == {"reference_genome": "hg38"}

    listed = await async_client.get(
        f"/api/v1/agent/memories?project_id={project_id}&status=proposed"
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["data"]] == [memory["id"]]

    accepted = await async_client.post(
        f"/api/v1/agent/memories/{memory['id']}/accept",
        json={"note": "confirmed"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["data"]["status"] == "accepted"

    rejected_proposal = await async_client.post(
        "/api/v1/agent/memories/proposals",
        json={
            "project_id": project_id,
            "scope": "workflow",
            "type": "run_lesson",
            "content": {"obsolete": True},
        },
    )
    rejected_memory = rejected_proposal.json()["data"]
    rejected = await async_client.post(
        f"/api/v1/agent/memories/{rejected_memory['id']}/reject",
        json={"note": "not reusable"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["status"] == "rejected"

    disabled_proposal = await async_client.post(
        "/api/v1/agent/memories/proposals",
        json={
            "project_id": project_id,
            "scope": "dataset",
            "type": "analysis_template",
            "content": {"template": "old-report"},
        },
    )
    disabled_memory = disabled_proposal.json()["data"]
    disabled = await async_client.post(
        f"/api/v1/agent/memories/{disabled_memory['id']}/disable",
        json={"note": "superseded"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["data"]["status"] == "disabled"
