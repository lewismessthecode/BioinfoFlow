from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import UploadFile

from app.services.agent_harness.assets import AgentHarnessAttachmentService
from app.services.agent_harness.contracts import (
    CancelCommand,
    InputAttachmentRefPart,
    InputTextPart,
    MessageCommand,
    OpenSessionRequest,
    SteerCommand,
)
from app.services.agent_harness.contracts import RespondCommand
from app.services.agent_harness.harness import AgentHarness
from app.services.agent_harness.loop import (
    HARNESS_VERSION,
    LoopLimits,
    _tool_result_history_output,
)
from app.services.agent_harness.model_target import model_target_from_snapshot
from app.services.agent_harness.recovery import create_checkpoint
from app.services.agent_harness.tools import ToolCall, ToolResult, ToolSpec
from app.services.agent_harness.workspace_runtime import (
    LocalWorkspaceBackend,
    WorkspaceRuntime,
)
from tests.test_agent_harness.run_test_helpers import create_agent_run
from app.services.model_runtime.contracts import (
    canonical_input_prefix_digest,
    CompletionMetadata,
    ImagePart,
    ModelEvent,
    ReasoningDelta,
    ResponsesContinuation,
    TextPart,
    TextDelta,
    ToolCallDelta,
    ToolCallPart,
    ToolResultPart,
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


def _message(
    command_id: str,
    text: str,
    *,
    attachment_ids=(),
) -> MessageCommand:
    return MessageCommand(
        command_id=command_id,
        parts=[
            InputTextPart(text=text),
            *(InputAttachmentRefPart(attachment_id=item) for item in attachment_ids),
        ],
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


def _active(snapshot):
    assert snapshot.active_run is not None
    return snapshot.active_run


def _text_values(payload) -> list[str]:
    return [part.text for part in payload.parts if part.type == "text"]


def _tool_result(payload):
    return next(part for part in payload.parts if part.type == "tool_result")


async def _durable_tool_output_text(harness, session_id: str, call_id: str) -> str:
    entries = await harness.repository.list_entries(session_id)
    for entry in entries:
        if entry.type != "message" or not isinstance(entry.payload, dict):
            continue
        for part in entry.payload.get("parts") or []:
            if not isinstance(part, dict) or part.get("type") != "tool_result":
                continue
            if part.get("call_id") != call_id:
                continue
            output = part.get("output")
            assert isinstance(output, dict) and output.get("type") == "text"
            return str(output.get("text") or "")
    raise AssertionError(f"durable tool result not found: {call_id}")


def _history_text(role: str, text: str) -> dict:
    return {
        "role": role,
        "parts": [{"id": "text:0", "type": "text", "text": text}],
    }


def test_terminal_tool_history_keeps_resolved_environment() -> None:
    result = ToolResult(
        call_id="call-1",
        tool_name="bash",
        status="failed",
        replay_policy="verify",
        output={"environment_id": "ssh:gpu"},
        error="command failed",
    )

    assert _tool_result_history_output(result) == {
        "environment_id": "ssh:gpu",
        "error": "command failed",
    }


def _history_calls(calls: list[dict], *, group_id: str | None = None) -> dict:
    group_id = group_id or f"tool-group:{calls[0]['call_id']}"
    parts = []
    for call in calls:
        name = call["name"]
        arguments = call.get("arguments", {})
        parts.append(
            {
                "id": f"tool-call:{call['call_id']}",
                "type": "tool_call",
                "call_id": call["call_id"],
                "group_id": group_id,
                "execution_mode": "serial",
                "name": name,
                "display_name": name,
                "category": {
                    "read": "read",
                    "bash": "command",
                    "edit": "edit",
                    "write": "write",
                    "ask_user": "interaction",
                }.get(name, "other"),
                "summary": name,
                "arguments": arguments,
            }
        )
    return {"role": "assistant", "parts": parts}


async def _append_tool_call_entry(harness, session_id: str, run_id: str, calls):
    entry_id = str(uuid4())
    return await harness.repository.append_entry(
        session_id,
        run_id=run_id,
        entry_type="message",
        entry_id=entry_id,
        payload=_history_calls(calls, group_id=entry_id),
    )


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
    run = await create_agent_run(harness.repository, str(opened.session.id))
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


@pytest.mark.asyncio
async def test_reasoning_deltas_preserve_public_trace_boundaries(
    harness_db,
    tmp_path,
) -> None:
    model = ScriptedModel(
        (
            ReasoningDelta(
                text="Inspecting ",
                provider="openai",
                model="gpt-5",
                source="reasoning_content",
            ),
            ReasoningDelta(
                text="the inputs.",
                provider="openai",
                model="gpt-5",
                source="reasoning_content",
            ),
            ReasoningDelta(
                text="A separate summary.",
                provider="openai",
                model="gpt-5",
                source="summary_text",
                truncated=True,
            ),
            TextDelta(text="Done."),
            CompletionMetadata(response_id="response-reasoning", finish_reason="stop"),
        )
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())

    await harness.dispatch(
        str(opened.session.id),
        _message("reasoning-trace", "Explain your inspection."),
    )
    snapshot = await harness.snapshot(str(opened.session.id))

    assistant = next(
        entry
        for entry in reversed(snapshot.entries)
        if entry.type == "message" and entry.payload.role == "assistant"
    )
    traces = [
        part for part in assistant.payload.parts if part.type == "reasoning_trace"
    ]
    assert [(trace.text, trace.source, trace.truncated) for trace in traces] == [
        ("Inspecting the inputs.", "reasoning_content", False),
        ("A separate summary.", "summary_text", True),
    ]
    assert all(trace.provider == "openai" for trace in traces)
    assert all(trace.model == "gpt-5" for trace in traces)
    assert all(trace.started_at is not None for trace in traces)
    assert all(trace.completed_at is not None for trace in traces)


@pytest.mark.asyncio
async def test_real_update_plan_tool_persists_plan_without_public_tool_messages(
    harness_db,
    tmp_path,
) -> None:
    model = ScriptedModel(
        (
            TextDelta(text="I will start with a short plan."),
            ToolCallDelta(
                index=0,
                call_id="plan-1",
                name="update_plan",
                arguments_delta=(
                    '{"explanation":"Initial analysis plan","plan":['
                    '{"step":"Inspect inputs","status":"in_progress"},'
                    '{"step":"Run workflow","status":"pending"}]}'
                ),
            ),
            CompletionMetadata(response_id="response-plan", finish_reason="tool_calls"),
        ),
        (
            ToolCallDelta(
                index=0,
                call_id="plan-2",
                name="update_plan",
                arguments_delta=(
                    '{"explanation":"Execution plan updated","plan":['
                    '{"step":"Inspect inputs","status":"completed"},'
                    '{"step":"Run workflow","status":"in_progress"}]}'
                ),
            ),
            CompletionMetadata(
                response_id="response-plan-2", finish_reason="tool_calls"
            ),
        ),
        (
            TextDelta(text="I have started with the input inspection."),
            CompletionMetadata(response_id="response-final", finish_reason="stop"),
        ),
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())

    await harness.dispatch(
        str(opened.session.id),
        _message("plan-request", "Create and execute a plan."),
    )
    snapshot = await harness.snapshot(str(opened.session.id))

    assert "update_plan" in {
        definition.name for definition in model.invocations[0].tools
    }
    plan_entries = [entry for entry in snapshot.entries if entry.type == "plan"]
    assert len(plan_entries) == 2
    assert [entry.payload.revision for entry in plan_entries] == [1, 2]
    assert len({entry.payload.plan_id for entry in plan_entries}) == 1
    assert plan_entries[0].payload.title == "Initial analysis plan"
    assert plan_entries[1].payload.title == "Execution plan updated"
    assert [item.text for item in plan_entries[1].payload.items] == [
        "Inspect inputs",
        "Run workflow",
    ]
    message_parts = [
        part
        for entry in snapshot.entries
        if entry.type == "message"
        for part in entry.payload.parts
    ]
    assert all(
        not (
            part.type in {"tool_call", "tool_result"}
            and getattr(part, "name", None) == "update_plan"
        )
        for part in message_parts
    )
    assert all(
        getattr(part, "call_id", None) not in {"plan-1", "plan-2"}
        for part in message_parts
    )
    assert len(model.invocations) == 3
    private_exchange = [
        item
        for item in model.invocations[1].input_items
        if isinstance(item, (ToolCallPart, ToolResultPart)) and item.call_id == "plan-1"
    ]
    assert private_exchange == [
        ToolCallPart(
            call_id="plan-1",
            name="update_plan",
            arguments={
                "explanation": "Initial analysis plan",
                "plan": [
                    {"step": "Inspect inputs", "status": "in_progress"},
                    {"step": "Run workflow", "status": "pending"},
                ],
            },
        ),
        ToolResultPart(
            call_id="plan-1",
            output='{"plan_id":"plan:'
            + str(_latest_run(snapshot).id)
            + '","revision":1,"status":"completed"}',
        ),
    ]
    assert _text_values(snapshot.entries[-1].payload) == [
        "I have started with the input inspection."
    ]
    assert _latest_run(snapshot).status == "completed"


@pytest.mark.asyncio
async def test_invalid_update_plan_is_returned_privately_for_model_correction(
    harness_db,
    tmp_path,
) -> None:
    model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="plan-invalid",
                name="update_plan",
                arguments_delta='{"plan":[{"status":"in_progress"}]}',
            ),
            CompletionMetadata(
                response_id="response-plan-invalid",
                finish_reason="tool_calls",
            ),
        ),
        (
            ToolCallDelta(
                index=0,
                call_id="plan-corrected",
                name="update_plan",
                arguments_delta=(
                    '{"plan":[{"step":"Finish the task",'
                    '"status":"completed"}]}'
                ),
            ),
            CompletionMetadata(
                response_id="response-plan-corrected",
                finish_reason="tool_calls",
            ),
        ),
        (
            TextDelta(text="Done.", phase="final_answer"),
            CompletionMetadata(response_id="response-final", finish_reason="stop"),
        ),
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())

    await harness.dispatch(
        str(opened.session.id),
        _message("repair-plan", "Complete the task."),
    )
    snapshot = await harness.snapshot(str(opened.session.id))

    assert _latest_run(snapshot).status == "completed"
    plans = [entry for entry in snapshot.entries if entry.type == "plan"]
    assert len(plans) == 1
    assert plans[0].payload.items[0].text == "Finish the task"
    correction_input = [
        item
        for item in model.invocations[1].input_items
        if isinstance(item, (ToolCallPart, ToolResultPart))
        and item.call_id == "plan-invalid"
    ]
    assert correction_input == [
        ToolCallPart(
            call_id="plan-invalid",
            name="update_plan",
            arguments={"plan": [{"status": "in_progress"}]},
        ),
        ToolResultPart(
            call_id="plan-invalid",
            output='{"error":"missing required tool arguments: step"}',
            is_error=True,
        ),
    ]
    assert _text_values(snapshot.entries[-1].payload) == ["Done."]


class _CancelSerialBatchTool:
    spec = ToolSpec(
        name="cancel_serial_batch",
        description="Cancel the current serial tool batch.",
        input_schema={"type": "object", "additionalProperties": False},
        replay_policy="safe",
        display_name="Cancel batch",
        category="other",
        summary="Cancel batch",
        serial=True,
    )

    async def run(self, _arguments, context):
        context.cancellation.set()
        return {"cancel_requested": True}


class _ControlledBatchTool:
    def __init__(self, *, serial: bool) -> None:
        self.spec = ToolSpec(
            name="controlled_batch",
            description="Wait until the test releases this tool call.",
            input_schema={
                "type": "object",
                "properties": {"label": {"type": "string"}},
                "required": ["label"],
                "additionalProperties": False,
            },
            replay_policy="safe",
            display_name="Controlled batch",
            category="other",
            summary="Process item",
            input_summary_fields=("label",),
            serial=serial,
        )
        self.started = {"first": asyncio.Event(), "second": asyncio.Event()}
        self.released = {"first": asyncio.Event(), "second": asyncio.Event()}

    async def run(self, arguments, _context):
        label = str(arguments["label"])
        self.started[label].set()
        await self.released[label].wait()
        return {"label": label}


class _ProjectedTool:
    def __init__(self) -> None:
        self.spec = ToolSpec(
            name="read_command",
            description="Exercise declared public presentation metadata.",
            input_schema={
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "path": {"type": "string"},
                    "command": {"type": "string"},
                },
                "required": ["label", "path", "command"],
                "additionalProperties": False,
            },
            replay_policy="safe",
            display_name="Inspect dataset",
            category="workflow",
            summary="Inspect dataset",
            input_summary_fields=("label",),
        )
        self.started = asyncio.Event()
        self.released = asyncio.Event()

    async def run(self, arguments, _context):
        self.started.set()
        await self.released.wait()
        return {"label": arguments["label"]}


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
async def test_message_commits_user_and_assistant_messages(
    harness_db, tmp_path
) -> None:
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
        _message("command-1", "Inspect the project."),
    )
    snapshot = await harness.snapshot(str(opened.session.id))

    assert _latest_run(snapshot).status == "completed"
    assert [entry.type for entry in snapshot.entries] == ["message", "message"]
    assert snapshot.entries[0].payload.role == "user"
    assert _text_values(snapshot.entries[0].payload) == ["Inspect the project."]
    assert snapshot.entries[1].payload.role == "assistant"
    assert _text_values(snapshot.entries[1].payload) == ["I found the answer."]
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
            _message("stream-draft", "Stream an answer."),
        )
    )
    await asyncio.wait_for(model.paused.wait(), timeout=1)

    streaming = await harness.snapshot(session_id)
    assert streaming.active_run is not None
    assert streaming.active_run.run.phase == "model"
    assert streaming.active_run.assistant_draft is not None
    text_part = next(
        part
        for part in streaming.active_run.assistant_draft.parts
        if part.type == "text"
    )
    assert text_part.text == "durable partial"
    assert text_part.end_offset == len("durable partial".encode("utf-8"))

    model.release.set()
    await asyncio.wait_for(dispatch, timeout=1)
    completed = await harness.snapshot(session_id)
    assert _latest_run(completed).status == "completed"
    assert completed.active_run is None
    assert _text_values(completed.entries[-1].payload) == ["durable partial answer"]


@pytest.mark.asyncio
async def test_message_attachments_are_durable_and_enter_model_context(
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
        _message(
            "with-attachments",
            "Inspect these files.",
            attachment_ids=[text_attachment.id, image_attachment.id],
        ),
    )

    snapshot = await harness.snapshot(str(opened.session.id))
    assert _latest_run(snapshot).status == "completed", _latest_run(snapshot).error
    message = snapshot.entries[0].payload
    attachments = [part for part in message.parts if part.type == "attachment_ref"]
    assert [str(part.attachment_id) for part in attachments] == [
        str(text_attachment.id),
        str(image_attachment.id),
    ]
    assert [part.type for part in message.parts] == [
        "text",
        "attachment_ref",
        "attachment_ref",
    ]
    assert attachments[0].filename == "notes.txt"
    assert attachments[1].filename == "pixel.png"
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
    old_run = await create_agent_run(harness.repository, session_id)
    old_message = await harness.repository.append_entry(
        session_id,
        run_id=str(old_run.id),
        entry_type="message",
        payload={
            "role": "user",
            "parts": [
                {
                    "id": "text:0",
                    "type": "text",
                    "text": "Inspect the old upload.",
                },
                {
                    "id": f"attachment:{old_attachment_id}",
                    "type": "attachment_ref",
                    "attachment_id": old_attachment_id,
                    "filename": "old-upload.txt",
                    "kind": "file",
                    "size_bytes": 0,
                },
            ],
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
        _message("after-compaction", "Continue."),
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
        _message(
            "unsupported-image",
            "Inspect this image.",
            attachment_ids=[image_attachment.id],
        ),
    )

    snapshot = await harness.snapshot(str(opened.session.id))
    assert model.invocations == []
    assert _latest_run(snapshot).status == "failed"
    assert _latest_run(snapshot).termination_reason == "model_vision_unsupported"
    assert _latest_run(snapshot).error is not None
    assert _latest_run(snapshot).error.model_dump() == {
        "code": "model_vision_unsupported",
        "message": "The selected model does not support image input.",
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

    await harness.dispatch(str(opened.session.id), _message("command-1", "Read it."))
    snapshot = await harness.snapshot(str(opened.session.id))

    assert [
        entry.payload.role for entry in snapshot.entries if entry.type == "message"
    ] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ], _latest_run(snapshot).error
    public_result = _tool_result(snapshot.entries[2].payload)
    assert public_result.call_id == "read-1"
    assert public_result.summary is not None
    assert [detail.kind for detail in public_result.public_details] == ["output"]
    assert "alpha" not in str(public_result.model_dump(mode="json"))
    assert "alpha" in await _durable_tool_output_text(
        harness, str(opened.session.id), "read-1"
    )
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
        _message("continuation", "Read it."),
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
    events = harness.events(session_id)
    assert (await anext(events)).type == "snapshot"
    old_run = await create_agent_run(repository, session_id)
    await repository.append_entry(
        session_id,
        run_id=str(old_run.id),
        entry_type="message",
        payload=_history_text("user", "Old context"),
    )
    await repository.update_run(str(old_run.id), status="completed")

    await harness.dispatch(
        session_id,
        _message("command-overflow", "Continue the work."),
    )
    published = []
    while True:
        event = await asyncio.wait_for(anext(events), timeout=0.5)
        published.append(event)
        if event.type == "run.updated" and event.run.status in {
            "completed",
            "failed",
            "cancelled",
        }:
            break
    await events.aclose()
    snapshot = await harness.snapshot(session_id)

    assert all(entry.type != "compaction" for entry in snapshot.entries)
    assert all(
        not (event.type == "entry.committed" and event.entry.type == "compaction")
        for event in published
    )
    stored_entries = await repository.list_entries(session_id)
    assert [entry.type for entry in stored_entries].count("compaction") == 1
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
    old_run = await create_agent_run(harness.repository, session_id)
    await harness.repository.append_entry(
        session_id,
        run_id=str(old_run.id),
        entry_type="message",
        payload=_history_text("user", "Old context"),
    )
    await harness.repository.update_run(str(old_run.id), status="completed")

    await harness.dispatch(
        session_id,
        _message("overflow-twice", "Continue."),
    )
    snapshot = await harness.snapshot(session_id)

    assert _latest_run(snapshot).status == "failed"
    assert all(entry.type != "compaction" for entry in snapshot.entries)
    assert [
        entry.type for entry in await harness.repository.list_entries(session_id)
    ].count("compaction") == 1
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

    await harness.dispatch(str(opened.session.id), _message("timeout", "Answer."))
    snapshot = await harness.snapshot(str(opened.session.id))

    assert _latest_run(snapshot).status == "completed"
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

    await harness.dispatch(str(opened.session.id), _message("timeout", "Answer."))
    snapshot = await harness.snapshot(str(opened.session.id))

    assert _latest_run(snapshot).status == "failed"
    assert _latest_run(snapshot).termination_reason == "model_attempt_timeout"
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
    run = await create_agent_run(harness.repository, session_id)
    user = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload=_history_text("user", "Go."),
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

    assert _latest_run(snapshot).termination_reason == "run_timeout_exceeded"
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

    await harness.dispatch(str(opened.session.id), _message("budget", "Work."))
    snapshot = await harness.snapshot(str(opened.session.id))

    assert _latest_run(snapshot).termination_reason == "token_budget_exceeded"
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

    await harness.dispatch(str(opened.session.id), _message("checkpoint", "Ask me."))
    latest = await harness.repository.get_latest_run(str(opened.session.id))
    snapshot = await harness.snapshot(str(opened.session.id))

    assert latest is not None
    assert latest.status == "waiting_user"
    assert latest.checkpoint["harness_version"] == HARNESS_VERSION
    assert latest.checkpoint["history_revision"] >= 2
    assistant = next(
        entry
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "assistant"
    )
    group_id = str(assistant.id)
    assert latest.checkpoint["in_flight_tools"] == [
        {
            "call_id": "ask-1",
            "group_id": group_id,
            "execution_mode": "serial",
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
    assert latest.checkpoint["history_revision"] == 3
    assert _active(snapshot).assistant_draft is None
    assert len(_active(snapshot).tool_progress) == 1
    assert _active(snapshot).tool_progress[0].call_id == "ask-1"
    assert _active(snapshot).tool_progress[0].group_id == group_id
    assert _active(snapshot).tool_progress[0].status == "interaction_required"
    assert _active(snapshot).tool_progress[0].revision == 3
    assert _active(snapshot).pending_interaction is not None
    assert _active(snapshot).pending_interaction.interaction_id == "tool:ask-1"

    tokens = list(harness._run_tokens)
    assert tokens == []


@pytest.mark.asyncio
async def test_serial_tool_batch_exposes_only_the_current_call_as_running(
    harness_db, tmp_path
) -> None:
    tool = _ControlledBatchTool(serial=True)
    model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="controlled-1",
                name="controlled_batch",
                arguments_delta='{"label":"first"}',
            ),
            ToolCallDelta(
                index=1,
                call_id="controlled-2",
                name="controlled_batch",
                arguments_delta='{"label":"second"}',
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        ),
        (
            TextDelta(text="Done.", phase="final_answer"),
            CompletionMetadata(response_id="response-2", finish_reason="stop"),
        ),
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: WorkspaceRuntime(
            LocalWorkspaceBackend(
                working_directory=tmp_path,
                read_roots=(tmp_path,),
                write_roots=(tmp_path,),
                sandbox_runner=None,
            ),
            extra_tools=(tool,),
        ),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)

    dispatch = asyncio.create_task(
        harness.dispatch(session_id, _message("serial-progress", "Run both."))
    )
    await asyncio.wait_for(tool.started["first"].wait(), timeout=1)

    first_snapshot = await harness.snapshot(session_id)
    first_progress = _active(first_snapshot).tool_progress
    assistant = next(
        entry
        for entry in first_snapshot.entries
        if entry.type == "message" and entry.payload.role == "assistant"
    )
    assert [item.status for item in first_progress] == ["running", "pending"]
    assert {item.group_id for item in first_progress} == {str(assistant.id)}
    assert {item.execution_mode for item in first_progress} == {"serial"}
    assert tool.started["second"].is_set() is False

    tool.released["first"].set()
    await asyncio.wait_for(tool.started["second"].wait(), timeout=1)
    second_snapshot = await harness.snapshot(session_id)
    assert [item.status for item in _active(second_snapshot).tool_progress] == [
        "completed",
        "running",
    ]

    tool.released["second"].set()
    await asyncio.wait_for(dispatch, timeout=2)


@pytest.mark.asyncio
async def test_parallel_tool_batch_exposes_each_started_call_as_running(
    harness_db, tmp_path
) -> None:
    tool = _ControlledBatchTool(serial=False)
    model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="controlled-1",
                name="controlled_batch",
                arguments_delta='{"label":"first"}',
            ),
            ToolCallDelta(
                index=1,
                call_id="controlled-2",
                name="controlled_batch",
                arguments_delta='{"label":"second"}',
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        ),
        (
            TextDelta(text="Done.", phase="final_answer"),
            CompletionMetadata(response_id="response-2", finish_reason="stop"),
        ),
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: WorkspaceRuntime(
            LocalWorkspaceBackend(
                working_directory=tmp_path,
                read_roots=(tmp_path,),
                write_roots=(tmp_path,),
                sandbox_runner=None,
            ),
            extra_tools=(tool,),
        ),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)

    dispatch = asyncio.create_task(
        harness.dispatch(session_id, _message("parallel-progress", "Run both."))
    )
    await asyncio.wait_for(tool.started["first"].wait(), timeout=1)
    await asyncio.sleep(0.05)
    if dispatch.done():
        dispatch.result()
    assert tool.started["second"].is_set() is True

    snapshot = await harness.snapshot(session_id)
    progress = _active(snapshot).tool_progress
    assistant = next(
        entry
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "assistant"
    )
    assert [item.status for item in progress] == ["running", "running"]
    assert {item.group_id for item in progress} == {str(assistant.id)}
    assert {
        part.group_id for part in assistant.payload.parts if part.type == "tool_call"
    } == {str(assistant.id)}
    assert {item.execution_mode for item in progress} == {"parallel"}

    tool.released["first"].set()
    tool.released["second"].set()
    await asyncio.wait_for(dispatch, timeout=2)


@pytest.mark.asyncio
async def test_tool_views_use_declared_public_projection_metadata(
    harness_db, tmp_path
) -> None:
    tool = _ProjectedTool()
    model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="projected-1",
                name="read_command",
                arguments_delta=(
                    '{"label":"Sample 42","path":"private/input.txt",'
                    '"command":"cat private/input.txt"}'
                ),
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        ),
        (
            TextDelta(text="Done.", phase="final_answer"),
            CompletionMetadata(response_id="response-2", finish_reason="stop"),
        ),
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: WorkspaceRuntime(
            LocalWorkspaceBackend(
                working_directory=tmp_path,
                read_roots=(tmp_path,),
                write_roots=(tmp_path,),
                sandbox_runner=None,
            ),
            extra_tools=(tool,),
        ),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)

    dispatch = asyncio.create_task(
        harness.dispatch(session_id, _message("declared-projection", "Inspect it."))
    )
    await asyncio.wait_for(tool.started.wait(), timeout=1)

    snapshot = await harness.snapshot(session_id)
    progress = _active(snapshot).tool_progress[0]
    assistant = next(
        entry
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "assistant"
    )
    call = next(part for part in assistant.payload.parts if part.type == "tool_call")

    assert progress.display_name == "Inspect dataset"
    assert progress.category == "workflow"
    assert progress.summary == "Inspect dataset: Sample 42"
    assert call.display_name == progress.display_name
    assert call.category == progress.category
    assert call.summary == progress.summary

    tool.released.set()
    await asyncio.wait_for(dispatch, timeout=2)


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
    await harness.dispatch(session_id, _message("message-1", "Ask me."))

    with pytest.raises(ValueError, match="interaction.*does not match"):
        await harness.dispatch(
            session_id,
            RespondCommand(
                command_id="late-answer",
                interaction_id="tool:ask-from-an-older-request",
                response={"type": "ask_user", "answers": {"Continue?": "Yes"}},
            ),
        )

    still_waiting = await harness.snapshot(session_id)
    assert _active(still_waiting).run.status == "waiting_user"
    assert _active(still_waiting).pending_interaction is not None
    assert _active(still_waiting).pending_interaction.interaction_id == "tool:ask-1"
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
    await harness.dispatch(session_id, _message("message-1", "Ask me."))

    await harness.dispatch(
        session_id,
        RespondCommand(
            command_id="answer-1",
            interaction_id="tool:ask-1",
            response={"type": "ask_user", "answers": {"Continue?": "Yes"}},
        ),
    )

    completed = await harness.snapshot(session_id)
    assert _latest_run(completed).status == "completed"
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
    await harness.dispatch(session_id, _message("message-1", "Ask me."))
    await harness.dispatch(
        session_id,
        _steer("steer-1", "Also inspect the metadata."),
    )

    waiting = await harness.snapshot(session_id)
    assert [
        entry
        for entry in waiting.entries
        if entry.type == "message"
        and entry.payload.role == "user"
        and _text_values(entry.payload) == ["Also inspect the metadata."]
    ] == []

    await harness.dispatch(
        session_id,
        RespondCommand(
            command_id="respond-1",
            interaction_id="tool:ask-1",
            response={"type": "ask_user", "answers": {"Continue?": "Yes"}},
        ),
    )
    completed = await harness.snapshot(session_id)
    steers = [
        entry
        for entry in completed.entries
        if entry.type == "message"
        and entry.payload.role == "user"
        and _text_values(entry.payload) == ["Also inspect the metadata."]
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
        _message("message-before-crash", "Ask me."),
    )
    waiting = await first.snapshot(session_id)
    run_id = str(_active(waiting).run.id)
    assert _active(waiting).run.status == "waiting_user"
    assert await first.repository.release_run_lease(
        run_id,
        owner=first._lease_owner(),
    )
    await first.repository.enqueue_command(
        session_id,
        RespondCommand(
            command_id="respond-before-crash",
            interaction_id="tool:ask-1",
            response={"type": "ask_user", "answers": {"Continue?": "Yes"}},
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
    assert _latest_run(recovered).status == "completed"
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
        _message("message-before-crash", "Ask me."),
    )
    waiting = await first.snapshot(session_id)
    run_id = str(_active(waiting).run.id)
    assert await first.repository.release_run_lease(
        run_id,
        owner="response-crash-worker",
    )
    await first.repository.enqueue_command(
        session_id,
        RespondCommand(
            command_id="answer-before-crash",
            interaction_id="tool:ask-1",
            response={"type": "ask_user", "answers": {"Continue?": "Yes"}},
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
    assert _latest_run(recovered).status == "completed"
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
        _message("message-before-crash", "Ask me."),
    )
    waiting = await first.snapshot(session_id)
    run_id = str(_active(waiting).run.id)
    assert await first.repository.release_run_lease(
        run_id,
        owner="response-commit-worker",
    )
    await first.repository.enqueue_command(
        session_id,
        RespondCommand(
            command_id="answer-committed-before-crash",
            interaction_id="tool:ask-1",
            response={"type": "ask_user", "answers": {"Continue?": "Yes"}},
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
        response={"type": "ask_user", "answers": {"Continue?": "Yes"}},
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
    assert _latest_run(recovered).status == "completed"
    assert recovered.active_run is None
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
        _message("message-before-crash", "Ask me."),
    )
    waiting = await first.snapshot(session_id)
    run_id = str(_active(waiting).run.id)
    assert await first.repository.release_run_lease(
        run_id,
        owner=first._lease_owner(),
    )
    await first.repository.enqueue_command(
        session_id,
        RespondCommand(
            command_id="stale-response",
            interaction_id="tool:older-ask",
            response={"type": "ask_user", "answers": {"Continue?": "No"}},
        ),
    )
    await first.repository.enqueue_command(
        session_id,
        RespondCommand(
            command_id="current-response",
            interaction_id="tool:ask-1",
            response={"type": "ask_user", "answers": {"Continue?": "Yes"}},
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
    assert _latest_run(recovered).status == "completed"
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
        _message("two-questions", "Ask both questions."),
    )
    first = await harness.snapshot(session_id)
    assert _active(first).pending_interaction is not None
    assert _active(first).pending_interaction.interaction_id == "tool:ask-1"

    await harness.dispatch(
        session_id,
        RespondCommand(
            command_id="answer-first",
            interaction_id="tool:ask-1",
            response={"type": "ask_user", "answers": {"First?": "Yes"}},
        ),
    )
    second = await harness.snapshot(session_id)

    assert _active(second).run.status == "waiting_user"
    assert _active(second).pending_interaction is not None
    assert _active(second).pending_interaction.interaction_id == "tool:ask-2"
    assert len(model.invocations) == 1

    await harness.dispatch(
        session_id,
        RespondCommand(
            command_id="answer-second",
            interaction_id="tool:ask-2",
            response={"type": "ask_user", "answers": {"Second?": "A"}},
        ),
    )
    completed = await harness.snapshot(session_id)
    assert _latest_run(completed).status == "completed"
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
    run = await create_agent_run(harness.repository, str(opened.session.id))
    assistant = await _append_tool_call_entry(
        harness,
        str(opened.session.id),
        str(run.id),
        [
            {
                "call_id": "bash-1",
                "name": "bash",
                "arguments": {"command": "touch marker.txt"},
            }
        ],
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
                    "group_id": str(assistant.id),
                    "execution_mode": "parallel",
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
    assert _active(snapshot).run.status == "waiting_user"
    assert [entry.type for entry in snapshot.entries] == [
        "message",
        "notice",
        "interaction_request",
    ]
    assert snapshot.entries[2].payload.interaction_id == "recovery:bash-1"
    assert len(_active(snapshot).tool_progress) == 1
    assert _active(snapshot).tool_progress[0].call_id == "bash-1"
    assert _active(snapshot).tool_progress[0].group_id == str(assistant.id)
    assert _active(snapshot).tool_progress[0].execution_mode == "parallel"
    assert _active(snapshot).tool_progress[0].status == "interaction_required"
    assert _active(snapshot).tool_progress[0].revision == 1
    assert _active(snapshot).pending_interaction is not None
    assert _active(snapshot).pending_interaction.interaction_id == "recovery:bash-1"
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
        _message("request-dangerous-bash", "Run it."),
    )
    waiting = await harness.snapshot(session_id)
    assert _active(waiting).pending_interaction is not None
    request = _active(waiting).pending_interaction.request
    assert request.summary == "Run command"
    assert request.input_preview == ("rm -f harmless && printf executed > executed.txt")
    risk = request.risk.model_dump()
    assert "boundary" not in risk
    assert "assessment_fingerprint" not in risk
    stored_waiting = await harness.repository.get_run(str(_active(waiting).run.id))
    assert stored_waiting is not None
    private_interaction = stored_waiting.checkpoint["interaction"]
    assert private_interaction["summary"] == "Run command"
    assert private_interaction["input_preview"] == (
        "rm -f harmless && printf executed > executed.txt"
    )
    private_risk = private_interaction["risk"]
    assert private_risk["boundary"]["working_directory"] == str(first.resolve())
    assert len(private_risk["assessment_fingerprint"]) == 64

    current.unlink()
    current.symlink_to(second, target_is_directory=True)

    with pytest.raises(ValueError, match="approval.*assessment.*changed"):
        await harness.dispatch(
            session_id,
            RespondCommand(
                command_id="approve-dangerous-bash",
                interaction_id=_active(waiting).pending_interaction.interaction_id,
                response={"type": "approval", "approved": True},
            ),
        )

    still_waiting = await harness.snapshot(session_id)
    assert _active(still_waiting).run.status == "waiting_user"
    assert _active(still_waiting).pending_interaction is not None
    assert backend.executed_cwds == []
    assert not (second / "executed.txt").exists()


@pytest.mark.asyncio
async def test_approval_response_must_be_allowed_by_pending_request(
    harness_db, tmp_path
) -> None:
    class RecordingBackend(LocalWorkspaceBackend):
        def __init__(self) -> None:
            super().__init__(
                working_directory=tmp_path,
                read_roots=(tmp_path,),
                write_roots=(tmp_path,),
                sandbox_runner=None,
            )
            self.executed = False

        async def run_command(self, **_kwargs):
            self.executed = True
            return {
                "exit_code": 0,
                "stdout": "",
                "stderr": "",
                "cwd": str(tmp_path),
            }

    backend = RecordingBackend()

    class RestrictedWorkspace(WorkspaceRuntime):
        async def execute_batch(self, *args, **kwargs):
            batch = await super().execute_batch(*args, **kwargs)
            return replace(
                batch,
                results=tuple(
                    replace(
                        result,
                        interaction=replace(
                            result.interaction,
                            allowed_responses=("reject",),
                        ),
                    )
                    if result.interaction is not None
                    else result
                    for result in batch.results
                ),
            )

    workspace = RestrictedWorkspace(backend)
    model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="bash-1",
                name="bash",
                arguments_delta='{"command":"rm -f harmless"}',
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        ),
        (
            TextDelta(text="Finished."),
            CompletionMetadata(response_id="response-2", finish_reason="stop"),
        ),
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: workspace,
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)

    await harness.dispatch(session_id, _message("request-bash", "Run it."))
    waiting = await harness.snapshot(session_id)
    assert _active(waiting).pending_interaction is not None
    assert _active(waiting).pending_interaction.request.allowed_responses == ["reject"]
    interaction_id = _active(waiting).pending_interaction.interaction_id

    with pytest.raises(ValueError, match="approval response is not allowed"):
        await harness.dispatch(
            session_id,
            RespondCommand(
                command_id="disallowed-approve",
                interaction_id=interaction_id,
                response={"type": "approval", "approved": True},
            ),
        )

    still_waiting = await harness.snapshot(session_id)
    assert _active(still_waiting).run.status == "waiting_user"
    assert backend.executed is False


@pytest.mark.asyncio
async def test_cancelled_run_approval_cannot_approve_reused_call_id(
    harness_db, tmp_path
) -> None:
    model = ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="shared-bash",
                name="bash",
                arguments_delta='{"command":"rm -f first.txt"}',
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        ),
        (
            ToolCallDelta(
                index=0,
                call_id="shared-bash",
                name="bash",
                arguments_delta='{"command":"rm -f second.txt"}',
            ),
            CompletionMetadata(response_id="response-2", finish_reason="tool_calls"),
        ),
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=lambda _session: _workspace(tmp_path),
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)

    await harness.dispatch(session_id, _message("run-a", "Delete the first file."))
    first = await harness.snapshot(session_id)
    first_interaction = _active(first).pending_interaction
    assert first_interaction is not None
    first_run_id = str(_active(first).run.id)

    await harness.dispatch(
        session_id,
        CancelCommand(command_id="cancel-run-a", reason="user_cancelled"),
    )
    await harness.dispatch(session_id, _message("run-b", "Delete the second file."))
    second = await harness.snapshot(session_id)
    second_interaction = _active(second).pending_interaction
    assert second_interaction is not None
    second_run_id = str(_active(second).run.id)

    assert first_interaction.interaction_id == (f"tool:{first_run_id}:shared-bash")
    assert second_interaction.interaction_id == (f"tool:{second_run_id}:shared-bash")
    assert first_interaction.interaction_id != second_interaction.interaction_id

    with pytest.raises(ValueError, match="interaction.*does not match"):
        await harness.dispatch(
            session_id,
            RespondCommand(
                command_id="stale-run-a-approval",
                interaction_id=first_interaction.interaction_id,
                response={"type": "approval", "approved": True},
            ),
        )

    still_waiting = await harness.snapshot(session_id)
    assert _active(still_waiting).run.status == "waiting_user"
    assert _active(still_waiting).pending_interaction is not None
    assert (
        _active(still_waiting).pending_interaction.interaction_id
        == second_interaction.interaction_id
    )


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
        "type": "approval",
        "call_id": call.call_id,
        "tool_name": call.name,
        "summary": "Allow this tool to run?",
        "input_preview": call.arguments["command"],
        "allowed_responses": ["approve", "reject"],
        "risk": {
            "level": pending.interaction.risk["level"],
            "effects": pending.interaction.risk.get("effects", []),
            "reasons": pending.interaction.risk.get("reasons", []),
            "affected_resources": [],
        },
    }
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=TextModel("Approval recovered."),
        workspace_factory=lambda _session: workspace,
    )
    opened = await harness.open_session(_open_request())
    session_id = str(opened.session.id)
    run = await create_agent_run(harness.repository, session_id)
    await _append_tool_call_entry(
        harness,
        session_id,
        str(run.id),
        [
            {
                "call_id": call.call_id,
                "name": call.name,
                "arguments": call.arguments,
            }
        ],
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
    restored = await harness.snapshot(session_id)
    assert _active(restored).pending_interaction is not None
    await harness.dispatch(
        session_id,
        RespondCommand(
            command_id="approve-restored-bash",
            interaction_id=_active(restored).pending_interaction.interaction_id,
            response={"type": "approval", "approved": True},
        ),
    )

    assert marker.read_text(encoding="utf-8") == "executed\n"
    snapshot = await harness.snapshot(session_id)
    tool_entry = next(
        entry
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "tool"
    )
    assert _tool_result(tool_entry.payload).call_id == "bash-1"
    assert _tool_result(tool_entry.payload).status == "completed"


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
    run = await create_agent_run(harness.repository, session_id)
    await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload=_history_calls(calls),
    )
    request = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="interaction_request",
        payload={
            "interaction_id": "tool:bash-1",
            "request": {
                "type": "approval",
                "call_id": "bash-1",
                "tool_name": "bash",
                "summary": "Allow this tool to run?",
                "allowed_responses": ["approve", "reject"],
                "risk": {"level": "act_high"},
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
    run = await create_agent_run(harness.repository, session_id)
    assistant = await _append_tool_call_entry(
        harness,
        session_id,
        str(run.id),
        [
            {
                "call_id": "bash-1",
                "name": "bash",
                "arguments": {
                    "command": (
                        "rm -f harmless && printf executed >> recovery-retry.txt"
                    )
                },
            }
        ],
    )
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
                    "group_id": str(assistant.id),
                    "execution_mode": "serial",
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
                response={"type": "recovery", "choice": "retry"},
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
    assert _active(snapshot).run.status == "waiting_user"
    assert _active(snapshot).pending_interaction is not None
    assert _active(snapshot).pending_interaction.interaction_id == "recovery:bash-1"


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
    checkpoint_interaction = {
        "request_id": pending.interaction.request_id,
        "call_id": call.call_id,
        "kind": pending.interaction.kind,
        "questions": list(pending.interaction.questions),
        "risk": pending.interaction.risk,
    }

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
    run = await create_agent_run(harness.repository, session_id)
    assistant = await _append_tool_call_entry(
        harness,
        session_id,
        str(run.id),
        [
            {
                "call_id": call.call_id,
                "name": call.name,
                "arguments": call.arguments,
            }
        ],
    )
    interaction = {
        "type": "approval",
        "call_id": call.call_id,
        "tool_name": call.name,
        "summary": "Allow this tool to run?",
        "input_preview": call.arguments["command"],
        "allowed_responses": ["approve", "reject"],
        "risk": {
            "level": pending.interaction.risk["level"],
            "effects": pending.interaction.risk.get("effects", []),
            "reasons": pending.interaction.risk.get("reasons", []),
            "affected_resources": [],
        },
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
                        "group_id": str(assistant.id),
                        "execution_mode": "serial",
                        "name": call.name,
                        "arguments": call.arguments,
                        "replay_policy": "never",
                    },
                ),
                interaction=checkpoint_interaction,
            ),
            "waiting_call": {
                "call_id": call.call_id,
                "group_id": str(assistant.id),
                "execution_mode": "serial",
                "name": call.name,
                "arguments": call.arguments,
            },
            "pending_calls": [],
        },
        tool_progress=[
            {
                "call_id": call.call_id,
                "group_id": str(assistant.id),
                "execution_mode": "serial",
                "name": call.name,
                "display_name": "Bash",
                "category": "command",
                "summary": "Run command",
                "arguments": call.arguments,
                "status": "interaction_required",
                "revision": 1,
            }
        ],
    )

    with pytest.raises(SimulatedProcessCrash):
        await harness.dispatch(
            session_id,
            RespondCommand(
                command_id="approve-bash",
                interaction_id="tool:bash-1",
                response={"type": "approval", "approved": True},
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
            "group_id": str(assistant.id),
            "execution_mode": "serial",
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
    assert _active(snapshot).run.status == "waiting_user"
    assert _active(snapshot).pending_interaction is not None
    assert _active(snapshot).pending_interaction.interaction_id == "recovery:bash-1"
    assert [
        option.id for option in _active(snapshot).pending_interaction.request.options
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
    run = await create_agent_run(harness.repository, session_id)
    assistant = await _append_tool_call_entry(
        harness,
        session_id,
        str(run.id),
        [
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
                    "group_id": str(assistant.id),
                    "execution_mode": "serial",
                    "name": "read",
                    "arguments": {"path": "sample.txt"},
                    "replay_policy": "safe",
                },
                {
                    "call_id": "bash-1",
                    "group_id": str(assistant.id),
                    "execution_mode": "serial",
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
            response={"type": "recovery", "choice": "inspect"},
        ),
    )
    snapshot = await harness.snapshot(session_id)

    tool_entries = [
        entry
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "tool"
    ]
    assert [_tool_result(entry.payload).call_id for entry in tool_entries] == [
        "read-1",
        "bash-1",
    ]
    assert "alpha" in await _durable_tool_output_text(harness, session_id, "read-1")
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
    run = await create_agent_run(harness.repository, session_id)
    assistant = await _append_tool_call_entry(
        harness,
        session_id,
        str(run.id),
        [
            {
                "call_id": "bash-1",
                "name": "bash",
                "arguments": {"command": "sleep 30"},
            }
        ],
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
                    "group_id": str(assistant.id),
                    "execution_mode": "serial",
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

    assert _latest_run(cancelled).status == "cancelled"
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
    assert _tool_result(tool_entries[0].payload).call_id == "bash-1"
    assert _tool_result(tool_entries[0].payload).status == "cancelled"
    assert "interrupted" in (_tool_result(tool_entries[0].payload).error or "")

    await harness.dispatch(
        session_id,
        _message("after-cancel", "Continue."),
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
        _message("cancel-serial-batch", "Run the batch."),
    )
    snapshot = await harness.snapshot(session_id)

    assert _latest_run(snapshot).status == "cancelled"
    tool_entries = [
        entry
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "tool"
    ]
    assert [_tool_result(entry.payload).call_id for entry in tool_entries] == [
        "cancel-1",
        "read-1",
        "read-2",
    ]
    assert [_tool_result(entry.payload).status for entry in tool_entries] == [
        "completed",
        "cancelled",
        "cancelled",
    ]
    for call_id in ["read-1", "read-2"]:
        assert "cancelled" in await _durable_tool_output_text(
            harness, session_id, call_id
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
    run = await create_agent_run(harness.repository, session_id)
    call = {
        "call_id": f"{tool_name}-1",
        "name": tool_name,
        "arguments": arguments,
    }
    assistant = await _append_tool_call_entry(harness, session_id, str(run.id), [call])
    durable_call = {
        **call,
        "group_id": str(assistant.id),
        "execution_mode": "serial",
    }
    request = {
        "type": "recovery",
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
                in_flight_tools=({**durable_call, "replay_policy": "verify"},),
                interaction=request,
            ),
            "waiting_call": durable_call,
            "recovery_interaction": request,
        },
        tool_progress=[
            {
                "call_id": call["call_id"],
                "group_id": str(assistant.id),
                "execution_mode": "serial",
                "name": tool_name,
                "display_name": tool_name.title(),
                "category": tool_name,
                "summary": f"{tool_name.title()} file: target.txt",
                "arguments": arguments,
                "status": "interaction_required",
                "revision": 1,
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
            response={"type": "recovery", "choice": "retry"},
        ),
    )
    snapshot = await harness.snapshot(session_id)

    assert assistant.sequence < request_entry.sequence
    assert captured_replay_policy == "verify"
    assert target.read_text(encoding="utf-8") == "beta"
    assert _latest_run(snapshot).status == "completed"
    assert any(
        entry.type == "message"
        and entry.payload.role == "tool"
        and _tool_result(entry.payload).call_id == call["call_id"]
        and _tool_result(entry.payload).status == "completed"
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
    cancelled_run = await create_agent_run(harness.repository, session_id)
    await harness.repository.update_run(
        str(cancelled_run.id),
        status="running",
        phase="model",
    )
    await harness.dispatch(
        session_id,
        _message("message-after-cancel", "Continue next."),
    )
    events = harness.events(session_id)
    await anext(events)

    try:
        await harness.dispatch(
            session_id,
            CancelCommand(command_id="cancel-current", reason="user_cancelled"),
        )

        snapshot = await harness.snapshot(session_id)
        assert _latest_run(snapshot).id != cancelled_run.id
        assert _latest_run(snapshot).status == "completed"
        terminal_events = []
        for _ in range(12):
            event = await asyncio.wait_for(anext(events), timeout=0.5)
            if (
                event.type == "run.updated"
                and event.run.id == cancelled_run.id
                and event.run.status == "cancelled"
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
    cancelled_run = await create_agent_run(first.repository, session_id)
    await first.repository.update_run(
        str(cancelled_run.id),
        status="running",
        phase="model",
    )
    await first.repository.enqueue_command(
        session_id,
        _message("message-after-restart", "Continue next."),
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
        assert _latest_run(snapshot).id != cancelled_run.id
        assert _latest_run(snapshot).status == "completed"
        stored = await restarted.repository.get_run(str(cancelled_run.id))
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.command_queue == []
        for _ in range(12):
            event = await asyncio.wait_for(anext(events), timeout=0.5)
            if (
                event.type == "run.updated"
                and event.run.id == cancelled_run.id
                and event.run.status == "cancelled"
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
    completed_run = await create_agent_run(first.repository, session_id)
    await first.repository.update_run(
        str(completed_run.id),
        status="completed",
        phase=None,
        termination_reason="completed",
    )
    await first.repository.enqueue_command(
        session_id,
        _message("message-after-terminal-crash", "Continue after restart."),
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

    assert _latest_run(snapshot).id != completed_run.id
    assert _latest_run(snapshot).status == "completed"
    assert stored_session is not None
    assert stored_session.command_queue == []
    assert len(restarted_model.invocations) == 1
    assert [
        part.text
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "user"
        for part in entry.payload.parts
        if part.type == "text"
    ] == ["Continue after restart."]


@pytest.mark.asyncio
async def test_steer_racing_run_completion_requires_a_new_message(
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
    finishing_run = await create_agent_run(harness.repository, session_id)
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

    with pytest.raises(ValueError, match="no active run to steer"):
        await harness.dispatch(
            session_id,
            _steer("boundary-steer", "Include this update."),
        )
    stored_session = await harness.repository.get_session(session_id)

    assert stored_session is not None
    assert stored_session.command_queue == []
    assert len(model.invocations) == 0


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
    run = await create_agent_run(first.repository, session_id)
    user = await first.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload=_history_text("user", "Start."),
    )
    await first.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload=_history_text("assistant", "Initial final answer."),
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
        _steer("steer-after-final-crash", "Also inspect the metadata."),
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

    assert _latest_run(snapshot).status == "completed"
    assert stored_run is not None
    assert stored_run.command_queue == []
    assert len(restarted_model.invocations) == 1
    user_texts = [
        part.text
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "user"
        for part in entry.payload.parts
        if part.type == "text"
    ]
    assert user_texts == ["Start.", "Also inspect the metadata."]
    assert any(
        getattr(item, "text", None) == "Also inspect the metadata."
        for item in restarted_model.invocations[0].input_items
    )
    assert _text_values(snapshot.entries[-1].payload) == ["Updated after steer."]


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
    run = await create_agent_run(first.repository, session_id)
    await first.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload=_history_text("user", "Start."),
    )
    await first.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload=_history_text("assistant", "Committed answer."),
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
            _steer("steer-at-recovery-safe-point", "Include the late metadata."),
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

    assert _latest_run(snapshot).status == "completed"
    assert stored_run is not None
    assert stored_run.command_queue == []
    assert len(restarted_model.invocations) == 1
    assert [
        part.text
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "user"
        for part in entry.payload.parts
        if part.type == "text"
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
    run = await create_agent_run(harness.repository, session_id)
    user = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload=_history_text("user", "Go."),
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
    run = await create_agent_run(harness.repository, session_id)
    await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload=_history_calls(
            [
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
            ]
        ),
    )
    await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="interaction_request",
        payload={
            "interaction_id": "tool:ask-1",
            "request": {
                "type": "ask_user",
                "call_id": "ask-1",
                "questions": [
                    {
                        "id": "proceed",
                        "header": "Proceed",
                        "question": "Proceed?",
                        "options": [
                            {"id": "yes", "label": "Yes"},
                            {"id": "no", "label": "No"},
                        ],
                    }
                ],
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
    assert _active(snapshot).run.status == "waiting_user"
    assert _active(snapshot).pending_interaction is not None
    assert _active(snapshot).pending_interaction.interaction_id == "tool:ask-1"
    assert model.invocations == []

    await harness.dispatch(
        session_id,
        RespondCommand(
            command_id="answer-after-restart",
            interaction_id="tool:ask-1",
            response={"type": "ask_user", "answers": {"Proceed?": "Yes"}},
        ),
    )
    completed = await harness.snapshot(session_id)
    assert _latest_run(completed).status == "completed"
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
    run = await create_agent_run(harness.repository, session_id)
    await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload=_history_text("user", "Question"),
    )
    await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload=_history_text("assistant", "Already committed answer"),
    )
    await harness.repository.update_run(
        str(run.id), status="running", phase="model", checkpoint=None
    )

    recovered = await harness.recover()
    snapshot = await harness.snapshot(session_id)

    assert recovered == 1
    assert _latest_run(snapshot).status == "completed"
    assert model.invocations == []
    answers = [
        _text_values(entry.payload)
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "assistant"
    ]
    assert answers == [["Already committed answer"]]


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
    run = await create_agent_run(harness.repository, session_id)
    await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload=_history_calls(
            [
                {
                    "call_id": "read-1",
                    "name": "read",
                    "arguments": {"path": "sample.txt"},
                }
            ]
        ),
    )
    await harness.repository.update_run(
        str(run.id), status="running", phase="model", checkpoint=None
    )

    recovered = await harness.recover()
    snapshot = await harness.snapshot(session_id)

    assert recovered == 1
    assert _latest_run(snapshot).status == "completed"
    tool_entries = [
        entry
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "tool"
    ]
    assert len(tool_entries) == 1
    assert _tool_result(tool_entries[0].payload).call_id == "read-1"
    assert "alpha" in await _durable_tool_output_text(harness, session_id, "read-1")
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
    run = await create_agent_run(harness.repository, session_id)
    user = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload=_history_text("user", "Go."),
    )
    await harness.repository.update_run(
        str(run.id),
        status="running",
        phase="model",
        draft={
            "id": f"draft:{run.id}",
            "run_id": str(run.id),
            "parts": [
                {
                    "id": f"draft:{run.id}:reasoning",
                    "type": "reasoning_summary",
                    "text": "partial reasoning",
                    "end_offset": 17,
                },
                {
                    "id": f"draft:{run.id}:text",
                    "type": "text",
                    "text": "partial text",
                    "end_offset": 12,
                },
            ],
        },
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
    run = await create_agent_run(harness.repository, str(opened.session.id))
    assistant = await _append_tool_call_entry(
        harness,
        str(opened.session.id),
        str(run.id),
        [
            {
                "call_id": "read-1",
                "name": "read",
                "arguments": {"path": "sample.txt"},
            }
        ],
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
                    "group_id": str(assistant.id),
                    "execution_mode": "serial",
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
    assert _latest_run(snapshot).status == "completed"
    assert [
        entry.payload.role for entry in snapshot.entries if entry.type == "message"
    ] == [
        "assistant",
        "tool",
        "assistant",
    ]
    assert "alpha" in await _durable_tool_output_text(
        harness, str(opened.session.id), "read-1"
    )
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
    run = await create_agent_run(harness.repository, session_id)
    user = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload=_history_text("user", "Read it."),
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
    assistant = await _append_tool_call_entry(
        harness,
        session_id,
        str(run.id),
        [
            {
                "call_id": "read-1",
                "name": "read",
                "arguments": {"path": "sample.txt"},
            }
        ],
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
                    "group_id": str(assistant.id),
                    "execution_mode": "serial",
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
    assert _tool_result(tool_entry.payload).call_id == "mutation-1"
    assert recovery_state in await _durable_tool_output_text(
        harness, str(opened.session.id), "mutation-1"
    )


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

    assert _active(snapshot).run.status == "waiting_user"
    assert _active(snapshot).pending_interaction is not None
    assert _active(snapshot).pending_interaction.request.type == "recovery"
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
    run = await create_agent_run(harness.repository, session_id)
    current_target = model_target_from_snapshot({"target": _model_target()})
    current_text = "Continue."
    entry = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload=_history_text("user", current_text),
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
                payload=_history_text("user", "Continue after summary."),
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
    run = await create_agent_run(harness.repository, str(opened.session.id))
    assistant = await _append_tool_call_entry(
        harness,
        str(opened.session.id),
        str(run.id),
        [
            {
                "call_id": "bash-1",
                "name": "bash",
                "arguments": {"command": "touch marker.txt"},
            }
        ],
    )
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
                    "group_id": str(assistant.id),
                    "execution_mode": "serial",
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
            response={"type": "recovery", "choice": "inspect"},
        ),
    )
    snapshot = await harness.snapshot(str(opened.session.id))

    assert marker.exists() is False
    assert _latest_run(snapshot).status == "completed"
    tool_entries = [
        entry
        for entry in snapshot.entries
        if entry.type == "message" and entry.payload.role == "tool"
    ]
    assert [_tool_result(entry.payload).call_id for entry in tool_entries] == ["bash-1"]
    assert "not replayed" in await _durable_tool_output_text(
        harness, str(opened.session.id), "bash-1"
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


async def _create_recoverable_tool_run(harness, session_id: str, call: ToolCall):
    run = await create_agent_run(harness.repository, session_id)
    assistant = await _append_tool_call_entry(
        harness,
        session_id,
        str(run.id),
        [
            {
                "call_id": call.call_id,
                "name": call.name,
                "arguments": call.arguments,
            }
        ],
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
                    "group_id": str(assistant.id),
                    "execution_mode": "serial",
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
