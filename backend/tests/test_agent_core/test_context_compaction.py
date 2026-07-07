from __future__ import annotations

import pytest

from app.models.llm import LlmModel, LlmProvider
from app.models.workspace import Workspace
from app.path_layout import skills_root
from app.repositories.agent_core_repo import AgentMessageRepository
from app.services.agent_core import AgentCoreService
from app.services.agent_core.context import AgentContextAssembler
from app.services.agent_core.transcript import AgentTranscriptStore, text_part
from app.workspace import DEFAULT_WORKSPACE_ID


async def _workspace(db_session) -> Workspace:
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()
    return workspace


async def _seed_catalog_model(db_session, *, model_id: str = "context-model") -> LlmModel:
    provider = LlmProvider(
        name=f"{model_id} provider",
        kind="openai_compatible",
        base_url="https://models.internal.example/v1",
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "openai-compatible"},
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    model = LlmModel(
        provider_id=str(provider.id),
        model_id=model_id,
        display_name=model_id,
        supports_tools=True,
        supports_streaming=True,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


@pytest.mark.asyncio
async def test_context_compaction_supersedes_older_messages(db_session):
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    session = await service.session_repo.update_all(
        session,
        compression_state={
            "enabled": True,
            "threshold_chars": 120,
            "preserve_recent_messages": 2,
        },
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="latest user input",
    )
    transcript = AgentTranscriptStore(db_session)
    await transcript.append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        parts=[text_part("old assistant reply one" * 8)],
    )
    await transcript.append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="user",
        parts=[text_part("old user follow-up two" * 8)],
    )
    await transcript.append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        parts=[text_part("recent assistant reply")],
    )

    messages = await AgentContextAssembler(db_session).provider_messages(
        agent_session=session,
        turn=turn,
    )
    stored = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    statuses = [message.status for message in stored]

    assert "superseded" in statuses
    summary_message = next(
        message
        for message in stored
        if message.role == "assistant"
        and (message.message_metadata or {}).get("kind") == "compaction_summary"
    )
    recent_messages = [message for message in stored if message.status == "committed"]
    assert summary_message.ordering_index < recent_messages[-1].ordering_index
    assert any(
        message.role == "assistant"
        and (message.message_metadata or {}).get("kind") == "compaction_summary"
        for message in stored
    )
    assert any(
        message["role"] == "assistant"
        and "Conversation summary for continuity" in message.get("content", "")
        for message in messages
    )
    assert not any(message.get("content") == "old assistant reply one" * 8 for message in messages)


@pytest.mark.asyncio
async def test_active_skill_body_is_added_to_current_turn_context(db_session):
    await _workspace(db_session)
    root = skills_root()
    skill_dir = root / "nextflow-debugging"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: nextflow-debugging",
                "description: Diagnose failed Nextflow runs.",
                "---",
                "Use run logs, DAG, and audit events before explaining failures.",
            ]
        ),
        encoding="utf-8",
    )
    inactive_dir = root / "wdl-debugging"
    inactive_dir.mkdir(parents=True)
    (inactive_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: wdl-debugging",
                "description: Diagnose WDL runs.",
                "---",
                "This inactive body should stay hidden.",
            ]
        ),
        encoding="utf-8",
    )

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Analyze this failed run.",
        active_skill_names=["nextflow-debugging"],
    )

    messages = await AgentContextAssembler(db_session).provider_messages(
        agent_session=session,
        turn=turn,
    )
    system_content = messages[0]["content"]

    assert "## Agent skills" in system_content
    assert "- nextflow-debugging (0.1.0): Diagnose failed Nextflow runs." in system_content
    assert "- wdl-debugging (0.1.0): Diagnose WDL runs." in system_content
    assert "## Active skills for this turn" in system_content
    assert "Use run logs, DAG, and audit events before explaining failures." in system_content
    assert "This inactive body should stay hidden." not in system_content
