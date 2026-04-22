from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import asyncio
import inspect
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.enums import ApprovalStatus
from app.models.approval import AgentApproval, ApprovalType
from app.models.conversation import Conversation
from app.models.message import Message, MessageRole, MessageType
from app.models.project import Project
from app.path_layout import ensure_project_layout
from app.services.agent.agent_service import AgentService
from app.services.agent.conversation_manager import conversation_manager


async def _create_project(
    db_session,
    name: str,
    workspace_path: str | None = None,
    *,
    storage_mode: str = "external",
    external_root_path: str | None = None,
) -> Project:
    project = Project(
        name=name,
        storage_mode=storage_mode,
        external_root_path=external_root_path or workspace_path,
        user_id="dev",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    ensure_project_layout(project)
    return project


async def _create_conversation(
    db_session,
    *,
    project_id: str,
    title: str = "Genome planning",
    pinned: bool = False,
) -> Conversation:
    conversation = Conversation(
        project_id=project_id,
        title=title,
        pinned=pinned,
        user_id="dev",
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)
    return conversation


async def _create_message(
    db_session,
    *,
    conversation_id: str,
    project_id: str,
    role: str,
    content: str,
    message_type: str = MessageType.TEXT.value,
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        project_id=project_id,
        role=role,
        type=message_type,
        content=content,
        message_metadata=None,
    )
    db_session.add(message)
    await db_session.commit()
    await db_session.refresh(message)
    return message


async def _create_approval(
    db_session,
    *,
    conversation_id: str,
    step_id: str,
    status: str = ApprovalStatus.PENDING,
) -> AgentApproval:
    approval = AgentApproval(
        conversation_id=conversation_id,
        step_id=step_id,
        approval_type=ApprovalType.RUN,
        payload={"command": "nextflow run main.nf"},
        status=status,
    )
    db_session.add(approval)
    await db_session.commit()
    await db_session.refresh(approval)
    return approval


async def _wait_for(predicate, *, timeout: float = 2.0, interval: float = 0.02):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        result = predicate()
        if inspect.isawaitable(result):
            result = await result
        if result:
            return
        await asyncio.sleep(interval)
    raise AssertionError("Condition was not met before timeout")


@pytest.mark.asyncio
async def test_agent_conversation_create_list_update(
    async_client, db_session, tmp_path
):
    project = await _create_project(
        db_session,
        name="Agent API Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "agent-api-workspace"),
    )

    create_resp = await async_client.post(
        "/api/v1/agent/conversations",
        json={"project_id": str(project.id), "title": "Initial planning"},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()["data"]
    conversation_id = created["id"]
    assert created["project_id"] == str(project.id)
    assert created["title"] == "Initial planning"
    assert created["pinned"] is False

    list_resp = await async_client.get(
        "/api/v1/agent/conversations",
        params={"project_id": str(project.id), "limit": 20},
    )
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert listed["success"] is True
    assert listed["meta"]["pagination"]["total_count"] >= 1
    assert any(item["id"] == conversation_id for item in listed["data"])

    update_resp = await async_client.patch(
        f"/api/v1/agent/conversations/{conversation_id}",
        json={"title": "Updated planning", "pinned": True},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()["data"]
    assert updated["title"] == "Updated planning"
    assert updated["pinned"] is True


@pytest.mark.asyncio
async def test_agent_conversation_create_without_project_uses_default_inbox(
    async_client,
):
    default_resp = await async_client.get("/api/v1/projects/default")
    assert default_resp.status_code == 200
    default_project = default_resp.json()["data"]

    create_resp = await async_client.post(
        "/api/v1/agent/conversations",
        json={"title": "Inbox planning"},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()["data"]
    assert created["project_id"] == default_project["id"]
    assert created["title"] == "Inbox planning"


@pytest.mark.asyncio
async def test_agent_conversation_message_history(async_client, db_session, tmp_path):
    project = await _create_project(
        db_session,
        name="Agent History Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "agent-history-workspace"),
    )
    create_resp = await async_client.post(
        "/api/v1/agent/conversations",
        json={"project_id": str(project.id), "title": "History test"},
    )
    assert create_resp.status_code == 201
    conversation_id = create_resp.json()["data"]["id"]

    await _create_message(
        db_session,
        conversation_id=conversation_id,
        project_id=str(project.id),
        role=MessageRole.USER.value,
        content="Inspect the reads folder",
    )
    await _create_message(
        db_session,
        conversation_id=conversation_id,
        project_id=str(project.id),
        role=MessageRole.AGENT.value,
        content="I found paired FASTQ files",
    )

    history_resp = await async_client.get(
        f"/api/v1/agent/conversations/{conversation_id}"
    )
    assert history_resp.status_code == 200
    history = history_resp.json()["data"]
    assert history["conversation_id"] == conversation_id
    assert [message["role"] for message in history["messages"]] == ["user", "agent"]
    assert history["messages"][0]["content"] == "Inspect the reads folder"
    assert history["messages"][1]["content"] == "I found paired FASTQ files"


@pytest.mark.asyncio
async def test_send_message_forwards_execution_policy_to_legacy_service(
    async_client, db_session, tmp_path, monkeypatch
):
    project = await _create_project(
        db_session,
        name="Legacy Message Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "legacy-message-workspace"),
    )

    captured: dict[str, object] = {}

    async def fake_send_message(self, **kwargs):
        captured.update(kwargs)
        return (
            SimpleNamespace(id=uuid4()),
            SimpleNamespace(id=uuid4()),
        )

    monkeypatch.setattr(AgentService, "send_message", fake_send_message)

    response = await async_client.post(
        "/api/v1/agent/message",
        json={
            "project_id": str(project.id),
            "content": "Run this in bypass mode",
            "execution_policy": "bypass",
        },
    )

    assert response.status_code == 202
    assert captured["execution_policy"] == "bypass"


@pytest.mark.asyncio
async def test_agent_message_endpoint_supports_follow_up_turns_with_runtime_v2(
    async_client, db_session, tmp_path, monkeypatch
):
    project = await _create_project(
        db_session,
        name="Agent Multi Turn Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "agent-multi-turn-workspace"),
    )

    async def _fake_run_v2(self, **kwargs):
        await self._persist_and_publish_agent_event(
            conversation_id=kwargs["conversation_id"],
            project_id=kwargs["project_id"],
            assistant_message_id=kwargs["assistant_message_id"],
            event={
                "type": "text",
                "content": "Agent reply",
                "metadata": {"usage": {"input_tokens": 100, "output_tokens": 30}},
            },
        )

    async def _fake_generate_title(self, *args, **kwargs):
        return None

    monkeypatch.setattr(AgentService, "_run_v2", _fake_run_v2)
    monkeypatch.setattr(AgentService, "_generate_title", _fake_generate_title)

    first_resp = await async_client.post(
        "/api/v1/agent/message",
        json={
            "project_id": str(project.id),
            "content": "show me a demo",
        },
    )
    assert first_resp.status_code == 202
    conversation_id = first_resp.json()["data"]["conversation_id"]

    async def _history_has_first_agent_reply() -> bool:
        history_resp = await async_client.get(
            f"/api/v1/agent/conversations/{conversation_id}"
        )
        if history_resp.status_code != 200:
            return False
        history = history_resp.json()["data"]["messages"]
        return Counter(
            message["content"]
            for message in history
            if message["type"] == "text" and message["role"] == "agent"
        ) == Counter(["Agent reply"])

    await _wait_for(_history_has_first_agent_reply)

    second_resp = await async_client.post(
        "/api/v1/agent/message",
        json={
            "project_id": str(project.id),
            "conversation_id": conversation_id,
            "content": "?",
        },
    )
    assert second_resp.status_code == 202

    async def _history_has_two_agent_replies() -> bool:
        history_resp = await async_client.get(
            f"/api/v1/agent/conversations/{conversation_id}"
        )
        if history_resp.status_code != 200:
            return False
        history = history_resp.json()["data"]["messages"]
        text_messages = [message for message in history if message["type"] == "text"]
        return Counter(
            message["content"]
            for message in text_messages
            if message["role"] == "agent"
        ) == Counter(["Agent reply", "Agent reply"])

    await _wait_for(_history_has_two_agent_replies)

    history_resp = await async_client.get(
        f"/api/v1/agent/conversations/{conversation_id}"
    )
    assert history_resp.status_code == 200

    history = history_resp.json()["data"]["messages"]
    text_messages = [message for message in history if message["type"] == "text"]
    assert Counter(
        message["content"] for message in text_messages if message["role"] == "user"
    ) == Counter(["show me a demo", "?"])
    assert Counter(
        message["content"] for message in text_messages if message["role"] == "agent"
    ) == Counter(["Agent reply", "Agent reply"])


@pytest.mark.asyncio
async def test_agent_message_endpoint_runs_in_background_and_creates_assistant_draft(
    async_client, db_session, tmp_path, monkeypatch
):
    project = await _create_project(
        db_session,
        name="Agent Background Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "agent-background-workspace"),
    )

    started = asyncio.Event()
    release = asyncio.Event()

    async def _fake_run_v2(self, **kwargs):
        started.set()
        await release.wait()

    async def _fake_generate_title(self, *args, **kwargs):
        return None

    monkeypatch.setattr(AgentService, "_run_v2", _fake_run_v2)
    monkeypatch.setattr(AgentService, "_generate_title", _fake_generate_title)

    response = await async_client.post(
        "/api/v1/agent/message",
        json={
            "project_id": str(project.id),
            "content": "run a python quick check",
        },
    )

    assert response.status_code == 202
    conversation_id = response.json()["data"]["conversation_id"]

    await asyncio.wait_for(started.wait(), timeout=1)

    status_resp = await async_client.get(
        f"/api/v1/agent/conversations/{conversation_id}/status"
    )
    assert status_resp.status_code == 200
    status_data = status_resp.json()["data"]
    assert status_data["conversation_id"] == conversation_id
    assert status_data["is_running"] is True
    assert status_data["assistant_message_id"]
    assert status_data["last_event_at"] is not None

    history_resp = await async_client.get(
        f"/api/v1/agent/conversations/{conversation_id}"
    )
    assert history_resp.status_code == 200
    history = history_resp.json()["data"]["messages"]
    assert [message["role"] for message in history] == ["user", "agent"]
    assert history[0]["content"] == "run a python quick check"
    assert history[1]["content"] == ""
    assert history[1]["metadata"]["streaming"] is True
    assert history[1]["metadata"]["status"] == "streaming"

    release.set()

    async def _conversation_idle() -> bool:
        idle_resp = await async_client.get(
            f"/api/v1/agent/conversations/{conversation_id}/status"
        )
        return (
            idle_resp.status_code == 200
            and idle_resp.json()["data"]["is_running"] is False
        )

    await _wait_for(_conversation_idle)


@pytest.mark.asyncio
async def test_agent_conversation_cancel_and_delete(async_client, db_session, tmp_path):
    project = await _create_project(
        db_session,
        name="Agent Cancel Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "agent-cancel-workspace"),
    )
    create_resp = await async_client.post(
        "/api/v1/agent/conversations",
        json={"project_id": str(project.id), "title": "Cancel test"},
    )
    assert create_resp.status_code == 201
    conversation_id = create_resp.json()["data"]["id"]

    await conversation_manager.register(conversation_id, str(project.id))
    try:
        status_resp = await async_client.get(
            f"/api/v1/agent/conversations/{conversation_id}/status"
        )
        assert status_resp.status_code == 200
        assert status_resp.json()["data"]["is_running"] is True
        assert status_resp.json()["data"]["assistant_message_id"] is None
        assert status_resp.json()["data"]["last_event_at"] is not None

        cancel_resp = await async_client.post(
            f"/api/v1/agent/conversations/{conversation_id}/cancel"
        )
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["data"] == {
            "conversation_id": conversation_id,
            "cancelled": True,
        }

        status_after_cancel = await async_client.get(
            f"/api/v1/agent/conversations/{conversation_id}/status"
        )
        assert status_after_cancel.status_code == 200
        assert status_after_cancel.json()["data"]["is_running"] is False
    finally:
        await conversation_manager.unregister(conversation_id)

    delete_resp = await async_client.delete(
        f"/api/v1/agent/conversations/{conversation_id}"
    )
    assert delete_resp.status_code == 204

    get_deleted_resp = await async_client.get(
        f"/api/v1/agent/conversations/{conversation_id}"
    )
    assert get_deleted_resp.status_code == 404
    assert get_deleted_resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_agent_approval_endpoints_and_resolution_guards(
    async_client, db_session, tmp_path
):
    project = await _create_project(
        db_session,
        name="Agent Approval Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "agent-approval-workspace"),
    )
    conversation = await _create_conversation(
        db_session,
        project_id=str(project.id),
        title="Approval flow",
    )
    pending = await _create_approval(
        db_session,
        conversation_id=str(conversation.id),
        step_id="step-1",
    )
    await _create_approval(
        db_session,
        conversation_id=str(conversation.id),
        step_id="step-2",
        status=ApprovalStatus.APPROVED,
    )

    get_resp = await async_client.get(f"/api/v1/agent/approvals/{pending.id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["status"] == ApprovalStatus.PENDING

    list_resp = await async_client.get(
        f"/api/v1/agent/conversations/{conversation.id}/approvals"
    )
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload["data"]["conversation_id"] == str(conversation.id)
    assert len(payload["data"]["approvals"]) == 2
    assert payload["meta"]["pagination"]["total_count"] >= 2

    pending_resp = await async_client.get(
        f"/api/v1/agent/conversations/{conversation.id}/approvals/pending"
    )
    assert pending_resp.status_code == 200
    pending_payload = pending_resp.json()["data"]
    assert [approval["id"] for approval in pending_payload["approvals"]] == [
        str(pending.id)
    ]

    resolve_resp = await async_client.post(
        f"/api/v1/agent/approvals/{pending.id}/resolve",
        json={"action": "approve"},
    )
    assert resolve_resp.status_code == 200
    resolved = resolve_resp.json()["data"]
    assert resolved["approval_id"] == str(pending.id)
    assert resolved["status"] == ApprovalStatus.APPROVED
    assert resolved["resolved_at"] is not None

    resolve_again_resp = await async_client.post(
        f"/api/v1/agent/approvals/{pending.id}/resolve",
        json={"action": "reject"},
    )
    assert resolve_again_resp.status_code == 400
    assert resolve_again_resp.json()["error"]["code"] == "BAD_REQUEST"
    assert "already resolved" in resolve_again_resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_agent_history_before_and_limit_preserve_user_anchor(
    async_client, db_session, tmp_path
):
    project = await _create_project(
        db_session,
        name="Agent History Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "agent-history-workspace"),
    )
    conversation = await _create_conversation(
        db_session,
        project_id=str(project.id),
        title="Boundary history",
    )
    first_user = await _create_message(
        db_session,
        conversation_id=str(conversation.id),
        project_id=str(project.id),
        role=MessageRole.USER.value,
        content="first user",
    )
    first_agent = await _create_message(
        db_session,
        conversation_id=str(conversation.id),
        project_id=str(project.id),
        role=MessageRole.AGENT.value,
        content="first agent",
    )
    second_user = await _create_message(
        db_session,
        conversation_id=str(conversation.id),
        project_id=str(project.id),
        role=MessageRole.USER.value,
        content="second user",
    )
    second_agent = await _create_message(
        db_session,
        conversation_id=str(conversation.id),
        project_id=str(project.id),
        role=MessageRole.AGENT.value,
        content="second agent",
    )
    base_time = datetime.now(timezone.utc)
    first_user.created_at = base_time
    first_agent.created_at = base_time + timedelta(seconds=1)
    second_user.created_at = base_time + timedelta(seconds=2)
    second_agent.created_at = base_time + timedelta(seconds=3)
    await db_session.commit()

    history_resp = await async_client.get(
        f"/api/v1/agent/conversations/{conversation.id}",
        params={"before": str(first_agent.id), "limit": 1},
    )
    assert history_resp.status_code == 200

    messages = history_resp.json()["data"]["messages"]
    assert [message["role"] for message in messages] == ["user"]
    assert [message["content"] for message in messages] == ["first user"]

    anchored_resp = await async_client.get(
        f"/api/v1/agent/conversations/{conversation.id}",
        params={"before": str(uuid4()), "limit": 1},
    )
    assert anchored_resp.status_code == 200
    anchored_messages = anchored_resp.json()["data"]["messages"]
    assert [message["role"] for message in anchored_messages] == ["user", "agent"]
    assert [message["content"] for message in anchored_messages] == [
        "second user",
        "second agent",
    ]


@pytest.mark.asyncio
async def test_agent_missing_resources_and_idle_conversation_semantics(
    async_client, db_session, tmp_path
):
    project = await _create_project(
        db_session,
        name="Agent Missing Resource Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "agent-missing-workspace"),
    )
    conversation = await _create_conversation(
        db_session,
        project_id=str(project.id),
        title="Idle conversation",
    )
    missing_id = str(uuid4())

    status_missing = await async_client.get(
        f"/api/v1/agent/conversations/{missing_id}/status"
    )
    assert status_missing.status_code == 404
    assert status_missing.json()["error"]["code"] == "NOT_FOUND"

    cancel_missing = await async_client.post(
        f"/api/v1/agent/conversations/{missing_id}/cancel"
    )
    assert cancel_missing.status_code == 404
    assert cancel_missing.json()["error"]["code"] == "NOT_FOUND"

    approval_missing = await async_client.get(f"/api/v1/agent/approvals/{missing_id}")
    assert approval_missing.status_code == 404
    assert approval_missing.json()["error"]["code"] == "NOT_FOUND"

    resolve_missing = await async_client.post(
        f"/api/v1/agent/approvals/{missing_id}/resolve",
        json={"action": "approve"},
    )
    assert resolve_missing.status_code == 404
    assert resolve_missing.json()["error"]["code"] == "NOT_FOUND"

    idle_status = await async_client.get(
        f"/api/v1/agent/conversations/{conversation.id}/status"
    )
    assert idle_status.status_code == 200
    assert idle_status.json()["data"] == {
        "conversation_id": str(conversation.id),
        "is_running": False,
        "assistant_message_id": None,
        "last_event_at": None,
    }

    idle_cancel = await async_client.post(
        f"/api/v1/agent/conversations/{conversation.id}/cancel"
    )
    assert idle_cancel.status_code == 200
    assert idle_cancel.json()["data"] == {
        "conversation_id": str(conversation.id),
        "cancelled": False,
    }
