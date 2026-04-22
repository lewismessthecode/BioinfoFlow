from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.models.agent_approval_handle import (
    AgentApprovalHandle,
    AgentApprovalHandleStatus,
)
from app.models.agent_response_handle import AgentResponseHandle, AgentResponseStatus
from app.models.conversation import Conversation, ConversationStorageBackend
from app.models.project import Project
from app.services.hermes_service.service import HermesConversationService


class FakeSessionStore:
    def __init__(self, messages):
        self._messages = messages
        self.title_updates: list[tuple[str, str]] = []

    def get_messages(self, session_id: str):
        return list(self._messages)

    def set_session_title(self, session_id: str, title: str) -> bool:
        self.title_updates.append((session_id, title))
        return True


@pytest.mark.asyncio
async def test_get_conversation_history_normalizes_hermes_messages(
    db_session, tmp_path
):
    project = Project(
        name="Hermes Service Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "workspace"),
        user_id="dev",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    conversation = Conversation(
        project_id=str(project.id),
        user_id="dev",
        title="Hermes Session",
        storage_backend=ConversationStorageBackend.HERMES,
        hermes_session_id="sess-1",
        workspace_binding_id=project.workspace_id,
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    service = HermesConversationService(db_session)
    service.session_store = FakeSessionStore(
        [
            {
                "id": 1,
                "role": "user",
                "content": "Inspect project",
                "timestamp": datetime.now(timezone.utc).timestamp(),
                "tool_call_id": None,
                "tool_name": None,
                "tool_calls": None,
                "reasoning": None,
            },
            {
                "id": 2,
                "role": "assistant",
                "content": "Working on it",
                "timestamp": datetime.now(timezone.utc).timestamp(),
                "tool_call_id": None,
                "tool_name": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "shell", "arguments": '{"command":"pwd"}'},
                    }
                ],
                "reasoning": "Need to inspect cwd",
            },
            {
                "id": 3,
                "role": "tool",
                "content": "/tmp/workspace",
                "timestamp": datetime.now(timezone.utc).timestamp(),
                "tool_call_id": "call_1",
                "tool_name": "shell",
                "tool_calls": None,
                "reasoning": None,
            },
            {
                "id": 4,
                "role": "assistant",
                "content": "Done",
                "timestamp": datetime.now(timezone.utc).timestamp(),
                "tool_call_id": None,
                "tool_name": None,
                "tool_calls": None,
                "reasoning": None,
            },
        ]
    )

    history = await service.get_conversation_history(
        conversation_id=str(conversation.id),
        user_id="dev",
        limit=50,
        before=None,
    )

    assert history.storage_backend == ConversationStorageBackend.HERMES
    assert [message.role for message in history.messages] == ["user", "agent", "agent"]
    assert history.messages[1].metadata["parts"][0]["type"] == "thinking"
    assert history.messages[1].metadata["parts"][1]["type"] == "text"
    assert history.messages[1].metadata["parts"][2]["type"] == "tool-call"
    assert history.messages[1].metadata["parts"][2]["status"] == "done"
    assert history.messages[1].metadata["parts"][2]["result"] == "/tmp/workspace"


@pytest.mark.asyncio
async def test_create_conversation_persists_execution_policy(db_session, tmp_path):
    project = Project(
        name="Hermes Policy Create Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "workspace"),
        user_id="dev",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    service = HermesConversationService(db_session)
    conversation = await service.create_conversation(
        project_id=str(project.id),
        user_id="dev",
        execution_policy="bypass",
    )

    assert conversation.execution_policy == "bypass"
    assert conversation.storage_backend == ConversationStorageBackend.HERMES


@pytest.mark.asyncio
async def test_get_conversation_history_includes_approval_parts(db_session, tmp_path):
    project = Project(
        name="Hermes Approval History Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "workspace"),
        user_id="dev",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    conversation = Conversation(
        project_id=str(project.id),
        user_id="dev",
        title="Hermes Session",
        storage_backend=ConversationStorageBackend.HERMES,
        hermes_session_id="sess-2",
        workspace_binding_id=project.workspace_id,
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    response_handle = AgentResponseHandle(
        conversation_id=str(conversation.id),
        status=AgentResponseStatus.RUNNING,
    )
    db_session.add(response_handle)
    await db_session.commit()
    await db_session.refresh(response_handle)

    approval = AgentApprovalHandle(
        conversation_id=str(conversation.id),
        response_id=str(response_handle.id),
        call_id="clarify:1",
        status=AgentApprovalHandleStatus.PENDING,
        payload={
            "question": "Approve shell?",
            "choices": ["approve", "reject"],
            "tool": "clarify",
            "approval_type": "clarify",
        },
    )
    db_session.add(approval)
    await db_session.commit()
    await db_session.refresh(approval)

    service = HermesConversationService(db_session)
    service.session_store = FakeSessionStore(
        [
            {
                "id": 1,
                "role": "user",
                "content": "Inspect project",
                "timestamp": datetime.now(timezone.utc).timestamp(),
                "tool_call_id": None,
                "tool_name": None,
                "tool_calls": None,
                "reasoning": None,
            }
        ]
    )

    history = await service.get_conversation_history(
        conversation_id=str(conversation.id),
        user_id="dev",
        limit=50,
        before=None,
    )

    assert len(history.messages) == 2
    approval_message = next(
        message
        for message in history.messages
        if message.metadata["parts"][0]["type"] == "approval"
    )
    assert approval_message.role == "agent"
    assert approval_message.metadata["parts"][0]["type"] == "approval"
    assert approval_message.metadata["parts"][0]["approvalId"] == str(approval.id)
    assert (
        approval_message.metadata["parts"][0]["status"]
        == AgentApprovalHandleStatus.PENDING
    )


@pytest.mark.asyncio
async def test_request_clarification_creates_handle_and_returns_resolution(
    db_session, tmp_path, monkeypatch
):
    project = Project(
        name="Hermes Clarify Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "workspace"),
        user_id="dev",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    conversation = Conversation(
        project_id=str(project.id),
        user_id="dev",
        title="Hermes Clarify",
        storage_backend=ConversationStorageBackend.HERMES,
        hermes_session_id="sess-3",
        workspace_binding_id=project.workspace_id,
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    response_handle = AgentResponseHandle(
        conversation_id=str(conversation.id),
        status=AgentResponseStatus.RUNNING,
    )
    db_session.add(response_handle)
    await db_session.commit()
    await db_session.refresh(response_handle)

    published: list[dict] = []

    async def fake_publish_event(**kwargs):
        published.append(kwargs)

    monkeypatch.setattr(
        "app.services.hermes_service.service.publish_event", fake_publish_event
    )

    service = HermesConversationService(db_session)
    task = asyncio.create_task(
        service.request_clarification(
            response_id=str(response_handle.id),
            conversation_id=str(conversation.id),
            project_id=str(project.id),
            question="Approve shell?",
            choices=["approve", "reject"],
        )
    )

    await asyncio.sleep(0.05)
    approvals = await service.list_pending_approvals(
        conversation_id=str(conversation.id),
        user_id="dev",
    )
    assert len(approvals) == 1
    assert approvals[0].payload["question"] == "Approve shell?"

    await service.resolve_approval(
        str(approvals[0].id), action="approve", user_id="dev"
    )
    result = await asyncio.wait_for(task, timeout=1)

    assert result == "approve"
    assert published
    assert published[0]["event"] == "agent.approval.requested"
    assert published[0]["data"]["approval_type"] == "clarify"
