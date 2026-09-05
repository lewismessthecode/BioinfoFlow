from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import replace
from typing import TypeVar

from app.services.agent_harness.tools.specs import (
    ReplayPolicy,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from app.services.agent_harness.workspace_router import (
    EnvironmentOutOfScopeError,
    EnvironmentRoutingError,
    WorkspaceRouter,
)


WorkspaceT = TypeVar("WorkspaceT")
ROUTED_WORKSPACE_TOOLS = frozenset(
    {"read", "bash", "edit", "write", "publish_artifact"}
)
DEFAULT_ENVIRONMENT_ID = "local"


def routed_tool_spec(spec: ToolSpec) -> ToolSpec:
    if spec.name not in ROUTED_WORKSPACE_TOOLS:
        return spec
    schema = deepcopy(spec.input_schema)
    properties = dict(schema.get("properties") or {})
    properties["environment_id"] = {"type": "string", "minLength": 1}
    schema["properties"] = properties
    return replace(spec, input_schema=schema)


async def execute_routed_tool_call(
    router: WorkspaceRouter[WorkspaceT],
    call: ToolCall,
    *,
    execute: Callable[[WorkspaceT, ToolCall], Awaitable[ToolResult]],
) -> ToolResult:
    environment_id = call.arguments.get("environment_id", DEFAULT_ENVIRONMENT_ID)
    if not isinstance(environment_id, str) or not environment_id.strip():
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.name,
            status="failed",
            replay_policy=_replay_policy(call.name),
            error="environment_id is required",
            output={"code": "environment_required"},
        )
    environment_id = environment_id.strip()
    routed_call = ToolCall(
        call_id=call.call_id,
        name=call.name,
        arguments={
            key: value
            for key, value in call.arguments.items()
            if key != "environment_id"
        },
    )
    try:
        result = await router.execute(
            environment_id,
            lambda workspace: execute(workspace, routed_call),
        )
        result = replace(
            result,
            output={**result.output, "environment_id": environment_id},
        )
        if result.interaction is None:
            return result
        environment = router.scope.require(environment_id)
        target = {
            "environment_id": environment.environment_id,
            "display_name": environment.display_name,
            "kind": environment.kind,
        }
        if environment.host:
            target["host"] = environment.host
        return replace(
            result,
            interaction=replace(
                result.interaction,
                target=target,
            ),
        )
    except EnvironmentRoutingError as exc:
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.name,
            status=(
                "blocked" if isinstance(exc, EnvironmentOutOfScopeError) else "failed"
            ),
            replay_policy=_replay_policy(call.name),
            error=str(exc),
            output={"code": exc.code, "environment_id": exc.environment_id},
        )
    except Exception as exc:  # noqa: BLE001 - adapter failures are tool results
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.name,
            status="failed",
            replay_policy=_replay_policy(call.name),
            error=str(exc) or "environment tool execution failed",
            output={
                "code": "environment_execution_failed",
                "environment_id": environment_id,
            },
        )


def _replay_policy(tool_name: str) -> ReplayPolicy:
    if tool_name in {"read", "publish_artifact"}:
        return "safe"
    if tool_name in {"edit", "write"}:
        return "verify"
    return "never"
