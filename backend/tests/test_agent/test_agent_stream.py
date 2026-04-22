from __future__ import annotations

import asyncio

import pytest

from app.models.message import MessageType
from app.models.project import Project
from app.repositories.message_repo import MessageRepository
from app.runtime.events import events
from app.services.agent.agent_service import AgentService


@pytest.mark.asyncio
async def test_agent_emits_events(async_client, db_session, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project = Project(
        name="Agent Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    queue = await events.subscribe(str(project.id))

    async def _fake_run_v2(self, **kwargs):
        await self._persist_and_publish_agent_event(
            conversation_id=kwargs["conversation_id"],
            project_id=kwargs["project_id"],
            assistant_message_id=kwargs["assistant_message_id"],
            event={
                "type": "text",
                "content": "I scanned the workspace and found no samples yet.",
                "metadata": {"usage": {"input_tokens": 42, "output_tokens": 13}},
            },
        )

    async def _fake_generate_title(self, *args, **kwargs):
        return None

    monkeypatch.setattr(AgentService, "_run_v2", _fake_run_v2)
    monkeypatch.setattr(AgentService, "_generate_title", _fake_generate_title)

    payload = {
        "project_id": str(project.id),
        "content": "scan samples in this workspace",
    }
    response = await async_client.post("/api/v1/agent/message", json=payload)
    assert response.status_code == 202
    conversation_id = response.json()["data"]["conversation_id"]

    received = []
    try:
        for _ in range(20):
            event = await asyncio.wait_for(queue.get(), timeout=2)
            received.append(event["event"])
            if event["event"] == "agent.done":
                break
    finally:
        events.unsubscribe(str(project.id), queue)

    # New streaming events: text_delta for streaming text, then message for final
    assert "agent.done" in received
    # Should have either text_delta (streaming) or message (final text)
    has_text = "agent.text_delta" in received or "agent.message" in received
    assert has_text, f"Expected text event in {received}"

    messages = await MessageRepository(db_session).get_conversation_messages(
        conversation_id
    )
    types = {message.type for message in messages}
    assert MessageType.TEXT.value in types
