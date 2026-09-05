from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.services.agent_harness.contracts import (
    AgentCommand,
    AgentEvent,
    OpenSessionRequest,
    SessionSnapshot,
)


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
    "HarnessAdapterManifest",
    "validate_harness_adapter_manifest",
]
