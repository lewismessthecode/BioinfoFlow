from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.database as app_database
from app.api.v1.agent import stream_events
from app.auth.agent_tokens import AgentTokenService
from app.auth.session import AuthUser
from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.services.agent_harness.contracts import (
    InputTextPart,
    MessageCommand,
    OpenSessionRequest,
    RespondCommand,
)
from app.services.agent_harness.harness import AgentHarness
from app.services.agent_harness.runtime import agent_runtime
from app.services.agent_harness.snapshot import AgentHarnessSnapshotService
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
from tests.test_agent_harness.run_test_helpers import create_agent_run


class BlockingModel:
    def __init__(self, *, resist_cancellation: bool = False) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.release = asyncio.Event()
        self.resist_cancellation = resist_cancellation

    async def invoke(self, _invocation) -> AsyncIterator[ModelEvent]:
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            if not self.resist_cancellation:
                raise
            await self.release.wait()
        yield TextDelta(text="late answer", phase="final_answer")
        yield CompletionMetadata(response_id="response-1", finish_reason="stop")


class InstructionCapturingModel:
    def __init__(self) -> None:
        self.invoked = asyncio.Event()
        self.instructions: list[str] = []

    async def invoke(self, invocation) -> AsyncIterator[ModelEvent]:
        self.instructions.append(invocation.instructions)
        self.invoked.set()
        yield TextDelta(text="done", phase="final_answer")
        yield CompletionMetadata(response_id="response-1", finish_reason="stop")


class BashThenAskThenBashModel:
    def __init__(self) -> None:
        self.invocations = 0

    async def invoke(self, _invocation) -> AsyncIterator[ModelEvent]:
        self.invocations += 1
        if self.invocations == 1:
            yield ToolCallDelta(
                index=0,
                call_id="bash-before-wait",
                name="bash",
                arguments_delta='{"command":"bif system health"}',
            )
            yield CompletionMetadata(
                response_id="response-1", finish_reason="tool_calls"
            )
            return
        if self.invocations == 2:
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
                response_id="response-2", finish_reason="tool_calls"
            )
            return
        if self.invocations == 3:
            yield ToolCallDelta(
                index=0,
                call_id="bash-1",
                name="bash",
                arguments_delta='{"command":"bif system health"}',
            )
            yield CompletionMetadata(
                response_id="response-3", finish_reason="tool_calls"
            )
            return
        yield TextDelta(text="done", phase="final_answer")
        yield CompletionMetadata(response_id="response-4", finish_reason="stop")


class TokenCapturingBackend(LocalWorkspaceBackend):
    def __init__(self, root: Path, token_service: AgentTokenService) -> None:
        super().__init__(
            working_directory=root,
            read_roots=(root,),
            write_roots=(root,),
            sandbox_runner=None,
        )
        self.token_service = token_service
        self.tokens: list[str] = []
        self.authenticated_during_execution = []

    def assess_command(self, command: str, *, cwd=None):
        from app.services.agent_harness.command_risk import CommandRiskAssessment

        del command, cwd
        return CommandRiskAssessment(level="act_low")

    async def run_command(self, **kwargs):
        token = kwargs["environment"]["BIOFLOW_AGENT_TOKEN"]
        self.tokens.append(token)
        self.authenticated_during_execution.append(
            await self.token_service.authenticate(token)
        )
        return {"exit_code": 0, "stdout": "", "stderr": ""}


@pytest.fixture
def install_api_harness(monkeypatch, tmp_path):
    models = []
    harness_db_ids: list[int] = []

    def install(model, *, workspace_factory=None):
        models.append(model)

        def build_harness(db: AsyncSession, **runtime) -> AgentHarness:
            harness_db_ids.append(id(db))
            return AgentHarness.for_database(
                db,
                model_gateway=model,
                workspace_factory=workspace_factory
                or (lambda _session: _workspace(tmp_path)),
                **runtime,
            )

        monkeypatch.setattr(agent_runtime, "_harness_factory", build_harness)
        return harness_db_ids

    return install


@pytest.mark.asyncio
async def test_new_session_freezes_current_custom_instructions_for_model_calls(
    async_client,
    monkeypatch,
    install_api_harness,
) -> None:
    model = InstructionCapturingModel()
    install_api_harness(model)
    _stub_session_configuration(monkeypatch)

    saved = await async_client.put(
        "/api/v1/agent/settings",
        json={"custom_instructions": "Use the validated reference first."},
    )
    assert saved.status_code == 200
    session_id = await _create_session(async_client)

    changed = await async_client.put(
        "/api/v1/agent/settings",
        json={"custom_instructions": "Use the experimental reference instead."},
    )
    assert changed.status_code == 200

    dispatched = await async_client.post(
        f"/api/v1/agent/sessions/{session_id}/commands",
        json={
            "type": "message",
            "command_id": "message-1",
            "parts": [{"type": "text", "text": "Inspect it"}],
        },
    )

    assert dispatched.status_code == 202
    await asyncio.wait_for(model.invoked.wait(), timeout=1)
    assert "Use the validated reference first." in model.instructions[0]
    assert "Use the experimental reference instead." not in model.instructions[0]
    for _ in range(100):
        snapshot = await async_client.get(
            f"/api/v1/agent/sessions/{session_id}/snapshot"
        )
        assert snapshot.status_code == 200
        runs = snapshot.json()["data"]["runs"]
        if runs and runs[-1]["status"] == "completed":
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail("background Agent run did not complete")


@pytest.mark.asyncio
async def test_prompt_returns_202_while_background_model_uses_another_db_session(
    async_client, monkeypatch, install_api_harness
) -> None:
    model = BlockingModel()
    db_ids = install_api_harness(model)
    _stub_session_configuration(monkeypatch)
    session_id = await _create_session(async_client)

    response = await asyncio.wait_for(
        async_client.post(
            f"/api/v1/agent/sessions/{session_id}/commands",
            json={
                "type": "message",
                "command_id": "message-1",
                "parts": [{"type": "text", "text": "wait"}],
            },
        ),
        timeout=1,
    )

    assert response.status_code == 202
    await asyncio.wait_for(model.started.wait(), timeout=1)
    assert response.json()["data"]["active_run"]["run"]["status"] in {
        "queued",
        "running",
    }
    assert len(set(db_ids)) >= 3

    cancelled = await async_client.post(
        f"/api/v1/agent/sessions/{session_id}/commands",
        json={"type": "cancel", "command_id": "cancel-1", "reason": "user_cancelled"},
    )
    assert cancelled.status_code == 202
    await asyncio.wait_for(model.cancelled.wait(), timeout=1)


@pytest.mark.asyncio
async def test_sse_starts_with_snapshot_then_streams_dispatch_events(
    async_client, monkeypatch, install_api_harness
) -> None:
    model = BlockingModel()
    install_api_harness(model)
    _stub_session_configuration(monkeypatch)
    session_id = await _create_session(async_client)

    async with app_database.async_session_maker() as db:
        response = await stream_events(session_id, user=_dev_user(), db=db)
        frames = response.body_iterator
        first = _parse_sse(await asyncio.wait_for(anext(frames), timeout=1))

        assert first["event"] == "snapshot"
        assert first["data"]["snapshot"]["session"]["id"] == session_id

        dispatched = await async_client.post(
            f"/api/v1/agent/sessions/{session_id}/commands",
            json={
                "type": "message",
                "command_id": "message-1",
                "parts": [{"type": "text", "text": "stream"}],
            },
        )
        assert dispatched.status_code == 202

        observed = []
        while {"entry.committed", "run.updated"} - set(observed):
            frame = _parse_sse(await asyncio.wait_for(anext(frames), timeout=1))
            observed.append(frame["event"])
        assert "entry.committed" in observed
        assert "run.updated" in observed

        await async_client.post(
            f"/api/v1/agent/sessions/{session_id}/commands",
            json={"type": "cancel", "command_id": "cancel-1"},
        )
        await frames.aclose()


@pytest.mark.asyncio
async def test_sse_reconnect_snapshot_recovers_all_active_run_ui_state(
    async_client, monkeypatch
) -> None:
    _stub_session_configuration(monkeypatch)
    session_id = await _create_session(async_client)

    async with app_database.async_session_maker() as db:
        repository = AgentHarnessRepository(db)
        run = await create_agent_run(repository, session_id)
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
                        "text": "",
                        "end_offset": 0,
                    },
                    {
                        "id": f"draft:{run.id}:text",
                        "type": "text",
                        "text": "durable partial",
                        "end_offset": 15,
                    },
                ],
            },
            tool_progress=[
                {
                    "call_id": "ask-1",
                    "group_id": "tool-group:ask-1",
                    "execution_mode": "serial",
                    "name": "ask_user",
                    "display_name": "ask_user",
                    "category": "interaction",
                    "summary": "Ask how to continue",
                    "arguments": {},
                    "status": "interaction_required",
                    "revision": 1,
                }
            ],
        )
        await repository.append_entry(
            session_id,
            run_id=str(run.id),
            entry_type="compaction",
            payload={"summary": "Private continuity state", "through_sequence": 0},
        )
        await repository.append_entry(
            session_id,
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
                                {"id": "yes", "label": "Yes"},
                                {"id": "no", "label": "No"},
                            ],
                        }
                    ],
                },
            },
        )

    for _reconnect in range(2):
        async with app_database.async_session_maker() as db:
            response = await stream_events(session_id, user=_dev_user(), db=db)
            frames = response.body_iterator
            first = _parse_sse(await asyncio.wait_for(anext(frames), timeout=1))

            assert first["event"] == "snapshot"
            snapshot = first["data"]["snapshot"]
            assert "history_revision" not in snapshot
            assert [entry["type"] for entry in snapshot["entries"]] == [
                "interaction_request"
            ]
            active_run = snapshot["active_run"]
            draft_parts = active_run["assistant_draft"]["parts"]
            assert {part["type"] for part in draft_parts} == {
                "reasoning_summary",
                "text",
            }
            text_part = next(part for part in draft_parts if part["type"] == "text")
            assert text_part["text"] == "durable partial"
            assert active_run["tool_progress"][0]["call_id"] == "ask-1"
            assert active_run["tool_progress"][0]["status"] == ("interaction_required")
            assert active_run["pending_interaction"]["interaction_id"] == ("question-1")
            assert (
                active_run["pending_interaction"]["request"]["questions"][0]["question"]
                == "Continue?"
            )
            await frames.aclose()


@pytest.mark.asyncio
async def test_waiting_user_revokes_old_token_and_respond_issues_fresh_bash_token(
    harness_db: AsyncSession, tmp_path: Path
) -> None:
    model = BashThenAskThenBashModel()
    token_service = AgentTokenService(harness_db)
    backend = TokenCapturingBackend(tmp_path, token_service)
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: WorkspaceRuntime(backend),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)

    await harness.dispatch(
        session_id,
        _message("message-1", "ask first"),
    )
    waiting = await harness.snapshot(session_id)
    assert waiting.active_run is not None
    assert waiting.active_run.run.status == "waiting_user"
    assert len(backend.tokens) == 1
    token_before_wait = backend.tokens[0]
    assert backend.authenticated_during_execution[0] is not None
    assert await token_service.authenticate(token_before_wait) is None

    await harness.dispatch(
        session_id,
        RespondCommand(
            command_id="respond-1",
            interaction_id="tool:ask-1",
            response={"type": "ask_user", "answers": {"Continue?": "Yes"}},
        ),
    )

    completed = await harness.snapshot(session_id)
    assert completed.active_run is None
    assert completed.runs[-1].status == "completed"
    assert len(backend.tokens) == 2
    token_after_response = backend.tokens[1]
    assert token_after_response != token_before_wait
    assert backend.authenticated_during_execution[1] is not None
    assert await token_service.authenticate(token_after_response) is None


@pytest.mark.asyncio
async def test_delete_active_session_prevents_stale_worker_from_writing_back(
    async_client, monkeypatch, install_api_harness
) -> None:
    model = BlockingModel(resist_cancellation=True)
    install_api_harness(model)
    _stub_session_configuration(monkeypatch)
    session_id = await _create_session(async_client)

    dispatched = await async_client.post(
        f"/api/v1/agent/sessions/{session_id}/commands",
        json={
            "type": "message",
            "command_id": "message-1",
            "parts": [{"type": "text", "text": "wait"}],
        },
    )
    assert dispatched.status_code == 202
    run_id = dispatched.json()["data"]["active_run"]["run"]["id"]
    await asyncio.wait_for(model.started.wait(), timeout=1)
    stale_worker = agent_runtime._tasks[run_id]
    monkeypatch.setattr(agent_runtime, "_quiesce_timeout_seconds", 0.05)
    monkeypatch.setattr(agent_runtime, "_cancel_poll_interval_seconds", 0.01)

    deleted = await async_client.delete(f"/api/v1/agent/sessions/{session_id}")
    assert deleted.status_code == 409
    async with app_database.async_session_maker() as db:
        closing = await AgentHarnessRepository(db).get_session(session_id)
        assert closing is not None
        assert closing.status == "closing"

    model.release.set()
    await asyncio.wait_for(
        asyncio.gather(stale_worker, return_exceptions=True), timeout=1
    )
    deleted = await async_client.delete(f"/api/v1/agent/sessions/{session_id}")
    assert deleted.status_code == 204

    async with app_database.async_session_maker() as db:
        repository = AgentHarnessRepository(db)
        assert await repository.get_session(session_id) is None
        with pytest.raises(LookupError, match="agent session not found"):
            await AgentHarnessSnapshotService(repository).build(session_id)


def _stub_session_configuration(monkeypatch) -> None:
    async def workspace(*_args, **_kwargs):
        return {"root": "/workspace", "runtime": "local"}

    async def model(*_args, **_kwargs):
        return {"target": _model_target()}

    monkeypatch.setattr("app.api.v1.agent.open_session_request_workspace", workspace)
    monkeypatch.setattr("app.api.v1.agent.resolve_model_snapshot", model)


async def _create_session(async_client) -> str:
    response = await async_client.post("/api/v1/agent/sessions", json={})
    assert response.status_code == 201
    return response.json()["data"]["session"]["id"]


def _parse_sse(frame: str | bytes) -> dict:
    if isinstance(frame, bytes):
        frame = frame.decode()
    fields = dict(line.split(": ", 1) for line in frame.strip().splitlines())
    return {"event": fields["event"], "data": json.loads(fields["data"])}


def _dev_user() -> AuthUser:
    return AuthUser(
        id="dev",
        name="Local User",
        email="local@bioinfoflow",
        role="owner",
        workspace_id="00000000-0000-0000-0000-000000000001",
    )


def _open_request() -> OpenSessionRequest:
    return OpenSessionRequest(
        user_id="user-1",
        workspace_id="00000000-0000-0000-0000-000000000001",
        prompt_snapshot={"content": "Help the user."},
        model={"target": _model_target()},
        workspace={"root": "/workspace"},
    )


def _model_target() -> dict[str, object]:
    return {
        "endpoint_id": "endpoint-1",
        "provider_kind": "openai",
        "model_name": "gpt-test",
        "routed_model_name": "gpt-test",
        "wire_protocol": "responses",
        "target_revision": "revision-1",
        "api_key": "test-key",
    }


def _workspace(root: Path) -> WorkspaceRuntime:
    return WorkspaceRuntime(
        LocalWorkspaceBackend(
            working_directory=root,
            read_roots=(root,),
            write_roots=(root,),
            sandbox_runner=None,
        )
    )


def _message(command_id: str, text: str) -> MessageCommand:
    return MessageCommand(command_id=command_id, parts=[InputTextPart(text=text)])
