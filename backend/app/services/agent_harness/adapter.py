from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.services.agent_harness.contracts import (
    AgentCommand,
    AgentEvent,
    OpenSessionRequest,
    SessionSnapshot,
)
from app.services.agent_harness.tools.specs import ToolCall, ToolResult


BIOINFOFLOW_HOST_CAPABILITIES = frozenset(
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
HOST_OWNED_TOOLS = frozenset({"publish_artifact"})


@dataclass(frozen=True, slots=True)
class ArtifactPublication:
    """Safe reference returned after the BioinfoFlow host publishes a file.

    The engine receives metadata only. File bytes, storage paths and the
    publication implementation remain inside the host boundary.
    """

    artifact_id: str
    title: str
    media_type: str | None = None
    location: str | None = None


@dataclass(frozen=True, slots=True)
class RunExecutionRequest:
    """The small input a replaceable run engine needs from the product host."""

    session_id: str
    run_id: str
    command: AgentCommand


@runtime_checkable
class HarnessHostPort(Protocol):
    """Host-owned capabilities exposed to a foreign run engine.

    A foreign engine may request tool execution, but it cannot reach the
    repository or storage directly. Artifact publication is intentionally a
    separate method so it cannot be mistaken for ordinary command output.
    """

    async def execute_tool(
        self, call: ToolCall, *, cancellation: Any | None = None
    ) -> ToolResult: ...

    async def publish_artifact(
        self,
        *,
        session_id: str,
        run_id: str,
        call_id: str,
        path: str,
        title: str | None = None,
        summary: str | None = None,
    ) -> ArtifactPublication: ...


@runtime_checkable
class RunExecutionEngine(Protocol):
    """Provider-neutral execution seam for an experimental harness adapter."""

    def run(
        self,
        request: RunExecutionRequest,
        *,
        host: HarnessHostPort,
    ) -> AsyncIterator[AgentEvent]: ...

    async def cancel(self, *, session_id: str, run_id: str) -> None: ...


def ensure_engine_tool_allowed(call: ToolCall) -> None:
    """Reject generic engine execution of a host-owned tool.

    An adapter may still expose the ``publish_artifact`` schema to its model,
    but the resulting call must be routed to ``HarnessHostPort.publish_artifact``
    instead of an engine-local implementation.
    """

    if call.name in HOST_OWNED_TOOLS:
        raise ValueError(f"{call.name} is host-owned and must use the host port")


@dataclass(frozen=True, slots=True)
class HarnessAdapterManifest:
    """Experimental self-declaration for one product-runtime adapter.

    This manifest has no negotiated contract version and is not proof that an
    implementation enforces the declared ownership. It only rejects obviously
    incompatible configuration at the BioinfoFlow composition root. The test Pi
    fixture is not verified against the live Pi wire protocol.
    """

    adapter_id: str
    adapter_version: str
    unmediated_tools_enabled: bool
    host_capabilities: frozenset[str]
    host_owned_tools: frozenset[str] = HOST_OWNED_TOOLS

    def __post_init__(self) -> None:
        validate_harness_adapter_manifest(self)


def validate_harness_adapter_manifest(manifest: HarnessAdapterManifest) -> None:
    """Validate an adapter's experimental ownership declaration."""

    if manifest.unmediated_tools_enabled:
        raise ValueError("Harness adapters cannot enable unmediated tools")
    missing = BIOINFOFLOW_HOST_CAPABILITIES - manifest.host_capabilities
    if missing:
        raise ValueError(
            "Harness adapters must preserve all BioinfoFlow host capabilities: "
            + ", ".join(sorted(missing))
        )
    missing_tools = HOST_OWNED_TOOLS - manifest.host_owned_tools
    if missing_tools:
        raise ValueError(
            "Harness adapters must keep these tools host-owned: "
            + ", ".join(sorted(missing_tools))
        )


@runtime_checkable
class AgentHarnessAdapter(Protocol):
    """Harness-independent product interface consumed by the Agent API.

    ``AgentRuntime`` is the native adapter. A foreign implementation replaces
    it at the application composition root; it is not injected into the native
    runtime or required to imitate its Repository/lease implementation. Both
    implementations return BioinfoFlow contracts and leave all tool effects,
    approvals, permissions, credentials, Workspace identity, Sandbox
    enforcement and Artifact publication under BioinfoFlow ownership.

    Reconnecting to ``events`` is snapshot-first. The snapshot is authoritative
    and contains durable history. Events queued while it is being built can
    overlap with facts already visible in that snapshot, so consumers reconcile
    them idempotently by stable IDs and revisions. This interface does not
    promise a duplicate-free cursor stream.
    """

    manifest: HarnessAdapterManifest

    async def open_session(self, request: OpenSessionRequest) -> SessionSnapshot: ...

    async def dispatch(self, session_id: str, command: AgentCommand) -> None: ...

    async def snapshot(self, session_id: str) -> SessionSnapshot: ...

    async def publish_snapshot(
        self, session_id: str, snapshot: SessionSnapshot
    ) -> None: ...

    async def delete_session(self, session_id: str) -> None: ...

    async def quiesce_session(self, session_id: str) -> None: ...

    def events(self, session_id: str) -> AsyncIterator[AgentEvent]: ...

    async def recover(self) -> int: ...

    async def shutdown(self) -> None: ...


__all__ = [
    "BIOINFOFLOW_HOST_CAPABILITIES",
    "AgentHarnessAdapter",
    "ArtifactPublication",
    "HarnessHostPort",
    "HarnessAdapterManifest",
    "HOST_OWNED_TOOLS",
    "RunExecutionEngine",
    "RunExecutionRequest",
    "ensure_engine_tool_allowed",
    "validate_harness_adapter_manifest",
]
