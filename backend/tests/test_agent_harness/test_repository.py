from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.services.agent_harness.contracts import (
    CancelCommand,
    InputTextPart,
    MessageCommand,
    NoticePayload,
    OpenSessionRequest,
    RespondCommand,
    SteerCommand,
)
from app.services.agent_harness.projection import entry_contract
from app.services.agent_harness.presentation_mutation_service import (
    AgentPresentationMutationService,
)
from app.services.agent_harness.snapshot import AgentHarnessSnapshotService
from tests.test_agent_harness.run_test_helpers import (
    agent_turn_execution_config,
    create_agent_run,
)


WORKSPACE_ID = UUID("30000000-0000-0000-0000-000000000001")

def _mutations(
    repository: AgentHarnessRepository,
) -> AgentPresentationMutationService:
    return AgentPresentationMutationService(repository)


async def _snapshot(repository: AgentHarnessRepository, session_id: str):
    return await AgentHarnessSnapshotService(repository).build(session_id)

def _message(command_id: str, text: str) -> MessageCommand:
    return MessageCommand(
        command_id=command_id,
        parts=[InputTextPart(text=text)],
    )


def _request() -> OpenSessionRequest:
    return OpenSessionRequest(
        user_id="user-1",
        workspace_id=WORKSPACE_ID,
        permission_mode="ask_dangerous",
        prompt_snapshot={"system": "stable"},
    )


@pytest.mark.asyncio
async def test_repository_opens_session_and_appends_strictly_ordered_history(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await create_agent_run(
        repository, str(session.id), model_snapshot={"model": "fake"}
    )

    first = await repository.append_entry(
        str(session.id),
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "user",
            "parts": [{"id": "part-1", "type": "text", "text": "hello"}],
        },
    )
    compaction = await repository.append_entry(
        str(session.id),
        run_id=str(run.id),
        entry_type="compaction",
        payload={"summary": "Earlier context", "through_sequence": 1},
    )
    second = await repository.append_entry(
        str(session.id),
        run_id=str(run.id),
        entry_type="notice",
        payload=NoticePayload(code="working", message="Still running").model_dump(),
    )

    assert (first.sequence, compaction.sequence, second.sequence) == (1, 2, 3)
    snapshot = await _snapshot(repository, str(session.id))
    assert [entry.type for entry in snapshot.entries] == ["message", "notice"]
    assert "history_revision" not in snapshot.model_dump(mode="json")
    assert [entry.type for entry in await repository.list_entries(str(session.id))] == [
        "message",
        "compaction",
        "notice",
    ]
    assert [item.id for item in snapshot.runs] == [run.id]
    assert snapshot.active_run is not None
    assert snapshot.active_run.run.id == run.id
    assert snapshot.active_run.assistant_draft is None


@pytest.mark.asyncio
async def test_session_setting_update_appends_private_public_safe_context_diff(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())

    updated = await repository.update_session_settings(
        str(session.id),
        model_snapshot={
            "target": {
                "provider_kind": "openai",
                "model_name": "gpt-5.6",
                "base_url": "https://private.example/v1",
                "target_revision": "secret-revision",
            }
        },
        permission_mode="full_access",
    )

    entries = await repository.list_entries(str(session.id))
    assert updated.settings_revision == 2
    assert len(entries) == 1
    assert entries[0].type == "context_update"
    assert entries[0].run_id is None
    assert entries[0].payload == {
        "settings_revision": 2,
        "changes": {
            "model": {"provider": "openai", "model": "gpt-5.6"},
            "permission_mode": "full_access",
        },
    }
    assert "private.example" not in str(entries[0].payload)
    assert "secret-revision" not in str(entries[0].payload)
    assert (await _snapshot(repository, str(session.id))).entries == []


@pytest.mark.asyncio
async def test_snapshot_projects_failed_run_error_without_private_diagnostics(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await create_agent_run(repository, str(session.id))
    await repository.update_run(str(run.id), status="running", phase="model")
    await repository.update_run(
        str(run.id),
        status="failed",
        phase=None,
        termination_reason="agent_failed",
        error={
            "code": "agent_failed",
            "message": "Provider rejected credential sk-private-value",
            "type": "ProviderCredentialError",
        },
    )

    snapshot = await _snapshot(repository, str(session.id))

    public_run = snapshot.runs[0]
    assert public_run.status == "failed"
    assert public_run.error is not None
    assert public_run.error.model_dump() == {
        "code": "agent_failed",
        "message": "The Agent run failed.",
    }
    assert "sk-private-value" not in str(snapshot.model_dump(mode="json"))
    assert "ProviderCredentialError" not in str(snapshot.model_dump(mode="json"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "private_error",
    [
        "provider returned sk-private-value",
        {
            "code": "provider_specific_failure",
            "message": "provider returned sk-private-value",
            "details": {"credential": "sk-private-value"},
        },
    ],
)
async def test_snapshot_replaces_unknown_or_malformed_run_errors(
    harness_db: AsyncSession,
    private_error: object,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await create_agent_run(repository, str(session.id))
    await repository.update_run(str(run.id), status="running", phase="model")
    await repository.update_run(
        str(run.id),
        status="failed",
        phase=None,
        termination_reason="provider_specific_failure",
        error=private_error,
    )

    snapshot = await _snapshot(repository, str(session.id))

    assert snapshot.runs[0].error is not None
    assert snapshot.runs[0].error.model_dump() == {
        "code": "agent_failed",
        "message": "The Agent run failed.",
    }
    assert "sk-private-value" not in str(snapshot.model_dump(mode="json"))
    assert "credential" not in str(snapshot.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_tool_progress_revisions_are_local_to_each_call(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await create_agent_run(repository, str(session.id))
    await repository.update_run(
        str(run.id),
        tool_progress=[
            {
                "call_id": "read-1",
                "group_id": "group-1",
                "execution_mode": "parallel",
                "name": "read",
                "display_name": "Read",
                "category": "read",
                "summary": "Read file: README.md",
                "arguments": {"path": "README.md"},
                "status": "pending",
                "revision": 0,
            },
            {
                "call_id": "read-2",
                "group_id": "group-1",
                "execution_mode": "parallel",
                "name": "read",
                "display_name": "Read",
                "category": "read",
                "summary": "Read file: RUNBOOK.md",
                "arguments": {"path": "RUNBOOK.md"},
                "status": "pending",
                "revision": 0,
            },
        ],
    )
    running = await _mutations(repository).update_tool_progress(
        str(run.id),
        call_id="read-1",
        name="read",
        status="running",
        group_id="group-1",
        execution_mode="parallel",
        arguments={"path": "README.md"},
    )
    completed = await _mutations(repository).update_tool_progress(
        str(run.id),
        call_id="read-1",
        name="read",
        status="completed",
        group_id="inconsistent-group",
        execution_mode="serial",
    )
    other = await _mutations(repository).update_tool_progress(
        str(run.id),
        call_id="read-2",
        name="read",
        status="running",
        group_id="group-1",
        execution_mode="parallel",
        arguments={"path": "RUNBOOK.md"},
    )

    assert (running.revision, completed.revision, other.revision) == (1, 2, 1)
    assert completed.group_id == "group-1"
    assert completed.execution_mode == "parallel"
    assert completed.arguments == {}
    assert completed.public_details[0].kind == "path"
    assert completed.public_details[0].value == "README.md"


@pytest.mark.asyncio
async def test_legacy_tool_progress_is_reprojected_for_snapshot_and_updates(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await create_agent_run(repository, str(session.id))
    await repository.update_run(
        str(run.id),
        status="running",
        phase="tools",
        tool_progress=[
            {
                "call_id": "bash-legacy",
                "group_id": "group-1",
                "execution_mode": "serial",
                "name": "bash",
                "display_name": "Bash",
                "category": "command",
                "summary": "Run AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE",
                "arguments": {
                    "command": "X-API-Key: sk-private-value curl file:///Users/private/a.txt"
                },
                "status": "running",
                "revision": 2,
                "public_details": [
                    {
                        "id": "command",
                        "kind": "command",
                        "value": "persisted sk-private-value",
                        "format": "code",
                        "copyable": True,
                    }
                ],
            }
        ],
    )

    snapshot = await _snapshot(repository, str(session.id))
    assert snapshot.active_run is not None
    snapshot_progress = snapshot.active_run.tool_progress[0].model_dump(mode="json")
    assert "sk-private-value" not in str(snapshot_progress)
    assert "AKIAIOSFODNN7EXAMPLE" not in str(snapshot_progress)
    assert "/Users/private" not in str(snapshot_progress)

    updated = await _mutations(repository).update_tool_progress(
        str(run.id),
        call_id="bash-legacy",
        name="bash",
        status="completed",
        output_summary="token=ghp_privatevalue1234567890\npassed",
    )
    public_update = updated.model_dump(mode="json")
    assert public_update["arguments"] == {}
    assert public_update["output_summary"] is None
    assert "private" not in str(public_update)
    assert "ghp_privatevalue" not in str(public_update)
    assert [detail["kind"] for detail in public_update["public_details"]] == ["command"]


@pytest.mark.asyncio
async def test_snapshot_is_authoritative_for_active_run_ui_state(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await create_agent_run(repository, str(session.id))
    await repository.update_run(
        str(run.id),
        status="waiting_user",
        phase="interaction",
        draft={
            "id": f"draft:{run.id}",
            "run_id": str(run.id),
            "parts": [
                {
                    "id": f"draft:{run.id}:reasoning",
                    "type": "reasoning_summary",
                    "text": "checking inputs",
                    "end_offset": 15,
                },
                {
                    "id": f"draft:{run.id}:text",
                    "type": "text",
                    "text": "partial answer",
                    "end_offset": 14,
                },
            ],
        },
        tool_progress=[
            {
                "call_id": "read-1",
                "group_id": "group-1",
                "name": "read",
                "display_name": "read",
                "category": "read",
                "summary": "Read inputs",
                "arguments": {"path": "inputs.csv"},
                "execution_mode": "serial",
                "status": "completed",
                "revision": 2,
            },
            {
                "call_id": "ask-1",
                "group_id": "group-1",
                "name": "ask_user",
                "display_name": "ask_user",
                "category": "interaction",
                "summary": "Ask how to continue",
                "arguments": {},
                "execution_mode": "serial",
                "status": "interaction_required",
                "revision": 1,
            },
        ],
    )
    await repository.append_entry(
        str(session.id),
        run_id=str(run.id),
        entry_type="interaction_request",
        payload={
            "interaction_id": "question-1",
            "request": {
                "type": "ask_user",
                "call_id": "ask-1",
                "questions": [
                    {
                        "id": "continue",
                        "header": "Continue",
                        "question": "Continue?",
                        "options": [
                            {
                                "id": "yes",
                                "label": "Yes",
                                "description": "Continue working",
                            },
                            {
                                "id": "no",
                                "label": "No",
                                "description": "Stop here",
                            },
                        ],
                    }
                ],
            },
        },
    )

    snapshot = await _snapshot(repository, str(session.id))

    assert snapshot.active_run is not None
    assert snapshot.active_run.assistant_draft is not None
    assert [part.text for part in snapshot.active_run.assistant_draft.parts] == [
        "checking inputs",
        "partial answer",
    ]
    assert [item.call_id for item in snapshot.active_run.tool_progress] == [
        "read-1",
        "ask-1",
    ]
    assert snapshot.active_run.tool_progress[1].status == "interaction_required"
    assert snapshot.active_run.pending_interaction is not None
    assert snapshot.active_run.pending_interaction.interaction_id == "question-1"
    assert (
        snapshot.active_run.pending_interaction.request.questions[0].question
        == "Continue?"
    )
    assert "checkpoint" not in snapshot.model_dump_json()

    await repository.append_entry(
        str(session.id),
        run_id=str(run.id),
        entry_type="interaction_response",
        payload={
            "interaction_id": "question-1",
            "response": {
                "type": "ask_user",
                "answers": {"choice": "continue"},
            },
        },
    )

    resumed = await _snapshot(repository, str(session.id))
    assert resumed.active_run is not None
    assert resumed.active_run.pending_interaction is None


@pytest.mark.asyncio
async def test_terminal_run_transitions_advance_the_public_revision(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    completed_run = await create_agent_run(repository, str(session.id))
    before_complete = completed_run.revision

    _, completed = await repository.commit_steers_or_complete_run(
        str(session.id),
        run_id=str(completed_run.id),
    )

    cancelled_run = await create_agent_run(repository, str(session.id))
    before_cancel = cancelled_run.revision
    _, cancelled = await repository.cancel_run_with_history(
        str(session.id),
        run_id=str(cancelled_run.id),
        reason="user_cancelled",
        tool_calls=[],
    )

    assert completed.status == "completed"
    assert completed.revision == before_complete + 1
    assert cancelled.status == "cancelled"
    assert cancelled.revision == before_cancel + 1


@pytest.mark.asyncio
async def test_repository_deduplicates_commands_and_keeps_message_durable(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await create_agent_run(repository, str(session.id))

    command = SteerCommand(
        command_id="same-command",
        parts=[InputTextPart(text="focus on tests")],
    )
    queued_run, inserted = await repository.enqueue_command(str(session.id), command)
    _, duplicated = await repository.enqueue_command(str(session.id), command)
    _, message_inserted = await repository.enqueue_command(
        str(session.id),
        _message("next-command", "summarize"),
    )

    assert queued_run is not None and queued_run.id == run.id
    assert inserted is True
    assert duplicated is False
    assert message_inserted is True
    assert [
        item["type"] for item in await repository.dequeue_commands(str(run.id))
    ] == ["steer"]
    fresh_session = await repository.get_session(str(session.id))
    assert fresh_session is not None
    assert [item["type"] for item in fresh_session.command_queue] == ["message"]


@pytest.mark.asyncio
async def test_repository_allows_only_one_active_run_per_session(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    await create_agent_run(repository, str(session.id))

    with pytest.raises(ValueError, match="active run"):
        await create_agent_run(repository, str(session.id))


@pytest.mark.asyncio
async def test_message_submission_atomically_creates_run_and_user_history(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    session_id = str(session.id)
    turn_execution_config = await agent_turn_execution_config(repository, session_id)

    run, entry, inserted = await repository.submit_user_command(
        session_id,
        _message("message-1", "hello"),
        turn_execution_config=turn_execution_config,
    )

    assert run is not None
    assert entry is not None
    assert inserted is True
    assert run.turn_execution_config == turn_execution_config
    snapshot = await _snapshot(repository, session_id)
    assert snapshot.active_run is not None
    assert snapshot.active_run.run.id == run.id
    assert snapshot.entries == [entry_contract(entry)]
    assert snapshot.entries[0].schema_version == 2
    assert snapshot.entries[0].payload.parts[0].type == "text"
    assert snapshot.entries[0].payload.parts[0].text == "hello"
    fresh_session = await repository.get_session(str(session.id))
    assert fresh_session is not None
    assert fresh_session.command_queue == []
    assert fresh_session.command_ids == ["message-1"]


@pytest.mark.asyncio
async def test_message_submission_persists_a_precomputed_conversation_title(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    session_id = str(session.id)
    turn_execution_config = await agent_turn_execution_config(repository, session_id)
    prompt = "Summarize this very long workflow request with many details"

    await repository.submit_user_command(
        session_id,
        _message("message-title", prompt),
        automatic_title="Summarize this very long",
        turn_execution_config=turn_execution_config,
    )

    snapshot = await _snapshot(repository, session_id)
    assert snapshot.session.title == "Summarize this very long"
    assert len(snapshot.entries) == 1
    assert snapshot.entries[0].payload.parts[0].text == prompt
    assert "title" not in snapshot.entries[0].payload.model_dump(mode="json")
    persisted = await repository.get_session(str(session.id))
    assert persisted is not None
    assert persisted.prompt_snapshot == {"system": "stable"}


@pytest.mark.asyncio
async def test_message_submission_preserves_an_existing_conversation_title(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(
        _request().model_copy(update={"title": "Manual title"})
    )
    session_id = str(session.id)
    turn_execution_config = await agent_turn_execution_config(repository, session_id)

    await repository.submit_user_command(
        session_id,
        _message("message-title", "Generate a different title"),
        automatic_title="Generated title",
        turn_execution_config=turn_execution_config,
    )

    snapshot = await _snapshot(repository, session_id)
    assert snapshot.session.title == "Manual title"


@pytest.mark.asyncio
async def test_first_user_message_sets_title_after_setting_changes(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    await repository.update_session_settings(
        str(session.id),
        permission_mode="full_access",
    )
    session_id = str(session.id)
    turn_execution_config = await agent_turn_execution_config(repository, session_id)

    await repository.submit_user_command(
        session_id,
        _message("message-title", "Review the configured workflow"),
        automatic_title="Review the configured workflow",
        turn_execution_config=turn_execution_config,
    )

    snapshot = await _snapshot(repository, session_id)
    assert snapshot.session.title == "Review the configured workflow"


@pytest.mark.asyncio
async def test_empty_user_text_does_not_create_a_conversation_title(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    session_id = str(session.id)
    turn_execution_config = await agent_turn_execution_config(repository, session_id)

    await repository.submit_user_command(
        session_id,
        _message("message-title", "  \n  "),
        turn_execution_config=turn_execution_config,
    )

    snapshot = await _snapshot(repository, session_id)
    assert snapshot.session.title is None


@pytest.mark.asyncio
async def test_message_submission_rolls_back_command_run_and_history_together(
    harness_db: AsyncSession,
    monkeypatch,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    session_id = str(session.id)
    turn_execution_config = await agent_turn_execution_config(repository, session_id)

    async def fail_commit() -> None:
        raise RuntimeError("simulated process loss before commit")

    monkeypatch.setattr(harness_db, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="simulated process loss"):
        await repository.submit_user_command(
            session_id,
            _message("message-1", "hello"),
            turn_execution_config=turn_execution_config,
        )

    async with factory() as verification_db:
        verification = AgentHarnessRepository(verification_db)
        stored = await verification.get_session(session_id)
        assert stored is not None
        assert stored.history_revision == 0
        assert stored.command_ids == []
        assert stored.command_queue == []
        assert await verification.get_current_run(session_id) is None
        assert await verification.list_entries(session_id) == []


@pytest.mark.asyncio
async def test_concurrent_messages_start_one_run_and_queue_the_other(
    harness_db: AsyncSession,
    monkeypatch,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    setup = AgentHarnessRepository(harness_db)
    session = await setup.open_session(_request())
    session_id = str(session.id)
    turn_execution_config = await agent_turn_execution_config(setup, session_id)

    async with factory() as first_db, factory() as second_db:
        first = AgentHarnessRepository(first_db)
        second = AgentHarnessRepository(second_db)
        _barrier_get_session(monkeypatch, first, second)
        results = await asyncio.gather(
            first.submit_user_command(
                session_id,
                _message("message-1", "first"),
                turn_execution_config=turn_execution_config,
            ),
            second.submit_user_command(
                session_id,
                _message("message-2", "second"),
                turn_execution_config=turn_execution_config,
            ),
            return_exceptions=True,
        )

    assert all(not isinstance(result, Exception) for result in results)
    assert sum(result[0] is not None for result in results) == 1
    assert sum(result[1] is not None for result in results) == 1
    assert all(result[2] is True for result in results)
    async with factory() as verification_db:
        verification = AgentHarnessRepository(verification_db)
        snapshot = await _snapshot(verification, session_id)
        assert snapshot.active_run is not None
        assert len(snapshot.runs) == 1
        assert len(snapshot.entries) == 1
        stored = await verification.get_session(session_id)
        assert stored is not None
        assert len(stored.command_queue) == 1
        assert stored.command_queue[0]["type"] == "message"
        assert len(stored.command_ids) == 2


@pytest.mark.asyncio
async def test_repository_claims_run_atomically_and_transfers_session_commands(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    await repository.enqueue_command(str(session.id), _message("message-1", "hello"))
    run = await create_agent_run(repository, str(session.id))
    moved = await repository.move_session_commands_to_run(
        str(session.id), str(run.id), kinds={"message"}
    )
    lease_until = datetime.now(timezone.utc) + timedelta(minutes=1)

    assert [command["command_id"] for command in moved] == ["message-1"]
    generation = await repository.claim_run(
        str(run.id), owner="worker-1", lease_expires_at=lease_until
    )
    assert generation == 1
    assert not await repository.claim_run(
        str(run.id), owner="worker-2", lease_expires_at=lease_until
    )

    renewed_until = lease_until + timedelta(minutes=1)
    assert await repository.renew_run_lease(
        str(run.id),
        owner="worker-1",
        generation=generation,
        lease_expires_at=renewed_until,
    )
    assert not await repository.renew_run_lease(
        str(run.id),
        owner="worker-2",
        generation=generation,
        lease_expires_at=renewed_until,
    )


@pytest.mark.asyncio
async def test_terminal_cancel_remains_visible_to_the_execution_worker(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await create_agent_run(repository, str(session.id))
    await repository.update_run(str(run.id), status="running", phase="model")

    _, cancelled = await repository.cancel_run_with_history(
        str(session.id),
        run_id=str(run.id),
        reason="user_cancelled",
        tool_calls=[],
    )

    assert cancelled.status == "cancelled"
    assert await repository.get_run_cancellation(str(run.id)) == "user_cancelled"


@pytest.mark.asyncio
async def test_cancel_history_rejects_a_non_owner_worker(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await create_agent_run(repository, str(session.id))
    run_id = str(run.id)
    generation = await repository.claim_run(
        run_id,
        owner="owner-worker",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    assert generation is not None

    with pytest.raises(ValueError, match="stale Agent run fence"):
        await repository.cancel_run_with_history(
            str(session.id),
            run_id=run_id,
            reason="user_cancelled",
            tool_calls=[],
        )

    stored = await repository.get_run(run_id)
    assert stored is not None
    assert stored.status == "queued"


@pytest.mark.asyncio
async def test_new_lease_generation_fences_stale_worker_writes(
    harness_db: AsyncSession,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with factory() as first_db, factory() as second_db:
        first = AgentHarnessRepository(first_db)
        second = AgentHarnessRepository(second_db)
        session = await first.open_session(_request())
        run = await create_agent_run(first, str(session.id))
        first_generation = await first.claim_run(
            str(run.id),
            owner="worker-1",
            lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        assert first_generation == 1
        first.bind_run_fence(str(run.id), owner="worker-1", generation=first_generation)

        second_generation = await second.claim_run(
            str(run.id),
            owner="worker-2",
            lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        )
        assert second_generation == 2
        second.bind_run_fence(
            str(run.id), owner="worker-2", generation=second_generation
        )

        with pytest.raises(ValueError, match="terminal Agent run"):
            await first.update_run(str(run.id), status="running", phase="model")
        with pytest.raises(ValueError, match="stale fence"):
            await first.append_entry(
                str(session.id),
                run_id=str(run.id),
                entry_type="message",
                payload={
                    "role": "assistant",
                    "parts": [{"id": "text:0", "type": "text", "text": "stale"}],
                },
            )

        updated = await second.update_run(str(run.id), status="running", phase="model")
        assert updated.lease_generation == 2


@pytest.mark.asyncio
async def test_new_lease_generation_fences_stale_worker_terminalization(
    harness_db: AsyncSession,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with factory() as first_db, factory() as second_db:
        first = AgentHarnessRepository(first_db)
        second = AgentHarnessRepository(second_db)
        session = await first.open_session(_request())
        run = await create_agent_run(first, str(session.id))
        first_generation = await first.claim_run(
            str(run.id),
            owner="worker-1",
            lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        assert first_generation == 1
        first.bind_run_fence(str(run.id), owner="worker-1", generation=first_generation)

        second_generation = await second.claim_run(
            str(run.id),
            owner="worker-2",
            lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        )
        assert second_generation == 2
        second.bind_run_fence(
            str(run.id), owner="worker-2", generation=second_generation
        )

        with pytest.raises(ValueError, match="stale Agent run fence"):
            await first.terminalize_run(
                str(run.id),
                status="completed",
                phase=None,
                termination_reason="completed",
            )

        active = await second.get_run(str(run.id))
        assert active is not None
        assert active.status == "queued"
        assert active.lease_owner == "worker-2"
        assert active.lease_generation == 2

        completed = await second.terminalize_run(
            str(run.id),
            status="completed",
            phase=None,
            termination_reason="completed",
        )
        assert completed.status == "completed"


@pytest.mark.asyncio
async def test_terminal_run_cannot_be_reactivated_by_stale_worker(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await create_agent_run(repository, str(session.id))
    await repository.update_run(
        str(run.id),
        status="cancelled",
        phase=None,
        termination_reason="user_cancelled",
    )

    with pytest.raises(ValueError, match="terminal Agent run"):
        await repository.update_run(str(run.id), status="running", phase="model")

    stored = await repository.get_run(str(run.id))
    assert stored is not None
    assert stored.status == "cancelled"
    assert stored.termination_reason == "user_cancelled"

    with pytest.raises(ValueError, match="terminal Agent run"):
        await repository.update_run(
            str(run.id),
            status="cancelled",
            termination_reason="stale_cancel",
        )

    stored = await repository.get_run(str(run.id))
    assert stored is not None
    assert stored.termination_reason == "user_cancelled"


@pytest.mark.asyncio
async def test_terminal_fence_rejects_worker_with_stale_identity_map(
    harness_db: AsyncSession,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with factory() as worker_db, factory() as command_db:
        worker = AgentHarnessRepository(worker_db)
        command = AgentHarnessRepository(command_db)
        session = await worker.open_session(_request())
        run = await create_agent_run(worker, str(session.id))
        await worker.update_run(str(run.id), status="running", phase="model")
        assert (await worker.get_run(str(run.id))).status == "running"

        await command.update_run(
            str(run.id),
            status="cancelled",
            phase=None,
            termination_reason="user_cancelled",
        )

        with pytest.raises(ValueError, match="terminal Agent run"):
            await worker.update_run(
                str(run.id),
                status="running",
                phase="tools",
                draft={
                    "id": f"draft:{run.id}",
                    "run_id": str(run.id),
                    "parts": [
                        {
                            "id": f"draft:{run.id}:text",
                            "type": "text",
                            "text": "stale",
                            "end_offset": 5,
                        }
                    ],
                },
            )

        stored = await command.get_run(str(run.id))
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.termination_reason == "user_cancelled"
        assert stored.draft is None


@pytest.mark.asyncio
async def test_terminal_fence_rejects_stale_history_append(
    harness_db: AsyncSession,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with factory() as worker_db, factory() as command_db:
        worker = AgentHarnessRepository(worker_db)
        command = AgentHarnessRepository(command_db)
        session = await worker.open_session(_request())
        run = await create_agent_run(worker, str(session.id))
        await worker.update_run(str(run.id), status="running", phase="model")
        assert (await worker.get_run(str(run.id))).status == "running"

        await command.update_run(
            str(run.id),
            status="cancelled",
            phase=None,
            termination_reason="user_cancelled",
        )

        with pytest.raises(ValueError, match="terminal Agent run"):
            await worker.append_entry(
                str(session.id),
                run_id=str(run.id),
                entry_type="message",
                payload={
                    "role": "assistant",
                    "parts": [{"id": "text:0", "type": "text", "text": "stale"}],
                },
            )

        assert await command.list_entries(str(session.id)) == []


@pytest.mark.asyncio
async def test_waiting_interaction_rolls_back_history_and_run_state_together(
    harness_db: AsyncSession,
    monkeypatch,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await create_agent_run(repository, str(session.id))
    generation = await repository.claim_run(
        str(run.id),
        owner="worker-1",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    assert generation is not None
    repository.bind_run_fence(str(run.id), owner="worker-1", generation=generation)
    run_id = str(run.id)
    session_id = str(session.id)

    async def fail_commit():
        raise RuntimeError("simulated process loss before commit")

    monkeypatch.setattr(harness_db, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="simulated process loss"):
        await _mutations(repository).commit_waiting_interaction(
            session_id,
            run_id=run_id,
            notice_payload={
                "code": "unknown_tool_effect",
                "message": "unknown",
                "details": {"interaction_id": "recovery:bash-1"},
            },
            request_payload={
                "interaction_id": "recovery:bash-1",
                "request": {"kind": "recovery"},
            },
            checkpoint={"phase": "interaction"},
            tool_progress=[
                {
                    "call_id": "bash-1",
                    "name": "bash",
                    "status": "interaction_required",
                }
            ],
        )

    async with factory() as verification_db:
        verification = AgentHarnessRepository(verification_db)
        stored = await verification.get_run(run_id)
        assert stored is not None
        assert stored.status == "queued"
        assert stored.checkpoint is None
        assert await verification.list_entries(session_id) == []


@pytest.mark.asyncio
async def test_waiting_interaction_advances_the_public_run_revision(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await create_agent_run(repository, str(session.id))
    before_waiting = run.revision

    _, _, waiting = await _mutations(repository).commit_waiting_interaction(
        str(session.id),
        run_id=str(run.id),
        request_payload={
            "interaction_id": "question-1",
            "request": {
                "kind": "question",
                "call_id": "ask-1",
                "questions": [
                    {
                        "id": "choice",
                        "header": "Choose",
                        "question": "Continue?",
                        "options": [
                            {"id": "yes", "label": "Yes"},
                            {"id": "no", "label": "No"},
                        ],
                    }
                ],
            },
        },
        checkpoint={"phase": "interaction"},
        tool_progress=[
            {
                "call_id": "ask-1",
                "group_id": "group-1",
                "execution_mode": "serial",
                "name": "ask_user",
                "display_name": "ask_user",
                "category": "interaction",
                "summary": "Ask user",
                "arguments": {},
                "status": "interaction_required",
                "revision": 1,
            }
        ],
    )

    assert waiting.status == "waiting_user"
    assert waiting.phase == "interaction"
    assert waiting.revision == before_waiting + 1


@pytest.mark.asyncio
async def test_respond_ack_rolls_back_with_interaction_response_history(
    harness_db: AsyncSession,
    monkeypatch,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await create_agent_run(repository, str(session.id))
    session_id = str(session.id)
    run_id = str(run.id)
    await repository.update_run(
        run_id,
        status="waiting_user",
        phase="interaction",
    )
    await repository.enqueue_command(
        session_id,
        RespondCommand(
            command_id="answer-1",
            interaction_id="tool:ask-1",
            response={"type": "ask_user", "answers": {"Continue?": "Yes"}},
        ),
    )
    generation = await repository.claim_run(
        run_id,
        owner="worker-1",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    assert generation is not None
    repository.bind_run_fence(run_id, owner="worker-1", generation=generation)

    async def fail_commit():
        raise RuntimeError("simulated process loss before response commit")

    monkeypatch.setattr(harness_db, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="before response commit"):
        await _mutations(repository).commit_interaction_response(
            session_id,
            run_id=run_id,
            command_id="answer-1",
            interaction_id="tool:ask-1",
            response={"type": "ask_user", "answers": {"Continue?": "Yes"}},
        )

    async with factory() as verification_db:
        verification = AgentHarnessRepository(verification_db)
        stored = await verification.get_run(run_id)
        assert stored is not None
        assert [item["command_id"] for item in stored.command_queue] == ["answer-1"]
        assert [
            entry
            for entry in await verification.list_entries(session_id)
            if entry.type == "interaction_response"
        ] == []


@pytest.mark.asyncio
async def test_approved_bash_ack_rolls_back_with_the_execution_fence(
    harness_db: AsyncSession,
    monkeypatch,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await create_agent_run(repository, str(session.id))
    session_id = str(session.id)
    run_id = str(run.id)
    call = {
        "call_id": "bash-1",
        "name": "bash",
        "arguments": {"command": "printf safe"},
    }
    durable_call = {
        **call,
        "group_id": "assistant-entry-1",
        "execution_mode": "serial",
    }
    await repository.update_run(
        run_id,
        status="waiting_user",
        phase="interaction",
        checkpoint={
            "phase": "interaction",
            "history_revision": 0,
            "in_flight_tools": [{**durable_call, "replay_policy": "never"}],
            "waiting_call": durable_call,
        },
        tool_progress=[
            {
                "call_id": "bash-1",
                "group_id": "assistant-entry-1",
                "execution_mode": "serial",
                "name": "bash",
                "display_name": "Bash",
                "category": "command",
                "summary": "Run command",
                "arguments": {"command": "printf safe"},
                "status": "interaction_required",
                "revision": 1,
            }
        ],
    )
    await repository.enqueue_command(
        session_id,
        RespondCommand(
            command_id="approve-1",
            interaction_id="tool:bash-1",
            response={"type": "approval", "approved": True},
        ),
    )
    generation = await repository.claim_run(
        run_id,
        owner="worker-1",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    assert generation is not None
    repository.bind_run_fence(run_id, owner="worker-1", generation=generation)

    async def fail_commit():
        raise RuntimeError("simulated process loss before approval fence commit")

    monkeypatch.setattr(harness_db, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="before approval fence commit"):
        await _mutations(repository).begin_approved_tool_execution(
            session_id,
            run_id=run_id,
            interaction_id="tool:bash-1",
            response={"type": "approval", "approved": True},
            call=call,
            replay_policy="never",
            command_id="approve-1",
        )

    async with factory() as verification_db:
        verification = AgentHarnessRepository(verification_db)
        stored = await verification.get_run(run_id)
        assert stored is not None
        assert stored.status == "waiting_user"
        assert [item["command_id"] for item in stored.command_queue] == ["approve-1"]
        assert stored.checkpoint["in_flight_tools"] == [
            {**durable_call, "replay_policy": "never"}
        ]
        assert [
            entry
            for entry in await verification.list_entries(session_id)
            if entry.type == "interaction_response"
        ] == []


@pytest.mark.asyncio
async def test_approved_tool_execution_preserves_complete_progress_in_snapshot(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await create_agent_run(repository, str(session.id))
    session_id = str(session.id)
    run_id = str(run.id)
    call = {
        "call_id": "bash-1",
        "name": "bash",
        "arguments": {"command": "printf safe"},
    }
    await repository.update_run(
        run_id,
        status="waiting_user",
        phase="interaction",
        checkpoint={
            "phase": "interaction",
            "history_revision": 0,
            "in_flight_tools": [{**call, "replay_policy": "never"}],
            "waiting_call": call,
        },
        tool_progress=[
            {
                "call_id": "bash-1",
                "group_id": "group-1",
                "execution_mode": "serial",
                "name": "bash",
                "display_name": "bash",
                "category": "command",
                "summary": "Run printf safe",
                "arguments": {"command": "printf safe"},
                "status": "interaction_required",
                "revision": 1,
            }
        ],
    )
    await repository.enqueue_command(
        session_id,
        RespondCommand(
            command_id="approve-1",
            interaction_id="tool:bash-1",
            response={"type": "approval", "approved": True},
        ),
    )

    await _mutations(repository).begin_approved_tool_execution(
        session_id,
        run_id=run_id,
        interaction_id="tool:bash-1",
        response={"type": "approval", "approved": True},
        call=call,
        replay_policy="never",
        command_id="approve-1",
    )

    snapshot = await _snapshot(repository, session_id)
    assert snapshot.active_run is not None
    progress = snapshot.active_run.tool_progress[0]
    assert snapshot.active_run.run.revision == 2
    assert progress.status == "running"
    assert progress.revision == 2
    assert progress.group_id == "group-1"
    assert progress.arguments == {}
    assert progress.public_details[0].kind == "command"
    assert progress.public_details[0].value == "printf safe"


@pytest.mark.asyncio
async def test_respond_ack_preserves_a_command_enqueued_after_the_worker_peek(
    harness_db: AsyncSession,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    setup = AgentHarnessRepository(harness_db)
    session = await setup.open_session(_request())
    run = await create_agent_run(setup, str(session.id))
    session_id = str(session.id)
    run_id = str(run.id)
    await setup.update_run(run_id, status="waiting_user", phase="interaction")
    await setup.enqueue_command(
        session_id,
        RespondCommand(
            command_id="answer-1",
            interaction_id="tool:ask-1",
            response={"type": "ask_user", "answers": {"Continue?": "Yes"}},
        ),
    )
    generation = await setup.claim_run(
        run_id,
        owner="worker-1",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    assert generation is not None

    async with factory() as worker_db, factory() as external_db:
        worker = AgentHarnessRepository(worker_db)
        worker.bind_run_fence(run_id, owner="worker-1", generation=generation)
        external = AgentHarnessRepository(external_db)
        assert [
            item["command_id"]
            for item in await worker.peek_commands(run_id, kinds={"respond"})
        ] == ["answer-1"]
        await external.enqueue_command(
            session_id,
            SteerCommand(
                command_id="steer-after-peek",
                parts=[InputTextPart(text="Keep this input.")],
            ),
        )
        await _mutations(worker).commit_interaction_response(
            session_id,
            run_id=run_id,
            command_id="answer-1",
            interaction_id="tool:ask-1",
            response={"type": "ask_user", "answers": {"Continue?": "Yes"}},
        )

    stored = await setup.get_run(run_id)
    assert stored is not None
    await harness_db.refresh(stored)
    assert [item["command_id"] for item in stored.command_queue] == ["steer-after-peek"]


@pytest.mark.asyncio
async def test_concurrent_different_commands_are_both_preserved(
    harness_db: AsyncSession,
    monkeypatch,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        harness_db.bind, expire_on_commit=False, class_=AsyncSession
    )
    setup = AgentHarnessRepository(harness_db)
    session = await setup.open_session(_request())
    run = await create_agent_run(setup, str(session.id))
    session_id = str(session.id)
    run_id = str(run.id)
    async with factory() as first_db, factory() as second_db:
        first = AgentHarnessRepository(first_db)
        second = AgentHarnessRepository(second_db)
        _barrier_get_current(monkeypatch, first, second)
        await asyncio.gather(
            first.enqueue_command(
                session_id,
                SteerCommand(command_id="steer-1", parts=[InputTextPart(text="first")]),
            ),
            second.enqueue_command(
                session_id,
                SteerCommand(
                    command_id="steer-2", parts=[InputTextPart(text="second")]
                ),
            ),
        )

    stored = await setup.get_run(run_id)
    assert stored is not None
    await harness_db.refresh(stored)
    assert {item["command_id"] for item in stored.command_queue} == {
        "steer-1",
        "steer-2",
    }


@pytest.mark.asyncio
async def test_concurrent_same_command_id_is_inserted_once(
    harness_db: AsyncSession,
    monkeypatch,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        harness_db.bind, expire_on_commit=False, class_=AsyncSession
    )
    setup = AgentHarnessRepository(harness_db)
    session = await setup.open_session(_request())
    run = await create_agent_run(setup, str(session.id))
    session_id = str(session.id)
    run_id = str(run.id)
    async with factory() as first_db, factory() as second_db:
        first = AgentHarnessRepository(first_db)
        second = AgentHarnessRepository(second_db)
        _barrier_get_current(monkeypatch, first, second)
        results = await asyncio.gather(
            first.enqueue_command(
                session_id,
                SteerCommand(command_id="same", parts=[InputTextPart(text="first")]),
            ),
            second.enqueue_command(
                session_id,
                SteerCommand(command_id="same", parts=[InputTextPart(text="second")]),
            ),
        )

    stored = await setup.get_run(run_id)
    assert stored is not None
    await harness_db.refresh(stored)
    assert sorted(inserted for _, inserted in results) == [False, True]
    assert [item["command_id"] for item in stored.command_queue] == ["same"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    [
        SteerCommand(command_id="new", parts=[InputTextPart(text="steer")]),
        RespondCommand(
            command_id="new",
            interaction_id="tool:ask-1",
            response={"type": "ask_user", "answers": {}},
        ),
        CancelCommand(command_id="new", reason="stop"),
    ],
)
async def test_worker_dequeue_and_external_command_cannot_overwrite_each_other(
    harness_db: AsyncSession,
    monkeypatch,
    command,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        harness_db.bind, expire_on_commit=False, class_=AsyncSession
    )
    setup = AgentHarnessRepository(harness_db)
    session = await setup.open_session(_request())
    run = await create_agent_run(setup, str(session.id))
    session_id = str(session.id)
    run_id = str(run.id)
    await setup.enqueue_command(
        session_id,
        SteerCommand(command_id="old", parts=[InputTextPart(text="already queued")]),
    )
    generation = await setup.claim_run(
        run_id,
        owner="worker",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    assert generation is not None

    async with factory() as worker_db, factory() as external_db:
        worker = AgentHarnessRepository(worker_db)
        worker.bind_run_fence(run_id, owner="worker", generation=generation)
        external = AgentHarnessRepository(external_db)
        _barrier_worker_and_external(monkeypatch, worker, external)
        consumed, _ = await asyncio.gather(
            worker.dequeue_commands(run_id, kinds={"steer", "respond", "cancel"}),
            external.enqueue_command(session_id, command),
        )

    stored = await setup.get_run(run_id)
    assert stored is not None
    await harness_db.refresh(stored)
    observed = [item["command_id"] for item in consumed] + [
        item["command_id"] for item in stored.command_queue
    ]
    assert sorted(observed) == ["new", "old"]


@pytest.mark.asyncio
async def test_concurrent_message_start_consumes_only_one_command(
    harness_db: AsyncSession,
    monkeypatch,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        harness_db.bind, expire_on_commit=False, class_=AsyncSession
    )
    setup = AgentHarnessRepository(harness_db)
    session = await setup.open_session(_request())
    session_id = str(session.id)
    await setup.enqueue_command(session_id, _message("message-1", "first"))
    await setup.enqueue_command(session_id, _message("message-2", "second"))
    turn_execution_config = await agent_turn_execution_config(setup, session_id)

    async with factory() as first_db, factory() as second_db:
        first = AgentHarnessRepository(first_db)
        second = AgentHarnessRepository(second_db)
        _barrier_get_session(monkeypatch, first, second)
        results = await asyncio.gather(
            first.create_run_from_next_session_command(
                session_id,
                kind="message",
                turn_execution_config=turn_execution_config,
            ),
            second.create_run_from_next_session_command(
                session_id,
                kind="message",
                turn_execution_config=turn_execution_config,
            ),
        )

    assert sum(result is not None for result in results) == 1
    stored_session = await setup.get_session(session_id)
    assert stored_session is not None
    await harness_db.refresh(stored_session)
    assert [item["command_id"] for item in stored_session.command_queue] == [
        "message-2"
    ]
    assert await setup.get_current_run(session_id) is not None
    await harness_db.refresh(stored_session)
    assert stored_session.history_revision == 1
    entries = await setup.list_entries(session_id)
    assert len(entries) == 1
    assert entries[0].payload["parts"] == [
        {"id": "input:message-1:0", "type": "text", "text": "first"}
    ]


@pytest.mark.asyncio
async def test_message_start_rolls_back_queue_run_and_history_together(
    harness_db: AsyncSession,
    monkeypatch,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    session_id = str(session.id)
    active = await create_agent_run(repository, session_id)
    await repository.enqueue_command(
        session_id,
        _message("message-1", "next"),
    )
    await repository.update_run(str(active.id), status="completed")
    turn_execution_config = await agent_turn_execution_config(repository, session_id)

    async def fail_commit() -> None:
        raise RuntimeError("simulated process loss before commit")

    monkeypatch.setattr(harness_db, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="simulated process loss"):
        await repository.create_run_from_next_session_command(
            session_id,
            kind="message",
            turn_execution_config=turn_execution_config,
        )

    async with factory() as verification_db:
        verification = AgentHarnessRepository(verification_db)
        stored = await verification.get_session(session_id)
        assert stored is not None
        assert stored.history_revision == 0
        assert [item["command_id"] for item in stored.command_queue] == ["message-1"]
        assert await verification.get_current_run(session_id) is None
        assert await verification.list_entries(session_id) == []


def _barrier_get_current(monkeypatch, first, second) -> None:
    first_ready = asyncio.Event()
    second_ready = asyncio.Event()
    first_get = first.get_current_run
    second_get = second.get_current_run

    async def blocked_first(session_id):
        run = await first_get(session_id)
        first_ready.set()
        await second_ready.wait()
        return run

    async def blocked_second(session_id):
        run = await second_get(session_id)
        second_ready.set()
        await first_ready.wait()
        return run

    monkeypatch.setattr(first, "get_current_run", blocked_first)
    monkeypatch.setattr(second, "get_current_run", blocked_second)


def _barrier_worker_and_external(monkeypatch, worker, external) -> None:
    worker_ready = asyncio.Event()
    external_ready = asyncio.Event()
    worker_get = worker.get_run
    external_get = external.get_current_run

    async def blocked_worker(run_id):
        run = await worker_get(run_id)
        worker_ready.set()
        await external_ready.wait()
        return run

    async def blocked_external(session_id):
        run = await external_get(session_id)
        external_ready.set()
        await worker_ready.wait()
        return run

    monkeypatch.setattr(worker, "get_run", blocked_worker)
    monkeypatch.setattr(external, "get_current_run", blocked_external)


def _barrier_get_session(monkeypatch, first, second) -> None:
    first_ready = asyncio.Event()
    second_ready = asyncio.Event()
    first_get = first.get_session
    second_get = second.get_session

    async def blocked_first(session_id):
        session = await first_get(session_id)
        first_ready.set()
        await second_ready.wait()
        return session

    async def blocked_second(session_id):
        session = await second_get(session_id)
        second_ready.set()
        await first_ready.wait()
        return session

    monkeypatch.setattr(first, "get_session", blocked_first)
    monkeypatch.setattr(second, "get_session", blocked_second)


@pytest.mark.asyncio
async def test_snapshot_keeps_latest_completed_run_and_delete_cascades(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await create_agent_run(repository, str(session.id))
    await repository.update_run(str(run.id), status="completed")

    snapshot = await _snapshot(repository, str(session.id))
    assert snapshot.active_run is None
    assert len(snapshot.runs) == 1
    assert snapshot.runs[0].status == "completed"
    assert await repository.delete_session(str(session.id)) is True
    assert await repository.get_run(str(run.id)) is None


@pytest.mark.asyncio
async def test_repository_lists_only_runs_that_need_recovery(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    first = await repository.open_session(_request())
    second = await repository.open_session(_request())
    active = await create_agent_run(repository, str(first.id))
    terminal = await create_agent_run(repository, str(second.id))
    await repository.update_run(str(active.id), status="running", phase="model")
    await repository.update_run(str(terminal.id), status="completed")

    runs = await repository.list_recoverable_runs()

    assert [run.id for run in runs] == [active.id]
