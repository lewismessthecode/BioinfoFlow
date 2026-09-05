from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest
from pydantic import TypeAdapter

from app.services.agent_harness.adapter import (
    AgentHarnessAdapter,
    ArtifactPublication,
    HarnessAdapterManifest,
    HarnessHostPort,
    RunExecutionEngine,
    RunExecutionRequest,
    ensure_engine_tool_allowed,
)
from app.services.agent_harness.contracts import (
    AgentEvent,
    InputTextPart,
    MessageCommand,
    RunUpdatedEvent,
    RunView,
)
from app.services.agent_harness.tools import ToolCall
from app.services.agent_harness.tools.specs import ToolResult


SESSION_ID = "10000000-0000-0000-0000-000000000001"
RUN_ID = "20000000-0000-0000-0000-000000000001"
NOW = datetime(2026, 9, 5, tzinfo=timezone.utc)


class _HostPort:
    def __init__(self) -> None:
        self.publications: list[ArtifactPublication] = []
        self.tool_calls: list[ToolCall] = []

    async def execute_tool(
        self, call: ToolCall, *, cancellation: Any | None = None
    ) -> ToolResult:
        del cancellation
        self.tool_calls.append(call)
        raise AssertionError("the fixture must use the explicit artifact host port")

    async def publish_artifact(
        self,
        *,
        session_id: str,
        run_id: str,
        call_id: str,
        path: str,
        title: str | None = None,
        summary: str | None = None,
    ) -> ArtifactPublication:
        publication = ArtifactPublication(
            artifact_id="50000000-0000-0000-0000-000000000001",
            title=title or path,
            media_type="text/html",
            location="/api/v1/agent/artifacts/50000000-0000-0000-0000-000000000001/download",
        )
        self.publications.append(publication)
        assert session_id == SESSION_ID
        assert run_id == RUN_ID
        assert call_id == "pi-call-1"
        assert path == "report.html"
        assert summary == "Final report"
        return publication


class _PiEngineFixture:
    """A tiny Pi-shaped engine; it has no database or artifact writer."""

    async def run(
        self,
        request: RunExecutionRequest,
        *,
        host: HarnessHostPort,
    ) -> AsyncIterator[AgentEvent]:
        assert request.session_id == SESSION_ID
        assert request.run_id == RUN_ID
        assert not hasattr(self, "repository")
        assert not hasattr(self, "db")

        publication = await host.publish_artifact(
            session_id=request.session_id,
            run_id=request.run_id,
            call_id="pi-call-1",
            path="report.html",
            title="Report",
            summary="Final report",
        )
        assert publication.artifact_id
        yield RunUpdatedEvent(
            run=RunView(
                id=UUID(RUN_ID),
                session_id=UUID(SESSION_ID),
                status="completed",
                created_at=NOW,
                updated_at=NOW,
            )
        )

    async def cancel(self, *, session_id: str, run_id: str) -> None:
        assert session_id == SESSION_ID
        assert run_id == RUN_ID


@pytest.mark.asyncio
async def test_pi_engine_uses_host_for_artifact_publication_and_keeps_public_events_stable() -> (
    None
):
    engine: RunExecutionEngine = _PiEngineFixture()
    host: HarnessHostPort = _HostPort()
    request = RunExecutionRequest(
        session_id=SESSION_ID,
        run_id=RUN_ID,
        command=MessageCommand(
            command_id="message-1",
            parts=[InputTextPart(text="publish the report")],
        ),
    )

    events = [event async for event in engine.run(request, host=host)]

    assert len(host.publications) == 1
    assert host.publications[0].title == "Report"
    assert not host.tool_calls
    assert all(
        TypeAdapter(AgentEvent).validate_python(event.model_dump(mode="json"))
        for event in events
    )
    assert events[0].presentation_protocol == "bioinfoflow.agent.presentation"
    assert "pi" not in events[0].model_dump(mode="json")


def test_engine_port_is_not_an_agent_api_or_repository_contract() -> None:
    assert isinstance(_PiEngineFixture(), RunExecutionEngine)
    assert isinstance(_HostPort(), HarnessHostPort)
    assert set(RunExecutionRequest.__annotations__) == {
        "session_id",
        "run_id",
        "command",
    }
    assert AgentHarnessAdapter


def test_foreign_engine_cannot_execute_host_owned_artifact_tool_as_a_generic_tool() -> (
    None
):
    with pytest.raises(ValueError, match="host-owned"):
        ensure_engine_tool_allowed(
            ToolCall(call_id="pi-call-1", name="publish_artifact", arguments={})
        )

    # Ordinary tools remain available through the host's generic execution port.
    ensure_engine_tool_allowed(
        ToolCall(call_id="pi-call-2", name="read", arguments={"path": "report.html"})
    )


def test_adapter_manifest_cannot_drop_host_owned_artifact_publication() -> None:
    with pytest.raises(ValueError, match="host-owned"):
        HarnessAdapterManifest(
            adapter_id="pi-engine",
            adapter_version="fixture",
            unmediated_tools_enabled=False,
            host_capabilities=frozenset(
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
            ),
            host_owned_tools=frozenset(),
        )
