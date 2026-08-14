from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import UploadFile

from app.services.agent_harness.assets import AgentHarnessAttachmentService
from app.services.agent_harness.contracts import (
    CancelCommand,
    FollowUpCommand,
    OpenSessionRequest,
    PromptCommand,
)
from app.services.agent_harness.contracts import RespondCommand
from app.services.agent_harness.contracts import SteerCommand
from app.services.agent_harness.harness import AgentHarness
from app.services.agent_harness.loop import HARNESS_VERSION, LoopLimits
from app.services.agent_harness.model_target import model_target_from_snapshot
from app.services.agent_harness.recovery import create_checkpoint
from app.services.agent_harness.tools import ToolCall, ToolSpec
from app.services.agent_harness.workspace_runtime import (
    LocalWorkspaceBackend,
    WorkspaceRuntime,
)
from app.services.model_runtime.contracts import (
    canonical_input_prefix_digest,
    CompletionMetadata,
    ImagePart,
    ModelEvent,
    ResponsesContinuation,
    TextPart,
    TextDelta,
    ToolCallDelta,
    UsageReport,
)
from app.services.model_runtime.codecs.responses import ResponsesCodec
from app.services.model_runtime.errors import ModelError


class TextModel:
    def __init__(self, text: str) -> None:
        self.text = text
        self.invocations = []

    async def invoke(self, invocation) -> AsyncIterator[ModelEvent]:
        self.invocations.append(invocation)
        yield TextDelta(text=self.text, phase="final_answer")
        yield CompletionMetadata(response_id="response-1", finish_reason="stop")


class _TokenProviderWorkspace:
    def __init__(self) -> None:
        self.provider = None

    def with_bash_environment_provider(self, provider) -> None:
        self.provider = provider


class _IssuingTokenService:
    async def issue(self, **_kwargs):
        return SimpleNamespace(token="one-tool-secret")

    async def revoke_run(self, *_args, **_kwargs) -> None:
        return None


@pytest.mark.asyncio
async def test_bif_token_plaintext_leaves_harness_memory_when_provider_returns(
    harness_db,
) -> None:
    workspace = _TokenProviderWorkspace()
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=TextModel("unused"),
        workspace_factory=lambda _session: workspace,
    )
    harness.token_service = _IssuingTokenService()
    opened = await harness.open_session(_open_request())
    run = await harness.repository.create_run(str(opened.session.id))
    generation = await harness.repository.claim_run(
        str(run.id),
        owner="token-test-worker",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    assert generation == 1
    harness.repository.bind_run_fence(
        str(run.id), owner="token-test-worker", generation=generation
    )
    session = await harness.repository.get_session(str(opened.session.id))
    assert session is not None
    harness.loop.workspace_factory(session, str(run.id))
    assert workspace.provider is not None

    environment = await workspace.provider()

    assert environment == {"BIOFLOW_AGENT_TOKEN": "one-tool-secret"}
    assert harness._run_tokens == {}


class ScriptedModel:
    def __init__(self, *responses: tuple[ModelEvent, ...]) -> None:
        self.responses = list(responses)
        self.invocations = []

    async def invoke(self, invocation) -> AsyncIterator[ModelEvent]:
        self.invocations.append(invocation)
        for event in self.responses.pop(0):
            yield event


class _CancelSerialBatchTool:
    spec = ToolSpec(
        name="cancel_serial_batch",
        description="Cancel the current serial tool batch.",
        input_schema={"type": "object", "additionalProperties": False},
        replay_policy="safe",
        serial=True,
    )

    async def run(self, _arguments, context):
        context.cancellation.set()
        return {"cancel_requested": True}


class ContinuationToolModel:
    def __init__(self) -> None:
        self.invocations = []
        self.continuation = None

    async def invoke(self, invocation) -> AsyncIterator[ModelEvent]:
        self.invocations.append(invocation)
        if len(self.invocations) == 1:
            self.continuation = ResponsesContinuation(
                response_id="response-1",
                output_items=(
                    {
                        "type": "function_call",
                        "call_id": "read-1",
                        "name": "read",
                        "arguments": '{"path":"sample.txt"}',
                    },
                ),
                canonical_input_count=len(invocation.input_items),
                canonical_input_digest=canonical_input_prefix_digest(
                    invocation.input_items
                ),
                target=invocation.target.continuation_target(),
            )
            yield ToolCallDelta(
                index=0,
                call_id="read-1",
                name="read",
                arguments_delta='{"path":"sample.txt"}',
            )
            yield CompletionMetadata(
                response_id="response-1",
                finish_reason="tool_calls",
                continuation=self.continuation,
            )
            return
        yield TextDelta(text="The file contains alpha.")
        yield CompletionMetadata(response_id="response-2", finish_reason="stop")


class OverflowThenTextModel:
    def __init__(self) -> None:
        self.invocations = []

    async def invoke(self, invocation) -> AsyncIterator[ModelEvent]:
        self.invocations.append(invocation)
        if len(self.invocations) == 1:
            raise ModelError(
                category="invalid_request",
                provider_code="context_length_exceeded",
                message="maximum context length exceeded",
            )
        yield TextDelta(text="Recovered after compression.")
        yield CompletionMetadata(response_id="response-2", finish_reason="stop")


class AlwaysOverflowModel:
    def __init__(self) -> None:
        self.invocations = []

    async def invoke(self, invocation) -> AsyncIterator[ModelEvent]:
        self.invocations.append(invocation)
        raise ModelError(
            category="invalid_request",
            provider_code="context_length_exceeded",
            message="maximum context length exceeded",
            retryable=True,
            replay_safe=True,
        )
        yield  # pragma: no cover - keep this an async generator


class TimeoutThenTextModel:
    def __init__(self, *, semantic_before_timeout: bool = False) -> None:
        self.semantic_before_timeout = semantic_before_timeout
        self.invocations = []

    async def invoke(self, invocation) -> AsyncIterator[ModelEvent]:
        self.invocations.append(invocation)
        if len(self.invocations) == 1:
            if self.semantic_before_timeout:
                yield TextDelta(text="visible partial")
            await asyncio.sleep(1)
            return
        yield TextDelta(text="retried")
        yield CompletionMetadata(response_id="response-2", finish_reason="stop")


class TokenBudgetModel:
    def __init__(self) -> None:
        self.invocations = []

    async def invoke(self, invocation) -> AsyncIterator[ModelEvent]:
        self.invocations.append(invocation)
        if len(self.invocations) == 1:
            yield ToolCallDelta(
                index=0,
                call_id="read-1",
                name="read",
                arguments_delta='{"path":"sample.txt"}',
            )
            yield UsageReport(input_tokens=4, output_tokens=2, total_tokens=6)
            yield CompletionMetadata(
                response_id="response-1", finish_reason="tool_calls"
            )
            return
        yield ToolCallDelta(
            index=0,
            call_id="write-1",
            name="write",
            arguments_delta='{"path":"marker.txt","content":"created"}',
        )
        yield UsageReport(input_tokens=4, output_tokens=2, total_tokens=6)
        yield CompletionMetadata(response_id="response-2", finish_reason="tool_calls")


class PausingStreamModel:
    def __init__(self) -> None:
        self.paused = asyncio.Event()
        self.release = asyncio.Event()

    async def invoke(self, _invocation) -> AsyncIterator[ModelEvent]:
        yield TextDelta(text="durable partial", phase="final_answer")
        self.paused.set()
        await self.release.wait()
        yield TextDelta(text=" answer", phase="final_answer")
        yield CompletionMetadata(response_id="response-1", finish_reason="stop")


class RecoveryInspectingModel(TextModel):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.repository = None
        self.session_id = None
        self.run_id = None
        self.observed_draft = "unset"
        self.observed_notice_codes = []

    async def invoke(self, invocation) -> AsyncIterator[ModelEvent]:
        assert self.repository is not None
        run = await self.repository.get_run(self.run_id)
        entries = await self.repository.list_entries(self.session_id)
        self.observed_draft = run.draft
        self.observed_notice_codes = [
            entry.payload.get("code") for entry in entries if entry.type == "notice"
        ]
        async for event in super().invoke(invocation):
            yield event


@pytest.mark.asyncio
async def test_prompt_commits_user_and_assistant_messages(harness_db, tmp_path) -> None:
    model = TextModel("I found the answer.")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id="00000000-0000-0000-0000-000000000001",
            prompt_snapshot={"content": "Help the user."},
            model={"target": _model_target()},
            workspace={"root": "/workspace"},
        )
    )

    await harness.dispatch(
        str(opened.session.id),
        PromptCommand(command_id="command-1", text="Inspect the project."),
    )
    snapshot = await harness.snapshot(str(opened.session.id))

    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "completed"
    assert [entry.type for entry in snapshot.entries] == ["message", "message"]
    assert snapshot.entries[0].payload.role == "user"
    assert snapshot.entries[0].payload.content == [
        {"type": "text", "text": "Inspect the project."}
    ]
    assert snapshot.entries[1].payload.role == "assistant"
    assert snapshot.entries[1].payload.content == [
        {"type": "text", "text": "I found the answer."}
    ]
    assert len(model.invocations) == 1


@pytest.mark.asyncio
async def test_streaming_draft_is_durable_until_assistant_message_commits(
    harness_db, tmp_path
) -> None:
    model = PausingStreamModel()
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)

    dispatch = asyncio.create_task(
        harness.dispatch(
            session_id,
            PromptCommand(command_id="stream-draft", text="Stream an answer."),
        )
    )
    await asyncio.wait_for(model.paused.wait(), timeout=1)

    streaming = await harness.snapshot(session_id)
    assert streaming.current_run is not None
    assert streaming.current_run.phase == "model"
    assert streaming.assistant_draft is not None
    assert streaming.assistant_draft.text == "durable partial"
    assert streaming.assistant_draft.end_offset == len(
        "durable partial".encode("utf-8")
    )

    model.release.set()
    await asyncio.wait_for(dispatch, timeout=1)
    completed = await harness.snapshot(session_id)
    assert completed.current_run is not None
    assert completed.current_run.status == "completed"
    assert completed.assistant_draft is None
    assert completed.entries[-1].payload.content == [
        {"type": "text", "text": "durable partial answer"}
    ]


@pytest.mark.asyncio
async def test_prompt_attachments_are_durable_and_enter_model_context(
    harness_db, tmp_path
) -> None:
    model = TextModel("I inspected both attachments.")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request(supports_vision=True))
    session = await harness.repository.get_session(str(opened.session.id))
    assert session is not None
    service = AgentHarnessAttachmentService(harness_db)
    text_attachment = (
        await service.ingest_files(
            agent_session=session,
            files=[UploadFile(filename="notes.txt", file=BytesIO(b"alpha beta"))],
        )
    )[0]
    image_attachment = await service.ingest_image(
        agent_session=session,
        file=UploadFile(
            filename="pixel.png",
            file=BytesIO(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
                    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
                )
            ),
        ),
        source="upload",
    )

    await harness.dispatch(
        str(opened.session.id),
        PromptCommand(
            command_id="with-attachments",
            text="Inspect these files.",
            attachment_ids=[text_attachment.id, image_attachment.id],
        ),
    )

    snapshot = await harness.snapshot(str(opened.session.id))
    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "completed", snapshot.current_run.error
    message = snapshot.entries[0].payload
    assert [str(item) for item in message.attachment_ids] == [
        str(text_attachment.id),
        str(image_attachment.id),
    ]
    assert [part["type"] for part in message.content] == [
        "text",
        "attachment",
        "attachment",
    ]
    assert message.content[1]["filename"] == "notes.txt"
    assert message.content[2]["filename"] == "pixel.png"
    input_items = model.invocations[0].input_items
    assert any(
        isinstance(item, TextPart) and "alpha beta" in item.text for item in input_items
    )
    assert any(
        isinstance(item, ImagePart) and item.mime_type == "image/png"
        for item in input_items
    )


@pytest.mark.asyncio
async def test_model_context_does_not_load_attachments_covered_by_compaction(
    harness_db, tmp_path, monkeypatch
) -> None:
    model = TextModel("Continued from the summary.")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    old_attachment_id = "30000000-0000-0000-0000-000000000001"
    old_run = await harness.repository.create_run(session_id)
    old_message = await harness.repository.append_entry(
        session_id,
        run_id=str(old_run.id),
        entry_type="message",
        payload={
            "role": "user",
            "content": [
                {"type": "text", "text": "Inspect the old upload."},
                {"type": "attachment", "attachment_id": old_attachment_id},
            ],
            "attachment_ids": [old_attachment_id],
        },
    )
    await harness.repository.update_run(str(old_run.id), status="completed")
    await harness.repository.append_entry(
        session_id,
        run_id=None,
        entry_type="compaction",
        payload={
            "summary": "The old upload was inspected successfully.",
            "through_sequence": old_message.sequence,
        },
    )

    requested_ids: list[str] = []

    async def record_requested_ids(_service, attachment_ids, **_scope):
        requested_ids.extend(attachment_ids)
        return {}

    monkeypatch.setattr(
        AgentHarnessAttachmentService,
        "model_parts_for_ids",
        record_requested_ids,
    )

    await harness.dispatch(
        session_id,
        PromptCommand(command_id="after-compaction", text="Continue."),
    )

    assert old_attachment_id not in requested_ids


@pytest.mark.asyncio
async def test_image_input_fails_before_invoking_model_without_vision_support(
    harness_db, tmp_path
) -> None:
    model = TextModel("The provider must not receive this image.")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request(supports_vision=False))
    session = await harness.repository.get_session(str(opened.session.id))
    assert session is not None
    image_attachment = await AgentHarnessAttachmentService(harness_db).ingest_image(
        agent_session=session,
        file=UploadFile(
            filename="pixel.png",
            file=BytesIO(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
                    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
                )
            ),
        ),
        source="upload",
    )

    await harness.dispatch(
        str(opened.session.id),
        PromptCommand(
            command_id="unsupported-image",
            text="Inspect this image.",
            attachment_ids=[image_attachment.id],
        ),
    )

    snapshot = await harness.snapshot(str(opened.session.id))
    assert model.invocations == []
    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "failed"
    assert snapshot.current_run.termination_reason == "model_vision_unsupported"
    assert snapshot.current_run.error == {
        "code": "model_vision_unsupported",
        "message": "The selected model does not support image input.",
        "type": None,
    }
    notices = [entry for entry in snapshot.entries if entry.type == "notice"]
    assert len(notices) == 1
    assert notices[0].payload.code == "model_vision_unsupported"
    assert notices[0].payload.message == (
        "The selected model does not support image input."
    )


@pytest.mark.asyncio
async def test_tool_call_result_is_committed_before_model_continues(
    harness_db, tmp_path
) -> None:
    (tmp_path / "sample.txt").write_text("alpha\n", encoding="utf-8")
    model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="read-1",
                name="read",
                arguments_delta='{"path":"sample.txt"}',
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        ),
        (
            TextDelta(text="The file contains alpha."),
            CompletionMetadata(response_id="response-2", finish_reason="stop"),
        ),
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())

    await harness.dispatch(
        str(opened.session.id), PromptCommand(command_id="command-1", text="Read it.")
    )
    snapshot = await harness.snapshot(str(opened.session.id))

    assert [
        entry.payload.role for entry in snapshot.entries if entry.type == "message"
    ] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert snapshot.entries[2].payload.call_id == "read-1"
    assert "alpha" in snapshot.entries[2].payload.content[0]["text"]
    assert len(model.invocations) == 2


@pytest.mark.asyncio
async def test_responses_continuation_is_reused_for_next_model_iteration(
    harness_db, tmp_path
) -> None:
    (tmp_path / "sample.txt").write_text("alpha\n", encoding="utf-8")
    model = ContinuationToolModel()
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())

    await harness.dispatch(
        str(opened.session.id),
        PromptCommand(command_id="continuation", text="Read it."),
    )

    assert len(model.invocations) == 2
    assert model.continuation is not None
    assert model.invocations[1].continuation is not None

    request = ResponsesCodec().encode_request(model.invocations[1])
    function_calls = [
        item for item in request["input"] if item.get("type") == "function_call"
    ]
    assert [item["call_id"] for item in function_calls] == ["read-1"]
    assert any(
        item.get("type") == "function_call_output" and item.get("call_id") == "read-1"
        for item in request["input"]
    )


@pytest.mark.asyncio
async def test_context_overflow_commits_compaction_before_single_retry(
    harness_db, tmp_path
) -> None:
    model = OverflowThenTextModel()
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
        limits=LoopLimits(compaction_threshold_chars=1, preserve_recent_entries=1),
    )
    opened = await harness.open_session(_open_request())
    repository = harness.repository
    session_id = str(opened.session.id)
    old_run = await repository.create_run(session_id)
    await repository.append_entry(
        session_id,
        run_id=str(old_run.id),
        entry_type="message",
        payload={"role": "user", "content": [{"type": "text", "text": "Old context"}]},
    )
    await repository.update_run(str(old_run.id), status="completed")

    await harness.dispatch(
        session_id,
        PromptCommand(command_id="command-overflow", text="Continue the work."),
    )
    snapshot = await harness.snapshot(session_id)

    assert [entry.type for entry in snapshot.entries].count("compaction") == 1
    compaction_index = next(
        index
        for index, entry in enumerate(snapshot.entries)
        if entry.type == "compaction"
    )
    assistant_index = max(
        index
        for index, entry in enumerate(snapshot.entries)
        if entry.type == "message" and entry.payload.role == "assistant"
    )
    assert compaction_index < assistant_index
    assert len(model.invocations) == 2
    assert (
        "Conversation summary for continuity"
        in model.invocations[1].input_items[0].text
    )


@pytest.mark.asyncio
async def test_context_overflow_is_compacted_and_retried_only_once(
    harness_db, tmp_path
) -> None:
    model = AlwaysOverflowModel()
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
        limits=LoopLimits(compaction_threshold_chars=1, preserve_recent_entries=1),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    old_run = await harness.repository.create_run(session_id)
    await harness.repository.append_entry(
        session_id,
        run_id=str(old_run.id),
        entry_type="message",
        payload={"role": "user", "content": [{"type": "text", "text": "Old context"}]},
    )
    await harness.repository.update_run(str(old_run.id), status="completed")

    await harness.dispatch(
        session_id,
        PromptCommand(command_id="overflow-twice", text="Continue."),
    )
    snapshot = await harness.snapshot(session_id)

    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "failed"
    assert [entry.type for entry in snapshot.entries].count("compaction") == 1
    assert len(model.invocations) == 2


@pytest.mark.asyncio
async def test_model_attempt_timeout_retries_before_semantic_output(
    harness_db, tmp_path
) -> None:
    model = TimeoutThenTextModel()
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
        limits=LoopLimits(model_attempt_timeout_seconds=0.01, retry_attempts=2),
    )
    opened = await harness.open_session(_open_request())

    await harness.dispatch(
        str(opened.session.id), PromptCommand(command_id="timeout", text="Answer.")
    )
    snapshot = await harness.snapshot(str(opened.session.id))

    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "completed"
    assert len(model.invocations) == 2


@pytest.mark.asyncio
async def test_model_attempt_timeout_does_not_retry_after_semantic_output(
    harness_db, tmp_path
) -> None:
    model = TimeoutThenTextModel(semantic_before_timeout=True)
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
        limits=LoopLimits(model_attempt_timeout_seconds=0.01, retry_attempts=2),
    )
    opened = await harness.open_session(_open_request())

    await harness.dispatch(
        str(opened.session.id), PromptCommand(command_id="timeout", text="Answer.")
    )
    snapshot = await harness.snapshot(str(opened.session.id))

    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "failed"
    assert snapshot.current_run.termination_reason == "model_attempt_timeout"
    assert len(model.invocations) == 1


@pytest.mark.asyncio
async def test_recovered_run_keeps_original_wall_clock_budget(
    harness_db, tmp_path
) -> None:
    model = TextModel("should not run")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
        limits=LoopLimits(run_timeout_seconds=1),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await harness.repository.create_run(session_id)
    user = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={"role": "user", "content": [{"type": "text", "text": "Go."}]},
    )
    await harness.repository.update_run(
        str(run.id),
        status="running",
        phase="model",
        checkpoint=create_checkpoint(
            harness_version=HARNESS_VERSION,
            phase="model",
            history_revision=user.sequence,
        ),
    )
    await harness.repository.update_run(
        str(run.id),
        started_at=datetime.now(timezone.utc) - timedelta(seconds=10),
    )

    await harness.recover()
    snapshot = await harness.snapshot(session_id)

    assert snapshot.current_run is not None
    assert snapshot.current_run.termination_reason == "run_timeout_exceeded"
    assert any(
        entry.type == "notice" and entry.payload.code == "run_timeout_exceeded"
        for entry in snapshot.entries
    )
    assert model.invocations == []


@pytest.mark.asyncio
async def test_token_budget_accumulates_across_model_iterations_before_tools(
    harness_db, tmp_path
) -> None:
    (tmp_path / "sample.txt").write_text("alpha\n", encoding="utf-8")
    model = TokenBudgetModel()
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
        limits=LoopLimits(run_token_budget=10),
    )
    opened = await harness.open_session(_open_request())

    await harness.dispatch(
        str(opened.session.id), PromptCommand(command_id="budget", text="Work.")
    )
    snapshot = await harness.snapshot(str(opened.session.id))

    assert snapshot.current_run is not None
    assert snapshot.current_run.termination_reason == "token_budget_exceeded"
    stored_run = await harness.repository.get_latest_run(str(opened.session.id))
    assert stored_run is not None
    assert stored_run.token_usage["total_tokens"] == 12
    assert len(model.invocations) == 2
    assert (tmp_path / "marker.txt").exists() is False


@pytest.mark.asyncio
async def test_tool_checkpoint_contains_version_revision_and_in_flight_policy(
    harness_db, tmp_path
) -> None:
    model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="ask-1",
                name="ask_user",
                arguments_delta=(
                    '{"questions":[{"question":"Continue?","header":"Confirm",'
                    '"options":[{"label":"Yes","description":"Continue"},'
                    '{"label":"No","description":"Stop"}]}]}'
                ),
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        ),
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())

    await harness.dispatch(
        str(opened.session.id), PromptCommand(command_id="checkpoint", text="Ask me.")
    )
    latest = await harness.repository.get_latest_run(str(opened.session.id))
    snapshot = await harness.snapshot(str(opened.session.id))

    assert latest is not None
    assert latest.status == "waiting_user"
    assert latest.checkpoint["harness_version"] == HARNESS_VERSION
    assert latest.checkpoint["history_revision"] >= 2
    assert latest.checkpoint["in_flight_tools"] == [
        {
            "call_id": "ask-1",
            "name": "ask_user",
            "arguments": {
                "questions": [
                    {
                        "question": "Continue?",
                        "header": "Confirm",
                        "options": [
                            {"label": "Yes", "description": "Continue"},
                            {"label": "No", "description": "Stop"},
                        ],
                    }
                ]
            },
            "replay_policy": "safe",
        }
    ]
    assert latest.checkpoint["history_revision"] == opened.revision + 3
    assert snapshot.assistant_draft is None
    assert [item.model_dump() for item in snapshot.tool_progress] == [
        {
            "call_id": "ask-1",
            "name": "ask_user",
            "status": "interaction_required",
        }
    ]
    assert snapshot.pending_interaction is not None
    assert snapshot.pending_interaction.interaction_id == "tool:ask-1"

    tokens = list(harness._run_tokens)
    assert tokens == []


@pytest.mark.asyncio
async def test_respond_rejects_a_different_pending_interaction(
    harness_db, tmp_path
) -> None:
    model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="ask-1",
                name="ask_user",
                arguments_delta=(
                    '{"questions":[{"question":"Continue?","header":"Confirm",'
                    '"options":[{"label":"Yes","description":"Continue"},'
                    '{"label":"No","description":"Stop"}]}]}'
                ),
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        ),
        (
            TextDelta(text="continued"),
            CompletionMetadata(response_id="response-2", finish_reason="stop"),
        ),
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    await harness.dispatch(
        session_id, PromptCommand(command_id="prompt-1", text="Ask me.")
    )

    with pytest.raises(ValueError, match="interaction.*does not match"):
        await harness.dispatch(
            session_id,
            RespondCommand(
                command_id="late-answer",
                interaction_id="tool:ask-from-an-older-request",
                response={"answers": {"Continue?": "Yes"}},
            ),
        )

    still_waiting = await harness.snapshot(session_id)
    assert still_waiting.current_run is not None
    assert still_waiting.current_run.status == "waiting_user"
    assert still_waiting.pending_interaction is not None
    assert still_waiting.pending_interaction.interaction_id == "tool:ask-1"
    assert len(model.invocations) == 1
    assert [
        entry for entry in still_waiting.entries if entry.type == "interaction_response"
    ] == []


@pytest.mark.asyncio
async def test_respond_command_interaction_id_cannot_be_overridden_by_response(
    harness_db, tmp_path
) -> None:
    model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="ask-1",
                name="ask_user",
                arguments_delta=(
                    '{"questions":[{"question":"Continue?","header":"Confirm",'
                    '"options":[{"label":"Yes","description":"Continue"},'
                    '{"label":"No","description":"Stop"}]}]}'
                ),
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        ),
        (
            TextDelta(text="continued"),
            CompletionMetadata(response_id="response-2", finish_reason="stop"),
        ),
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    await harness.dispatch(
        session_id, PromptCommand(command_id="prompt-1", text="Ask me.")
    )

    await harness.dispatch(
        session_id,
        RespondCommand(
            command_id="answer-1",
            interaction_id="tool:ask-1",
            response={
                "request_id": "tool:unrelated-request",
                "answers": {"Continue?": "Yes"},
            },
        ),
    )

    completed = await harness.snapshot(session_id)
    assert completed.current_run is not None
    assert completed.current_run.status == "completed"
    responses = [
        entry.payload.interaction_id
        for entry in completed.entries
        if entry.type == "interaction_response"
    ]
    assert responses == ["tool:ask-1"]


@pytest.mark.asyncio
async def test_steer_while_waiting_user_is_committed_once_at_next_safe_point(
    harness_db, tmp_path
) -> None:
    model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="ask-1",
                name="ask_user",
                arguments_delta=(
                    '{"questions":[{"question":"Continue?","header":"Confirm",'
                    '"options":[{"label":"Yes","description":"Continue"},'
                    '{"label":"No","description":"Stop"}]}]}'
                ),
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        ),
        (
            TextDelta(text="continued"),
            CompletionMetadata(response_id="response-2", finish_reason="stop"),
        ),
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    await harness.dispatch(
        session_id, PromptCommand(command_id="prompt-1", text="Ask me.")
    )
    await harness.dispatch(
        session_id,
        SteerCommand(command_id="steer-1", text="Also inspect the metadata."),
    )

    waiting = await harness.snapshot(session_id)
    assert [
        entry
        for entry in waiting.entries
        if entry.type == "message"
        and entry.payload.role == "user"
        and entry.payload.content
        == [{"type": "text", "text": "Also inspect the metadata."}]
    ] == []

    await harness.dispatch(
        session_id,
        RespondCommand(
            command_id="respond-1",
            interaction_id="tool:ask-1",
            response={"answers": {"Continue?": "Yes"}},
        ),
    )
    completed = await harness.snapshot(session_id)
    steers = [
        entry
        for entry in completed.entries
        if entry.type == "message"
        and entry.payload.role == "user"
        and entry.payload.content
        == [{"type": "text", "text": "Also inspect the metadata."}]
    ]
    assert len(steers) == 1


@pytest.mark.asyncio
async def test_recovery_consumes_a_durable_respond_command(
    harness_db, tmp_path
) -> None:
    asking_model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="ask-1",
                name="ask_user",
                arguments_delta=(
                    '{"questions":[{"question":"Continue?","header":"Confirm",'
                    '"options":[{"label":"Yes","description":"Continue"},'
                    '{"label":"No","description":"Stop"}]}]}'
                ),
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        ),
    )
    first = AgentHarness.for_database(
        harness_db,
        model_gateway=asking_model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await first.open_session(_open_request())
    session_id = str(opened.session.id)
    await first.dispatch(
        session_id,
        PromptCommand(command_id="prompt-before-crash", text="Ask me."),
    )
    waiting = await first.snapshot(session_id)
    assert waiting.current_run is not None
    run_id = str(waiting.current_run.id)
    assert waiting.current_run.status == "waiting_user"
    assert await first.repository.release_run_lease(
        run_id,
        owner=first._lease_owner(),
    )
    await first.repository.enqueue_command(
        session_id,
        RespondCommand(
            command_id="respond-before-crash",
            interaction_id="tool:ask-1",
            response={"answers": {"Continue?": "Yes"}},
        ),
    )

    restarted_model = TextModel("Recovered after the durable response.")
    restarted = AgentHarness.for_database(
        harness_db,
        model_gateway=restarted_model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )

    assert await restarted.recover() == 1
    recovered = await restarted.snapshot(session_id)
    assert recovered.current_run is not None
    assert recovered.current_run.status == "completed"
    assert len(restarted_model.invocations) == 1
    stored = await restarted.repository.get_run(run_id)
    assert stored is not None
    assert stored.command_queue == []


@pytest.mark.asyncio
async def test_crash_before_response_effect_keeps_the_durable_answer_for_recovery(
    harness_db, tmp_path, monkeypatch
) -> None:
    class SimulatedProcessCrash(BaseException):
        pass

    asking_model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="ask-1",
                name="ask_user",
                arguments_delta=(
                    '{"questions":[{"question":"Continue?","header":"Confirm",'
                    '"options":[{"label":"Yes","description":"Continue"},'
                    '{"label":"No","description":"Stop"}]}]}'
                ),
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        ),
    )
    first = AgentHarness.for_database(
        harness_db,
        model_gateway=asking_model,
        workspace_factory=lambda _session: _workspace(tmp_path),
        lease_owner="response-crash-worker",
    )
    opened = await first.open_session(_open_request())
    session_id = str(opened.session.id)
    await first.dispatch(
        session_id,
        PromptCommand(command_id="prompt-before-crash", text="Ask me."),
    )
    waiting = await first.snapshot(session_id)
    assert waiting.current_run is not None
    run_id = str(waiting.current_run.id)
    assert await first.repository.release_run_lease(
        run_id,
        owner="response-crash-worker",
    )
    await first.repository.enqueue_command(
        session_id,
        RespondCommand(
            command_id="answer-before-crash",
            interaction_id="tool:ask-1",
            response={"answers": {"Continue?": "Yes"}},
        ),
    )

    crashing = AgentHarness.for_database(
        harness_db,
        model_gateway=TextModel("must not run"),
        workspace_factory=lambda _session: _workspace(tmp_path),
        lease_owner="response-crash-worker",
    )

    async def crash_before_effect(*_args, **_kwargs):
        raise SimulatedProcessCrash

    monkeypatch.setattr(crashing, "drive_response", crash_before_effect)
    with pytest.raises(SimulatedProcessCrash):
        await crashing.process_durable_commands(session_id, run_id)

    stored_after_crash = await crashing.repository.get_run(run_id)
    assert stored_after_crash is not None
    assert [item["command_id"] for item in stored_after_crash.command_queue] == [
        "answer-before-crash"
    ]

    restarted_model = TextModel("Recovered without losing the answer.")
    restarted = AgentHarness.for_database(
        harness_db,
        model_gateway=restarted_model,
        workspace_factory=lambda _session: _workspace(tmp_path),
        lease_owner="response-crash-worker",
    )
    assert await restarted.recover() == 1
    recovered = await restarted.snapshot(session_id)
    assert recovered.current_run is not None
    assert recovered.current_run.status == "completed"
    assert len(restarted_model.invocations) == 1


@pytest.mark.asyncio
async def test_recovery_reuses_an_acknowledged_answer_after_response_commit(
    harness_db, tmp_path
) -> None:
    asking_model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="ask-1",
                name="ask_user",
                arguments_delta=(
                    '{"questions":[{"question":"Continue?","header":"Confirm",'
                    '"options":[{"label":"Yes","description":"Continue"},'
                    '{"label":"No","description":"Stop"}]}]}'
                ),
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        ),
    )
    first = AgentHarness.for_database(
        harness_db,
        model_gateway=asking_model,
        workspace_factory=lambda _session: _workspace(tmp_path),
        lease_owner="response-commit-worker",
    )
    opened = await first.open_session(_open_request())
    session_id = str(opened.session.id)
    await first.dispatch(
        session_id,
        PromptCommand(command_id="prompt-before-crash", text="Ask me."),
    )
    waiting = await first.snapshot(session_id)
    assert waiting.current_run is not None
    run_id = str(waiting.current_run.id)
    assert await first.repository.release_run_lease(
        run_id,
        owner="response-commit-worker",
    )
    await first.repository.enqueue_command(
        session_id,
        RespondCommand(
            command_id="answer-committed-before-crash",
            interaction_id="tool:ask-1",
            response={"answers": {"Continue?": "Yes"}},
        ),
    )
    generation = await first.repository.claim_run(
        run_id,
        owner="response-commit-worker",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    assert generation is not None
    first.repository.bind_run_fence(
        run_id,
        owner="response-commit-worker",
        generation=generation,
    )
    await first.repository.commit_interaction_response(
        session_id,
        run_id=run_id,
        command_id="answer-committed-before-crash",
        interaction_id="tool:ask-1",
        response={
            "request_id": "tool:ask-1",
            "answers": {"Continue?": "Yes"},
        },
    )

    committed = await first.repository.get_run(run_id)
    assert committed is not None
    assert committed.command_queue == []
    assert await first.repository.release_run_lease(
        run_id,
        owner="response-commit-worker",
    )

    restarted_model = TextModel("Recovered from the committed answer.")
    restarted = AgentHarness.for_database(
        harness_db,
        model_gateway=restarted_model,
        workspace_factory=lambda _session: _workspace(tmp_path),
        lease_owner="response-recovery-worker",
    )
    assert await restarted.recover() == 1
    recovered = await restarted.snapshot(session_id)
    assert recovered.current_run is not None
    assert recovered.current_run.status == "completed"
    assert recovered.pending_interaction is None
    assert len(restarted_model.invocations) == 1
    assert [
        entry.payload.interaction_id
        for entry in recovered.entries
        if entry.type == "interaction_response"
    ] == ["tool:ask-1"]


@pytest.mark.asyncio
async def test_recovery_skips_a_stale_response_before_the_current_response(
    harness_db, tmp_path
) -> None:
    asking_model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="ask-1",
                name="ask_user",
                arguments_delta=(
                    '{"questions":[{"question":"Continue?","header":"Confirm",'
                    '"options":[{"label":"Yes","description":"Continue"},'
                    '{"label":"No","description":"Stop"}]}]}'
                ),
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        ),
    )
    first = AgentHarness.for_database(
        harness_db,
        model_gateway=asking_model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await first.open_session(_open_request())
    session_id = str(opened.session.id)
    await first.dispatch(
        session_id,
        PromptCommand(command_id="prompt-before-crash", text="Ask me."),
    )
    waiting = await first.snapshot(session_id)
    assert waiting.current_run is not None
    run_id = str(waiting.current_run.id)
    assert await first.repository.release_run_lease(
        run_id,
        owner=first._lease_owner(),
    )
    await first.repository.enqueue_command(
        session_id,
        RespondCommand(
            command_id="stale-response",
            interaction_id="tool:older-ask",
            response={"answers": {"Continue?": "No"}},
        ),
    )
    await first.repository.enqueue_command(
        session_id,
        RespondCommand(
            command_id="current-response",
            interaction_id="tool:ask-1",
            response={"answers": {"Continue?": "Yes"}},
        ),
    )

    restarted_model = TextModel("Recovered after the current response.")
    restarted = AgentHarness.for_database(
        harness_db,
        model_gateway=restarted_model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )

    assert await restarted.recover() == 1
    recovered = await restarted.snapshot(session_id)
    assert recovered.current_run is not None
    assert recovered.current_run.status == "completed"
    assert [
        entry.payload.interaction_id
        for entry in recovered.entries
        if entry.type == "interaction_response"
    ] == ["tool:ask-1"]


@pytest.mark.asyncio
async def test_multiple_ask_user_calls_pause_once_for_each_answer(
    harness_db, tmp_path
) -> None:
    model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="ask-1",
                name="ask_user",
                arguments_delta=(
                    '{"questions":[{"question":"First?","header":"First",'
                    '"options":[{"label":"Yes","description":"Continue"},'
                    '{"label":"No","description":"Stop"}]}]}'
                ),
            ),
            ToolCallDelta(
                index=1,
                call_id="ask-2",
                name="ask_user",
                arguments_delta=(
                    '{"questions":[{"question":"Second?","header":"Second",'
                    '"options":[{"label":"A","description":"Choose A"},'
                    '{"label":"B","description":"Choose B"}]}]}'
                ),
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        ),
        (
            TextDelta(text="Both answers received."),
            CompletionMetadata(response_id="response-2", finish_reason="stop"),
        ),
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)

    await harness.dispatch(
        session_id,
        PromptCommand(command_id="two-questions", text="Ask both questions."),
    )
    first = await harness.snapshot(session_id)
    assert first.pending_interaction is not None
    assert first.pending_interaction.interaction_id == "tool:ask-1"

    await harness.dispatch(
        session_id,
        RespondCommand(
            command_id="answer-first",
            interaction_id="tool:ask-1",
            response={"answers": {"First?": "Yes"}},
        ),
    )
    second = await harness.snapshot(session_id)

    assert second.current_run is not None
    assert second.current_run.status == "waiting_user"
    assert second.pending_interaction is not None
    assert second.pending_interaction.interaction_id == "tool:ask-2"
    assert len(model.invocations) == 1

    await harness.dispatch(
        session_id,
        RespondCommand(
            command_id="answer-second",
            interaction_id="tool:ask-2",
            response={"answers": {"Second?": "A"}},
        ),
    )
    completed = await harness.snapshot(session_id)
    assert completed.current_run is not None
    assert completed.current_run.status == "completed"
    assert len(model.invocations) == 2
    assert [
        entry.payload.interaction_id
        for entry in completed.entries
        if entry.type == "interaction_request"
    ] == ["tool:ask-1", "tool:ask-2"]
    assert [
        entry.payload.interaction_id
        for entry in completed.entries
        if entry.type == "interaction_response"
    ] == ["tool:ask-1", "tool:ask-2"]


@pytest.mark.asyncio
async def test_recover_unknown_bash_effect_waits_for_user_without_replay(
    harness_db, tmp_path
) -> None:
    model = TextModel("should not be invoked")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    run = await harness.repository.create_run(str(opened.session.id))
    await harness.repository.update_run(
        str(run.id),
        status="running",
        phase="tools",
        checkpoint=create_checkpoint(
            harness_version=HARNESS_VERSION,
            phase="tools",
            history_revision=0,
            in_flight_tools=(
                {
                    "call_id": "bash-1",
                    "name": "bash",
                    "arguments": {"command": "touch marker.txt"},
                    "replay_policy": "never",
                },
            ),
        ),
    )

    recovered = await harness.recover()
    snapshot = await harness.snapshot(str(opened.session.id))

    assert recovered == 1
    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "waiting_user"
    assert [entry.type for entry in snapshot.entries] == [
        "notice",
        "interaction_request",
    ]
    assert snapshot.entries[1].payload.interaction_id == "recovery:bash-1"
    assert [item.model_dump() for item in snapshot.tool_progress] == [
        {
            "call_id": "bash-1",
            "name": "bash",
            "status": "interaction_required",
        }
    ]
    assert snapshot.pending_interaction is not None
    assert snapshot.pending_interaction.interaction_id == "recovery:bash-1"
    assert model.invocations == []


@pytest.mark.asyncio
async def test_approved_bash_rejects_changed_cwd_assessment_before_execution(
    harness_db, tmp_path
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    current = tmp_path / "current"
    current.symlink_to(first, target_is_directory=True)

    class RecordingBackend(LocalWorkspaceBackend):
        def __init__(self) -> None:
            super().__init__(
                working_directory=tmp_path,
                read_roots=(tmp_path,),
                write_roots=(tmp_path,),
                sandbox_runner=None,
            )
            self.executed_cwds: list[Path] = []

        async def run_command(self, *, cwd, **_kwargs):
            working_directory = self.policy.require_allowed_dir(cwd)
            self.executed_cwds.append(working_directory)
            (working_directory / "executed.txt").write_text(
                "executed\n", encoding="utf-8"
            )
            return {
                "exit_code": 0,
                "stdout": "",
                "stderr": "",
                "cwd": str(working_directory),
            }

    backend = RecordingBackend()
    workspace = WorkspaceRuntime(backend)
    model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="bash-1",
                name="bash",
                arguments_delta=(
                    '{"command":"rm -f harmless && printf executed > '
                    'executed.txt","cwd":"current"}'
                ),
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        ),
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: workspace,
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)

    await harness.dispatch(
        session_id,
        PromptCommand(command_id="request-dangerous-bash", text="Run it."),
    )
    waiting = await harness.snapshot(session_id)
    assert waiting.pending_interaction is not None
    risk = waiting.pending_interaction.request["risk"]
    assert risk["boundary"]["working_directory"] == str(first.resolve())
    assert len(risk["assessment_fingerprint"]) == 64

    current.unlink()
    current.symlink_to(second, target_is_directory=True)

    with pytest.raises(ValueError, match="approval.*assessment.*changed"):
        await harness.dispatch(
            session_id,
            RespondCommand(
                command_id="approve-dangerous-bash",
                interaction_id="tool:bash-1",
                response={"approved": True},
            ),
        )

    still_waiting = await harness.snapshot(session_id)
    assert still_waiting.current_run is not None
    assert still_waiting.current_run.status == "waiting_user"
    assert still_waiting.pending_interaction is not None
    assert backend.executed_cwds == []
    assert not (second / "executed.txt").exists()


@pytest.mark.asyncio
async def test_corrupt_checkpoint_restores_pending_bash_approval_fence(
    harness_db, tmp_path
) -> None:
    marker = tmp_path / "restored-approval.txt"

    class RecordingBackend(LocalWorkspaceBackend):
        async def run_command(self, **_kwargs):
            marker.write_text("executed\n", encoding="utf-8")
            return {
                "exit_code": 0,
                "stdout": "",
                "stderr": "",
                "cwd": str(tmp_path),
            }

    workspace = WorkspaceRuntime(
        RecordingBackend(
            working_directory=tmp_path,
            read_roots=(tmp_path,),
            write_roots=(tmp_path,),
            sandbox_runner=None,
        )
    )
    call = ToolCall(
        call_id="bash-1",
        name="bash",
        arguments={"command": "rm -f harmless && touch restored-approval.txt"},
    )
    pending = await workspace.execute(call)
    assert pending.interaction is not None
    interaction = {
        "request_id": pending.interaction.request_id,
        "call_id": call.call_id,
        "kind": pending.interaction.kind,
        "questions": list(pending.interaction.questions),
        "risk": pending.interaction.risk,
    }
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=TextModel("Approval recovered."),
        workspace_factory=lambda _session: workspace,
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await harness.repository.create_run(session_id)
    await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "assistant",
            "content": [],
            "tool_calls": [
                {
                    "call_id": call.call_id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
            ],
        },
    )
    request = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="interaction_request",
        payload={"interaction_id": "tool:bash-1", "request": interaction},
    )
    await harness.repository.update_run(
        str(run.id),
        status="waiting_user",
        phase="interaction",
        checkpoint={
            "schema_version": 0,
            "harness_version": HARNESS_VERSION,
            "history_revision": request.sequence,
            "phase": "interaction",
        },
    )

    assert await harness.recover() == 1
    await harness.dispatch(
        session_id,
        RespondCommand(
            command_id="approve-restored-bash",
            interaction_id="tool:bash-1",
            response={"approved": True},
        ),
    )

    assert marker.read_text(encoding="utf-8") == "executed\n"
    snapshot = await harness.snapshot(session_id)
    tool_entry = next(
        entry
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "tool"
    )
    assert tool_entry.payload.is_error is False


@pytest.mark.asyncio
async def test_corrupt_checkpoint_restores_registered_tool_replay_policies(
    harness_db, tmp_path
) -> None:
    calls = [
        {
            "call_id": "bash-1",
            "name": "bash",
            "arguments": {"command": "rm -f harmless"},
        },
        {"call_id": "read-1", "name": "read", "arguments": {"path": "a.txt"}},
        {
            "call_id": "edit-1",
            "name": "edit",
            "arguments": {"path": "a.txt", "old_text": "a", "new_text": "b"},
        },
        {
            "call_id": "write-1",
            "name": "write",
            "arguments": {"path": "b.txt", "content": "b"},
        },
        {
            "call_id": "ask-1",
            "name": "ask_user",
            "arguments": {"questions": []},
        },
    ]
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=TextModel("unused"),
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await harness.repository.create_run(session_id)
    await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={"role": "assistant", "content": [], "tool_calls": calls},
    )
    request = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="interaction_request",
        payload={
            "interaction_id": "tool:bash-1",
            "request": {
                "request_id": "tool:bash-1",
                "call_id": "bash-1",
                "kind": "confirmation",
            },
        },
    )
    await harness.repository.update_run(
        str(run.id),
        status="waiting_user",
        phase="interaction",
        checkpoint={
            "schema_version": 0,
            "harness_version": HARNESS_VERSION,
            "history_revision": request.sequence,
            "phase": "interaction",
        },
    )

    assert await harness.recover() == 1

    restored = await harness.repository.get_run(str(run.id))
    assert restored is not None
    assert [
        (item["name"], item["replay_policy"])
        for item in restored.checkpoint["in_flight_tools"]
    ] == [
        ("bash", "never"),
        ("read", "safe"),
        ("edit", "verify"),
        ("write", "verify"),
        ("ask_user", "safe"),
    ]


@pytest.mark.asyncio
async def test_recovery_retry_fences_and_executes_dangerous_bash_once(
    harness_db, tmp_path
) -> None:
    class SimulatedProcessCrash(BaseException):
        pass

    marker = tmp_path / "recovery-retry.txt"

    class CrashAfterExecutionBackend(LocalWorkspaceBackend):
        async def run_command(self, *, cwd, **_kwargs):
            working_directory = self.policy.require_allowed_dir(cwd)
            with marker.open("a", encoding="utf-8") as stream:
                stream.write("executed\n")
            assert working_directory == tmp_path.resolve()
            raise SimulatedProcessCrash

    backend = CrashAfterExecutionBackend(
        working_directory=tmp_path,
        read_roots=(tmp_path,),
        write_roots=(tmp_path,),
        sandbox_runner=None,
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=TextModel("must not continue after the crash"),
        workspace_factory=lambda _session: WorkspaceRuntime(backend),
        lease_owner="recovery-retry-worker",
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await harness.repository.create_run(session_id)
    await harness.repository.update_run(
        str(run.id),
        status="running",
        phase="tools",
        checkpoint=create_checkpoint(
            harness_version=HARNESS_VERSION,
            phase="tools",
            history_revision=0,
            in_flight_tools=(
                {
                    "call_id": "bash-1",
                    "name": "bash",
                    "arguments": {
                        "command": (
                            "rm -f harmless && printf executed >> recovery-retry.txt"
                        )
                    },
                    "replay_policy": "never",
                },
            ),
        ),
    )
    await harness.recover()

    with pytest.raises(SimulatedProcessCrash):
        await harness.dispatch(
            session_id,
            RespondCommand(
                command_id="retry-dangerous-bash",
                interaction_id="recovery:bash-1",
                response={"choice": "retry"},
            ),
        )

    assert marker.read_text(encoding="utf-8") == "executed\n"
    entries_after_crash = await harness.repository.list_entries(session_id)
    assert [
        entry.payload["interaction_id"]
        for entry in entries_after_crash
        if entry.type == "interaction_response"
    ] == ["recovery:bash-1"]
    assert not any(
        entry.type == "message"
        and entry.payload.get("role") == "tool"
        and entry.payload.get("call_id") == "bash-1"
        for entry in entries_after_crash
    )

    recovered = AgentHarness.for_database(
        harness_db,
        model_gateway=TextModel("must still wait for recovery"),
        workspace_factory=lambda _session: _workspace(tmp_path),
        lease_owner="recovery-retry-worker",
    )
    assert await recovered.recover() == 1
    snapshot = await recovered.snapshot(session_id)

    assert marker.read_text(encoding="utf-8") == "executed\n"
    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "waiting_user"
    assert snapshot.pending_interaction is not None
    assert snapshot.pending_interaction.interaction_id == "recovery:bash-1"


@pytest.mark.asyncio
async def test_crash_during_approved_bash_recovers_as_unknown_effect_without_replay(
    harness_db, tmp_path
) -> None:
    class SimulatedProcessCrash(BaseException):
        pass

    call = ToolCall(
        call_id="bash-1",
        name="bash",
        arguments={"command": "rm -f harmless && printf 'executed\\n' >> marker.txt"},
    )
    marker = tmp_path / "marker.txt"
    executions = 0
    crashing_workspace = _workspace(tmp_path)

    pending = await crashing_workspace.execute(call)
    assert pending.interaction is not None

    async def execute_then_crash(
        tool_call,
        *,
        cancellation=None,
        interaction_response=None,
    ):
        nonlocal executions
        assert tool_call == call
        assert interaction_response is not None
        assert interaction_response["approved"] is True
        executions += 1
        marker.write_text("executed\n", encoding="utf-8")
        raise SimulatedProcessCrash

    crashing_workspace.execute = execute_then_crash
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=TextModel("should not be invoked"),
        workspace_factory=lambda _session: crashing_workspace,
        lease_owner="crash-recovery-worker",
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await harness.repository.create_run(session_id)
    await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "assistant",
            "content": [],
            "tool_calls": [
                {
                    "call_id": call.call_id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
            ],
        },
    )
    interaction = {
        "request_id": pending.interaction.request_id,
        "call_id": call.call_id,
        "kind": pending.interaction.kind,
        "questions": list(pending.interaction.questions),
        "risk": pending.interaction.risk,
    }
    request = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="interaction_request",
        payload={"interaction_id": "tool:bash-1", "request": interaction},
    )
    await harness.repository.update_run(
        str(run.id),
        status="waiting_user",
        phase="interaction",
        checkpoint={
            **create_checkpoint(
                harness_version=HARNESS_VERSION,
                phase="interaction",
                history_revision=request.sequence,
                in_flight_tools=(
                    {
                        "call_id": call.call_id,
                        "name": call.name,
                        "arguments": call.arguments,
                        "replay_policy": "never",
                    },
                ),
                interaction=interaction,
            ),
            "waiting_call": {
                "call_id": call.call_id,
                "name": call.name,
                "arguments": call.arguments,
            },
            "pending_calls": [],
        },
        tool_progress=[
            {
                "call_id": call.call_id,
                "name": call.name,
                "status": "interaction_required",
            }
        ],
    )

    with pytest.raises(SimulatedProcessCrash):
        await harness.dispatch(
            session_id,
            RespondCommand(
                command_id="approve-bash",
                interaction_id="tool:bash-1",
                response={"approved": True},
            ),
        )

    crashed_run = await harness.repository.get_run(str(run.id))
    assert crashed_run is not None
    assert crashed_run.command_queue == []
    assert crashed_run.status == "running"
    assert crashed_run.phase == "tools"
    assert crashed_run.checkpoint["in_flight_tools"] == [
        {
            "call_id": call.call_id,
            "name": call.name,
            "arguments": call.arguments,
            "replay_policy": "never",
            "execution_started": True,
        }
    ]
    response_entries = [
        entry
        for entry in await harness.repository.list_entries(session_id)
        if entry.type == "interaction_response"
    ]
    assert len(response_entries) == 1
    assert response_entries[0].payload["interaction_id"] == "tool:bash-1"
    assert executions == 1
    assert marker.read_text(encoding="utf-8") == "executed\n"

    recovered_harness = AgentHarness.for_database(
        harness_db,
        model_gateway=TextModel("should not be invoked"),
        workspace_factory=lambda _session: _workspace(tmp_path),
        lease_owner="crash-recovery-worker",
    )
    recovered = await recovered_harness.recover()
    snapshot = await recovered_harness.snapshot(session_id)

    assert recovered == 1
    assert executions == 1
    assert marker.read_text(encoding="utf-8") == "executed\n"
    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "waiting_user"
    assert snapshot.pending_interaction is not None
    assert snapshot.pending_interaction.interaction_id == "recovery:bash-1"
    assert [
        option["id"] for option in snapshot.pending_interaction.request["options"]
    ] == [
        "inspect",
        "retry",
        "cancel",
    ]
    assert any(
        entry.type == "notice" and entry.payload.code == "unknown_tool_effect"
        for entry in snapshot.entries
    )
    assert all(
        entry.payload.interaction_id != "tool:bash-1"
        for entry in snapshot.entries
        if entry.type == "interaction_request"
        and entry.sequence > response_entries[0].sequence
    )


@pytest.mark.asyncio
async def test_recovery_interaction_preserves_other_in_flight_tools(
    harness_db, tmp_path
) -> None:
    (tmp_path / "sample.txt").write_text("alpha\n", encoding="utf-8")
    model = TextModel("Recovery complete.")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await harness.repository.create_run(session_id)
    assistant = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "assistant",
            "content": [],
            "tool_calls": [
                {
                    "call_id": "read-1",
                    "name": "read",
                    "arguments": {"path": "sample.txt"},
                },
                {
                    "call_id": "bash-1",
                    "name": "bash",
                    "arguments": {"command": "touch marker.txt"},
                },
            ],
        },
    )
    await harness.repository.update_run(
        str(run.id),
        status="running",
        phase="tools",
        checkpoint=create_checkpoint(
            harness_version=HARNESS_VERSION,
            phase="tools",
            history_revision=assistant.sequence,
            in_flight_tools=(
                {
                    "call_id": "read-1",
                    "name": "read",
                    "arguments": {"path": "sample.txt"},
                    "replay_policy": "safe",
                },
                {
                    "call_id": "bash-1",
                    "name": "bash",
                    "arguments": {"command": "touch marker.txt"},
                    "replay_policy": "never",
                },
            ),
        ),
    )

    await harness.recover()
    await harness.dispatch(
        session_id,
        RespondCommand(
            command_id="inspect-before-continuing",
            interaction_id="recovery:bash-1",
            response={"choice": "inspect"},
        ),
    )
    snapshot = await harness.snapshot(session_id)

    tool_entries = [
        entry
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "tool"
    ]
    assert [entry.payload.call_id for entry in tool_entries] == ["read-1", "bash-1"]
    assert "alpha" in tool_entries[0].payload.content[0]["text"]
    assert len(model.invocations) == 1
    call_ids = [
        getattr(item, "call_id", None) for item in model.invocations[0].input_items
    ]
    assert call_ids.count("bash-1") == 2
    assert call_ids.count("read-1") == 2


@pytest.mark.asyncio
async def test_user_cancel_commits_interrupted_results_for_unfinished_tools(
    harness_db, tmp_path
) -> None:
    model = TextModel("Continued after cancellation.")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await harness.repository.create_run(session_id)
    assistant = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "assistant",
            "content": [],
            "tool_calls": [
                {
                    "call_id": "bash-1",
                    "name": "bash",
                    "arguments": {"command": "sleep 30"},
                }
            ],
        },
    )
    await harness.repository.update_run(
        str(run.id),
        status="running",
        phase="tools",
        checkpoint=create_checkpoint(
            harness_version=HARNESS_VERSION,
            phase="tools",
            history_revision=assistant.sequence,
            in_flight_tools=(
                {
                    "call_id": "bash-1",
                    "name": "bash",
                    "arguments": {"command": "sleep 30"},
                    "replay_policy": "never",
                },
            ),
        ),
    )

    await harness.dispatch(
        session_id,
        CancelCommand(command_id="cancel-1", reason="user_cancelled"),
    )
    cancelled = await harness.snapshot(session_id)

    assert cancelled.current_run is not None
    assert cancelled.current_run.status == "cancelled"
    notices = [
        entry
        for entry in cancelled.entries
        if entry.type == "notice" and entry.payload.code == "user_cancelled"
    ]
    assert len(notices) == 1
    tool_entries = [
        entry
        for entry in cancelled.entries
        if entry.type == "message" and entry.payload.role == "tool"
    ]
    assert len(tool_entries) == 1
    assert tool_entries[0].payload.call_id == "bash-1"
    assert tool_entries[0].payload.is_error is True
    assert "interrupted" in tool_entries[0].payload.content[0]["text"]

    await harness.dispatch(
        session_id,
        PromptCommand(command_id="after-cancel", text="Continue."),
    )
    call_ids = [
        getattr(item, "call_id", None) for item in model.invocations[0].input_items
    ]
    assert call_ids.count("bash-1") == 2


@pytest.mark.asyncio
async def test_serial_batch_cancellation_commits_every_unfinished_tool_result(
    harness_db, tmp_path
) -> None:
    model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="cancel-1",
                name="cancel_serial_batch",
                arguments_delta="{}",
            ),
            ToolCallDelta(
                index=1,
                call_id="read-1",
                name="read",
                arguments_delta='{"path":"first.txt"}',
            ),
            ToolCallDelta(
                index=2,
                call_id="read-2",
                name="read",
                arguments_delta='{"path":"second.txt"}',
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        )
    )
    backend = LocalWorkspaceBackend(
        working_directory=tmp_path,
        read_roots=(tmp_path,),
        write_roots=(tmp_path,),
        sandbox_runner=None,
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: WorkspaceRuntime(
            backend,
            extra_tools=(_CancelSerialBatchTool(),),
        ),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)

    await harness.dispatch(
        session_id,
        PromptCommand(command_id="cancel-serial-batch", text="Run the batch."),
    )
    snapshot = await harness.snapshot(session_id)

    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "cancelled"
    tool_entries = [
        entry
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "tool"
    ]
    assert [entry.payload.call_id for entry in tool_entries] == [
        "cancel-1",
        "read-1",
        "read-2",
    ]
    assert [entry.payload.is_error for entry in tool_entries] == [False, True, True]
    assert all(
        "cancelled" in entry.payload.content[0]["text"] for entry in tool_entries[1:]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "initial_content"),
    [
        (
            "edit",
            {"path": "target.txt", "old_text": "alpha", "new_text": "beta"},
            "alpha",
        ),
        ("write", {"path": "target.txt", "content": "beta"}, "alpha"),
    ],
)
async def test_verify_recovery_retry_executes_without_bash_approval_fingerprint(
    harness_db,
    tmp_path,
    monkeypatch,
    tool_name: str,
    arguments: dict,
    initial_content: str,
) -> None:
    target = tmp_path / "target.txt"
    target.write_text(initial_content, encoding="utf-8")
    model = TextModel("Recovery completed.")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await harness.repository.create_run(session_id)
    call = {
        "call_id": f"{tool_name}-1",
        "name": tool_name,
        "arguments": arguments,
    }
    assistant = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={"role": "assistant", "content": [], "tool_calls": [call]},
    )
    request = {
        "kind": "recovery",
        "call_id": call["call_id"],
        "tool_name": tool_name,
        "message": "The interrupted operation has an unknown effect.",
        "options": [
            {"id": "inspect", "label": "Inspect", "description": "Inspect state."},
            {"id": "retry", "label": "Retry", "description": "Retry once."},
            {"id": "cancel", "label": "Cancel", "description": "Cancel the run."},
        ],
    }
    request_entry = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="interaction_request",
        payload={
            "interaction_id": f"recovery:{call['call_id']}",
            "request": request,
        },
    )
    await harness.repository.update_run(
        str(run.id),
        status="waiting_user",
        phase="interaction",
        checkpoint={
            **create_checkpoint(
                harness_version=HARNESS_VERSION,
                phase="interaction",
                history_revision=request_entry.sequence,
                in_flight_tools=({**call, "replay_policy": "verify"},),
                interaction=request,
            ),
            "waiting_call": call,
            "recovery_interaction": request,
        },
        tool_progress=[
            {
                "call_id": call["call_id"],
                "name": tool_name,
                "status": "interaction_required",
            }
        ],
    )
    captured_replay_policy = None
    original_begin = harness.repository.begin_approved_tool_execution

    async def capture_replay_policy(*args, **kwargs):
        nonlocal captured_replay_policy
        captured_replay_policy = kwargs.get("replay_policy")
        return await original_begin(*args, **kwargs)

    monkeypatch.setattr(
        harness.repository,
        "begin_approved_tool_execution",
        capture_replay_policy,
    )

    await harness.dispatch(
        session_id,
        RespondCommand(
            command_id=f"retry-{tool_name}",
            interaction_id=f"recovery:{call['call_id']}",
            response={"choice": "retry"},
        ),
    )
    snapshot = await harness.snapshot(session_id)

    assert assistant.sequence < request_entry.sequence
    assert captured_replay_policy == "verify"
    assert target.read_text(encoding="utf-8") == "beta"
    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "completed"
    assert any(
        entry.type == "message"
        and entry.payload.role == "tool"
        and entry.payload.call_id == call["call_id"]
        and entry.payload.is_error is False
        for entry in snapshot.entries
    )


@pytest.mark.asyncio
async def test_explicit_cancel_publishes_terminal_run_and_starts_follow_up(
    harness_db, tmp_path
) -> None:
    model = TextModel("Follow-up completed.")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    cancelled_run = await harness.repository.create_run(session_id)
    await harness.repository.update_run(
        str(cancelled_run.id),
        status="running",
        phase="model",
    )
    await harness.dispatch(
        session_id,
        FollowUpCommand(command_id="follow-after-cancel", text="Continue next."),
    )
    events = harness.events(session_id)
    await anext(events)

    try:
        await harness.dispatch(
            session_id,
            CancelCommand(command_id="cancel-current", reason="user_cancelled"),
        )

        snapshot = await harness.snapshot(session_id)
        assert snapshot.current_run is not None
        assert snapshot.current_run.id != cancelled_run.id
        assert snapshot.current_run.status == "completed"
        terminal_events = []
        for _ in range(12):
            event = await asyncio.wait_for(anext(events), timeout=0.5)
            if (
                event.type == "run.updated"
                and event.run_id == cancelled_run.id
                and event.status == "cancelled"
            ):
                terminal_events.append(event)
                break
        assert len(terminal_events) == 1
        assert len(model.invocations) == 1
    finally:
        await events.aclose()


@pytest.mark.asyncio
async def test_recovery_consumes_a_durable_cancel_and_starts_follow_up(
    harness_db, tmp_path
) -> None:
    first = AgentHarness.for_database(
        harness_db,
        model_gateway=TextModel("unused"),
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await first.open_session(_open_request())
    session_id = str(opened.session.id)
    cancelled_run = await first.repository.create_run(session_id)
    await first.repository.update_run(
        str(cancelled_run.id),
        status="running",
        phase="model",
    )
    await first.repository.enqueue_command(
        session_id,
        FollowUpCommand(command_id="follow-after-restart", text="Continue next."),
    )
    await first.repository.enqueue_command(
        session_id,
        CancelCommand(command_id="cancel-before-restart", reason="user_cancelled"),
    )

    restarted_model = TextModel("Recovered follow-up completed.")
    restarted = AgentHarness.for_database(
        harness_db,
        model_gateway=restarted_model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    events = restarted.events(session_id)
    await anext(events)

    try:
        assert await restarted.recover() == 1
        snapshot = await restarted.snapshot(session_id)
        assert snapshot.current_run is not None
        assert snapshot.current_run.id != cancelled_run.id
        assert snapshot.current_run.status == "completed"
        stored = await restarted.repository.get_run(str(cancelled_run.id))
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.command_queue == []
        for _ in range(12):
            event = await asyncio.wait_for(anext(events), timeout=0.5)
            if (
                event.type == "run.updated"
                and event.run_id == cancelled_run.id
                and event.status == "cancelled"
            ):
                break
        else:
            pytest.fail("recovery did not publish the cancelled Run")
        assert len(restarted_model.invocations) == 1
    finally:
        await events.aclose()


@pytest.mark.asyncio
async def test_recovery_starts_follow_up_left_after_terminal_run(
    harness_db, tmp_path
) -> None:
    first = AgentHarness.for_database(
        harness_db,
        model_gateway=TextModel("unused"),
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await first.open_session(_open_request())
    session_id = str(opened.session.id)
    completed_run = await first.repository.create_run(session_id)
    await first.repository.update_run(
        str(completed_run.id),
        status="completed",
        phase=None,
        termination_reason="completed",
    )
    await first.repository.enqueue_command(
        session_id,
        FollowUpCommand(
            command_id="follow-after-terminal-crash",
            text="Continue after restart.",
        ),
    )

    restarted_model = TextModel("Recovered follow-up completed.")
    restarted = AgentHarness.for_database(
        harness_db,
        model_gateway=restarted_model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )

    assert await restarted.recover() == 1
    snapshot = await restarted.snapshot(session_id)
    stored_session = await restarted.repository.get_session(session_id)

    assert snapshot.current_run is not None
    assert snapshot.current_run.id != completed_run.id
    assert snapshot.current_run.status == "completed"
    assert stored_session is not None
    assert stored_session.command_queue == []
    assert len(restarted_model.invocations) == 1
    assert [
        part["text"]
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "user"
        for part in entry.payload.content
        if part.get("type") == "text"
    ] == ["Continue after restart."]


@pytest.mark.asyncio
async def test_steer_racing_run_completion_becomes_an_immediate_follow_up(
    harness_db, tmp_path, monkeypatch
) -> None:
    model = TextModel("Completed after the boundary steer.")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    finishing_run = await harness.repository.create_run(session_id)
    original_enqueue = harness.repository.enqueue_command

    async def finish_before_enqueue(target_session_id, command):
        await harness.repository.terminalize_run(
            str(finishing_run.id),
            status="completed",
            phase=None,
            termination_reason="completed",
        )
        return await original_enqueue(target_session_id, command)

    monkeypatch.setattr(
        harness.repository,
        "enqueue_command",
        finish_before_enqueue,
    )

    await harness.dispatch(
        session_id,
        SteerCommand(command_id="boundary-steer", text="Include this update."),
    )
    snapshot = await harness.snapshot(session_id)
    stored_session = await harness.repository.get_session(session_id)

    assert snapshot.current_run is not None
    assert snapshot.current_run.id != finishing_run.id
    assert snapshot.current_run.status == "completed"
    assert stored_session is not None
    assert stored_session.command_queue == []
    assert len(model.invocations) == 1
    assert [
        part["text"]
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "user"
        for part in entry.payload.content
        if part.get("type") == "text"
    ] == ["Include this update."]


@pytest.mark.asyncio
async def test_recovery_continues_when_steer_follows_committed_final_answer(
    harness_db, tmp_path
) -> None:
    first = AgentHarness.for_database(
        harness_db,
        model_gateway=TextModel("unused"),
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await first.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await first.repository.create_run(session_id)
    user = await first.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "user",
            "content": [{"type": "text", "text": "Start."}],
        },
    )
    await first.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "assistant",
            "content": [{"type": "text", "text": "Initial final answer."}],
        },
    )
    await first.repository.update_run(
        str(run.id),
        status="running",
        phase="model",
        checkpoint=create_checkpoint(
            harness_version=HARNESS_VERSION,
            phase="model",
            history_revision=user.sequence,
        ),
    )
    await first.repository.enqueue_command(
        session_id,
        SteerCommand(
            command_id="steer-after-final-crash",
            text="Also inspect the metadata.",
        ),
    )

    restarted_model = TextModel("Updated after steer.")
    restarted = AgentHarness.for_database(
        harness_db,
        model_gateway=restarted_model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )

    assert await restarted.recover() == 1
    snapshot = await restarted.snapshot(session_id)
    stored_run = await restarted.repository.get_run(str(run.id))

    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "completed"
    assert stored_run is not None
    assert stored_run.command_queue == []
    assert len(restarted_model.invocations) == 1
    user_texts = [
        part["text"]
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "user"
        for part in entry.payload.content
        if part.get("type") == "text"
    ]
    assert user_texts == ["Start.", "Also inspect the metadata."]
    assert any(
        getattr(item, "text", None) == "Also inspect the metadata."
        for item in restarted_model.invocations[0].input_items
    )
    assert snapshot.entries[-1].payload.content == [
        {"type": "text", "text": "Updated after steer."}
    ]


@pytest.mark.asyncio
async def test_recovery_final_answer_safe_point_atomically_commits_a_new_steer(
    harness_db, tmp_path, monkeypatch
) -> None:
    first = AgentHarness.for_database(
        harness_db,
        model_gateway=TextModel("unused"),
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await first.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await first.repository.create_run(session_id)
    await first.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={"role": "user", "content": [{"type": "text", "text": "Start."}]},
    )
    await first.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "assistant",
            "content": [{"type": "text", "text": "Committed answer."}],
        },
    )
    await first.repository.update_run(
        str(run.id),
        status="running",
        phase="model",
    )

    restarted_model = TextModel("Updated after the boundary steer.")
    restarted = AgentHarness.for_database(
        harness_db,
        model_gateway=restarted_model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    original_safe_point = restarted.repository.commit_steers_or_complete_run

    async def enqueue_at_safe_point(target_session_id, *, run_id):
        await restarted.repository.enqueue_command(
            target_session_id,
            SteerCommand(
                command_id="steer-at-recovery-safe-point",
                text="Include the late metadata.",
            ),
        )
        return await original_safe_point(target_session_id, run_id=run_id)

    monkeypatch.setattr(
        restarted.repository,
        "commit_steers_or_complete_run",
        enqueue_at_safe_point,
    )

    assert await restarted.recover() == 1
    snapshot = await restarted.snapshot(session_id)
    stored_run = await restarted.repository.get_run(str(run.id))

    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "completed"
    assert stored_run is not None
    assert stored_run.command_queue == []
    assert len(restarted_model.invocations) == 1
    assert [
        part["text"]
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "user"
        for part in entry.payload.content
        if part.get("type") == "text"
    ] == ["Start.", "Include the late metadata."]


@pytest.mark.asyncio
async def test_recovery_checkpoint_fallback_is_visible_before_model_retry(
    harness_db, tmp_path
) -> None:
    model = TextModel("Continued from history.")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await harness.repository.create_run(session_id)
    user = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={"role": "user", "content": [{"type": "text", "text": "Go."}]},
    )
    await harness.repository.update_run(
        str(run.id),
        status="running",
        phase="model",
        checkpoint=create_checkpoint(
            harness_version="foreign-version",
            phase="model",
            history_revision=user.sequence,
        ),
    )

    await harness.recover()
    snapshot = await harness.snapshot(session_id)

    assert [entry.type for entry in snapshot.entries] == [
        "message",
        "notice",
        "message",
    ]
    assert snapshot.entries[1].payload.code == "recovery_state_ignored"


@pytest.mark.asyncio
async def test_corrupt_checkpoint_preserves_pending_interaction_from_history(
    harness_db, tmp_path
) -> None:
    model = TextModel("must not continue without the user's answer")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await harness.repository.create_run(session_id)
    await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "assistant",
            "content": [],
            "tool_calls": [
                {
                    "call_id": "ask-1",
                    "name": "ask_user",
                    "arguments": {
                        "questions": [
                            {
                                "question": "Proceed?",
                                "header": "Confirm",
                                "options": [
                                    {"label": "Yes", "description": "Continue"},
                                    {"label": "No", "description": "Stop"},
                                ],
                            }
                        ]
                    },
                }
            ],
        },
    )
    await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="interaction_request",
        payload={
            "interaction_id": "tool:ask-1",
            "request": {
                "kind": "question",
                "call_id": "ask-1",
                "questions": ["Proceed?"],
            },
        },
    )
    await harness.repository.update_run(
        str(run.id),
        status="waiting_user",
        phase="interaction",
        checkpoint={"corrupt": True},
    )

    recovered = await harness.recover()
    snapshot = await harness.snapshot(session_id)

    assert recovered == 1
    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "waiting_user"
    assert snapshot.pending_interaction is not None
    assert snapshot.pending_interaction.interaction_id == "tool:ask-1"
    assert model.invocations == []

    await harness.dispatch(
        session_id,
        RespondCommand(
            command_id="answer-after-restart",
            interaction_id="tool:ask-1",
            response={"answers": {"Proceed?": "Yes"}},
        ),
    )
    completed = await harness.snapshot(session_id)
    assert completed.current_run is not None
    assert completed.current_run.status == "completed"
    assert len(model.invocations) == 1


@pytest.mark.asyncio
async def test_recovery_does_not_repeat_an_already_committed_final_answer(
    harness_db, tmp_path
) -> None:
    model = TextModel("duplicate answer")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await harness.repository.create_run(session_id)
    await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "user",
            "content": [{"type": "text", "text": "Question"}],
        },
    )
    await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "assistant",
            "content": [{"type": "text", "text": "Already committed answer"}],
        },
    )
    await harness.repository.update_run(
        str(run.id), status="running", phase="model", checkpoint=None
    )

    recovered = await harness.recover()
    snapshot = await harness.snapshot(session_id)

    assert recovered == 1
    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "completed"
    assert model.invocations == []
    answers = [
        entry.payload.content
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "assistant"
    ]
    assert answers == [[{"type": "text", "text": "Already committed answer"}]]


@pytest.mark.asyncio
async def test_recovery_executes_tools_from_an_already_committed_assistant_message(
    harness_db, tmp_path
) -> None:
    (tmp_path / "sample.txt").write_text("alpha\n", encoding="utf-8")
    model = TextModel("Recovered after the tool result.")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await harness.repository.create_run(session_id)
    await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "assistant",
            "content": [],
            "tool_calls": [
                {
                    "call_id": "read-1",
                    "name": "read",
                    "arguments": {"path": "sample.txt"},
                }
            ],
        },
    )
    await harness.repository.update_run(
        str(run.id), status="running", phase="model", checkpoint=None
    )

    recovered = await harness.recover()
    snapshot = await harness.snapshot(session_id)

    assert recovered == 1
    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "completed"
    tool_entries = [
        entry
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "tool"
    ]
    assert len(tool_entries) == 1
    assert tool_entries[0].payload.call_id == "read-1"
    assert "alpha" in tool_entries[0].payload.content[0]["text"]
    assert len(model.invocations) == 1
    assert any(
        getattr(item, "call_id", None) == "read-1"
        for item in model.invocations[0].input_items
    )


@pytest.mark.asyncio
async def test_model_draft_recovery_notices_and_clears_draft_before_retry(
    harness_db, tmp_path
) -> None:
    model = RecoveryInspectingModel("Retried from permanent history.")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await harness.repository.create_run(session_id)
    user = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={"role": "user", "content": [{"type": "text", "text": "Go."}]},
    )
    await harness.repository.update_run(
        str(run.id),
        status="running",
        phase="model",
        draft={"text": "partial text", "reasoning": "partial reasoning"},
        checkpoint=create_checkpoint(
            harness_version=HARNESS_VERSION,
            phase="model",
            history_revision=user.sequence,
        ),
    )
    model.repository = harness.repository
    model.session_id = session_id
    model.run_id = str(run.id)

    await harness.recover()

    assert model.observed_draft is None
    assert model.observed_notice_codes == ["model_stream_interrupted"]


@pytest.mark.asyncio
async def test_recover_same_version_read_commits_result_then_continues_model(
    harness_db, tmp_path
) -> None:
    (tmp_path / "sample.txt").write_text("alpha\n", encoding="utf-8")
    model = TextModel("The recovered read contains alpha.")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    run = await harness.repository.create_run(str(opened.session.id))
    assistant = await harness.repository.append_entry(
        str(opened.session.id),
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "assistant",
            "content": [],
            "tool_calls": [
                {
                    "call_id": "read-1",
                    "name": "read",
                    "arguments": {"path": "sample.txt"},
                }
            ],
        },
    )
    await harness.repository.update_run(
        str(run.id),
        status="running",
        phase="tools",
        checkpoint=create_checkpoint(
            harness_version=HARNESS_VERSION,
            phase="tools",
            history_revision=assistant.sequence,
            in_flight_tools=(
                {
                    "call_id": "read-1",
                    "name": "read",
                    "arguments": {"path": "sample.txt"},
                    "replay_policy": "safe",
                },
            ),
        ),
    )

    recovered = await harness.recover()
    snapshot = await harness.snapshot(str(opened.session.id))

    assert recovered == 1
    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "completed"
    assert [
        entry.payload.role for entry in snapshot.entries if entry.type == "message"
    ] == [
        "assistant",
        "tool",
        "assistant",
    ]
    assert "alpha" in snapshot.entries[1].payload.content[0]["text"]
    assert len(model.invocations) == 1


@pytest.mark.asyncio
async def test_process_recovery_reuses_responses_continuation(
    harness_db, tmp_path
) -> None:
    (tmp_path / "sample.txt").write_text("alpha\n", encoding="utf-8")
    model = TextModel("The recovered read contains alpha.")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await harness.repository.create_run(session_id)
    user = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "user",
            "content": [{"type": "text", "text": "Read it."}],
        },
    )
    target = model_target_from_snapshot({"target": _model_target()})
    continuation = ResponsesContinuation(
        response_id="response-1",
        output_items=(
            {
                "type": "function_call",
                "call_id": "read-1",
                "name": "read",
                "arguments": '{"path":"sample.txt"}',
            },
        ),
        canonical_input_count=1,
        canonical_input_digest=canonical_input_prefix_digest(
            (TextPart(text="Read it."),)
        ),
        target=target.continuation_target(),
    )
    assistant = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "assistant",
            "content": [],
            "tool_calls": [
                {
                    "call_id": "read-1",
                    "name": "read",
                    "arguments": {"path": "sample.txt"},
                }
            ],
        },
    )
    assert assistant.sequence == user.sequence + 1
    await harness.repository.update_run(
        str(run.id),
        status="running",
        phase="tools",
        checkpoint=create_checkpoint(
            harness_version=HARNESS_VERSION,
            phase="tools",
            history_revision=assistant.sequence,
            continuation=continuation.to_private_dict(),
            in_flight_tools=(
                {
                    "call_id": "read-1",
                    "name": "read",
                    "arguments": {"path": "sample.txt"},
                    "replay_policy": "safe",
                },
            ),
        ),
    )

    recovered = await harness.recover()

    assert recovered == 1
    assert len(model.invocations) == 1
    assert model.invocations[0].continuation == continuation


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "before", "expected", "recovery_state"),
    [
        (
            "write",
            {"path": "sample.txt", "content": "new\n"},
            "old\n",
            "new\n",
            "executed_after_verification",
        ),
        (
            "write",
            {"path": "sample.txt", "content": "new\n"},
            "new\n",
            "new\n",
            "already_applied",
        ),
        (
            "edit",
            {
                "path": "sample.txt",
                "old_text": "old",
                "new_text": "new",
            },
            "old\n",
            "new\n",
            "executed_after_verification",
        ),
        (
            "edit",
            {
                "path": "sample.txt",
                "old_text": "old",
                "new_text": "new",
            },
            "new\n",
            "new\n",
            "already_applied",
        ),
    ],
)
async def test_recoverable_write_tools_verify_before_replay(
    harness_db,
    tmp_path,
    tool_name,
    arguments,
    before,
    expected,
    recovery_state,
) -> None:
    path = tmp_path / "sample.txt"
    path.write_text(before, encoding="utf-8")
    model = TextModel("Recovery complete.")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    await _create_recoverable_tool_run(
        harness,
        str(opened.session.id),
        ToolCall(call_id="mutation-1", name=tool_name, arguments=arguments),
    )

    await harness.recover()
    snapshot = await harness.snapshot(str(opened.session.id))

    assert path.read_text(encoding="utf-8") == expected
    tool_entry = next(
        entry
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "tool"
    )
    assert recovery_state in tool_entry.payload.content[0]["text"]


@pytest.mark.asyncio
async def test_ambiguous_edit_recovery_waits_for_user(harness_db, tmp_path) -> None:
    (tmp_path / "sample.txt").write_text("old and new\n", encoding="utf-8")
    model = TextModel("should not run")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    await _create_recoverable_tool_run(
        harness,
        str(opened.session.id),
        ToolCall(
            call_id="edit-1",
            name="edit",
            arguments={
                "path": "sample.txt",
                "old_text": "old",
                "new_text": "new",
                "replace_all": True,
            },
        ),
    )

    await harness.recover()
    snapshot = await harness.snapshot(str(opened.session.id))

    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "waiting_user"
    assert snapshot.pending_interaction is not None
    assert snapshot.pending_interaction.request["kind"] == "recovery"
    assert model.invocations == []


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["corrupt", "foreign", "compacted"])
async def test_untrusted_responses_continuation_is_ignored(
    harness_db, tmp_path, case
) -> None:
    model = TextModel("Continued from permanent history.")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await harness.repository.create_run(session_id)
    current_target = model_target_from_snapshot({"target": _model_target()})
    current_text = "Continue."
    entry = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "user",
            "content": [{"type": "text", "text": current_text}],
        },
    )

    if case == "corrupt":
        private_continuation = {
            "response_id": "response-1",
            "output_items": "not-a-list",
        }
    else:
        continuation_target = current_target
        digest_text = current_text
        if case == "foreign":
            foreign_target = _model_target()
            foreign_target["target_revision"] = "foreign-revision"
            continuation_target = model_target_from_snapshot({"target": foreign_target})
        else:
            digest_text = "Old context."
            compaction = await harness.repository.append_entry(
                session_id,
                run_id=str(run.id),
                entry_type="compaction",
                payload={
                    "summary": "The prior context was compacted.",
                    "through_sequence": entry.sequence,
                },
            )
            entry = await harness.repository.append_entry(
                session_id,
                run_id=str(run.id),
                entry_type="message",
                payload={
                    "role": "user",
                    "content": [{"type": "text", "text": "Continue after summary."}],
                },
            )
            assert entry.sequence == compaction.sequence + 1
        private_continuation = ResponsesContinuation(
            response_id="response-1",
            output_items=(),
            canonical_input_count=1,
            canonical_input_digest=canonical_input_prefix_digest(
                (TextPart(text=digest_text),)
            ),
            target=continuation_target.continuation_target(),
        ).to_private_dict()

    await harness.repository.update_run(
        str(run.id),
        status="running",
        phase="model",
        checkpoint=create_checkpoint(
            harness_version=HARNESS_VERSION,
            phase="model",
            history_revision=entry.sequence,
            continuation=private_continuation,
        ),
    )

    recovered = await harness.recover()

    assert recovered == 1
    assert len(model.invocations) == 1
    assert model.invocations[0].continuation is None


@pytest.mark.asyncio
async def test_recovery_inspect_choice_does_not_replay_unknown_bash(
    harness_db, tmp_path
) -> None:
    marker = tmp_path / "marker.txt"
    model = TextModel("I will inspect the current state safely.")
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    run = await harness.repository.create_run(str(opened.session.id))
    await harness.repository.update_run(
        str(run.id),
        status="running",
        phase="tools",
        checkpoint=create_checkpoint(
            harness_version=HARNESS_VERSION,
            phase="tools",
            history_revision=0,
            in_flight_tools=(
                {
                    "call_id": "bash-1",
                    "name": "bash",
                    "arguments": {"command": "touch marker.txt"},
                    "replay_policy": "never",
                },
            ),
        ),
    )
    await harness.recover()

    await harness.dispatch(
        str(opened.session.id),
        RespondCommand(
            command_id="recovery-answer",
            interaction_id="recovery:bash-1",
            response={"choice": "inspect"},
        ),
    )
    snapshot = await harness.snapshot(str(opened.session.id))

    assert marker.exists() is False
    assert snapshot.current_run is not None
    assert snapshot.current_run.status == "completed"
    tool_entries = [
        entry
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "tool"
    ]
    assert "not replayed" in tool_entries[0].payload.content[0]["text"]


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


async def _create_recoverable_tool_run(harness, session_id: str, call: ToolCall):
    run = await harness.repository.create_run(session_id)
    assistant = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "assistant",
            "content": [],
            "tool_calls": [
                {
                    "call_id": call.call_id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
            ],
        },
    )
    await harness.repository.update_run(
        str(run.id),
        status="running",
        phase="tools",
        checkpoint=create_checkpoint(
            harness_version=HARNESS_VERSION,
            phase="tools",
            history_revision=assistant.sequence,
            in_flight_tools=(
                {
                    "call_id": call.call_id,
                    "name": call.name,
                    "arguments": call.arguments,
                    "replay_policy": "verify",
                },
            ),
        ),
    )
    return run


def _open_request(*, supports_vision: bool = False) -> OpenSessionRequest:
    return OpenSessionRequest(
        user_id="user-1",
        workspace_id="00000000-0000-0000-0000-000000000001",
        prompt_snapshot={"content": "Help the user."},
        model={
            "target": _model_target(),
            "capabilities": {"supports_vision": supports_vision},
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
