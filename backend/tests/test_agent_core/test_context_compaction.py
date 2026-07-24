from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import settings
from app.models.llm import LlmModel, LlmProvider
from app.models.workspace import Workspace
from app.path_layout import skills_root
from app.repositories.agent_core_repo import AgentMessageRepository
from app.services.agent_core import AgentCoreService
from app.services.agent_core.context import AgentContextAssembler
from app.services.agent_core.transcript import (
    AgentTranscriptStore,
    parts_to_text,
    text_part,
)
from app.services.model_runtime.contracts import TextPart
from app.workspace import DEFAULT_WORKSPACE_ID


def _write_skill(
    root: Path,
    name: str,
    description: str,
    body: str,
) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                "---",
                body,
            ]
        ),
        encoding="utf-8",
    )


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
    summary_metadata = summary_message.message_metadata or {}
    assert summary_metadata["_temporal_context"] == turn.model_profile_snapshot[
        "temporal_context"
    ]
    assert parts_to_text(summary_message.content_parts).startswith(
        "<environment_context>\n"
        f"  <current_date>{turn.model_profile_snapshot['temporal_context']['current_date']}</current_date>\n"
        "  <timezone>Etc/UTC</timezone>\n"
        "</environment_context>\n\n"
    )
    assert any(
        message["role"] == "assistant"
        and "Conversation summary for continuity" in message.get("content", "")
        for message in messages
    )
    assert not any(message.get("content") == "old assistant reply one" * 8 for message in messages)

    for cycle in range(3):
        await transcript.append_parts(
            session_id=str(session.id),
            turn_id=str(turn.id),
            role="user",
            parts=[text_part(f"later user message {cycle} " * 20)],
        )
        await transcript.append_parts(
            session_id=str(session.id),
            turn_id=str(turn.id),
            role="assistant",
            parts=[text_part(f"later assistant message {cycle} " * 20)],
        )
        await transcript.append_parts(
            session_id=str(session.id),
            turn_id=str(turn.id),
            role="user",
            parts=[text_part(f"recent user message {cycle}")],
        )
        await AgentContextAssembler(db_session).provider_messages(
            agent_session=session,
            turn=turn,
        )

    stored = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    latest_summary = next(
        message
        for message in reversed(stored)
        if message.status == "committed"
        and (message.message_metadata or {}).get("kind") == "compaction_summary"
    )
    assert (latest_summary.message_metadata or {})["_temporal_context"] == (
        turn.model_profile_snapshot["temporal_context"]
    )
    assert parts_to_text(latest_summary.content_parts).startswith(
        "<environment_context>\n"
    )


@pytest.mark.asyncio
async def test_context_compaction_preserves_active_request_and_todo_state(
    db_session,
):
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
    active_request = (
        "Implement the approved human WGS germline pipeline now. Preserve the "
        "full design, create every WDL module, validate the syntax, and do not "
        "switch back to an unrelated completed run."
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text=active_request,
    )
    todos = [
        {"content": "Create WGS pipeline directory", "status": "completed"},
        {"content": "Write all WDL task modules", "status": "in_progress"},
        {"content": "Connect the main workflow", "status": "pending"},
        {"content": "Write form spec and README", "status": "pending"},
        {"content": "Validate WDL syntax", "status": "pending"},
    ]
    transcript = AgentTranscriptStore(db_session)
    await transcript.append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        parts=[text_part("An unrelated historical run completed. " * 12)],
    )
    await transcript.append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="tool",
        parts=[
            text_part(
                json.dumps(
                    {
                        "tool": "todo_write",
                        "status": "completed",
                        "result": {"todos": todos},
                        "error": None,
                    }
                )
            )
        ],
        metadata={"tool": "todo_write", "tool_call_id": "todo-1"},
    )
    await transcript.append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        parts=[text_part("Inspecting WDL examples. " * 12)],
    )
    await transcript.append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        parts=[text_part("Preparing module files.")],
    )

    await AgentContextAssembler(db_session).model_context(
        agent_session=session,
        turn=turn,
    )

    stored = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    first_summary = next(
        message
        for message in reversed(stored)
        if message.status == "committed"
        and (message.message_metadata or {}).get("kind") == "compaction_summary"
    )
    first_metadata = first_summary.message_metadata or {}
    first_text = parts_to_text(first_summary.content_parts)

    assert first_metadata["continuity_state"] == {
        "active_user_request": active_request,
        "active_todos": todos,
    }
    assert "## Active user request" in first_text
    assert active_request in first_text
    assert "## Active task checklist" in first_text
    assert all(todo["content"] in first_text for todo in todos)

    for index in range(3):
        await transcript.append_parts(
            session_id=str(session.id),
            turn_id=str(turn.id),
            role="assistant",
            parts=[text_part(f"Continuing implementation phase {index}. " * 20)],
        )
    await AgentContextAssembler(db_session).model_context(
        agent_session=session,
        turn=turn,
    )

    stored = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    latest_summary = next(
        message
        for message in reversed(stored)
        if message.status == "committed"
        and (message.message_metadata or {}).get("kind") == "compaction_summary"
    )
    latest_metadata = latest_summary.message_metadata or {}
    latest_text = parts_to_text(latest_summary.content_parts)

    assert latest_metadata["continuity_state"] == first_metadata["continuity_state"]
    assert active_request in latest_text
    assert all(todo["content"] in latest_text for todo in todos)


@pytest.mark.asyncio
async def test_model_context_preserves_each_assistant_phase_from_canonical_parts(
    db_session,
):
    await _workspace(db_session)
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
        input_text="Continue the investigation.",
    )
    await AgentTranscriptStore(db_session).append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        parts=[
            text_part("Checking inputs.", phase="commentary"),
            text_part("Investigation complete.", phase="final_answer"),
        ],
    )

    context = await AgentContextAssembler(db_session).model_context(
        agent_session=session,
        turn=turn,
    )

    assert context.input_items == (
        TextPart(
            text=(
                "<environment_context>\n"
                f"  <current_date>{turn.model_profile_snapshot['temporal_context']['current_date']}</current_date>\n"
                "  <timezone>Etc/UTC</timezone>\n"
                "</environment_context>\n\n"
                "Continue the investigation."
            )
        ),
        TextPart(text="Checking inputs.", phase="commentary"),
        TextPart(text="Investigation complete.", phase="final_answer"),
    )


@pytest.mark.asyncio
async def test_compaction_does_not_supersede_image_reference_messages(db_session):
    await _workspace(db_session)
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
            "threshold_chars": 40,
            "preserve_recent_messages": 1,
        },
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="old image",
    )
    messages = AgentMessageRepository(db_session)
    first = (await messages.list_for_session(str(session.id)))[0]
    await messages.update_all(
        first,
        content_parts=[
            text_part("old image context"),
            {
                "type": "image_ref",
                "attachment_id": "image-1",
                "mime_type": "image/png",
                "sha256": "a" * 64,
                "detail": "high",
            },
        ],
    )
    await AgentTranscriptStore(db_session).append_text(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        text="new reply" * 20,
    )

    await AgentContextAssembler(db_session)._compact_if_needed(
        agent_session=session,
        turn=turn,
    )
    stored = await messages.list_for_session(str(session.id))

    image_message = next(
        message
        for message in stored
        if any(part.get("type") == "image_ref" for part in message.content_parts)
    )
    assert image_message.status == "committed"


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
    assert f"Skill directory: {skill_dir.resolve()}" in system_content
    assert "Use run logs, DAG, and audit events before explaining failures." in system_content
    assert "This inactive body should stay hidden." not in system_content


@pytest.mark.asyncio
async def test_skill_summary_budget_does_not_truncate_active_repo_skill_body(
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    await _workspace(db_session)
    repo_root = tmp_path / "repo"
    repo_skills_root = repo_root / ".agents" / "skills"
    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    configured_root = skills_root()
    for index in range(80):
        _write_skill(
            configured_root,
            f"inactive-{index:03d}",
            f"Inactive configured skill {index:03d} " + ("x" * 180),
            f"Inactive body {index:03d} should not be injected.",
        )
    active_body = "ACTIVE-START\n" + ("active-body-line\n" * 700) + "ACTIVE-END"
    _write_skill(
        repo_skills_root,
        "active-repo-skill",
        "Repo-scoped active skill should load in full.",
        active_body,
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
        input_text="Use the repo skill.",
        active_skill_names=["active-repo-skill"],
    )

    messages = await AgentContextAssembler(db_session).provider_messages(
        agent_session=session,
        turn=turn,
    )
    system_content = messages[0]["content"]
    summary_section = system_content.split("## Agent skills", 1)[1].split(
        "## Active skills for this turn",
        1,
    )[0]
    summary_lines = "\n".join(
        line for line in summary_section.splitlines() if line.startswith("- ")
    )

    assert len(summary_lines) <= 8000
    assert "inactive-079" not in summary_section
    assert "## Active skills for this turn" in system_content
    assert active_body in system_content
