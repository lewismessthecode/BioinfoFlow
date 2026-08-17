from __future__ import annotations

from uuid import UUID

import pytest

from app.models.workspace import Workspace
from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.repositories.agent_trace_repo import AgentModelTraceRepository
from app.services.agent_harness.contracts import (
    InputTextPart,
    MessageCommand,
    OpenSessionRequest,
)
from app.services.agent_harness.harness import AgentHarness
from app.services.agent_harness.workspace_runtime import (
    LocalWorkspaceBackend,
    WorkspaceRuntime,
)
from app.services.agent_trace.recorder import ModelExchangeRecorder
from app.services.model_runtime.contracts import CompletionMetadata, TextDelta
from app.services.model_runtime.errors import ModelError
from app.services.model_runtime.gateway import ModelGateway


WORKSPACE_ID = UUID("72000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_harness_records_each_model_exchange_with_usage_and_context(
    db_session,
    tmp_path,
) -> None:
    db_session.add(
        Workspace(
            id=str(WORKSPACE_ID),
            name="Trace Recorder",
            slug="trace-recorder",
            is_default=False,
        )
    )
    await db_session.commit()

    class Backend:
        async def invoke(self, wire_protocol, request, *, network_access):
            assert wire_protocol == "chat_completions"
            assert network_access == "unrestricted"
            assert request["messages"][0]["role"] == "system"
            return {
                "id": "chatcmpl-1",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "QC is complete."},
                    }
                ],
                "usage": {
                    "prompt_tokens": 24,
                    "completion_tokens": 4,
                    "total_tokens": 28,
                    "prompt_tokens_details": {"cached_tokens": 12},
                },
            }

    trace_repository = AgentModelTraceRepository(db_session)
    recorder = ModelExchangeRecorder(trace_repository)
    gateway = ModelGateway(backend=Backend(), exchange_observer=recorder)
    harness = AgentHarness(
        AgentHarnessRepository(db_session),
        model_gateway=gateway,
        workspace_factory=lambda _session: WorkspaceRuntime(
            LocalWorkspaceBackend(
                working_directory=tmp_path,
                read_roots=(tmp_path,),
                write_roots=(tmp_path,),
                sandbox_runner=None,
            )
        ),
        model_exchange_recorder=recorder,
    )
    opened = await harness.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id=WORKSPACE_ID,
            prompt_snapshot={"schema_version": 1, "content": "System prompt."},
            model={
                "target": {
                    "endpoint_id": "endpoint-1",
                    "provider_kind": "openai",
                    "model_name": "gpt-5",
                    "routed_model_name": "openai/gpt-5",
                    "wire_protocol": "chat_completions",
                },
                "capabilities": {
                    "supports_streaming": False,
                    "supports_tools": True,
                },
                "context_window_tokens": 128000,
            },
        )
    )

    await harness.dispatch(
        str(opened.session.id),
        MessageCommand(
            command_id="message-1",
            parts=[InputTextPart(text="Run QC.")],
        ),
    )

    traces = await trace_repository.list_for_session(str(opened.session.id))

    assert len(traces) == 1
    trace = traces[0]
    assert trace.status == "completed"
    assert trace.request_prepared_at is not None
    assert trace.first_byte_at is not None
    assert trace.completed_at is not None
    assert trace.started_at <= trace.request_prepared_at
    assert trace.request_prepared_at <= trace.first_byte_at
    assert trace.first_byte_at <= trace.completed_at
    assert trace.request_payload["messages"][-1] == {
        "role": "user",
        "content": "Run QC.",
    }
    assert trace.response_payload["id"] == "chatcmpl-1"
    assert trace.usage == {
        "input_tokens": 24,
        "output_tokens": 4,
        "total_tokens": 28,
        "cached_input_tokens": 12,
        "reasoning_tokens": None,
    }
    assert trace.context_snapshot["max_context_tokens"] == 128000
    assert trace.context_snapshot["composition"][:2] == [
        {"category": "system", "characters": 14, "tokens": None},
        {"category": "user", "characters": 7, "tokens": None},
    ]
    assert trace.context_snapshot["composition"][2]["category"] == "tool"
    assert trace.context_snapshot["composition"][2]["characters"] > 0


class FailingCaptureRecorder:
    def __init__(self, stage: str) -> None:
        self.stage = stage
        self.recoveries = 0

    async def start(self, **kwargs) -> str:
        if self.stage == "start":
            raise RuntimeError("trace-storage-secret")
        return "trace-1"

    async def complete(self, exchange_id: str, **kwargs) -> None:
        if self.stage == "complete":
            raise RuntimeError("trace-storage-secret")

    async def fail(self, exchange_id: str, **kwargs) -> None:
        if self.stage == "fail":
            raise RuntimeError("trace-storage-secret")

    async def recover_after_failure(self) -> None:
        self.recoveries += 1


class SuccessfulModel:
    async def invoke(self, invocation):
        yield TextDelta(text="QC is complete.")
        yield CompletionMetadata(response_id="response-1", finish_reason="stop")


class FailingModel:
    async def invoke(self, invocation):
        raise ModelError(
            category="service_unavailable",
            message="Provider is unavailable.",
        )
        yield  # pragma: no cover - keep this an async generator


class DetailedFailingModel:
    async def invoke(self, invocation):
        raise ModelError(
            category="rate_limit",
            message="Provider rate limit reached.",
            http_status=429,
            provider_code="rate_limit_exceeded",
            retryable=True,
            retry_after_seconds=0.001,
            request_id="request-safe-1",
            cause=RuntimeError("credential-secret"),
        )
        yield  # pragma: no cover - keep this an async generator


@pytest.mark.asyncio
async def test_harness_records_only_safe_model_error_metadata(
    db_session,
    tmp_path,
) -> None:
    db_session.add(
        Workspace(
            id=str(WORKSPACE_ID),
            name="Trace Safe Error",
            slug="trace-safe-error",
            is_default=False,
        )
    )
    await db_session.commit()
    trace_repository = AgentModelTraceRepository(db_session)
    recorder = ModelExchangeRecorder(trace_repository)
    harness = AgentHarness(
        AgentHarnessRepository(db_session),
        model_gateway=DetailedFailingModel(),
        workspace_factory=lambda _session: WorkspaceRuntime(
            LocalWorkspaceBackend(
                working_directory=tmp_path,
                read_roots=(tmp_path,),
                write_roots=(tmp_path,),
                sandbox_runner=None,
            )
        ),
        model_exchange_recorder=recorder,
    )
    opened = await harness.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id=WORKSPACE_ID,
            prompt_snapshot={"schema_version": 1, "content": "System prompt."},
            model={
                "target": {
                    "endpoint_id": "endpoint-1",
                    "provider_kind": "openai",
                    "model_name": "gpt-5",
                    "routed_model_name": "openai/gpt-5",
                    "wire_protocol": "chat_completions",
                },
                "capabilities": {
                    "supports_streaming": False,
                    "supports_tools": True,
                },
            },
        )
    )

    await harness.dispatch(
        str(opened.session.id),
        MessageCommand(
            command_id="message-safe-error",
            parts=[InputTextPart(text="Run QC.")],
        ),
    )
    traces = await trace_repository.list_for_session(str(opened.session.id))

    expected_error = {
        "code": "rate_limit",
        "message": "Provider rate limit reached.",
        "http_status": 429,
        "provider_code": "rate_limit_exceeded",
        "retryable": True,
        "retry_after_seconds": 0.001,
        "request_id": "request-safe-1",
    }
    assert len(traces) == 3
    assert all(trace.error == expected_error for trace in traces)
    assert "credential-secret" not in str([trace.error for trace in traces])


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["start", "complete"])
async def test_harness_ignores_trace_capture_failure_on_successful_turn(
    db_session,
    tmp_path,
    caplog,
    stage: str,
) -> None:
    db_session.add(
        Workspace(
            id=str(WORKSPACE_ID),
            name="Trace Best Effort",
            slug=f"trace-best-effort-{stage}",
            is_default=False,
        )
    )
    await db_session.commit()
    recorder = FailingCaptureRecorder(stage)
    harness = AgentHarness(
        AgentHarnessRepository(db_session),
        model_gateway=SuccessfulModel(),
        workspace_factory=lambda _session: WorkspaceRuntime(
            LocalWorkspaceBackend(
                working_directory=tmp_path,
                read_roots=(tmp_path,),
                write_roots=(tmp_path,),
                sandbox_runner=None,
            )
        ),
        model_exchange_recorder=recorder,
    )
    opened = await harness.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id=WORKSPACE_ID,
            prompt_snapshot={"schema_version": 1, "content": "System prompt."},
            model={
                "target": {
                    "endpoint_id": "endpoint-1",
                    "provider_kind": "openai",
                    "model_name": "gpt-5",
                    "routed_model_name": "openai/gpt-5",
                    "wire_protocol": "chat_completions",
                },
                "capabilities": {
                    "supports_streaming": False,
                    "supports_tools": True,
                },
            },
        )
    )

    await harness.dispatch(
        str(opened.session.id),
        MessageCommand(
            command_id=f"message-{stage}", parts=[InputTextPart(text="Run QC.")]
        ),
    )
    snapshot = await harness.snapshot(str(opened.session.id))

    assert snapshot.runs[-1].status == "completed"
    assert recorder.recoveries == 1
    assert "trace-storage-secret" not in caplog.text


@pytest.mark.asyncio
async def test_trace_failure_capture_does_not_mask_model_failure(
    db_session,
    tmp_path,
    caplog,
) -> None:
    db_session.add(
        Workspace(
            id=str(WORKSPACE_ID),
            name="Trace Failure Best Effort",
            slug="trace-failure-best-effort",
            is_default=False,
        )
    )
    await db_session.commit()
    recorder = FailingCaptureRecorder("fail")
    harness = AgentHarness(
        AgentHarnessRepository(db_session),
        model_gateway=FailingModel(),
        workspace_factory=lambda _session: WorkspaceRuntime(
            LocalWorkspaceBackend(
                working_directory=tmp_path,
                read_roots=(tmp_path,),
                write_roots=(tmp_path,),
                sandbox_runner=None,
            )
        ),
        model_exchange_recorder=recorder,
    )
    opened = await harness.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id=WORKSPACE_ID,
            prompt_snapshot={"schema_version": 1, "content": "System prompt."},
            model={
                "target": {
                    "endpoint_id": "endpoint-1",
                    "provider_kind": "openai",
                    "model_name": "gpt-5",
                    "routed_model_name": "openai/gpt-5",
                    "wire_protocol": "chat_completions",
                },
                "capabilities": {
                    "supports_streaming": False,
                    "supports_tools": True,
                },
            },
        )
    )

    await harness.dispatch(
        str(opened.session.id),
        MessageCommand(
            command_id="message-fail", parts=[InputTextPart(text="Run QC.")]
        ),
    )
    snapshot = await harness.snapshot(str(opened.session.id))
    stored_run = await harness.repository.get_run(str(snapshot.runs[-1].id))

    assert snapshot.runs[-1].status == "failed"
    assert snapshot.runs[-1].error is not None
    assert stored_run is not None
    assert stored_run.error["message"] == "Provider is unavailable."
    assert recorder.recoveries == 1
    assert "trace-storage-secret" not in caplog.text
