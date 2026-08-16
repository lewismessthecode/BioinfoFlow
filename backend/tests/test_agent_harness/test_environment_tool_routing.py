from __future__ import annotations

import pytest

from app.services.agent_harness.environment_scope import (
    EnvironmentDescriptor,
    EnvironmentScopeRequest,
    resolve_environment_scope,
)
from app.services.agent_harness.environment_tool_routing import (
    execute_routed_tool_call,
    routed_tool_spec,
)
from app.services.agent_harness.tools.read import ReadTool
from app.services.agent_harness.tools.specs import ToolCall, ToolResult
from app.services.agent_harness.workspace_router import WorkspaceRouter


def test_routed_tool_schema_accepts_an_optional_opaque_environment_id() -> None:
    spec = routed_tool_spec(ReadTool.spec)

    assert spec.input_schema["properties"]["environment_id"] == {
        "type": "string",
        "minLength": 1,
    }
    assert spec.input_schema["required"] == ["path"]
    assert "enum" not in repr(spec.input_schema)


@pytest.mark.asyncio
async def test_routed_tool_call_selects_runtime_and_strips_routing_argument() -> None:
    scope = resolve_environment_scope(
        EnvironmentScopeRequest(mode="auto"),
        [EnvironmentDescriptor("ssh:gpu", "ssh", "GPU")],
    )

    async def authorize(_environment_id: str) -> bool:
        return True

    async def resolve(_environment_id: str) -> str | None:
        return "gpu-runtime"

    observed: list[tuple[str, ToolCall]] = []

    async def execute(runtime: str, call: ToolCall) -> ToolResult:
        observed.append((runtime, call))
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.name,
            status="completed",
            replay_policy="safe",
            output={"ok": True},
        )

    result = await execute_routed_tool_call(
        WorkspaceRouter(scope=scope, authorize=authorize, resolve=resolve),
        ToolCall(
            call_id="call-1",
            name="read",
            arguments={"environment_id": "ssh:gpu", "path": "README.md"},
        ),
        execute=execute,
    )

    assert result.status == "completed"
    assert observed == [
        (
            "gpu-runtime",
            ToolCall("call-1", "read", {"path": "README.md"}),
        )
    ]


@pytest.mark.asyncio
async def test_routed_tool_call_defaults_to_local_when_environment_is_omitted() -> None:
    scope = resolve_environment_scope(
        EnvironmentScopeRequest(mode="auto"),
        [
            EnvironmentDescriptor("local", "local", "Local"),
            EnvironmentDescriptor("ssh:gpu", "ssh", "GPU"),
        ],
    )
    authorization_checks: list[str] = []

    async def authorize(environment_id: str) -> bool:
        authorization_checks.append(environment_id)
        return True

    async def resolve(environment_id: str) -> str | None:
        return f"{environment_id}-runtime"

    observed: list[tuple[str, ToolCall]] = []

    async def execute(runtime: str, call: ToolCall) -> ToolResult:
        observed.append((runtime, call))
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.name,
            status="completed",
            replay_policy="safe",
            output={"ok": True},
        )

    result = await execute_routed_tool_call(
        WorkspaceRouter(scope=scope, authorize=authorize, resolve=resolve),
        ToolCall(
            call_id="call-local",
            name="read",
            arguments={"path": "README.md"},
        ),
        execute=execute,
    )

    assert result.status == "completed"
    assert authorization_checks == ["local"]
    assert observed == [
        (
            "local-runtime",
            ToolCall("call-local", "read", {"path": "README.md"}),
        )
    ]


@pytest.mark.asyncio
async def test_omitted_environment_is_blocked_when_manual_scope_excludes_local() -> (
    None
):
    scope = resolve_environment_scope(
        EnvironmentScopeRequest(
            mode="manual",
            selected_environment_ids=("ssh:gpu",),
        ),
        [
            EnvironmentDescriptor("local", "local", "Local"),
            EnvironmentDescriptor("ssh:gpu", "ssh", "GPU"),
        ],
    )

    async def authorize(_environment_id: str) -> bool:
        raise AssertionError("out-of-scope environments must not be authorized")

    async def resolve(_environment_id: str) -> object | None:
        raise AssertionError("out-of-scope environments must not be resolved")

    async def execute(_runtime: object, _call: ToolCall) -> ToolResult:
        raise AssertionError("out-of-scope calls must not execute")

    result = await execute_routed_tool_call(
        WorkspaceRouter(scope=scope, authorize=authorize, resolve=resolve),
        ToolCall(
            call_id="call-local-blocked",
            name="write",
            arguments={"path": "README.md", "content": "updated"},
        ),
        execute=execute,
    )

    assert result.status == "blocked"
    assert result.output == {
        "code": "environment_out_of_scope",
        "environment_id": "local",
    }


@pytest.mark.asyncio
async def test_routing_failures_are_structured_tool_results() -> None:
    scope = resolve_environment_scope(
        EnvironmentScopeRequest(
            mode="manual",
            selected_environment_ids=("local",),
        ),
        [EnvironmentDescriptor("local", "local", "Local")],
    )

    async def authorize(_environment_id: str) -> bool:
        return True

    async def resolve(_environment_id: str) -> object | None:
        return object()

    async def execute(_runtime: object, _call: ToolCall) -> ToolResult:
        raise AssertionError("out-of-scope calls must not execute")

    result = await execute_routed_tool_call(
        WorkspaceRouter(scope=scope, authorize=authorize, resolve=resolve),
        ToolCall(
            call_id="call-2",
            name="bash",
            arguments={"environment_id": "ssh:gpu", "command": "pwd"},
        ),
        execute=execute,
    )

    assert result.status == "blocked"
    assert result.error == "environment is outside this run's scope: ssh:gpu"
    assert result.output == {
        "code": "environment_out_of_scope",
        "environment_id": "ssh:gpu",
    }
