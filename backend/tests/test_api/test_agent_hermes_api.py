from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.config import settings
from app.models.agent_approval_handle import (
    AgentApprovalHandle,
    AgentApprovalHandleStatus,
)
from app.models.conversation import Conversation, ConversationStorageBackend
from app.models.project import Project


async def _create_project(
    db_session, tmp_path, name: str = "Hermes Project"
) -> Project:
    project = Project(
        name=name,
        storage_mode="external",
        external_root_path=str(tmp_path / "workspace"),
        user_id="dev",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest.mark.asyncio
async def test_create_conversation_uses_hermes_backend_when_flag_enabled(
    async_client, db_session, tmp_path, monkeypatch
):
    project = await _create_project(db_session, tmp_path)
    monkeypatch.setattr(settings, "agent_engine", "hermes_service", raising=False)

    response = await async_client.post(
        "/api/v1/agent/conversations",
        json={"project_id": str(project.id), "title": "Hermes Thread"},
    )

    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["storage_backend"] == ConversationStorageBackend.HERMES
    assert payload["workspace_binding_id"] == project.workspace_id
    assert "hermes_session_id" not in payload

    conversation = await db_session.get(Conversation, payload["id"])
    assert conversation is not None
    assert conversation.storage_backend == ConversationStorageBackend.HERMES
    assert conversation.hermes_session_id


@pytest.mark.asyncio
async def test_send_message_branches_to_hermes_service(
    async_client, db_session, tmp_path, monkeypatch
):
    project = await _create_project(db_session, tmp_path, name="Hermes Send Project")
    monkeypatch.setattr(settings, "agent_engine", "hermes_service", raising=False)

    create_response = await async_client.post(
        "/api/v1/agent/conversations",
        json={"project_id": str(project.id), "title": "Hermes Send"},
    )
    conversation_id = create_response.json()["data"]["id"]
    fake_response_id = str(uuid4())

    async def fake_send_message(self, **kwargs):
        return {
            "response_id": fake_response_id,
            "conversation_id": kwargs["conversation_id"],
            "status": "processing",
        }

    from app.services.hermes_service.service import HermesConversationService

    monkeypatch.setattr(HermesConversationService, "send_message", fake_send_message)

    response = await async_client.post(
        "/api/v1/agent/message",
        json={
            "project_id": str(project.id),
            "conversation_id": conversation_id,
            "content": "Use Hermes",
        },
    )

    assert response.status_code == 202
    payload = response.json()["data"]
    assert payload["conversation_id"] == conversation_id
    assert payload["response_id"] == fake_response_id
    assert payload["message_id"] is None
    assert payload["status"] == "processing"


@pytest.mark.asyncio
async def test_send_message_keeps_legacy_threads_on_legacy_service(
    async_client, db_session, tmp_path, monkeypatch
):
    project = await _create_project(db_session, tmp_path, name="Legacy Thread Project")
    monkeypatch.setattr(settings, "agent_engine", "hermes_service", raising=False)

    legacy_conversation = Conversation(
        project_id=str(project.id),
        user_id="dev",
        title="Legacy Thread",
        storage_backend=ConversationStorageBackend.LEGACY,
    )
    db_session.add(legacy_conversation)
    await db_session.commit()
    await db_session.refresh(legacy_conversation)

    async def fail_hermes(self, **kwargs):
        raise AssertionError("Hermes service should not be used for legacy threads")

    async def fake_legacy_send(self, **kwargs):
        from types import SimpleNamespace

        return (
            SimpleNamespace(id=uuid4()),
            SimpleNamespace(id=legacy_conversation.id),
        )

    from app.services.agent.agent_service import AgentService
    from app.services.hermes_service.service import HermesConversationService

    monkeypatch.setattr(HermesConversationService, "send_message", fail_hermes)
    monkeypatch.setattr(AgentService, "send_message", fake_legacy_send)

    response = await async_client.post(
        "/api/v1/agent/message",
        json={
            "project_id": str(project.id),
            "conversation_id": str(legacy_conversation.id),
            "content": "Stay on legacy",
        },
    )

    assert response.status_code == 202
    payload = response.json()["data"]
    assert payload["conversation_id"] == str(legacy_conversation.id)
    assert payload["message_id"] is not None
    assert payload["response_id"] is None


@pytest.mark.asyncio
async def test_send_message_uses_existing_hermes_history(
    async_client, db_session, tmp_path, monkeypatch
):
    project = await _create_project(
        db_session, tmp_path, name="Hermes History Reuse Project"
    )
    monkeypatch.setattr(settings, "agent_engine", "hermes_service", raising=False)

    create_response = await async_client.post(
        "/api/v1/agent/conversations",
        json={"project_id": str(project.id), "title": "Hermes Existing History"},
    )
    conversation_id = create_response.json()["data"]["id"]

    captured = {}

    async def fake_send_message(self, **kwargs):
        captured.update(kwargs)
        return {
            "response_id": str(uuid4()),
            "conversation_id": kwargs["conversation_id"],
            "status": "processing",
        }

    from app.services.hermes_service.service import HermesConversationService

    monkeypatch.setattr(HermesConversationService, "send_message", fake_send_message)

    response = await async_client.post(
        "/api/v1/agent/message",
        json={
            "project_id": str(project.id),
            "conversation_id": conversation_id,
            "content": "Continue this thread",
        },
    )

    assert response.status_code == 202
    assert captured["conversation_id"] == conversation_id
    assert captured["content"] == "Continue this thread"


@pytest.mark.asyncio
async def test_send_message_forwards_execution_policy_to_hermes_service(
    async_client, db_session, tmp_path, monkeypatch
):
    project = await _create_project(db_session, tmp_path, name="Hermes Policy Project")
    monkeypatch.setattr(settings, "agent_engine", "hermes_service", raising=False)

    captured = {}

    async def fake_send_message(self, **kwargs):
        captured.update(kwargs)
        return {
            "response_id": str(uuid4()),
            "conversation_id": str(uuid4()),
            "status": "processing",
        }

    from app.services.hermes_service.service import HermesConversationService

    monkeypatch.setattr(HermesConversationService, "send_message", fake_send_message)

    response = await async_client.post(
        "/api/v1/agent/message",
        json={
            "project_id": str(project.id),
            "content": "Start in bypass mode",
            "execution_policy": "bypass",
        },
    )

    assert response.status_code == 202
    assert captured["execution_policy"] == "bypass"


@pytest.mark.asyncio
async def test_get_conversation_history_uses_hermes_service_for_hermes_threads(
    async_client, db_session, tmp_path, monkeypatch
):
    project = await _create_project(db_session, tmp_path, name="Hermes History Project")
    monkeypatch.setattr(settings, "agent_engine", "hermes_service", raising=False)

    create_response = await async_client.post(
        "/api/v1/agent/conversations",
        json={"project_id": str(project.id), "title": "Hermes History"},
    )
    conversation_id = create_response.json()["data"]["id"]

    from app.schemas.agent import (
        AgentConversationHistory,
        AgentMessageRead,
        AgentMessageRole,
        AgentMessageType,
    )
    from app.services.hermes_service.service import HermesConversationService

    async def fake_get_history(self, **kwargs):
        return AgentConversationHistory(
            conversation_id=conversation_id,
            project_id=str(project.id),
            title="Hermes History",
            pinned=False,
            storage_backend=ConversationStorageBackend.HERMES,
            messages=[
                AgentMessageRead(
                    id=uuid4(),
                    role=AgentMessageRole.USER,
                    type=AgentMessageType.TEXT,
                    content="Use Hermes",
                    metadata=None,
                    created_at=datetime.now(timezone.utc),
                ),
                AgentMessageRead(
                    id=uuid4(),
                    role=AgentMessageRole.AGENT,
                    type=AgentMessageType.TEXT,
                    content="",
                    metadata={
                        "response_id": str(uuid4()),
                        "parts": [
                            {
                                "type": "thinking",
                                "text": "Reasoning",
                                "isStreaming": False,
                            },
                            {"type": "text", "text": "Hermes answer"},
                        ],
                    },
                    created_at=datetime.now(timezone.utc),
                ),
            ],
        )

    monkeypatch.setattr(
        HermesConversationService, "get_conversation_history", fake_get_history
    )

    response = await async_client.get(f"/api/v1/agent/conversations/{conversation_id}")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["storage_backend"] == ConversationStorageBackend.HERMES
    assert len(payload["messages"]) == 2
    assert payload["messages"][1]["metadata"]["parts"][1]["text"] == "Hermes answer"


@pytest.mark.asyncio
async def test_list_pending_approvals_uses_hermes_handles(
    async_client, db_session, tmp_path, monkeypatch
):
    project = await _create_project(
        db_session, tmp_path, name="Hermes Approval Project"
    )
    monkeypatch.setattr(settings, "agent_engine", "hermes_service", raising=False)

    create_response = await async_client.post(
        "/api/v1/agent/conversations",
        json={"project_id": str(project.id), "title": "Hermes Approval"},
    )
    conversation_id = create_response.json()["data"]["id"]

    from app.models.agent_response_handle import AgentResponseHandle

    response_handle = AgentResponseHandle(
        conversation_id=conversation_id,
        status="running",
    )
    db_session.add(response_handle)
    await db_session.commit()
    await db_session.refresh(response_handle)

    approval = AgentApprovalHandle(
        conversation_id=conversation_id,
        response_id=str(response_handle.id),
        call_id="call_approve",
        status=AgentApprovalHandleStatus.PENDING,
        payload={"question": "Approve shell?", "choices": ["approve", "reject"]},
    )
    db_session.add(approval)
    await db_session.commit()
    await db_session.refresh(approval)

    response = await async_client.get(
        f"/api/v1/agent/conversations/{conversation_id}/approvals/pending"
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["conversation_id"] == conversation_id
    assert len(payload["approvals"]) == 1
    assert payload["approvals"][0]["id"] == str(approval.id)


@pytest.mark.asyncio
async def test_resolve_approval_uses_hermes_handles(
    async_client, db_session, tmp_path, monkeypatch
):
    project = await _create_project(db_session, tmp_path, name="Hermes Resolve Project")
    monkeypatch.setattr(settings, "agent_engine", "hermes_service", raising=False)

    create_response = await async_client.post(
        "/api/v1/agent/conversations",
        json={"project_id": str(project.id), "title": "Hermes Resolve"},
    )
    conversation_id = create_response.json()["data"]["id"]

    from app.models.agent_response_handle import AgentResponseHandle

    response_handle = AgentResponseHandle(
        conversation_id=conversation_id,
        status="running",
    )
    db_session.add(response_handle)
    await db_session.commit()
    await db_session.refresh(response_handle)

    approval = AgentApprovalHandle(
        conversation_id=conversation_id,
        response_id=str(response_handle.id),
        call_id="call_approve",
        status=AgentApprovalHandleStatus.PENDING,
        payload={"question": "Approve shell?", "choices": ["approve", "reject"]},
    )
    db_session.add(approval)
    await db_session.commit()
    await db_session.refresh(approval)

    response = await async_client.post(
        f"/api/v1/agent/approvals/{approval.id}/resolve",
        json={"action": "approve"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["approval_id"] == str(approval.id)
    assert payload["status"] == AgentApprovalHandleStatus.APPROVED
