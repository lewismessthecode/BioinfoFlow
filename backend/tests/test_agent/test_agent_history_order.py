from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.conversation import Conversation
from app.models.message import Message, MessageRole, MessageType
from app.models.project import Project
from app.services.agent.agent_service import AgentService


@pytest.mark.asyncio
async def test_history_places_user_before_agent_when_timestamps_match(
    db_session, tmp_path
):
    project = Project(
        name="History Order Project", storage_mode="external", external_root_path=str(tmp_path), user_id="dev"
    )
    db_session.add(project)
    await db_session.flush()

    conversation = Conversation(
        project_id=str(project.id), title="Order Test", user_id="dev"
    )
    db_session.add(conversation)
    await db_session.flush()

    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    user_message = Message(
        id=uuid4(),
        conversation_id=str(conversation.id),
        project_id=str(project.id),
        role=MessageRole.USER.value,
        type=MessageType.TEXT.value,
        content="Run the SARS-CoV-2 demo",
        created_at=created_at,
        updated_at=created_at,
    )
    leading_thinking = Message(
        id=uuid4(),
        conversation_id=str(conversation.id),
        project_id=str(project.id),
        role=MessageRole.AGENT.value,
        type=MessageType.THINKING.value,
        content="Analyzing request",
        created_at=created_at,
        updated_at=created_at,
    )
    agent_reply = Message(
        id=uuid4(),
        conversation_id=str(conversation.id),
        project_id=str(project.id),
        role=MessageRole.AGENT.value,
        type=MessageType.TEXT.value,
        content="I found the workflow.",
        created_at=created_at + timedelta(seconds=1),
        updated_at=created_at + timedelta(seconds=1),
    )

    db_session.add_all([user_message, leading_thinking, agent_reply])
    await db_session.commit()

    service = AgentService(db_session)
    _, messages = await service.get_conversation_history(
        conversation_id=str(conversation.id),
        user_id="dev",
    )

    assert messages[0].role == MessageRole.USER.value
    assert messages[0].content == "Run the SARS-CoV-2 demo"
