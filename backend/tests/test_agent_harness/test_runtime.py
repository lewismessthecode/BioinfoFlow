from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.agent_harness.contracts import (
    CancelCommand,
    InputTextPart,
    MessageCommand,
    OpenSessionRequest,
    SteerCommand,
)
from app.services.agent_harness.command_risk import CommandRiskAssessment
from app.services.agent_harness.harness import AgentHarness
from app.services.agent_harness.loop import HARNESS_VERSION
from app.services.agent_harness.recovery import create_checkpoint
from app.services.agent_harness.runtime import AgentRuntime
from app.services.agent_harness.workspace_runtime import (
    LocalWorkspaceBackend,
    WorkspaceRuntime,
)
from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ModelEvent,
    TextDelta,
    ToolCallDelta,
)


class BlockingModel:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def invoke(self, _invocation) -> AsyncIterator[ModelEvent]:
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        yield TextDelta(text="done")
        yield CompletionMetadata(response_id="response-1", finish_reason="stop")


class CancellationResistantModel:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def invoke(self, _invocation) -> AsyncIterator[ModelEvent]:
        self.started.set()
        await self.release.wait()
        yield TextDelta(text="released")
        yield CompletionMetadata(response_id="response-resistant", finish_reason="stop")


class ImmediateModel:
    def __init__(self, text: str) -> None:
        self.text = text
        self.invocations = []

    async def invoke(self, invocation) -> AsyncIterator[ModelEvent]:
        self.invocations.append(invocation)
        yield TextDelta(text=self.text)
        yield CompletionMetadata(response_id="response-2", finish_reason="stop")


class BashModel:
    async def invoke(self, _invocation) -> AsyncIterator[ModelEvent]:
        yield ToolCallDelta(
            index=0,
            call_id="bash-1",
            name="bash",
            arguments_delta='{"command":"run-until-cancelled"}',
        )
        yield CompletionMetadata(
            response_id="response-bash", finish_reason="tool_calls"
        )


class AskModel:
    async def invoke(self, _invocation) -> AsyncIterator[ModelEvent]:
        yield ToolCallDelta(
            index=0,
            call_id="ask-1",
            name="ask_user",
            arguments_delta=(
                '{"questions":[{"question":"Continue?","header":"Confirm",'
                '"options":[{"label":"Yes","description":"Continue"},'
                '{"label":"No","description":"Stop"}]}]}'
            ),
        )
        yield CompletionMetadata(
            response_id="response-ask",
            finish_reason="tool_calls",
        )


class CancellableCommandBackend:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()

    def canonical_path(self, raw_path: str) -> Path:
        return self.root / raw_path

    def assess_command(self, _command: str, *, cwd=None) -> CommandRiskAssessment:
        return CommandRiskAssessment(level="act_low", effects=["process_control"])

    async def run_command(self, **_kwargs):
        self.started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.stopped.set()
            raise


class SteerDuringStreamModel:
    def __init__(self) -> None:
        self.paused = asyncio.Event()
        self.release = asyncio.Event()
        self.invocations = []

    async def invoke(self, invocation) -> AsyncIterator[ModelEvent]:
        self.invocations.append(invocation)
        if len(self.invocations) == 1:
            yield TextDelta(text="First answer")
            self.paused.set()
            await self.release.wait()
            yield CompletionMetadata(response_id="response-1", finish_reason="stop")
            return
        yield TextDelta(text="Answer including the steer")
        yield CompletionMetadata(response_id="response-2", finish_reason="stop")


class BlockingRecoveryWorkspace:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    def with_bash_environment_provider(self, _provider) -> None:
        return None

    async def execute(self, _call):
        self.started.set()
        await self.release.wait()
        raise AssertionError("test releases recovery by cancelling the runtime")


def _message(command_id: str, text: str) -> MessageCommand:
    return MessageCommand(
        command_id=command_id,
        parts=[InputTextPart(text=text)],
    )


def _steer(command_id: str, text: str) -> SteerCommand:
    return SteerCommand(
        command_id=command_id,
        parts=[InputTextPart(text=text)],
    )


def _latest_run(snapshot):
    if snapshot.active_run is not None:
        return snapshot.active_run.run
    return snapshot.runs[-1]


@pytest.mark.asyncio
async def test_runtime_dispatches_in_background_and_cancel_crosses_requests(
    harness_db: AsyncSession,
    tmp_path: Path,
) -> None:
    model = BlockingModel()
    session_factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    def build_harness(db: AsyncSession, **runtime) -> AgentHarness:
        return AgentHarness.for_database(
            db,
            model_gateway=model,
            workspace_factory=lambda _session: _workspace(tmp_path),
            **runtime,
        )

    runtime = AgentRuntime(session_factory, harness_factory=build_harness)
    opened = await runtime.open_session(_open_request())

    await runtime.dispatch(
        str(opened.session.id),
        _message("message-1", "wait"),
    )

    await asyncio.wait_for(model.started.wait(), timeout=1)
    running = await runtime.snapshot(str(opened.session.id))
    assert running.active_run is not None
    assert running.active_run.run.status == "running"

    await runtime.dispatch(
        str(opened.session.id),
        CancelCommand(command_id="cancel-1", reason="user_cancelled"),
    )

    await asyncio.wait_for(model.cancelled.wait(), timeout=1)
    cancelled = await _wait_for_run_status(
        runtime,
        str(opened.session.id),
        "cancelled",
    )
    assert _latest_run(cancelled).status == "cancelled"
    assert _latest_run(cancelled).termination_reason == "user_cancelled"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_cross_worker_cancel_interrupts_a_running_model(
    harness_db: AsyncSession,
    tmp_path: Path,
) -> None:
    model = BlockingModel()
    session_factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    def build_harness(db: AsyncSession, **runtime) -> AgentHarness:
        return AgentHarness.for_database(
            db,
            model_gateway=model,
            workspace_factory=lambda _session: _workspace(tmp_path),
            **runtime,
        )

    running_worker = AgentRuntime(
        session_factory,
        harness_factory=build_harness,
        cancel_poll_interval_seconds=0.01,
    )
    cancelling_worker = AgentRuntime(
        session_factory,
        harness_factory=build_harness,
        cancel_poll_interval_seconds=0.01,
    )
    opened = await running_worker.open_session(_open_request())
    session_id = str(opened.session.id)
    await running_worker.dispatch(
        session_id,
        _message("message-cross-worker", "Wait."),
    )
    await asyncio.wait_for(model.started.wait(), timeout=1)

    try:
        await cancelling_worker.dispatch(
            session_id,
            CancelCommand(command_id="cancel-cross-worker", reason="user_cancelled"),
        )

        await asyncio.wait_for(model.cancelled.wait(), timeout=0.5)
        snapshot = await _wait_for_run_status(
            cancelling_worker,
            session_id,
            "cancelled",
        )
        assert _latest_run(snapshot).status == "cancelled"
        assert _latest_run(snapshot).termination_reason == "user_cancelled"
    finally:
        model.release.set()
        await running_worker.shutdown()
        await cancelling_worker.shutdown()


@pytest.mark.asyncio
async def test_cross_worker_cancel_stops_a_running_bash_command(
    harness_db: AsyncSession,
    tmp_path: Path,
) -> None:
    session_factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    backend = CancellableCommandBackend(tmp_path)

    def build_harness(db: AsyncSession, **runtime) -> AgentHarness:
        return AgentHarness.for_database(
            db,
            model_gateway=BashModel(),
            workspace_factory=lambda _session: WorkspaceRuntime(backend),
            **runtime,
        )

    running_worker = AgentRuntime(
        session_factory,
        harness_factory=build_harness,
        cancel_poll_interval_seconds=0.01,
    )
    cancelling_worker = AgentRuntime(
        session_factory,
        harness_factory=build_harness,
        cancel_poll_interval_seconds=0.01,
    )
    opened = await running_worker.open_session(_open_request())
    session_id = str(opened.session.id)
    await running_worker.dispatch(
        session_id,
        _message("message-cross-worker-bash", "Run it."),
    )
    await asyncio.wait_for(backend.started.wait(), timeout=1)

    try:
        await cancelling_worker.dispatch(
            session_id,
            CancelCommand(
                command_id="cancel-cross-worker-bash",
                reason="user_cancelled",
            ),
        )

        await asyncio.wait_for(backend.stopped.wait(), timeout=0.5)
        snapshot = await _wait_for_run_status(
            cancelling_worker,
            session_id,
            "cancelled",
        )
        assert _latest_run(snapshot).status == "cancelled"
        assert _latest_run(snapshot).termination_reason == "user_cancelled"
    finally:
        await running_worker.shutdown()
        await cancelling_worker.shutdown()


@pytest.mark.asyncio
async def test_runtime_cancel_claims_a_waiting_user_run(
    harness_db: AsyncSession,
    tmp_path: Path,
) -> None:
    session_factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    def build_harness(db: AsyncSession, **runtime) -> AgentHarness:
        return AgentHarness.for_database(
            db,
            model_gateway=AskModel(),
            workspace_factory=lambda _session: _workspace(tmp_path),
            **runtime,
        )

    runtime = AgentRuntime(session_factory, harness_factory=build_harness)
    opened = await runtime.open_session(_open_request())
    session_id = str(opened.session.id)
    await runtime.dispatch(
        session_id,
        _message("message-before-wait", "Ask me."),
    )
    await _wait_for_run_status(runtime, session_id, "waiting_user")

    await runtime.dispatch(
        session_id,
        CancelCommand(command_id="cancel-waiting", reason="user_cancelled"),
    )

    cancelled = await _wait_for_run_status(runtime, session_id, "cancelled")
    assert _latest_run(cancelled).termination_reason == "user_cancelled"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_quiesces_active_session_before_file_deletion(
    harness_db: AsyncSession,
    tmp_path: Path,
) -> None:
    model = BlockingModel()
    session_factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    def build_harness(db: AsyncSession, **runtime) -> AgentHarness:
        return AgentHarness.for_database(
            db,
            model_gateway=model,
            workspace_factory=lambda _session: _workspace(tmp_path),
            **runtime,
        )

    runtime = AgentRuntime(session_factory, harness_factory=build_harness)
    opened = await runtime.open_session(_open_request())
    session_id = str(opened.session.id)
    await runtime.dispatch(
        session_id,
        _message("message-before-delete", "wait"),
    )
    await asyncio.wait_for(model.started.wait(), timeout=1)

    await runtime.quiesce_session(session_id)

    assert model.cancelled.is_set()
    snapshot = await runtime.snapshot(session_id)
    assert _latest_run(snapshot).status == "cancelled"
    assert _latest_run(snapshot).termination_reason == "session_deleted"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_cross_worker_delete_waits_for_running_bash_to_quiesce(
    harness_db: AsyncSession,
    tmp_path: Path,
) -> None:
    session_factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    backend = CancellableCommandBackend(tmp_path)

    def build_harness(db: AsyncSession, **runtime) -> AgentHarness:
        return AgentHarness.for_database(
            db,
            model_gateway=BashModel(),
            workspace_factory=lambda _session: WorkspaceRuntime(backend),
            **runtime,
        )

    running_worker = AgentRuntime(session_factory, harness_factory=build_harness)
    deleting_worker = AgentRuntime(session_factory, harness_factory=build_harness)
    opened = await running_worker.open_session(_open_request())
    session_id = str(opened.session.id)
    await running_worker.dispatch(
        session_id,
        _message("message-bash", "Run the command."),
    )
    await asyncio.wait_for(backend.started.wait(), timeout=1)

    await deleting_worker.quiesce_session(session_id)

    assert backend.stopped.is_set()
    snapshot = await deleting_worker.snapshot(session_id)
    assert _latest_run(snapshot).status == "cancelled"
    assert _latest_run(snapshot).termination_reason == "session_deleted"
    await deleting_worker.delete_session(session_id)
    with pytest.raises(LookupError, match="agent session not found"):
        await deleting_worker.snapshot(session_id)
    await running_worker.shutdown()
    await deleting_worker.shutdown()


@pytest.mark.asyncio
async def test_cross_worker_quiesce_timeout_keeps_closing_session_durable(
    harness_db: AsyncSession,
    tmp_path: Path,
) -> None:
    model = CancellationResistantModel()
    session_factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    def build_harness(db: AsyncSession, **runtime) -> AgentHarness:
        return AgentHarness.for_database(
            db,
            model_gateway=model,
            workspace_factory=lambda _session: _workspace(tmp_path),
            **runtime,
        )

    running_worker = AgentRuntime(session_factory, harness_factory=build_harness)
    deleting_worker = AgentRuntime(
        session_factory,
        harness_factory=build_harness,
        quiesce_timeout_seconds=0.05,
        cancel_poll_interval_seconds=0.01,
    )
    opened = await running_worker.open_session(_open_request())
    session_id = str(opened.session.id)
    await running_worker.dispatch(
        session_id,
        _message("message-resistant", "Wait."),
    )
    await asyncio.wait_for(model.started.wait(), timeout=1)

    with pytest.raises(TimeoutError, match="did not quiesce"):
        await deleting_worker.quiesce_session(session_id)

    snapshot = await deleting_worker.snapshot(session_id)
    assert snapshot.session.status == "closing"
    assert snapshot.active_run is not None
    assert snapshot.active_run.run.status == "running"
    with pytest.raises(ValueError, match="closing"):
        await deleting_worker.dispatch(
            session_id,
            _message("late-message", "Do not start."),
        )

    model.release.set()
    for _ in range(100):
        snapshot = await deleting_worker.snapshot(session_id)
        if (
            _latest_run(snapshot).status == "cancelled"
        ):
            break
        await asyncio.sleep(0.01)
    assert _latest_run(snapshot).status == "cancelled"
    await deleting_worker.quiesce_session(session_id)
    await running_worker.shutdown()
    await deleting_worker.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_expiry", [False, True])
async def test_quiesce_terminalizes_run_owned_by_a_dead_worker(
    harness_db: AsyncSession,
    tmp_path: Path,
    missing_expiry: bool,
) -> None:
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import update

    from app.models.agent_harness import AgentHarnessRun
    from app.repositories.agent_harness_repo import AgentHarnessRepository

    session_factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_open_request())
    run = await repository.create_run(str(session.id))
    assert await repository.claim_run(
        str(run.id),
        owner="dead-process",
        lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    if missing_expiry:
        await harness_db.execute(
            update(AgentHarnessRun)
            .where(AgentHarnessRun.id == run.id)
            .values(lease_expires_at=None)
        )
        await harness_db.commit()

    def build_harness(db: AsyncSession, **runtime) -> AgentHarness:
        return AgentHarness.for_database(
            db,
            model_gateway=ImmediateModel("unused"),
            workspace_factory=lambda _session: _workspace(tmp_path),
            **runtime,
        )

    runtime = AgentRuntime(
        session_factory,
        harness_factory=build_harness,
        quiesce_timeout_seconds=0.05,
        cancel_poll_interval_seconds=0.01,
    )
    await runtime.quiesce_session(str(session.id))

    snapshot = await runtime.snapshot(str(session.id))
    assert snapshot.session.status == "closing"
    assert _latest_run(snapshot).status == "cancelled"
    assert _latest_run(snapshot).termination_reason == "session_deleted"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_shutdown_preserves_active_run_for_startup_recovery(
    harness_db: AsyncSession,
    tmp_path: Path,
) -> None:
    blocking = BlockingModel()
    session_factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    def build_blocking_harness(db: AsyncSession, **runtime) -> AgentHarness:
        return AgentHarness.for_database(
            db,
            model_gateway=blocking,
            workspace_factory=lambda _session: _workspace(tmp_path),
            **runtime,
        )

    first_runtime = AgentRuntime(
        session_factory, harness_factory=build_blocking_harness
    )
    opened = await first_runtime.open_session(_open_request())
    session_id = str(opened.session.id)
    await first_runtime.dispatch(
        session_id,
        _message("message-before-shutdown", "Keep working."),
    )
    await asyncio.wait_for(blocking.started.wait(), timeout=1)

    await first_runtime.shutdown()

    after_shutdown = await first_runtime.snapshot(session_id)
    assert blocking.cancelled.is_set()
    assert after_shutdown.active_run is not None
    assert after_shutdown.active_run.run.status == "running"

    recovered_model = ImmediateModel("Recovered after restart.")

    def build_recovered_harness(db: AsyncSession, **runtime) -> AgentHarness:
        return AgentHarness.for_database(
            db,
            model_gateway=recovered_model,
            workspace_factory=lambda _session: _workspace(tmp_path),
            **runtime,
        )

    second_runtime = AgentRuntime(
        session_factory, harness_factory=build_recovered_harness
    )
    assert await second_runtime.recover() == 1
    for _ in range(30):
        recovered = await second_runtime.snapshot(session_id)
        if (
            _latest_run(recovered).status == "completed"
        ):
            break
        await asyncio.sleep(0.01)

    assert _latest_run(recovered).status == "completed"
    assert len(recovered_model.invocations) == 1
    assert [
        [part.model_dump(mode="json", exclude={"id"}) for part in entry.payload.parts]
        for entry in recovered.entries
        if entry.type == "message" and entry.payload.role == "assistant"
    ] == [[{"type": "text", "text": "Recovered after restart."}]]
    await second_runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_shutdown_does_not_reschedule_commands_after_task_snapshot(
    harness_db: AsyncSession,
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.repositories.agent_harness_repo import AgentHarnessRepository

    session_factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    release_started = asyncio.Event()
    release_allowed = asyncio.Event()
    release_cancelled = asyncio.Event()
    original_release = AgentHarnessRepository.release_run_lease
    release_calls = 0

    async def block_first_release(repository, run_id: str, *, owner: str) -> bool:
        nonlocal release_calls
        release_calls += 1
        if release_calls == 1:
            release_started.set()
            try:
                await release_allowed.wait()
            except asyncio.CancelledError:
                release_cancelled.set()
                raise
        return await original_release(repository, run_id, owner=owner)

    monkeypatch.setattr(
        AgentHarnessRepository,
        "release_run_lease",
        block_first_release,
    )

    def build_harness(db: AsyncSession, **runtime) -> AgentHarness:
        return AgentHarness.for_database(
            db,
            model_gateway=AskModel(),
            workspace_factory=lambda _session: _workspace(tmp_path),
            **runtime,
        )

    runtime = AgentRuntime(session_factory, harness_factory=build_harness)
    opened = await runtime.open_session(_open_request())
    session_id = str(opened.session.id)
    await runtime.dispatch(
        session_id,
        _message("message-before-shutdown-race", "Ask me."),
    )
    await asyncio.wait_for(release_started.wait(), timeout=1)
    waiting = await runtime.snapshot(session_id)
    assert waiting.active_run is not None
    assert waiting.active_run.run.status == "waiting_user"

    claim_started = asyncio.Event()

    async def block_rescheduled_claim(_run_id: str, _cancellation: asyncio.Event):
        claim_started.set()
        await asyncio.Future()

    monkeypatch.setattr(runtime, "_claim_when_available", block_rescheduled_claim)
    await runtime.dispatch(
        session_id,
        CancelCommand(command_id="cancel-before-shutdown", reason="user_cancelled"),
    )

    shutdown_task = asyncio.create_task(runtime.shutdown())
    try:
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not shutdown_task.done()
        assert not release_cancelled.is_set()
    finally:
        release_allowed.set()
        await asyncio.gather(shutdown_task, return_exceptions=True)

    await asyncio.sleep(0)
    current = asyncio.current_task()
    leaked = [
        task
        for task in asyncio.all_tasks()
        if task is not current
        and not task.done()
        and task.get_name().startswith("agent-commands:")
    ]
    leaked_names = [task.get_name() for task in leaked]
    for task in leaked:
        task.cancel()
    await asyncio.gather(*leaked, return_exceptions=True)

    assert leaked_names == []
    assert not claim_started.is_set()
    assert not release_cancelled.is_set()
    assert release_calls == 1
    assert runtime._tasks == {}

    async with session_factory() as db:
        persisted = await AgentHarnessRepository(db).get_run(
            str(waiting.active_run.run.id)
        )
    assert persisted is not None
    assert persisted.lease_owner is None
    assert persisted.lease_expires_at is None


@pytest.mark.asyncio
async def test_steer_arriving_during_model_stream_continues_before_run_completion(
    harness_db: AsyncSession,
    tmp_path: Path,
) -> None:
    model = SteerDuringStreamModel()
    session_factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    def build_harness(db: AsyncSession, **runtime) -> AgentHarness:
        return AgentHarness.for_database(
            db,
            model_gateway=model,
            workspace_factory=lambda _session: _workspace(tmp_path),
            **runtime,
        )

    runtime = AgentRuntime(session_factory, harness_factory=build_harness)
    opened = await runtime.open_session(_open_request())
    session_id = str(opened.session.id)
    await runtime.dispatch(
        session_id,
        _message("message-1", "Start."),
    )
    await asyncio.wait_for(model.paused.wait(), timeout=1)

    await runtime.dispatch(
        session_id,
        _steer("steer-while-streaming", "Also check metadata."),
    )
    model.release.set()
    for _ in range(50):
        snapshot = await runtime.snapshot(session_id)
        if (
            _latest_run(snapshot).status == "completed"
        ):
            break
        await asyncio.sleep(0.01)

    assert _latest_run(snapshot).status == "completed"
    assert len(model.invocations) == 2
    user_texts = [
        part.text
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "user"
        for part in entry.payload.parts
        if part.type == "text"
    ]
    assert user_texts == ["Start.", "Also check metadata."]
    assert any(
        getattr(item, "text", None) == "Also check metadata."
        for item in model.invocations[1].input_items
    )
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_shares_live_events_across_request_sessions(
    harness_db: AsyncSession,
    tmp_path: Path,
) -> None:
    model = BlockingModel()
    session_factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    def build_harness(db: AsyncSession, **runtime) -> AgentHarness:
        return AgentHarness.for_database(
            db,
            model_gateway=model,
            workspace_factory=lambda _session: _workspace(tmp_path),
            **runtime,
        )

    runtime = AgentRuntime(session_factory, harness_factory=build_harness)
    opened = await runtime.open_session(_open_request())
    events = runtime.events(str(opened.session.id))
    first = await anext(events)
    assert first.type == "snapshot"

    await runtime.dispatch(
        str(opened.session.id),
        _message("message-1", "stream"),
    )

    observed = []
    while len(observed) < 2:
        event = await asyncio.wait_for(anext(events), timeout=1)
        observed.append(event.type)
        if event.type == "run.updated":
            break
    assert "entry.committed" in observed
    assert "run.updated" in observed
    running = await runtime.snapshot(str(opened.session.id))
    assert running.active_run is not None
    run_id = running.active_run.run.id

    await runtime.dispatch(
        str(opened.session.id),
        CancelCommand(command_id="cancel-1"),
    )
    for _ in range(12):
        event = await asyncio.wait_for(anext(events), timeout=1)
        if (
            event.type == "run.updated"
            and event.run.id == run_id
            and event.run.status == "cancelled"
        ):
            break
    else:
        pytest.fail("cancel did not publish the terminal Run update")
    await events.aclose()
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_recovery_schedules_tool_resume_without_blocking_startup(
    harness_db: AsyncSession,
) -> None:
    from app.repositories.agent_harness_repo import AgentHarnessRepository

    workspace = BlockingRecoveryWorkspace()
    session_factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_open_request())
    run = await repository.create_run(str(session.id))
    await repository.update_run(
        str(run.id),
        status="running",
        phase="tools",
        checkpoint=create_checkpoint(
            harness_version=HARNESS_VERSION,
            phase="tools",
            history_revision=0,
            in_flight_tools=(
                {
                    "call_id": "read-1",
                    "name": "read",
                    "arguments": {"path": "input.txt"},
                    "replay_policy": "safe",
                },
            ),
        ),
    )

    def build_harness(db: AsyncSession, **runtime) -> AgentHarness:
        return AgentHarness.for_database(
            db,
            model_gateway=BlockingModel(),
            workspace_factory=lambda _session: workspace,
            **runtime,
        )

    runtime = AgentRuntime(session_factory, harness_factory=build_harness)
    recovered = await asyncio.wait_for(runtime.recover(), timeout=0.2)

    assert recovered == 1
    await asyncio.wait_for(workspace.started.wait(), timeout=1)
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_retries_recovery_after_foreign_lease_expires(
    harness_db: AsyncSession,
    tmp_path: Path,
) -> None:
    from datetime import datetime, timedelta, timezone

    from app.repositories.agent_harness_repo import AgentHarnessRepository

    model = BlockingModel()
    session_factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_open_request())
    run = await repository.create_run(str(session.id))
    assert await repository.claim_run(
        str(run.id),
        owner="dead-process",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(milliseconds=100),
    )

    def build_harness(db: AsyncSession, **runtime) -> AgentHarness:
        return AgentHarness.for_database(
            db,
            model_gateway=model,
            workspace_factory=lambda _session: _workspace(tmp_path),
            **runtime,
        )

    runtime = AgentRuntime(session_factory, harness_factory=build_harness)
    assert await runtime.recover() == 1
    assert not model.started.is_set()
    await asyncio.wait_for(model.started.wait(), timeout=1)
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_background_bootstrap_failure_is_persisted_instead_of_leaking_task(
    harness_db: AsyncSession,
) -> None:
    session_factory = async_sessionmaker(
        harness_db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    def build_harness(db: AsyncSession, **runtime) -> AgentHarness:
        def broken_workspace(_session):
            raise RuntimeError("workspace bootstrap failed")

        return AgentHarness.for_database(
            db,
            model_gateway=BlockingModel(),
            workspace_factory=broken_workspace,
            **runtime,
        )

    runtime = AgentRuntime(session_factory, harness_factory=build_harness)
    opened = await runtime.open_session(_open_request())
    events = runtime.events(str(opened.session.id))
    initial = await asyncio.wait_for(anext(events), timeout=1)
    assert initial.type == "snapshot"
    await runtime.dispatch(
        str(opened.session.id),
        _message("message-1", "start"),
    )

    failed_event = None
    for _ in range(20):
        event = await asyncio.wait_for(anext(events), timeout=1)
        if event.type == "run.updated" and event.run.status == "failed":
            failed_event = event
            break

    for _ in range(20):
        snapshot = await runtime.snapshot(str(opened.session.id))
        if _latest_run(snapshot).status == "failed":
            break
        await asyncio.sleep(0)

    assert _latest_run(snapshot).status == "failed"
    assert _latest_run(snapshot).termination_reason == "runtime_failed"
    assert _latest_run(snapshot).error == {
        "code": "runtime_failed",
        "message": "workspace bootstrap failed",
        "type": "RuntimeError",
    }
    assert failed_event is not None
    await events.aclose()
    await runtime.shutdown()


async def _wait_for_run_status(
    runtime: AgentRuntime,
    session_id: str,
    status: str,
):
    for _ in range(100):
        snapshot = await runtime.snapshot(session_id)
        if _latest_run(snapshot).status == status:
            return snapshot
        await asyncio.sleep(0.01)
    raise AssertionError(f"Agent run did not reach {status}")


def _open_request() -> OpenSessionRequest:
    return OpenSessionRequest(
        user_id="user-1",
        workspace_id="00000000-0000-0000-0000-000000000001",
        prompt_snapshot={"content": "Help the user."},
        model={
            "target": {
                "endpoint_id": "endpoint-1",
                "provider_kind": "openai",
                "model_name": "gpt-test",
                "routed_model_name": "gpt-test",
                "wire_protocol": "responses",
                "target_revision": "revision-1",
                "api_key": "test-key",
            }
        },
        workspace={"root": "/workspace"},
    )


def _workspace(root: Path) -> WorkspaceRuntime:
    return WorkspaceRuntime(
        LocalWorkspaceBackend(
            working_directory=root,
            read_roots=(root,),
            write_roots=(root,),
            sandbox_runner=None,
        )
    )
