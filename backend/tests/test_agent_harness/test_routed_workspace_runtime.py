from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.services.agent_harness.environment_scope import (
    EnvironmentDescriptor,
    EnvironmentScopeRequest,
    resolve_environment_scope,
)
from app.services.agent_harness.routed_workspace_runtime import RoutedWorkspaceRuntime
from app.services.agent_harness.tools.bash import BashTool
from app.services.agent_harness.tools.read import ReadTool
from app.services.agent_harness.tools.specs import (
    ToolBatchResult,
    ToolCall,
    ToolResult,
)
from app.services.agent_harness.workspace_router import WorkspaceRouter


@dataclass
class _Runtime:
    name: str
    calls: list[ToolCall] = field(default_factory=list)
    approvals: list[ToolCall] = field(default_factory=list)

    @property
    def tools(self):
        return (ReadTool.spec, BashTool.spec)

    async def execute(self, call: ToolCall, **_kwargs) -> ToolResult:
        self.calls.append(call)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.name,
            status="completed",
            replay_policy="safe" if call.name == "read" else "never",
            output={"runtime": self.name},
        )

    def approval_assessment_matches(self, call: ToolCall, _interaction) -> bool:
        self.approvals.append(call)
        return True

    def approval_assessment_fingerprint(self, call: ToolCall) -> str:
        self.approvals.append(call)
        return f"fingerprint:{self.name}"

    async def verify_recovery(self, call: ToolCall) -> ToolResult:
        self.calls.append(call)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.name,
            status="completed",
            replay_policy="verify",
            output={"runtime": self.name, "recovery_state": "verified"},
        )


def _routed_runtime() -> tuple[RoutedWorkspaceRuntime, dict[str, _Runtime], list[str]]:
    environments = (
        EnvironmentDescriptor("local", "local", "Local", status="online"),
        EnvironmentDescriptor("ssh:gpu", "ssh", "GPU", status="online"),
    )
    scope = resolve_environment_scope(
        EnvironmentScopeRequest(mode="auto"), environments
    )
    runtimes = {
        "local": _Runtime("local"),
        "ssh:gpu": _Runtime("gpu"),
    }
    authorization_checks: list[str] = []

    async def authorize(environment_id: str) -> bool:
        authorization_checks.append(environment_id)
        return True

    async def resolve(environment_id: str) -> _Runtime | None:
        return runtimes.get(environment_id)

    return (
        RoutedWorkspaceRuntime(
            router=WorkspaceRouter(
                scope=scope,
                authorize=authorize,
                resolve=resolve,
            ),
            control_runtime=runtimes["local"],
            environments=environments,
        ),
        runtimes,
        authorization_checks,
    )


def test_routed_runtime_exposes_fixed_routed_tools_and_environment_discovery() -> None:
    runtime, _, _ = _routed_runtime()

    assert [spec.name for spec in runtime.tools] == [
        "read",
        "bash",
        "list_environments",
    ]
    read_schema = runtime.tool_spec("read").input_schema
    assert read_schema["required"] == ["path"]
    assert "enum" not in repr(read_schema)


@pytest.mark.asyncio
async def test_routed_runtime_executes_and_discovers_environments() -> None:
    runtime, runtimes, checks = _routed_runtime()

    result = await runtime.execute(
        ToolCall(
            "call-1",
            "read",
            {"environment_id": "ssh:gpu", "path": "README.md"},
        )
    )
    listed = await runtime.execute(ToolCall("call-2", "list_environments", {}))

    assert result.output == {"runtime": "gpu"}
    assert runtimes["ssh:gpu"].calls == [
        ToolCall("call-1", "read", {"path": "README.md"})
    ]
    assert checks == ["ssh:gpu"]
    assert [item["environment_id"] for item in listed.output["environments"]] == [
        "local",
        "ssh:gpu",
    ]


@pytest.mark.asyncio
async def test_routed_runtime_reauthorizes_async_approval_and_recovery_operations() -> (
    None
):
    runtime, runtimes, checks = _routed_runtime()
    call = ToolCall(
        "call-3",
        "bash",
        {"environment_id": "ssh:gpu", "command": "pwd"},
    )

    assert await runtime.approval_assessment_matches(call, {"risk": {}}) is True
    assert await runtime.approval_assessment_fingerprint(call) == "fingerprint:gpu"
    recovered = await runtime.verify_recovery(
        ToolCall(
            "call-4",
            "write",
            {"environment_id": "ssh:gpu", "path": "x", "content": "y"},
        )
    )

    assert checks == ["ssh:gpu", "ssh:gpu", "ssh:gpu"]
    assert runtimes["ssh:gpu"].approvals == [
        ToolCall("call-3", "bash", {"command": "pwd"}),
        ToolCall("call-3", "bash", {"command": "pwd"}),
    ]
    assert recovered.output["recovery_state"] == "verified"


@pytest.mark.asyncio
async def test_routed_runtime_defaults_approval_routing_to_local() -> None:
    runtime, runtimes, checks = _routed_runtime()

    fingerprint = await runtime.approval_assessment_fingerprint(
        ToolCall("call-local-approval", "bash", {"command": "pwd"})
    )

    assert fingerprint == "fingerprint:local"
    assert checks == ["local"]
    assert runtimes["local"].approvals == [
        ToolCall("call-local-approval", "bash", {"command": "pwd"})
    ]


@pytest.mark.asyncio
async def test_routed_runtime_accepts_async_approval_runtime_methods() -> None:
    runtime, runtimes, _ = _routed_runtime()

    async def async_fingerprint(_call: ToolCall) -> str:
        return "async-fingerprint"

    runtimes["ssh:gpu"].approval_assessment_fingerprint = async_fingerprint  # type: ignore[method-assign]

    fingerprint = await runtime.approval_assessment_fingerprint(
        ToolCall(
            "call-async",
            "bash",
            {"environment_id": "ssh:gpu", "command": "pwd"},
        )
    )

    assert fingerprint == "async-fingerprint"


@pytest.mark.asyncio
async def test_routed_runtime_batch_uses_the_same_per_call_routing() -> None:
    runtime, _, checks = _routed_runtime()

    batch = await runtime.execute_batch(
        (
            ToolCall("local-read", "read", {"environment_id": "local", "path": "a"}),
            ToolCall(
                "remote-read",
                "read",
                {"environment_id": "ssh:gpu", "path": "b"},
            ),
        )
    )

    assert isinstance(batch, ToolBatchResult)
    assert [result.output["runtime"] for result in batch.results] == ["local", "gpu"]
    assert checks == ["local", "ssh:gpu"]


@pytest.mark.asyncio
async def test_routed_runtime_serial_batch_cancels_calls_after_cancellation() -> None:
    runtime, runtimes, checks = _routed_runtime()
    original_execute = runtimes["local"].execute

    async def cancel_first(call: ToolCall, **kwargs) -> ToolResult:
        if call.call_id == "cancelled-bash":
            runtimes["local"].calls.append(call)
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.name,
                status="cancelled",
                replay_policy="never",
                error="tool execution was cancelled",
            )
        return await original_execute(call, **kwargs)

    runtimes["local"].execute = cancel_first  # type: ignore[method-assign]
    notified: list[ToolResult] = []

    batch = await runtime.execute_batch(
        (
            ToolCall(
                "cancelled-bash",
                "bash",
                {"environment_id": "local", "command": "sleep 1"},
            ),
            ToolCall(
                "unstarted-bash",
                "bash",
                {"environment_id": "ssh:gpu", "command": "pwd"},
            ),
        ),
        on_result=lambda result: _append_result(notified, result),
    )

    assert [result.status for result in batch.results] == ["cancelled", "cancelled"]
    assert [result.call_id for result in notified] == [
        "cancelled-bash",
        "unstarted-bash",
    ]
    assert batch.pending_calls == ()
    assert checks == ["local"]
    assert runtimes["ssh:gpu"].calls == []


async def _append_result(results: list[ToolResult], result: ToolResult) -> None:
    results.append(result)
