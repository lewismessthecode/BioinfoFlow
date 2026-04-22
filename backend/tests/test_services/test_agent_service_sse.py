"""Tests for AgentService SSE envelope extensions (Task 3.2).

Validates: timestamp, sequence, stream fields in published events,
and the streaming persistence filter (stream=True skips DB).
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.message import Message, MessageRole, MessageType
from app.models.project import Project
from app.models.conversation import Conversation
from app.services.agent.agent_service import AgentService


def _make_fake_message(*, type_: str = "text", content: str = "hi"):
    """Return a minimal mock Message object."""
    msg = MagicMock()
    msg.id = "msg-1"
    msg.type = type_
    msg.content = content
    msg.message_metadata = None
    return msg


@pytest.mark.asyncio
async def test_publish_agent_event_includes_timestamp_and_sequence():
    """_publish_agent_event should add timestamp, sequence, and stream fields."""
    service = AgentService.__new__(AgentService)
    service._sequence_counter = 0
    service.logger = MagicMock()

    published = []

    async def fake_publish_event(**kwargs):
        published.append(kwargs)

    with patch("app.services.agent.agent_streaming.publish_event", side_effect=fake_publish_event):
        await service._publish_agent_event(
            message_type="text",
            message_id="msg-1",
            project_id="p-1",
            conversation_id="c-1",
            content="hello",
            metadata=None,
        )
        await service._publish_agent_event(
            message_type="thinking",
            message_id="msg-2",
            project_id="p-1",
            conversation_id="c-1",
            content="analyzing",
            metadata={"summary": ["Thinking..."]},
        )

    assert len(published) == 2

    # First event
    data0 = published[0]["data"]
    assert "timestamp" in data0
    # Should be ISO 8601 parseable
    datetime.fromisoformat(data0["timestamp"])
    assert data0["sequence"] == 1
    assert data0["stream"] is False

    # Second event — sequence monotonically increases
    data1 = published[1]["data"]
    assert data1["sequence"] == 2
    assert "timestamp" in data1


@pytest.mark.asyncio
async def test_persist_and_publish_skips_db_for_stream_events():
    """Events with stream=True should be published via SSE but NOT persisted."""
    service = AgentService.__new__(AgentService)
    service._sequence_counter = 0
    service.logger = MagicMock()
    service.message_repo = MagicMock()
    service.message_repo.create = AsyncMock(return_value=_make_fake_message())

    published = []

    async def fake_publish_event(**kwargs):
        published.append(kwargs)

    with patch("app.services.agent.agent_streaming.publish_event", side_effect=fake_publish_event):
        # Non-streaming event — should persist AND publish
        await service._persist_and_publish_agent_event(
            conversation_id="c-1",
            project_id="p-1",
            event={"type": "text", "content": "hi", "metadata": None},
        )

    assert service.message_repo.create.call_count == 1
    assert len(published) == 1

    # Reset
    service.message_repo.create.reset_mock()
    published.clear()

    with patch("app.services.agent.agent_streaming.publish_event", side_effect=fake_publish_event):
        # Streaming event — should publish but NOT persist
        await service._persist_and_publish_agent_event(
            conversation_id="c-1",
            project_id="p-1",
            event={"type": "thinking_content", "content": "reasoning...", "metadata": None, "stream": True},
        )

    assert service.message_repo.create.call_count == 0, "stream=True events should NOT be persisted"
    assert len(published) == 1, "stream=True events should still be published via SSE"
    assert published[0]["data"]["stream"] is True


@pytest.mark.asyncio
async def test_sequence_counter_is_monotonic():
    """Sequence numbers should increase monotonically across calls."""
    service = AgentService.__new__(AgentService)
    service._sequence_counter = 0
    service.logger = MagicMock()

    sequences = []

    async def fake_publish_event(**kwargs):
        sequences.append(kwargs["data"]["sequence"])

    with patch("app.services.agent.agent_streaming.publish_event", side_effect=fake_publish_event):
        for _ in range(5):
            await service._publish_agent_event(
                message_type="text",
                message_id="msg-x",
                project_id="p-1",
                conversation_id="c-1",
                content="test",
                metadata=None,
            )

    assert sequences == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_stream_events_update_existing_assistant_draft(db_session, tmp_path):
    """Streaming and final events should update one assistant draft message."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project = Project(name="Draft Project", storage_mode="external", external_root_path=str(workspace), user_id="dev")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    conversation = Conversation(project_id=str(project.id), user_id="dev")
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    draft = Message(
        conversation_id=str(conversation.id),
        project_id=str(project.id),
        role=MessageRole.AGENT.value,
        type=MessageType.TEXT.value,
        content="",
        message_metadata={"parts": [], "status": "streaming", "streaming": True},
    )
    db_session.add(draft)
    await db_session.commit()
    await db_session.refresh(draft)

    service = AgentService(db_session)

    published = []

    async def fake_publish_event(**kwargs):
        published.append(kwargs)

    with patch("app.services.agent.agent_streaming.publish_event", side_effect=fake_publish_event):
        await service._persist_and_publish_agent_event(
            conversation_id=str(conversation.id),
            project_id=str(project.id),
            assistant_message_id=str(draft.id),
            event={"type": "thinking_delta", "content": "Planning...", "stream": True},
        )
        await service._persist_and_publish_agent_event(
            conversation_id=str(conversation.id),
            project_id=str(project.id),
            assistant_message_id=str(draft.id),
            event={
                "type": "tool_call_start",
                "content": "shell",
                "metadata": {"id": "tool-1", "name": "shell", "args": {"command": "pwd"}},
                "stream": True,
            },
        )
        await service._persist_and_publish_agent_event(
            conversation_id=str(conversation.id),
            project_id=str(project.id),
            assistant_message_id=str(draft.id),
            event={
                "type": "tool_call_end",
                "content": "shell",
                "metadata": {
                    "id": "tool-1",
                    "name": "shell",
                    "result": "/tmp/workspace",
                    "is_error": False,
                    "duration_ms": 12.5,
                },
                "stream": True,
            },
        )
        await service._persist_and_publish_agent_event(
            conversation_id=str(conversation.id),
            project_id=str(project.id),
            assistant_message_id=str(draft.id),
            event={
                "type": "text",
                "content": "Executed the script successfully.",
                "metadata": {"usage": {"input_tokens": 12, "output_tokens": 7}},
            },
        )

    refreshed = await db_session.get(Message, str(draft.id))
    assert refreshed is not None
    assert refreshed.content == "Executed the script successfully."
    assert refreshed.type == MessageType.TEXT.value
    assert refreshed.message_metadata["streaming"] is False
    assert refreshed.message_metadata["status"] == "completed"
    assert refreshed.message_metadata["usage"] == {"input_tokens": 12, "output_tokens": 7}
    assert refreshed.message_metadata["parts"][0] == {
        "type": "thinking",
        "text": "Planning...",
        "isStreaming": False,
    }
    assert refreshed.message_metadata["parts"][1]["type"] == "tool-call"
    assert refreshed.message_metadata["parts"][1]["toolName"] == "shell"
    assert refreshed.message_metadata["parts"][1]["status"] == "done"
    assert refreshed.message_metadata["parts"][2] == {
        "type": "text",
        "text": "Executed the script successfully.",
    }

    assert all(item["data"]["id"] == str(draft.id) for item in published)


@pytest.mark.asyncio
async def test_generate_title_falls_back_to_first_message_when_llm_fails(
    db_session, tmp_path, monkeypatch
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project = Project(name="Title Project", storage_mode="external", external_root_path=str(workspace), user_id="dev")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    conversation = Conversation(project_id=str(project.id), user_id="dev")
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    service = AgentService(db_session)

    async def _fail_create(*args, **kwargs):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(
        "app.services.agent.runtime.llm_client.LLMClient.create",
        _fail_create,
    )

    message = "  Investigate   differential expression for treated vs control samples in cohort A  "
    await service._generate_title(str(conversation.id), message, user_id="dev")

    await db_session.refresh(conversation)
    assert conversation.title == "Investigate differential expression for treated vs control..."
