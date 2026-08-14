from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.services.agent_harness.contracts import (
    CancelCommand,
    FollowUpCommand,
    NoticePayload,
    OpenSessionRequest,
    PromptCommand,
    RespondCommand,
    SteerCommand,
)


WORKSPACE_ID = UUID("30000000-0000-0000-0000-000000000001")


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
    run = await repository.create_run(str(session.id), model_snapshot={"model": "fake"})

    first = await repository.append_entry(
        str(session.id),
        run_id=str(run.id),
        entry_type="message",
        payload={"role": "user", "content": [{"type": "text", "text": "hello"}]},
    )
    second = await repository.append_entry(
        str(session.id),
        run_id=str(run.id),
        entry_type="notice",
        payload=NoticePayload(code="working", message="Still running").model_dump(),
    )

    assert (first.sequence, second.sequence) == (1, 2)
    snapshot = await repository.snapshot(str(session.id))
    assert snapshot.revision == 2
    assert [entry.type for entry in snapshot.entries] == ["message", "notice"]
    assert snapshot.current_run is not None
    assert snapshot.current_run.id == run.id


@pytest.mark.asyncio
async def test_snapshot_is_authoritative_for_active_run_ui_state(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await repository.create_run(str(session.id))
    await repository.update_run(
        str(run.id),
        status="waiting_user",
        phase="interaction",
        draft={"text": "partial answer", "reasoning": "checking inputs"},
        tool_progress=[
            {"call_id": "read-1", "name": "read", "status": "completed"},
            {
                "call_id": "ask-1",
                "name": "ask_user",
                "status": "interaction_required",
            },
        ],
    )
    await repository.append_entry(
        str(session.id),
        run_id=str(run.id),
        entry_type="interaction_request",
        payload={
            "interaction_id": "question-1",
            "request": {"kind": "question", "questions": [{"question": "Continue?"}]},
        },
    )

    snapshot = await repository.snapshot(str(session.id))

    assert snapshot.assistant_draft is not None
    assert snapshot.assistant_draft.text == "partial answer"
    assert snapshot.assistant_draft.reasoning_summary == "checking inputs"
    assert [item.call_id for item in snapshot.tool_progress] == ["read-1", "ask-1"]
    assert snapshot.tool_progress[1].status == "interaction_required"
    assert snapshot.pending_interaction is not None
    assert snapshot.pending_interaction.interaction_id == "question-1"
    assert (
        snapshot.pending_interaction.request["questions"][0]["question"] == "Continue?"
    )
    assert "checkpoint" not in snapshot.model_dump_json()

    await repository.append_entry(
        str(session.id),
        run_id=str(run.id),
        entry_type="interaction_response",
        payload={
            "interaction_id": "question-1",
            "response": {"choice": "continue"},
        },
    )

    resumed = await repository.snapshot(str(session.id))
    assert resumed.pending_interaction is None


@pytest.mark.asyncio
async def test_repository_deduplicates_commands_and_keeps_follow_up_durable(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await repository.create_run(str(session.id))

    command = SteerCommand(command_id="same-command", text="focus on tests")
    queued_run, inserted = await repository.enqueue_command(str(session.id), command)
    _, duplicated = await repository.enqueue_command(str(session.id), command)
    _, follow_up_inserted = await repository.enqueue_command(
        str(session.id),
        FollowUpCommand(command_id="next-command", text="summarize"),
    )

    assert queued_run is not None and queued_run.id == run.id
    assert inserted is True
    assert duplicated is False
    assert follow_up_inserted is True
    assert [
        item["type"] for item in await repository.dequeue_commands(str(run.id))
    ] == ["steer"]
    fresh_session = await repository.get_session(str(session.id))
    assert fresh_session is not None
    assert [item["type"] for item in fresh_session.command_queue] == ["follow_up"]


@pytest.mark.asyncio
async def test_repository_allows_only_one_active_run_per_session(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    await repository.create_run(str(session.id))

    with pytest.raises(ValueError, match="active run"):
        await repository.create_run(str(session.id))


@pytest.mark.asyncio
async def test_prompt_submission_atomically_creates_run_and_user_history(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())

    run, entry, inserted = await repository.submit_user_command(
        str(session.id), PromptCommand(command_id="prompt-1", text="hello")
    )

    assert run is not None
    assert entry is not None
    assert inserted is True
    snapshot = await repository.snapshot(str(session.id))
    assert snapshot.current_run is not None
    assert snapshot.current_run.id == run.id
    assert snapshot.revision == 1
    assert snapshot.entries == [repository._entry_contract(entry)]
    assert snapshot.entries[0].payload.content == [{"type": "text", "text": "hello"}]
    fresh_session = await repository.get_session(str(session.id))
    assert fresh_session is not None
    assert fresh_session.command_queue == []
    assert fresh_session.command_ids == ["prompt-1"]


@pytest.mark.asyncio
async def test_prompt_submission_rolls_back_command_run_and_history_together(
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

    async def fail_commit() -> None:
        raise RuntimeError("simulated process loss before commit")

    monkeypatch.setattr(harness_db, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="simulated process loss"):
        await repository.submit_user_command(
            session_id,
            PromptCommand(command_id="prompt-1", text="hello"),
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
async def test_concurrent_prompts_publish_only_one_complete_run(
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

    async with factory() as first_db, factory() as second_db:
        first = AgentHarnessRepository(first_db)
        second = AgentHarnessRepository(second_db)
        _barrier_get_session(monkeypatch, first, second)
        results = await asyncio.gather(
            first.submit_user_command(
                session_id,
                PromptCommand(command_id="prompt-1", text="first"),
            ),
            second.submit_user_command(
                session_id,
                PromptCommand(command_id="prompt-2", text="second"),
            ),
            return_exceptions=True,
        )

    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert (
        sum(
            isinstance(result, ValueError) and "active run" in str(result)
            for result in results
        )
        == 1
    )
    async with factory() as verification_db:
        verification = AgentHarnessRepository(verification_db)
        snapshot = await verification.snapshot(session_id)
        assert snapshot.current_run is not None
        assert snapshot.revision == 1
        assert len(snapshot.entries) == 1
        stored = await verification.get_session(session_id)
        assert stored is not None
        assert stored.command_queue == []
        assert len(stored.command_ids) == 1


@pytest.mark.asyncio
async def test_repository_claims_run_atomically_and_transfers_session_commands(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    await repository.enqueue_command(
        str(session.id), PromptCommand(command_id="prompt-1", text="hello")
    )
    run = await repository.create_run(str(session.id))
    moved = await repository.move_session_commands_to_run(
        str(session.id), str(run.id), kinds={"prompt"}
    )
    lease_until = datetime.now(timezone.utc) + timedelta(minutes=1)

    assert [command["command_id"] for command in moved] == ["prompt-1"]
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
    run = await repository.create_run(str(session.id))
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
    run = await repository.create_run(str(session.id))
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
        run = await first.create_run(str(session.id))
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
                    "content": [{"type": "text", "text": "stale"}],
                    "tool_calls": [],
                    "artifact_ids": [],
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
        run = await first.create_run(str(session.id))
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
    run = await repository.create_run(str(session.id))
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
        run = await worker.create_run(str(session.id))
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
                draft={"text": "stale"},
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
        run = await worker.create_run(str(session.id))
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
                    "content": [{"type": "text", "text": "stale"}],
                    "tool_calls": [],
                    "artifact_ids": [],
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
    run = await repository.create_run(str(session.id))
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
        await repository.commit_waiting_interaction(
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
    run = await repository.create_run(str(session.id))
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
            response={"answers": {"Continue?": "Yes"}},
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
        await repository.commit_interaction_response(
            session_id,
            run_id=run_id,
            command_id="answer-1",
            interaction_id="tool:ask-1",
            response={"answers": {"Continue?": "Yes"}},
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
    run = await repository.create_run(str(session.id))
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
    )
    await repository.enqueue_command(
        session_id,
        RespondCommand(
            command_id="approve-1",
            interaction_id="tool:bash-1",
            response={"approved": True},
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
        await repository.begin_approved_tool_execution(
            session_id,
            run_id=run_id,
            interaction_id="tool:bash-1",
            response={"request_id": "tool:bash-1", "approved": True},
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
            {**call, "replay_policy": "never"}
        ]
        assert [
            entry
            for entry in await verification.list_entries(session_id)
            if entry.type == "interaction_response"
        ] == []


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
    run = await setup.create_run(str(session.id))
    session_id = str(session.id)
    run_id = str(run.id)
    await setup.update_run(run_id, status="waiting_user", phase="interaction")
    await setup.enqueue_command(
        session_id,
        RespondCommand(
            command_id="answer-1",
            interaction_id="tool:ask-1",
            response={"answers": {"Continue?": "Yes"}},
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
            SteerCommand(command_id="steer-after-peek", text="Keep this input."),
        )
        await worker.commit_interaction_response(
            session_id,
            run_id=run_id,
            command_id="answer-1",
            interaction_id="tool:ask-1",
            response={"answers": {"Continue?": "Yes"}},
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
    run = await setup.create_run(str(session.id))
    session_id = str(session.id)
    run_id = str(run.id)
    async with factory() as first_db, factory() as second_db:
        first = AgentHarnessRepository(first_db)
        second = AgentHarnessRepository(second_db)
        _barrier_get_current(monkeypatch, first, second)
        await asyncio.gather(
            first.enqueue_command(
                session_id, SteerCommand(command_id="steer-1", text="first")
            ),
            second.enqueue_command(
                session_id, SteerCommand(command_id="steer-2", text="second")
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
    run = await setup.create_run(str(session.id))
    session_id = str(session.id)
    run_id = str(run.id)
    async with factory() as first_db, factory() as second_db:
        first = AgentHarnessRepository(first_db)
        second = AgentHarnessRepository(second_db)
        _barrier_get_current(monkeypatch, first, second)
        results = await asyncio.gather(
            first.enqueue_command(
                session_id, SteerCommand(command_id="same", text="first")
            ),
            second.enqueue_command(
                session_id, SteerCommand(command_id="same", text="second")
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
        SteerCommand(command_id="new", text="steer"),
        RespondCommand(
            command_id="new", interaction_id="tool:ask-1", response={"answers": {}}
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
    run = await setup.create_run(str(session.id))
    session_id = str(session.id)
    run_id = str(run.id)
    await setup.enqueue_command(
        session_id, SteerCommand(command_id="old", text="already queued")
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
async def test_concurrent_follow_up_start_consumes_only_one_command(
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
    await setup.enqueue_command(
        session_id, FollowUpCommand(command_id="follow-1", text="first")
    )
    await setup.enqueue_command(
        session_id, FollowUpCommand(command_id="follow-2", text="second")
    )

    async with factory() as first_db, factory() as second_db:
        first = AgentHarnessRepository(first_db)
        second = AgentHarnessRepository(second_db)
        _barrier_get_session(monkeypatch, first, second)
        results = await asyncio.gather(
            first.create_run_from_next_session_command(session_id, kind="follow_up"),
            second.create_run_from_next_session_command(session_id, kind="follow_up"),
        )

    assert sum(result is not None for result in results) == 1
    stored_session = await setup.get_session(session_id)
    assert stored_session is not None
    await harness_db.refresh(stored_session)
    assert [item["command_id"] for item in stored_session.command_queue] == ["follow-2"]
    assert await setup.get_current_run(session_id) is not None
    await harness_db.refresh(stored_session)
    assert stored_session.history_revision == 1
    entries = await setup.list_entries(session_id)
    assert len(entries) == 1
    assert entries[0].payload["content"] == [{"type": "text", "text": "first"}]


@pytest.mark.asyncio
async def test_follow_up_start_rolls_back_queue_run_and_history_together(
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
    active = await repository.create_run(session_id)
    await repository.enqueue_command(
        session_id,
        FollowUpCommand(command_id="follow-1", text="next"),
    )
    await repository.update_run(str(active.id), status="completed")

    async def fail_commit() -> None:
        raise RuntimeError("simulated process loss before commit")

    monkeypatch.setattr(harness_db, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="simulated process loss"):
        await repository.create_run_from_next_session_command(
            session_id,
            kind="follow_up",
        )

    async with factory() as verification_db:
        verification = AgentHarnessRepository(verification_db)
        stored = await verification.get_session(session_id)
        assert stored is not None
        assert stored.history_revision == 0
        assert [item["command_id"] for item in stored.command_queue] == ["follow-1"]
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
    run = await repository.create_run(str(session.id))
    await repository.update_run(str(run.id), status="completed")

    snapshot = await repository.snapshot(str(session.id))
    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "completed"
    assert await repository.delete_session(str(session.id)) is True
    assert await repository.get_run(str(run.id)) is None


@pytest.mark.asyncio
async def test_repository_lists_only_runs_that_need_recovery(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    first = await repository.open_session(_request())
    second = await repository.open_session(_request())
    active = await repository.create_run(str(first.id))
    terminal = await repository.create_run(str(second.id))
    await repository.update_run(str(active.id), status="running", phase="model")
    await repository.update_run(str(terminal.id), status="completed")

    runs = await repository.list_recoverable_runs()

    assert [run.id for run in runs] == [active.id]
