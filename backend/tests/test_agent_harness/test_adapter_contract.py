"""Contract experiment for a replaceable Agent product runtime.

The Pi adapter below is deliberately a recorded, test-only fixture based on Pi
commit ``9841914c71a74d81abe07f751aefd271fd924e63``. It proves that Pi-shaped
session and event data can stay behind BioinfoFlow's product seam; it does not
spawn Pi or claim wire compatibility. A real pinned smoke test must separately
start that commit, disable built-in tools, and exercise JSONL reconnect/error
behavior before a production adapter is considered.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.services.agent_harness.adapter import (
    BIOINFOFLOW_HOST_CAPABILITIES,
    AgentHarnessAdapter,
    HarnessAdapterManifest,
    validate_harness_adapter_manifest,
)
from app.services.agent_harness.contracts import (
    AgentCommand,
    AgentEvent,
    ApprovalInteractionResponse,
    CancelCommand,
    EntryCommittedEvent,
    InputTextPart,
    InteractionRequestedEvent,
    MessageCommand,
    OpenSessionRequest,
    RespondCommand,
    RunUpdatedEvent,
    SessionSnapshot,
    SnapshotEvent,
    ToolUpdatedEvent,
)
from app.services.agent_harness.runtime import AgentRuntime
from app.services.agent_harness.events import AgentEventHub


NOW = datetime(2026, 9, 5, tzinfo=timezone.utc)
SESSION_ID = UUID("10000000-0000-0000-0000-000000000001")
WORKSPACE_ID = UUID("20000000-0000-0000-0000-000000000001")
RUN_ID = UUID("30000000-0000-0000-0000-000000000001")


def _snapshot(*, run_status: str | None = None) -> SessionSnapshot:
    runs = []
    active_run = None
    if run_status is not None:
        run = {
            "id": RUN_ID,
            "session_id": SESSION_ID,
            "status": run_status,
            "phase": "model" if run_status == "running" else None,
            "revision": 1,
            "termination_reason": (
                "user_cancelled"
                if run_status == "cancelled"
                else "adapter_failed"
                if run_status == "failed"
                else None
            ),
            "error": (
                {
                    "code": "adapter_failed",
                    "message": "The Agent runtime stopped unexpectedly.",
                }
                if run_status == "failed"
                else None
            ),
            "created_at": NOW,
            "updated_at": NOW,
        }
        runs = [run]
        if run_status in {"queued", "running", "waiting_user"}:
            active_run = {
                "run": run,
                "assistant_draft": None,
                "tool_progress": [],
                "pending_interaction": None,
            }
    return SessionSnapshot.model_validate(
        {
            "session": {
                "id": SESSION_ID,
                "user_id": "user-1",
                "workspace_id": WORKSPACE_ID,
                "project_id": None,
                "title": "Adapter contract",
                "model": {
                    "provider": "fixture",
                    "model": "fixture-model",
                    "display_name": "Fixture",
                    "supports_tools": True,
                },
                "permission_mode": "ask_dangerous",
                "workspace_access": "read_write",
                "status": "active",
                "created_at": NOW,
                "updated_at": NOW,
            },
            "runs": runs,
            "entries": [],
            "active_run": active_run,
        }
    )


class _RecordedPiRpcFixtureAdapter:
    """Recorded Pi RPC/SDK shapes projected behind the product seam."""

    manifest = HarnessAdapterManifest(
        adapter_id="pi-rpc-fixture",
        adapter_version="fixture@9841914c",
        unmediated_tools_enabled=False,
        host_capabilities=BIOINFOFLOW_HOST_CAPABILITIES,
    )

    def __init__(self) -> None:
        self.sdk_options = {
            "noTools": "builtin",
            "customTools": [
                "read",
                "bash",
                "edit",
                "write",
                "publish_artifact",
            ],
        }
        self.native_state = {
            "sessionId": "pi-session-1",
            "sessionFile": "/private/pi-session-1.jsonl",
            "leafId": "pi-entry-1",
        }
        self.native_events = [
            {
                "type": "tool_execution_start",
                "toolCallId": "pi-call-1",
                "toolName": "publish_artifact",
                "args": {"path": "report.html"},
            }
        ]
        self.current = _snapshot()
        self.events_published: list[AgentEvent] = []
        self.commands: list[AgentCommand] = []
        self.deleted = False

    async def open_session(self, _request: OpenSessionRequest) -> SessionSnapshot:
        return self.current

    async def dispatch(self, _session_id: str, command: AgentCommand) -> None:
        self.commands.append(command)
        if isinstance(command, MessageCommand):
            text = next(part.text for part in command.parts if part.type == "text")
            if text == "use unavailable tool":
                raise ValueError("This tool is not available in this session.")
            if text == "provider failed":
                self.current = _snapshot(run_status="failed")
                return
            self.current = _snapshot(run_status="running")
            if text == "run risky command":
                from app.services.agent_harness.contracts import (
                    ApprovalInteractionRequest,
                    ApprovalRiskView,
                    ApprovalTargetView,
                    PendingInteractionView,
                )

                pending = PendingInteractionView(
                    interaction_id="approval-1",
                    run_id=RUN_ID,
                    revision=1,
                    request=ApprovalInteractionRequest(
                        call_id="call-bash-1",
                        tool_name="bash",
                        summary="Run a command",
                        allowed_responses=["approve", "reject"],
                        target=ApprovalTargetView(
                            environment_id="local",
                            display_name="Local",
                            kind="local",
                        ),
                        risk=ApprovalRiskView(level="high"),
                    ),
                )
                self.current = _snapshot(run_status="waiting_user")
                self.current = self.current.model_copy(
                    update={
                        "active_run": {
                            "run": self.current.runs[-1],
                            "assistant_draft": None,
                            "tool_progress": [],
                            "pending_interaction": pending,
                        }
                    }
                )
                self.events_published.append(
                    InteractionRequestedEvent(run_id=RUN_ID, interaction=pending)
                )
            elif text == "publish report":
                from app.services.agent_harness.contracts import (
                    ArtifactRefPart,
                    MessageEntry,
                    MessagePayload,
                    ToolProgressView,
                )

                tool = ToolProgressView(
                    call_id="call-publish-1",
                    group_id="group-publish-1",
                    execution_mode="serial",
                    name="publish_artifact",
                    display_name="Publish artifact",
                    category="write",
                    summary="Publish report.html",
                    status="completed",
                    revision=1,
                )
                self.events_published.append(ToolUpdatedEvent(run_id=RUN_ID, tool=tool))

                entry = MessageEntry(
                    id=UUID("40000000-0000-0000-0000-000000000001"),
                    session_id=SESSION_ID,
                    run_id=RUN_ID,
                    sequence=1,
                    created_at=NOW,
                    payload=MessagePayload(
                        role="assistant",
                        parts=[
                            ArtifactRefPart(
                                id="artifact-ref-1",
                                artifact_id=UUID("50000000-0000-0000-0000-000000000001"),
                                title="report.html",
                                media_type="text/html",
                            )
                        ],
                    ),
                )
                self.current = self.current.model_copy(
                    update={"entries": [entry]}
                )
                self.events_published.append(EntryCommittedEvent(entry=entry))
            else:
                from app.services.agent_harness.contracts import ToolProgressView

                tool = ToolProgressView(
                    call_id="call-read-1",
                    group_id="group-1",
                    execution_mode="serial",
                    name="read",
                    display_name="Read",
                    category="read",
                    summary="Read a file",
                    status="completed",
                    revision=1,
                )
                self.current = self.current.model_copy(
                    update={
                        "active_run": {
                            "run": self.current.runs[-1],
                            "assistant_draft": None,
                            "tool_progress": [tool],
                            "pending_interaction": None,
                        }
                    }
                )
                self.events_published.append(ToolUpdatedEvent(run_id=RUN_ID, tool=tool))
        elif isinstance(command, CancelCommand):
            self.current = _snapshot(run_status="cancelled")
        elif isinstance(command, RespondCommand):
            if command.response.type == "approval" and command.response.approved:
                self.current = _snapshot(run_status="completed")

    async def snapshot(self, _session_id: str) -> SessionSnapshot:
        return self.current

    async def publish_snapshot(
        self, _session_id: str, snapshot: SessionSnapshot
    ) -> None:
        self.current = snapshot
        self.events_published.append(SnapshotEvent(snapshot=snapshot))

    async def delete_session(self, _session_id: str) -> None:
        self.deleted = True

    async def quiesce_session(self, _session_id: str) -> None:
        return None

    def events(self, _session_id: str) -> AsyncIterator[AgentEvent]:
        async def stream() -> AsyncIterator[AgentEvent]:
            # Reconnect always starts from durable BioinfoFlow truth. Native Pi
            # deltas are transient and never replace this authoritative snapshot.
            yield SnapshotEvent(snapshot=self.current)

        return stream()

    async def recover(self) -> int:
        return 0

    async def shutdown(self) -> None:
        return None


@pytest.mark.parametrize("kind", ["native", "pi"])
def test_adapters_satisfy_the_same_product_harness_protocol(kind: str) -> None:
    runtime = AgentRuntime(lambda: None, harness_factory=lambda *_args, **_kwargs: None)
    adapter = runtime if kind == "native" else _RecordedPiRpcFixtureAdapter()

    assert isinstance(adapter, AgentHarnessAdapter)
    validate_harness_adapter_manifest(adapter.manifest)


def test_adapter_manifest_rejects_unmediated_tools_and_host_ownership_drift() -> None:
    with pytest.raises(ValueError, match="unmediated tools"):
        HarnessAdapterManifest(
            adapter_id="unsafe-pi",
            adapter_version="0.85.0",
            unmediated_tools_enabled=True,
            host_capabilities=BIOINFOFLOW_HOST_CAPABILITIES,
        )

    with pytest.raises(ValueError, match="BioinfoFlow host capabilities"):
        HarnessAdapterManifest(
            adapter_id="unsafe-pi",
            adapter_version="0.85.0",
            unmediated_tools_enabled=False,
            host_capabilities=frozenset({"workspace"}),
        )


@pytest.mark.asyncio
async def test_pi_sidecar_fixture_preserves_session_cancel_and_reconnect_contract() -> (
    None
):
    adapter: AgentHarnessAdapter = _RecordedPiRpcFixtureAdapter()
    opened = await adapter.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id=WORKSPACE_ID,
            permission_mode="ask_dangerous",
            workspace_access="read_write",
            prompt_snapshot={},
        )
    )

    await adapter.dispatch(
        str(opened.session.id),
        MessageCommand(
            command_id="message-1",
            parts=[InputTextPart(text="Create a report")],
        ),
    )
    assert (await adapter.snapshot(str(SESSION_ID))).active_run is not None

    await adapter.dispatch(
        str(SESSION_ID),
        CancelCommand(command_id="cancel-1", reason="user_cancelled"),
    )
    cancelled = await adapter.snapshot(str(SESSION_ID))
    assert cancelled.runs[-1].status == "cancelled"
    assert cancelled.runs[-1].termination_reason == "user_cancelled"

    reconnected = adapter.events(str(SESSION_ID))
    first = await anext(reconnected)
    assert isinstance(first, SnapshotEvent)
    assert first.snapshot == cancelled
    assert first.presentation_protocol == "bioinfoflow.agent.presentation"
    with pytest.raises(StopAsyncIteration):
        await anext(reconnected)


@pytest.mark.asyncio
async def test_snapshot_first_stream_allows_idempotent_revision_overlap() -> None:
    hub = AgentEventHub(liveness_interval_seconds=0.01)
    snapshot_started = asyncio.Event()
    release_snapshot = asyncio.Event()
    authoritative = _snapshot(run_status="running")

    async def snapshot() -> SessionSnapshot:
        snapshot_started.set()
        await release_snapshot.wait()
        return authoritative

    stream = hub.stream(str(SESSION_ID), snapshot)
    first_task = asyncio.create_task(anext(stream))
    await snapshot_started.wait()
    await hub.publish(
        str(SESSION_ID),
        RunUpdatedEvent(run=authoritative.runs[-1]),
    )
    release_snapshot.set()

    first = await first_task
    second = await anext(stream)
    assert isinstance(first, SnapshotEvent)
    assert isinstance(second, RunUpdatedEvent)
    assert first.snapshot.runs[-1].id == second.run.id
    assert first.snapshot.runs[-1].revision == second.run.revision
    await stream.aclose()
    await hub.close()


@pytest.mark.asyncio
async def test_adapter_contract_keeps_tools_approvals_and_artifacts_distinct() -> None:
    adapter = _RecordedPiRpcFixtureAdapter()

    await adapter.dispatch(
        str(SESSION_ID),
        MessageCommand(
            command_id="read-1",
            parts=[InputTextPart(text="read a file")],
        ),
    )
    assert isinstance(adapter.events_published[-1], ToolUpdatedEvent)
    assert adapter.events_published[-1].tool.name == "read"
    assert not any(
        isinstance(event, EntryCommittedEvent)
        and any(
            part.type == "artifact_ref"
            for part in event.entry.payload.parts
        )
        for event in adapter.events_published
    )

    await adapter.dispatch(
        str(SESSION_ID),
        MessageCommand(
            command_id="approval-1",
            parts=[InputTextPart(text="run risky command")],
        ),
    )
    assert isinstance(adapter.events_published[-1], InteractionRequestedEvent)
    assert adapter.events_published[-1].interaction.request.type == "approval"

    await adapter.dispatch(
        str(SESSION_ID),
        RespondCommand(
            command_id="approval-response-1",
            interaction_id="approval-1",
            response=ApprovalInteractionResponse(approved=True),
        ),
    )
    assert (await adapter.snapshot(str(SESSION_ID))).runs[-1].status == "completed"

    await adapter.dispatch(
        str(SESSION_ID),
        MessageCommand(
            command_id="artifact-1",
            parts=[InputTextPart(text="publish report")],
        ),
    )
    artifact_event = adapter.events_published[-1]
    assert isinstance(artifact_event, EntryCommittedEvent)
    assert artifact_event.entry.payload.parts[0].type == "artifact_ref"
    assert isinstance(adapter.events_published[-2], ToolUpdatedEvent)
    assert adapter.events_published[-2].tool.name == "publish_artifact"

    with pytest.raises(ValueError, match="not available"):
        await adapter.dispatch(
            str(SESSION_ID),
            MessageCommand(
                command_id="blocked-1",
                parts=[InputTextPart(text="use unavailable tool")],
            ),
        )

    await adapter.dispatch(
        str(SESSION_ID),
        MessageCommand(
            command_id="failed-1",
            parts=[InputTextPart(text="provider failed")],
        ),
    )
    failed = await adapter.snapshot(str(SESSION_ID))
    assert failed.runs[-1].status == "failed"
    assert failed.runs[-1].error is not None
    assert failed.runs[-1].error.model_dump() == {
        "code": "adapter_failed",
        "message": "The Agent runtime stopped unexpectedly.",
    }


def test_pi_sidecar_fixture_uses_only_the_stable_presentation_contract() -> None:
    adapter = _RecordedPiRpcFixtureAdapter()
    dumped = adapter.current.model_dump(mode="json")

    assert adapter.sdk_options["noTools"] == "builtin"
    assert adapter.native_state["sessionFile"].endswith(".jsonl")
    assert adapter.native_events[0]["toolCallId"] == "pi-call-1"
    assert "pi" not in dumped
    assert "sessionFile" not in dumped
    assert "leafId" not in dumped
    assert "toolCallId" not in dumped
    assert "fullOutputPath" not in dumped
    assert adapter.manifest.host_capabilities == frozenset(
        {
            "artifact",
            "approval",
            "credentials",
            "identity",
            "permission",
            "sandbox",
            "tool_execution",
            "tool_output",
            "workspace",
        }
    )
