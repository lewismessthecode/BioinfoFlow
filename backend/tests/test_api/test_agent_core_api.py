from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import app.api.v1.agent as agent_api_module
from app.api.deps import get_current_user
from app.auth.session import AuthUser
from app.config import settings
from app.models.agent_core import AgentEvent, AgentTurn
from app.models.llm import LlmModel, LlmProvider, LlmProviderCredential
from app.models.remote_connection import RemoteConnection
from app.path_layout import project_home, skills_root
from app.services.agent_core import AgentCoreService
from app.services.agent_core.actions import AgentActionService
from app.services.agent_core.runtime import AgentCoreRuntime
from app.services.agent_core.tools import AgentToolContext, build_default_tool_registry
from app.services.agent_core.tools.executor import AgentToolExecutor
from app.services.llm.credentials import encrypt_secret, generate_credential_fingerprint
from app.services.model_runtime.gateway import ModelGateway
from app.workspace import DEFAULT_WORKSPACE_ID


class _FakeBackend:
    def __init__(self, completion: Callable[..., Awaitable[Any]]) -> None:
        self.completion = completion

    async def invoke(
        self,
        wire_protocol: str,
        request: dict[str, Any],
        *,
        network_access: str = "unrestricted",
    ) -> Any:
        assert wire_protocol == "chat_completions"
        return await self.completion(**request)


def _install_fake_completion(monkeypatch, completion) -> None:
    gateway = ModelGateway(backend=_FakeBackend(completion))
    monkeypatch.setattr(
        "app.services.agent_core.runtime.ModelGateway",
        lambda: gateway,
    )


@pytest.mark.asyncio
async def test_permission_policy_version_and_action_audit_api_contract(
    async_client,
    db_session,
) -> None:
    created_response = await async_client.post(
        "/api/v1/agent/sessions",
        json={"title": "Permission audit"},
    )
    assert created_response.status_code == 201
    created = created_response.json()["data"]
    assert created["permission_policy_version"] == 1

    updated_response = await async_client.patch(
        f"/api/v1/agent/sessions/{created['id']}",
        json={"permission_mode": "ask_each_action"},
    )
    assert updated_response.status_code == 200
    updated = updated_response.json()["data"]
    assert updated["permission_policy_version"] == 2

    service = AgentCoreService(db_session)
    turn = await service.create_turn_record(
        session_id=created["id"],
        workspace_id=created["workspace_id"],
        user_id=created["user_id"],
        input_text="Create an auditable action.",
    )
    audited = await AgentActionService(db_session).request_action(
        turn_id=str(turn.id),
        kind="tool",
        name="test.high",
        requested_risk="act_high",
        permission_mode="ask_each_action",
        evaluated_policy_version=2,
        permission_context_snapshot={"policy_version": 2},
    )
    audited_response = await async_client.post(
        f"/api/v1/agent/actions/{audited.id}/decision",
        json={"decision": "reject"},
    )
    assert audited_response.status_code == 200
    audited_payload = audited_response.json()["data"]
    assert audited_payload["evaluated_policy_version"] == 2
    assert audited_payload["permission_context_snapshot"] == {"policy_version": 2}

    legacy = await service.action_repo.create(
        session_id=created["id"],
        turn_id=str(turn.id),
        kind="tool",
        name="legacy.action",
        input={},
        risk_level="act_high",
        permission_decision={"decision": "ask"},
        status="waiting_decision",
    )
    legacy_response = await async_client.post(
        f"/api/v1/agent/actions/{legacy.id}/decision",
        json={"decision": "reject"},
    )
    assert legacy_response.status_code == 200
    legacy_payload = legacy_response.json()["data"]
    assert legacy_payload["evaluated_policy_version"] is None
    assert legacy_payload["permission_context_snapshot"] is None


@pytest.mark.asyncio
async def test_get_remote_action_exposes_safe_executor_snapshot(
    async_client,
    db_session,
) -> None:
    connection = RemoteConnection(
        workspace_id=DEFAULT_WORKSPACE_ID,
        name="Sensitive remote",
        host="safe-host.internal",
        port=22,
        username="analyst",
        auth_method="password",
        encrypted_password="encrypted-password-must-not-leak",
        encrypted_private_key="encrypted-key-must-not-leak",
        key_path="/sensitive/id_ed25519",
    )
    db_session.add(connection)
    await db_session.commit()
    await db_session.refresh(connection)
    create_response = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "title": "Remote action audit",
            "execution_target": {
                "type": "remote_ssh",
                "connection_id": str(connection.id),
            },
            "permission_mode": "ask_each_action",
        },
    )
    assert create_response.status_code == 201
    session = create_response.json()["data"]
    service = AgentCoreService(db_session)
    turn = await service.create_turn_record(
        session_id=session["id"],
        workspace_id=session["workspace_id"],
        user_id=session["user_id"],
        input_text="Run a remote diagnostic.",
    )
    result = await AgentToolExecutor(
        db_session,
        build_default_tool_registry(),
    ).execute(
        tool_name="remote.exec",
        input={"command": "hostname"},
        context=AgentToolContext(
            db=db_session,
            workspace_id=session["workspace_id"],
            user_id=session["user_id"],
            session_id=session["id"],
            turn_id=str(turn.id),
        ),
        toolset_policy={"name": "execution"},
    )
    assert result.status == "waiting_decision"

    response = await async_client.get(f"/api/v1/agent/actions/{result.action_id}")

    assert response.status_code == 200
    action = response.json()["data"]
    assert action["permission_context_snapshot"]["command_risk"]["level"] == "act_low"
    assert action["permission_context_snapshot"]["command_risk"]["effects"] == [
        "read"
    ]
    assert action["permission_context_snapshot"]["remote_identity"]["host"] == (
        "safe-host.internal"
    )
    serialized = str(action)
    assert "encrypted-password-must-not-leak" not in serialized
    assert "encrypted-key-must-not-leak" not in serialized
    assert "/sensitive/id_ed25519" not in serialized


@pytest.mark.asyncio
async def test_get_action_does_not_reveal_cross_scope_existence(
    async_client,
    app,
    db_session,
) -> None:
    create_response = await async_client.post(
        "/api/v1/agent/sessions",
        json={"title": "Private action"},
    )
    session = create_response.json()["data"]
    service = AgentCoreService(db_session)
    turn = await service.create_turn_record(
        session_id=session["id"],
        workspace_id=session["workspace_id"],
        user_id=session["user_id"],
        input_text="Private action.",
    )
    action = await service.action_repo.create(
        session_id=session["id"],
        turn_id=str(turn.id),
        kind="tool",
        name="private.action",
        input={},
        risk_level="read",
        status="completed",
    )

    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="other-user",
        workspace_id="other-workspace",
    )
    try:
        hidden = await async_client.get(f"/api/v1/agent/actions/{action.id}")
        missing = await async_client.get(
            "/api/v1/agent/actions/00000000-0000-0000-0000-000000000099"
        )
        hidden_resume = await async_client.post(
            f"/api/v1/agent/actions/{action.id}/resume"
        )
        missing_resume = await async_client.post(
            "/api/v1/agent/actions/00000000-0000-0000-0000-000000000099/resume"
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert hidden.status_code == missing.status_code == 404
    assert hidden.json()["error"]["code"] == missing.json()["error"]["code"]
    assert hidden.json()["error"]["message"] == missing.json()["error"]["message"]
    assert hidden_resume.status_code == missing_resume.status_code == 404
    assert hidden_resume.json()["error"]["code"] == missing_resume.json()["error"][
        "code"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "status", "requires_resume", "message"),
    [
        ("platform", "requested", True, "Only tool actions can be resumed"),
        ("tool", "completed", True, "Tool action is not awaiting resume"),
        ("tool", "requested", False, "Tool action is not awaiting resume"),
    ],
)
async def test_resume_action_rejects_actions_outside_external_resume_boundary(
    async_client,
    db_session,
    kind: str,
    status: str,
    requires_resume: bool,
    message: str,
) -> None:
    create_response = await async_client.post(
        "/api/v1/agent/sessions",
        json={"title": "Non-resumable action"},
    )
    assert create_response.status_code == 201
    session = create_response.json()["data"]
    service = AgentCoreService(db_session)
    turn = await service.create_turn_record(
        session_id=session["id"],
        workspace_id=session["workspace_id"],
        user_id=session["user_id"],
        input_text="Run an automatically allowed tool.",
    )
    action = await service.action_repo.create(
        session_id=session["id"],
        turn_id=str(turn.id),
        kind=kind,
        name="auto.allowed",
        input={},
        risk_level="read",
        permission_decision={"decision": "allow"},
        status=status,
        requires_resume=requires_resume,
        tool_call_id="call-auto-allowed",
    )

    response = await async_client.post(
        f"/api/v1/agent/actions/{action.id}/resume"
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == message
    await db_session.refresh(turn)
    assert turn.resume_batch_token is None


def _auth_user(
    *,
    user_id: str = "user-1",
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    role: str = "owner",
) -> AuthUser:
    return AuthUser(
        id=user_id,
        name=f"User {user_id}",
        email=f"{user_id}@bioinfoflow.test",
        role=role,
        workspace_id=workspace_id,
    )


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


def _event_types(events: list[dict]) -> list[str]:
    return [item["type"] for item in events]


def _write_skill(name: str, description: str, body: str) -> None:
    skill_dir = skills_root() / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                "tags: [agent, test]",
                "---",
                body,
            ]
        ),
        encoding="utf-8",
    )


def _write_repo_skill(
    repo_root: Path,
    name: str,
    description: str,
    body: str,
) -> None:
    skill_dir = repo_root / ".agents" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                "tags: [repo, test]",
                "---",
                body,
            ]
        ),
        encoding="utf-8",
    )


async def _create_llm_model(async_client) -> dict:
    provider_response = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Agent Test Gateway",
            "kind": "openai_compatible",
            "base_url": "https://models.internal.example/v1",
        },
    )
    assert provider_response.status_code == 201
    provider = provider_response.json()["data"]

    model_response = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": provider["id"],
            "model_id": "agent-test-model",
            "display_name": "Agent Test Model",
            "supports_tools": True,
            "supports_streaming": True,
        },
    )
    assert model_response.status_code == 201
    return model_response.json()["data"]


async def _create_llm_profile(
    async_client,
    *,
    name: str,
    primary_model_id: str,
    prefer_streaming: bool | None = None,
    allow_thinking: bool | None = None,
    allow_tools: bool | None = None,
) -> dict:
    payload: dict[str, object] = {
        "name": name,
        "task_type": "agent_core",
        "primary_model_id": primary_model_id,
    }
    if prefer_streaming is not None:
        payload["prefer_streaming"] = prefer_streaming
    if allow_thinking is not None:
        payload["allow_thinking"] = allow_thinking
    if allow_tools is not None:
        payload["allow_tools"] = allow_tools
    response = await async_client.post("/api/v1/llm/model-profiles", json=payload)
    assert response.status_code == 201
    return response.json()["data"]


async def _create_scoped_llm_model(
    db_session,
    *,
    provider_user_id: str,
    model_name: str,
) -> LlmModel:
    provider = LlmProvider(
        name=f"{model_name} provider",
        kind="openai_compatible",
        base_url="https://models.internal.example/v1",
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id=provider_user_id,
        enabled=True,
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    model = LlmModel(
        provider_id=str(provider.id),
        model_id=model_name,
        display_name=model_name,
        supports_tools=True,
        supports_streaming=True,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


@pytest.mark.asyncio
async def test_agent_skills_api_lists_and_loads_local_manifests(
    async_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "repo_root", str(tmp_path / "empty-repo"))
    _write_skill(
        "nextflow-debugging",
        "Diagnose failed Nextflow runs.",
        "Use logs and audit events before explaining failures.",
    )

    listed = await async_client.get("/api/v1/agent/skills")
    assert listed.status_code == 200
    skills = listed.json()["data"]["skills"]
    assert skills == [
        {
            "name": "nextflow-debugging",
            "version": "0.1.0",
            "description": "Diagnose failed Nextflow runs.",
            "tags": ["agent", "test"],
            "source": "configured",
            "root": str(skills_root()),
            "path": str(skills_root() / "nextflow-debugging" / "SKILL.md"),
        }
    ]
    assert "body" not in skills[0]

    loaded = await async_client.get("/api/v1/agent/skills/nextflow-debugging")
    assert loaded.status_code == 200
    assert loaded.json()["data"]["body"] == "Use logs and audit events before explaining failures."

    missing = await async_client.get("/api/v1/agent/skills/missing-skill")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_agent_skills_api_prefers_repo_skill_over_configured_duplicate(
    async_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo_root = tmp_path / "repo"
    repo_skills_root = repo_root / ".agents" / "skills"
    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    _write_skill(
        "shared-qc",
        "Configured duplicate guidance.",
        "Configured body should not be loaded.",
    )
    _write_repo_skill(
        repo_root,
        "shared-qc",
        "Repo duplicate guidance.",
        "Repo body should be loaded.",
    )

    listed = await async_client.get("/api/v1/agent/skills")

    assert listed.status_code == 200
    assert listed.json()["data"]["skills"] == [
        {
            "name": "shared-qc",
            "version": "0.1.0",
            "description": "Repo duplicate guidance.",
            "tags": ["repo", "test"],
            "source": "repo",
            "root": str(repo_skills_root.resolve()),
            "path": str(repo_skills_root / "shared-qc" / "SKILL.md"),
        }
    ]

    loaded = await async_client.get("/api/v1/agent/skills/shared-qc")
    assert loaded.status_code == 200
    assert loaded.json()["data"]["source"] == "repo"
    assert loaded.json()["data"]["root"] == str(repo_skills_root.resolve())
    assert loaded.json()["data"]["body"] == "Repo body should be loaded."


@pytest.mark.asyncio
async def test_agent_turn_create_accepts_valid_active_skills(async_client):
    _write_skill(
        "run-failure-triage",
        "Triage failed workflow runs.",
        "Gather run logs before proposing fixes.",
    )
    create_session = await async_client.post("/api/v1/agent/sessions", json={})
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={
            "input_text": "Analyze this failed run.",
            "active_skill_names": ["run-failure-triage", "run-failure-triage"],
        },
    )
    assert create_turn.status_code == 202
    turn = create_turn.json()["data"]
    assert turn["active_skill_names"] == ["run-failure-triage"]
    assert turn["model_profile_snapshot"]["metadata"]["active_skill_names"] == [
        "run-failure-triage"
    ]

    rejected = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={
            "input_text": "Use a missing skill.",
            "active_skill_names": ["missing-skill"],
        },
    )
    assert rejected.status_code == 400


@pytest.mark.asyncio
async def test_agent_turn_create_accepts_repo_scoped_active_skills(
    async_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo_root = tmp_path / "repo"
    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    _write_repo_skill(
        repo_root,
        "repo-run-triage",
        "Triage failed runs from this repository.",
        "Repo-local turn guidance.",
    )
    create_session = await async_client.post("/api/v1/agent/sessions", json={})
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={
            "input_text": "Analyze this failed run.",
            "active_skill_names": ["repo-run-triage"],
        },
    )

    assert create_turn.status_code == 202
    turn = create_turn.json()["data"]
    assert turn["active_skill_names"] == ["repo-run-triage"]


@pytest.mark.asyncio
async def test_agent_core_session_turn_event_and_artifact_contract(async_client, monkeypatch):
    stream_log_records: list[tuple[str, str, dict]] = []

    class SpyLogger:
        def info(self, event: str, **fields):
            stream_log_records.append(("info", event, fields))

        def debug(self, event: str, **fields):
            stream_log_records.append(("debug", event, fields))

    monkeypatch.setattr(agent_api_module, "logger", SpyLogger())

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

    _install_fake_completion(monkeypatch, fake_completion)

    model = await _create_llm_model(async_client)
    project_id = await _create_project(async_client)

    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "WGS triage",
            "permission_mode": "guarded_auto",
            "automation_mode": "assisted",
            "model_selection": {"model_id": model["id"]},
            "metadata": {"batch": "b001"},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]
    assert session["title"] == "WGS triage"
    assert session["metadata"] == {
        "batch": "b001",
        "model_selection": {"model_id": model["id"]},
    }
    assert session["model_selection"] == {"model_id": model["id"]}
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
    assert turn["token_usage"] == {
        "prompt_tokens": 6,
        "completion_tokens": 10,
        "total_tokens": 16,
    }
    assert turn["model_selection"] == {"model_id": model["id"]}
    assert turn["model_profile_snapshot"]["resolved_model_selection"] == {
        "provider": "openai_compatible",
        "model": "agent-test-model",
    }
    assert turn["model_profile_snapshot"]["resolved_model_id"] == model["id"]
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
    info_log_names = [
        event_name
        for level, event_name, _fields in stream_log_records
        if level == "info"
    ]
    delivered_logs = [
        fields
        for level, event_name, fields in stream_log_records
        if level == "debug" and event_name == "agent_core.stream.event"
    ]
    assert "agent_core.stream.event" not in info_log_names
    assert "agent_core.stream.batch" in info_log_names
    assert "agent_core.stream.ready" in info_log_names
    assert {
        "session_id": session["id"],
        "turn_id": turn["id"],
        "seq": 1,
        "event_type": "turn.created",
        "follow": False,
    } in delivered_logs
    assert all("payload" not in fields for fields in delivered_logs)

    artifacts = await async_client.get(
        f"/api/v1/agent/sessions/{session['id']}/artifacts"
    )
    assert artifacts.status_code == 200
    assert artifacts.json()["data"] == []


@pytest.mark.asyncio
async def test_agent_session_state_can_limit_large_event_payload(async_client, db_session):
    project_id = await _create_project(async_client)
    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "Large tool trace",
            "permission_mode": "guarded_auto",
            "automation_mode": "assisted",
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    turn = await AgentCoreService(db_session).create_turn_record(
        session_id=session["id"],
        workspace_id=session["workspace_id"],
        user_id=session["user_id"],
        input_text="inspect a long run",
    )

    for seq in range(100, 107):
        db_session.add(
            AgentEvent(
                session_id=session["id"],
                turn_id=str(turn.id),
                seq=seq,
                type="assistant.tool_call.completed",
                payload={"index": seq},
                visibility="user",
                schema_version=1,
            )
        )
    await db_session.commit()

    state = await async_client.get(
        f"/api/v1/agent/sessions/{session['id']}/state?event_limit=3"
    )
    assert state.status_code == 200
    payload = state.json()["data"]
    assert [event["seq"] for event in payload["events"]] == [104, 105, 106]
    assert [item["id"] for item in payload["turns"]] == [str(turn.id)]

    cancel = await async_client.post(f"/api/v1/agent/turns/{turn.id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["data"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_agent_session_state_includes_cumulative_token_usage_summary(
    async_client,
    db_session,
):
    project_id = await _create_project(async_client)
    model = await _create_llm_model(async_client)
    model_row = await db_session.get(LlmModel, model["id"])
    assert model_row is not None
    model_row.context_length = 128000
    model_row.max_output_tokens = 8192
    await db_session.commit()

    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "Usage ledger",
            "model_selection": {"model_id": model["id"]},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    service = AgentCoreService(db_session)
    first_turn = await service.create_turn_record(
        session_id=session["id"],
        workspace_id=session["workspace_id"],
        user_id=session["user_id"],
        input_text="first request",
    )
    second_turn = await service.create_turn_record(
        session_id=session["id"],
        workspace_id=session["workspace_id"],
        user_id=session["user_id"],
        input_text="second request",
    )
    empty_turn = await service.create_turn_record(
        session_id=session["id"],
        workspace_id=session["workspace_id"],
        user_id=session["user_id"],
        input_text="provider omitted usage",
    )
    first_turn_row = await db_session.get(AgentTurn, str(first_turn.id))
    second_turn_row = await db_session.get(AgentTurn, str(second_turn.id))
    empty_turn_row = await db_session.get(AgentTurn, str(empty_turn.id))
    assert first_turn_row is not None
    assert second_turn_row is not None
    assert empty_turn_row is not None
    first_turn_row.token_usage = {
        "prompt_tokens": 1200,
        "completion_tokens": 300,
        "total_tokens": 1500,
        "prompt_tokens_details": {"cached_tokens": 125},
    }
    second_turn_row.token_usage = {
        "input_tokens": 800,
        "output_tokens": 200,
        "cached_input_tokens": 25,
        "reasoning_tokens": 45,
    }
    second_turn_row.model_profile_snapshot = {
        **(second_turn_row.model_profile_snapshot or {}),
        "resolved_model_id": model["id"],
    }
    empty_turn_row.token_usage = None
    await db_session.commit()

    state = await async_client.get(f"/api/v1/agent/sessions/{session['id']}/state")

    assert state.status_code == 200
    summary = state.json()["data"]["session"]["token_usage_summary"]
    assert summary == {
        "has_token_usage": True,
        "input_tokens": 2000,
        "output_tokens": 500,
        "total_tokens": 2500,
        "cached_input_tokens": 150,
        "reasoning_tokens": 45,
        "context_window": 128000,
        "max_output_tokens": 8192,
        "turns_with_usage": 2,
        "raw_totals": {
            "cached_input_tokens": 25,
            "completion_tokens": 300,
            "input_tokens": 800,
            "output_tokens": 200,
            "prompt_tokens": 1200,
            "reasoning_tokens": 45,
            "total_tokens": 1500,
        },
    }


@pytest.mark.asyncio
async def test_agent_core_accepts_catalog_model_selection(async_client, monkeypatch):
    async def fake_completion(*args, **kwargs):
        class FakeMessage:
            content = "Catalog model reply."

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    _install_fake_completion(monkeypatch, fake_completion)

    project_id = await _create_project(async_client)
    model = await _create_llm_model(async_client)
    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "Catalog-routed session",
            "model_selection": {"model_id": model["id"]},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]
    assert session["model_selection"]["model_id"] == model["id"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={
            "input_text": "Use the catalog model.",
            "model_selection": {"model_id": model["id"]},
        },
    )
    assert create_turn.status_code == 202
    turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])

    assert turn["status"] == "completed"
    assert turn["final_text"] == "Catalog model reply."
    assert turn["model_selection"]["model_id"] == model["id"]
    assert turn["model_profile_snapshot"]["requested_model_selection"] == {
        "model_id": model["id"],
    }
    assert turn["model_profile_snapshot"]["resolved_model_id"] == model["id"]
    assert turn["model_profile_snapshot"]["resolved_model_selection"] == {
        "provider": "openai_compatible",
        "model": "agent-test-model",
    }


@pytest.mark.asyncio
async def test_agent_core_metadata_patch_preserves_model_selection(async_client):
    project_id = await _create_project(async_client)
    model = await _create_llm_model(async_client)
    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "Remote-routed session",
            "model_selection": {"model_id": model["id"]},
            "metadata": {"batch": "b001"},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    update_session = await async_client.patch(
        f"/api/v1/agent/sessions/{session['id']}",
        json={"metadata": {"batch": "b001", "remote_connection_id": "connection-1"}},
    )

    assert update_session.status_code == 200
    updated = update_session.json()["data"]
    assert updated["metadata"] == {
        "batch": "b001",
        "remote_connection_id": "connection-1",
        "model_selection": {"model_id": model["id"]},
    }
    assert updated["model_selection"] == {"model_id": model["id"]}


@pytest.mark.asyncio
async def test_agent_core_session_execution_target_contract(async_client):
    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "title": "Remote target",
            "metadata": {"batch": "b001"},
            "execution_target": {
                "type": "remote_ssh",
                "connection_id": "connection-1",
            },
        },
    )

    assert create_session.status_code == 201
    session = create_session.json()["data"]
    assert session["execution_target"] == {
        "type": "remote_ssh",
        "connection_id": "connection-1",
    }
    assert session["metadata"] == {
        "batch": "b001",
        "execution_target": {
            "type": "remote_ssh",
            "connection_id": "connection-1",
        },
    }

    fetched = await async_client.get(f"/api/v1/agent/sessions/{session['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["execution_target"] == {
        "type": "remote_ssh",
        "connection_id": "connection-1",
    }

    metadata_only_update = await async_client.patch(
        f"/api/v1/agent/sessions/{session['id']}",
        json={"metadata": {"batch": "b002"}},
    )
    assert metadata_only_update.status_code == 200
    assert metadata_only_update.json()["data"]["execution_target"] == {
        "type": "remote_ssh",
        "connection_id": "connection-1",
    }
    assert metadata_only_update.json()["data"]["metadata"] == {
        "batch": "b002",
        "execution_target": {
            "type": "remote_ssh",
            "connection_id": "connection-1",
        },
    }

    updated = await async_client.patch(
        f"/api/v1/agent/sessions/{session['id']}",
        json={"execution_target": {"type": "local"}},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["execution_target"] == {"type": "local"}
    assert updated.json()["data"]["metadata"]["execution_target"] == {"type": "local"}

    legacy = await async_client.post(
        "/api/v1/agent/sessions",
        json={"metadata": {"remote_connection_id": "connection-2"}},
    )
    assert legacy.status_code == 201
    assert legacy.json()["data"]["execution_target"] == {
        "type": "remote_ssh",
        "connection_id": "connection-2",
    }
    assert legacy.json()["data"]["metadata"] == {"remote_connection_id": "connection-2"}

    alias_session_response = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "execution_target": {
                "kind": "remote_ssh",
                "remote_connection_id": "connection-3",
            },
        },
    )
    assert alias_session_response.status_code == 201
    alias_session = alias_session_response.json()["data"]
    assert alias_session["execution_target"] == {
        "type": "remote_ssh",
        "connection_id": "connection-3",
    }

    turn_response = await async_client.post(
        f"/api/v1/agent/sessions/{alias_session['id']}/turns",
        json={
            "input_text": "Run this turn locally.",
            "execution_target": {"kind": "local"},
        },
    )
    assert turn_response.status_code == 202
    assert turn_response.json()["data"]["model_profile_snapshot"]["metadata"][
        "execution_target"
    ] == {"type": "local"}

    refetched_alias_session = await async_client.get(
        f"/api/v1/agent/sessions/{alias_session['id']}"
    )
    assert refetched_alias_session.status_code == 200
    assert refetched_alias_session.json()["data"]["execution_target"] == {
        "type": "local"
    }
    assert refetched_alias_session.json()["data"]["metadata"]["execution_target"] == {
        "type": "local"
    }


@pytest.mark.asyncio
async def test_agent_core_streams_text_and_reasoning_events(async_client, monkeypatch):
    completion_kwargs: list[dict] = []

    async def fake_completion(*args, **kwargs):
        completion_kwargs.append(kwargs)

        async def stream():
            yield {
                "choices": [
                    {
                        "delta": {
                            "reasoning_content": "Inspecting the workspace context.",
                        }
                    }
                ]
            }
            yield {"choices": [{"delta": {"content": "Streaming reply "}}]}
            yield {
                "choices": [{"delta": {"content": "completed."}}],
                "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 4,
                    "total_tokens": 11,
                },
            }

        return stream()

    _install_fake_completion(monkeypatch, fake_completion)

    project_id = await _create_project(async_client)
    provider_response = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Streaming Test Gateway",
            "kind": "openai_compatible",
            "base_url": "https://models.internal.example/v1",
        },
    )
    assert provider_response.status_code == 201
    provider = provider_response.json()["data"]
    model_response = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": provider["id"],
            "model_id": "streaming-reasoner",
            "display_name": "Streaming Reasoner",
            "supports_streaming": True,
            "supports_reasoning": True,
            "supports_tools": False,
        },
    )
    assert model_response.status_code == 201
    model = model_response.json()["data"]

    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "Streaming session",
            "model_selection": {"model_id": model["id"]},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={"input_text": "Explain what you are doing."},
    )
    assert create_turn.status_code == 202
    turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])

    assert turn["status"] == "completed"
    assert turn["final_text"] == "Streaming reply completed."
    assert completion_kwargs[0]["stream"] is True

    events_response = await async_client.get(f"/api/v1/agent/turns/{turn['id']}/events")
    assert events_response.status_code == 200
    events = events_response.json()["data"]
    assert _event_types(events) == [
        "turn.created",
        "turn.started",
        "model.selected",
        "assistant.thinking.delta",
        "assistant.thinking.completed",
        "assistant.text.delta",
        "assistant.text.delta",
        "assistant.text.completed",
        "turn.completed",
    ]
    assert events[3]["payload"]["delta"] == "Inspecting the workspace context."
    assert events[4]["payload"]["content"] == "Inspecting the workspace context."
    assert events[5]["payload"]["delta"] == "Streaming reply "
    assert events[7]["payload"]["text"] == "Streaming reply completed."


@pytest.mark.asyncio
async def test_agent_core_emits_tool_call_lifecycle_events(async_client, monkeypatch):
    completion_calls: list[dict] = []

    async def fake_completion(*args, **kwargs):
        completion_calls.append(kwargs)

        async def tool_call_stream():
            yield {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_projects",
                                    "function": {
                                        "name": "projects__list",
                                        "arguments": '{"limit":',
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
            yield {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {
                                        "arguments": " 1}",
                                    },
                                }
                            ]
                        }
                    }
                ]
            }

        async def final_text_stream():
            yield {"choices": [{"delta": {"content": "Projects checked."}}]}

        if len(completion_calls) == 1:
            return tool_call_stream()
        return final_text_stream()

    _install_fake_completion(monkeypatch, fake_completion)

    project_id = await _create_project(async_client)
    model = await _create_llm_model(async_client)
    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "Tool stream session",
            "model_selection": {"model_id": model["id"]},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={"input_text": "List my projects."},
    )
    assert create_turn.status_code == 202
    turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])

    assert turn["status"] == "completed"
    assert turn["final_text"] == "Projects checked."
    assert completion_calls[0]["stream"] is True

    events_response = await async_client.get(f"/api/v1/agent/turns/{turn['id']}/events")
    assert events_response.status_code == 200
    events = events_response.json()["data"]
    event_types = _event_types(events)
    assert "assistant.tool_call.started" in event_types
    assert "assistant.tool_call.delta" in event_types
    assert "assistant.tool_call.completed" in event_types
    assert "action.requested" in event_types
    assert "action.started" in event_types
    assert "action.completed" in event_types
    tool_completed = next(
        item for item in events if item["type"] == "assistant.tool_call.completed"
    )
    assert tool_completed["payload"]["call_id"] == "call_projects"
    assert tool_completed["payload"]["name"] == "projects__list"
    assert tool_completed["payload"]["arguments"] == {"limit": 1}


@pytest.mark.asyncio
async def test_agent_core_ollama_catalog_selection_uses_root_api_base(
    async_client,
    monkeypatch,
):
    completion_kwargs: dict = {}

    async def fake_completion(*args, **kwargs):
        completion_kwargs.update(kwargs)

        class FakeMessage:
            content = "Ollama model reply."

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    _install_fake_completion(monkeypatch, fake_completion)

    project_id = await _create_project(async_client)
    provider_response = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Local Ollama",
            "kind": "ollama",
            "base_url": "http://localhost:11434",
        },
    )
    assert provider_response.status_code == 201
    provider = provider_response.json()["data"]
    credential_response = await async_client.put(
        f"/api/v1/llm/providers/{provider['id']}/credential",
        json={"source": "none"},
    )
    assert credential_response.status_code == 200
    model_response = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": provider["id"],
            "model_id": "deepseek-r1:latest",
            "display_name": "DeepSeek R1",
            "supports_streaming": True,
            "supports_reasoning": True,
        },
    )
    assert model_response.status_code == 201
    model = model_response.json()["data"]

    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "Ollama-routed session",
            "model_selection": {"model_id": model["id"]},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={"input_text": "Use local DeepSeek."},
    )
    assert create_turn.status_code == 202
    turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])

    assert turn["status"] == "completed"
    assert completion_kwargs["model"] == "ollama_chat/deepseek-r1:latest"
    assert completion_kwargs["api_base"] == "http://127.0.0.1:11434"
    assert "api_key" not in completion_kwargs
    assert "tools" not in completion_kwargs


@pytest.mark.asyncio
async def test_agent_core_anthropic_catalog_selection_preserves_native_api_base(
    async_client,
    monkeypatch,
):
    completion_kwargs: dict = {}

    async def fake_completion(*args, **kwargs):
        completion_kwargs.update(kwargs)

        class FakeMessage:
            content = "Anthropic model reply."

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    _install_fake_completion(monkeypatch, fake_completion)

    project_id = await _create_project(async_client)
    provider_response = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Anthropic",
            "kind": "anthropic",
            "base_url": "https://api.anthropic.com",
            "metadata": {"providerTemplate": "anthropic"},
        },
    )
    assert provider_response.status_code == 201
    provider = provider_response.json()["data"]
    credential_response = await async_client.put(
        f"/api/v1/llm/providers/{provider['id']}/credential",
        json={"source": "stored", "secret": "sk-ant-test"},
    )
    assert credential_response.status_code == 200
    model_response = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": provider["id"],
            "model_id": "claude-sonnet-4-6",
            "display_name": "Claude Sonnet 4.6",
            "supports_streaming": True,
        },
    )
    assert model_response.status_code == 201
    model = model_response.json()["data"]

    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "Anthropic-routed session",
            "model_selection": {"model_id": model["id"]},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={"input_text": "Use Claude."},
    )
    assert create_turn.status_code == 202
    turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])

    assert turn["status"] == "completed"
    assert completion_kwargs["model"] == "anthropic/claude-sonnet-4-6"
    # Host root must be preserved — no /v1 suffix appended for Anthropic.
    assert completion_kwargs["api_base"] == "https://api.anthropic.com"
    assert completion_kwargs["api_key"] == "sk-ant-test"


@pytest.mark.asyncio
async def test_agent_core_profile_strategy_can_disable_streaming_thinking_and_tools(
    async_client,
    monkeypatch,
):
    completion_kwargs: dict = {}

    async def fake_completion(*args, **kwargs):
        completion_kwargs.update(kwargs)

        class FakeMessage:
            content = "Profile strategy reply."

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    _install_fake_completion(monkeypatch, fake_completion)

    project_id = await _create_project(async_client)
    provider_response = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Profile Test Gateway",
            "kind": "openai_compatible",
            "base_url": "https://models.internal.example/v1",
        },
    )
    assert provider_response.status_code == 201
    provider = provider_response.json()["data"]
    model_response = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": provider["id"],
            "model_id": "profile-strategy-model",
            "display_name": "Profile Strategy Model",
            "supports_streaming": True,
            "supports_reasoning": True,
            "supports_tools": True,
        },
    )
    assert model_response.status_code == 201
    model = model_response.json()["data"]
    profile = await _create_llm_profile(
        async_client,
        name="No-stream strategy",
        primary_model_id=model["id"],
        prefer_streaming=False,
        allow_thinking=False,
        allow_tools=False,
    )

    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "Profile strategy session",
            "model_selection": {"profile_id": profile["id"]},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={"input_text": "Apply the profile strategy."},
    )
    assert create_turn.status_code == 202
    turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])

    assert turn["status"] == "completed"
    assert turn["final_text"] == "Profile strategy reply."
    assert "stream" not in completion_kwargs or completion_kwargs["stream"] is False
    assert "tools" not in completion_kwargs
    assert turn["model_profile_snapshot"]["resolved_profile_id"] == profile["id"]
    strategy = turn["model_profile_snapshot"]["resolved_runtime_strategy"]
    assert strategy["allow_thinking"] is False
    assert strategy["allow_tools"] is False
    assert strategy["use_streaming"] is False

    events_response = await async_client.get(f"/api/v1/agent/turns/{turn['id']}/events")
    assert events_response.status_code == 200
    event_types = _event_types(events_response.json()["data"])
    assert "assistant.text.delta" not in event_types
    assert "assistant.thinking.delta" not in event_types


@pytest.mark.asyncio
async def test_agent_core_tool_capable_catalog_model_receives_tools(
    async_client,
    monkeypatch,
):
    completion_kwargs: dict = {}

    async def fake_completion(*args, **kwargs):
        completion_kwargs.update(kwargs)

        class FakeMessage:
            content = "Tool-capable model reply."

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    _install_fake_completion(monkeypatch, fake_completion)

    project_id = await _create_project(async_client)
    model = await _create_llm_model(async_client)
    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "Tool-capable catalog session",
            "model_selection": {"model_id": model["id"]},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={"input_text": "Use tools if needed."},
    )
    assert create_turn.status_code == 202
    turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])

    assert turn["status"] == "completed"
    assert completion_kwargs["model"] == "openai/agent-test-model"
    assert completion_kwargs["tools"]


@pytest.mark.asyncio
async def test_catalog_default_prefers_env_managed_vllm_over_other_env_provider(
    db_session,
):
    # Within one scope the env-managed vLLM endpoint a deployment configures on
    # purpose must win over an incidentally-available env provider, even when the
    # other provider is more recently updated (so it sorts first by recency).
    base = datetime(2026, 6, 15, tzinfo=timezone.utc)
    vllm_provider = LlmProvider(
        name="Env vLLM",
        kind="vllm",
        base_url="http://vllm.internal.test:8000/v1",
        scope="global",
        workspace_id=None,
        user_id=None,
        enabled=True,
        provider_metadata={"envManaged": True, "providerTemplate": "vllm"},
        updated_at=base,
    )
    other_provider = LlmProvider(
        name="Env OpenRouter",
        kind="openrouter",
        base_url="https://openrouter.ai/api/v1",
        scope="global",
        workspace_id=None,
        user_id=None,
        enabled=True,
        provider_metadata={"envManaged": True, "providerTemplate": "openrouter"},
        updated_at=base + timedelta(hours=1),
    )
    db_session.add_all([vllm_provider, other_provider])
    await db_session.commit()
    await db_session.refresh(vllm_provider)
    await db_session.refresh(other_provider)
    db_session.add_all(
        [
            LlmProviderCredential(
                provider_id=str(vllm_provider.id),
                source="stored",
                encrypted_secret=encrypt_secret("vllm-key"),
                fingerprint=generate_credential_fingerprint(),
                masked_hint="vllm",
            ),
            LlmProviderCredential(
                provider_id=str(other_provider.id),
                source="stored",
                encrypted_secret=encrypt_secret("or-key"),
                fingerprint=generate_credential_fingerprint(),
                masked_hint="or",
            ),
            LlmModel(
                provider_id=str(vllm_provider.id),
                model_id="deepseek_v4",
                display_name="DeepSeek V4",
                supports_tools=True,
                supports_streaming=True,
            ),
            LlmModel(
                provider_id=str(other_provider.id),
                model_id="openrouter/auto",
                display_name="OpenRouter Auto",
                supports_tools=True,
                supports_streaming=True,
            ),
        ]
    )
    await db_session.commit()

    runtime = AgentCoreRuntime(db_session)
    resolved = await runtime._catalog_default_selection(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    assert resolved is not None
    assert resolved["provider"] == "vllm"
    assert resolved["model"] == "deepseek_v4"
    assert resolved["source"] == "catalog_default"


@pytest.mark.asyncio
async def test_agent_core_prefers_user_catalog_model_over_environment_global_default(
    async_client,
    db_session,
    monkeypatch,
):
    completion_kwargs: dict = {}

    async def fake_completion(*args, **kwargs):
        completion_kwargs.update(kwargs)

        class FakeMessage:
            content = "UI-configured model reply."

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    _install_fake_completion(monkeypatch, fake_completion)

    global_provider = LlmProvider(
        name="Env vLLM",
        kind="vllm",
        base_url="http://env.example.test/v1",
        scope="global",
        workspace_id=None,
        user_id=None,
        enabled=True,
        provider_metadata={"envManaged": True, "providerTemplate": "vllm"},
    )
    user_provider = LlmProvider(
        name="UI vLLM",
        kind="vllm",
        base_url="http://ui.example.test/v1",
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "vllm"},
    )
    db_session.add_all([global_provider, user_provider])
    await db_session.commit()
    await db_session.refresh(global_provider)
    await db_session.refresh(user_provider)
    db_session.add_all(
        [
            LlmProviderCredential(
                provider_id=str(global_provider.id),
                source="stored",
                encrypted_secret=encrypt_secret("env-key"),
                fingerprint=generate_credential_fingerprint(),
                masked_hint="env-key",
            ),
            LlmProviderCredential(
                provider_id=str(user_provider.id),
                source="stored",
                encrypted_secret=encrypt_secret("ui-key"),
                fingerprint=generate_credential_fingerprint(),
                masked_hint="ui-key",
            ),
            LlmModel(
                provider_id=str(global_provider.id),
                model_id="env-model",
                display_name="Env Model",
                supports_tools=True,
                supports_streaming=True,
            ),
            LlmModel(
                provider_id=str(user_provider.id),
                model_id="ui-model",
                display_name="UI Model",
                supports_tools=True,
                supports_streaming=True,
            ),
        ]
    )
    await db_session.commit()

    project_id = await _create_project(async_client)
    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "UI model precedence",
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={"input_text": "Use the UI configured model."},
    )
    assert create_turn.status_code == 202
    turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])

    assert turn["status"] == "completed"
    assert completion_kwargs["model"] == "openai/ui-model"
    assert completion_kwargs["api_base"] == "http://ui.example.test/v1"
    assert completion_kwargs["api_key"] == "ui-key"
    assert turn["model_profile_snapshot"]["resolved_model_source"] == "catalog_default"


@pytest.mark.asyncio
async def test_agent_core_rejects_invisible_catalog_model_selection(
    async_client,
    app,
    db_session,
    monkeypatch,
):
    completion = False

    async def fake_completion(*args, **kwargs):
        nonlocal completion
        completion = True
        raise AssertionError("invisible catalog model should not be called")

    _install_fake_completion(monkeypatch, fake_completion)
    invisible_model = await _create_scoped_llm_model(
        db_session,
        provider_user_id="other-user",
        model_name="other-user-model",
    )

    app.dependency_overrides[get_current_user] = lambda: _auth_user(user_id="user-1")
    try:
        project_id = await _create_project(async_client)
        create_session = await async_client.post(
            "/api/v1/agent/sessions",
            json={
                "project_id": project_id,
                "title": "Cross-scope model attempt",
                "model_selection": {"model_id": str(invisible_model.id)},
            },
        )
        assert create_session.status_code == 201
        session = create_session.json()["data"]

        create_turn = await async_client.post(
            f"/api/v1/agent/sessions/{session['id']}/turns",
            json={"input_text": "Use the invisible catalog model."},
        )
        assert create_turn.status_code == 202
        turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert completion is False
    assert turn["status"] == "failed"
    assert turn["error_code"] == "model_selection_missing"


@pytest.mark.asyncio
async def test_agent_fs_tree_and_file_are_confined_to_allowed_roots(async_client):
    tree = await async_client.get("/api/v1/agent/fs/tree")
    assert tree.status_code == 200
    entries = tree.json()["data"]["entries"]
    assert isinstance(entries, list)
    files = [e for e in entries if e["type"] == "file"]
    # Fetch one in-root file and confirm its contents come back.
    if files:
        target = files[0]["path"]
        file_resp = await async_client.get(f"/api/v1/agent/fs/file?path={target}")
        assert file_resp.status_code == 200
        assert "content" in file_resp.json()["data"]

    # A path outside the allowed roots is rejected, not served.
    blocked = await async_client.get("/api/v1/agent/fs/tree?path=/etc")
    assert blocked.status_code == 403
    blocked_file = await async_client.get("/api/v1/agent/fs/file?path=/etc/passwd")
    assert blocked_file.status_code == 403


@pytest.mark.asyncio
async def test_agent_fs_tree_defaults_to_project_home(async_client):
    project_id = await _create_project(async_client)
    project_root = project_home(project_id)
    marker = project_root / "project-note.txt"
    marker.write_text("project scoped", encoding="utf-8")

    response = await async_client.get(
        f"/api/v1/agent/fs/tree?project_id={project_id}"
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["path"] == str(project_root)
    assert "project-note.txt" in {entry["name"] for entry in data["entries"]}


@pytest.mark.asyncio
async def test_agent_fs_file_rejects_sensitive_files(async_client, tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "data"
    repo_root.mkdir()
    data_root.mkdir()
    public_file = repo_root / "notes.txt"
    public_file.write_text("safe note", encoding="utf-8")
    secret_file = repo_root / ".env"
    secret_file.write_text("OPENAI_API_KEY=secret", encoding="utf-8")
    nested_secret = data_root / "auth" / "better-auth.db"
    nested_secret.parent.mkdir()
    nested_secret.write_text("auth db bytes", encoding="utf-8")

    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    monkeypatch.setattr(settings, "bioinfoflow_home", str(data_root))

    public_resp = await async_client.get(
        f"/api/v1/agent/fs/file?path={public_file}"
    )
    assert public_resp.status_code == 200

    secret_resp = await async_client.get(
        f"/api/v1/agent/fs/file?path={secret_file}"
    )
    assert secret_resp.status_code == 403
    data_secret_resp = await async_client.get(
        f"/api/v1/agent/fs/file?path={nested_secret}"
    )
    assert data_secret_resp.status_code == 403


@pytest.mark.asyncio
async def test_agent_fs_file_supports_binary_preview_download(async_client, tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "data"
    repo_root.mkdir()
    data_root.mkdir()
    pdf_file = repo_root / "summary.pdf"
    pdf_file.write_bytes(b"%PDF-1.7\nbinary-\xff\n")
    xlsm_file = repo_root / "metrics.xlsm"
    xlsm_file.write_bytes(b"PK\x03\x04binary-\xff\n")
    ods_file = repo_root / "metrics.ods"
    ods_file.write_bytes(b"PK\x03\x04binary-\xff\n")
    png_file = repo_root / "plot.png"
    png_file.write_bytes(b"\x89PNG\r\n\x1a\nbinary-\xff\n")
    svg_file = repo_root / "plot.svg"
    svg_file.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8")
    html_file = repo_root / 'report "qc"; v1.html'
    html_file.write_text("<h1>QC</h1>", encoding="utf-8")

    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    monkeypatch.setattr(settings, "bioinfoflow_home", str(data_root))

    metadata_resp = await async_client.get(
        "/api/v1/agent/fs/file",
        params={"path": str(pdf_file)},
    )
    assert metadata_resp.status_code == 200
    data = metadata_resp.json()["data"]
    assert data["binary"] is True
    assert data["content"] == ""
    assert data["mime_type"] == "application/pdf"

    for workbook_file in (xlsm_file, ods_file):
        workbook_metadata_resp = await async_client.get(
            "/api/v1/agent/fs/file",
            params={"path": str(workbook_file)},
        )
        assert workbook_metadata_resp.status_code == 200
        workbook_data = workbook_metadata_resp.json()["data"]
        assert workbook_data["binary"] is True
        assert workbook_data["content"] == ""
        assert workbook_data["language"] == "spreadsheet"

    for image_file, expected_mime_type in (
        (png_file, "image/png"),
        (svg_file, "image/svg+xml"),
    ):
        image_metadata_resp = await async_client.get(
            "/api/v1/agent/fs/file",
            params={"path": str(image_file)},
        )
        assert image_metadata_resp.status_code == 200
        image_data = image_metadata_resp.json()["data"]
        assert image_data["binary"] is True
        assert image_data["content"] == ""
        assert image_data["mime_type"] == expected_mime_type

    download_resp = await async_client.get(
        "/api/v1/agent/fs/download",
        params={"path": str(pdf_file), "inline": "true"},
    )
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"].startswith("application/pdf")
    assert "inline" in download_resp.headers["content-disposition"]
    assert download_resp.content.startswith(b"%PDF-1.7")

    html_download_resp = await async_client.get(
        "/api/v1/agent/fs/download",
        params={"path": str(html_file), "inline": "true"},
    )
    assert html_download_resp.status_code == 200
    assert html_download_resp.headers["content-type"].startswith("text/html")
    content_disposition = html_download_resp.headers["content-disposition"]
    assert content_disposition.startswith("inline")
    assert 'filename="report _qc__ v1.html"' in content_disposition
    assert "filename*=UTF-8''report%20%22qc%22%3B%20v1.html" in content_disposition
    assert html_download_resp.headers["content-security-policy"].startswith("sandbox")
    assert "default-src 'none'" in html_download_resp.headers["content-security-policy"]
    assert "form-action 'none'" in html_download_resp.headers["content-security-policy"]

    svg_download_resp = await async_client.get(
        "/api/v1/agent/fs/download",
        params={"path": str(svg_file), "inline": "true"},
    )
    assert svg_download_resp.status_code == 200
    assert svg_download_resp.headers["content-type"].startswith("image/svg+xml")
    assert svg_download_resp.headers["content-security-policy"].startswith("sandbox")


@pytest.mark.asyncio
async def test_agent_toolsets_include_plan_mode(async_client):
    response = await async_client.get("/api/v1/agent/toolsets")

    assert response.status_code == 200
    toolsets = {item["name"]: item["tools"] for item in response.json()["data"]["toolsets"]}
    assert "plan" in toolsets
    assert "exit_plan_mode" in toolsets["plan"]
    assert "bash" not in toolsets["plan"]


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
