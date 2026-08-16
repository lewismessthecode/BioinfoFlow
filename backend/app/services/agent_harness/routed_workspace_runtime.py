from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
import inspect
from typing import Any, Literal

from app.services.agent_harness.environment_scope import EnvironmentDescriptor
from app.services.agent_harness.environment_tool_routing import (
    DEFAULT_ENVIRONMENT_ID,
    ROUTED_WORKSPACE_TOOLS,
    execute_routed_tool_call,
    routed_tool_spec,
)
from app.services.agent_harness.tools.list_environments import ListEnvironmentsTool
from app.services.agent_harness.tools.specs import (
    ToolBatchResult,
    ToolCall,
    ToolResult,
)
from app.services.agent_harness.workspace_router import (
    EnvironmentRoutingError,
    WorkspaceRouter,
)


class RoutedWorkspaceRuntime:
    def __init__(
        self,
        *,
        router: WorkspaceRouter[Any],
        control_runtime: Any,
        environments: tuple[EnvironmentDescriptor, ...]
        | Callable[[], Awaitable[tuple[EnvironmentDescriptor, ...]]],
    ) -> None:
        self.router = router
        self.control_runtime = control_runtime
        self._list_environments = ListEnvironmentsTool(environments)
        routed = tuple(routed_tool_spec(spec) for spec in control_runtime.tools)
        self._tools = (*routed, self._list_environments.spec)
        self._tool_by_name = {spec.name: spec for spec in self._tools}
        self._bash_environment: dict[str, str] = {}
        self._interaction_scope: str | None = None
        self._bash_environment_provider: (
            Callable[[], Awaitable[dict[str, str]]] | None
        ) = None

    def with_bash_environment(self, environment: dict[str, str]):
        self._bash_environment = dict(environment)
        self.control_runtime.with_bash_environment(environment)
        return self

    def with_interaction_scope(self, scope: str):
        self._interaction_scope = scope
        self.control_runtime.with_interaction_scope(scope)
        return self

    def with_bash_environment_provider(
        self, provider: Callable[[], Awaitable[dict[str, str]]]
    ):
        self._bash_environment_provider = provider
        self.control_runtime.with_bash_environment_provider(provider)
        return self

    @property
    def tools(self):
        return self._tools

    @property
    def model_tools(self):
        return tuple(spec.model_definition() for spec in self._tools)

    def tool_spec(self, name: str):
        return self._tool_by_name.get(name)

    async def execute(
        self,
        call: ToolCall,
        *,
        cancellation: Any | None = None,
        interaction_response: dict[str, Any] | None = None,
    ) -> ToolResult:
        if call.name == "list_environments":
            output = await self._list_environments.run({}, _unused_context())
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.name,
                status="completed",
                replay_policy="safe",
                output=output,
            )
        if call.name not in ROUTED_WORKSPACE_TOOLS:
            return await self.control_runtime.execute(
                call,
                cancellation=cancellation,
                interaction_response=interaction_response,
            )

        async def execute_on(workspace: Any, routed_call: ToolCall) -> ToolResult:
            self._configure_runtime(workspace)
            return await workspace.execute(
                routed_call,
                cancellation=cancellation,
                interaction_response=interaction_response,
            )

        return await execute_routed_tool_call(
            self.router,
            call,
            execute=execute_on,
        )

    def _configure_runtime(self, workspace: Any) -> None:
        if self._interaction_scope:
            workspace.with_interaction_scope(self._interaction_scope)
        if self._bash_environment:
            workspace.with_bash_environment(self._bash_environment)
        if self._bash_environment_provider is not None:
            workspace.with_bash_environment_provider(self._bash_environment_provider)

    async def execute_batch(
        self,
        calls: Iterable[ToolCall],
        *,
        cancellation: Any | None = None,
        on_start: Callable[[ToolCall], Awaitable[None]] | None = None,
        on_result: Callable[[ToolResult], Awaitable[None]] | None = None,
    ) -> ToolBatchResult:
        ordered = tuple(calls)
        if not ordered:
            return ToolBatchResult(())
        pause_index = next(
            (index for index, call in enumerate(ordered) if call.name == "ask_user"),
            None,
        )
        active = ordered if pause_index is None else ordered[: pause_index + 1]
        pending = () if pause_index is None else ordered[pause_index + 1 :]
        callback_lock = asyncio.Lock()

        async def execute_one(call: ToolCall) -> ToolResult:
            if on_start is not None:
                async with callback_lock:
                    await on_start(call)
            result = await self.execute(call, cancellation=cancellation)
            if on_result is not None and result.status != "interaction_required":
                async with callback_lock:
                    await on_result(result)
            return result

        if self.batch_execution_mode(active) == "serial":
            results: list[ToolResult] = []
            for index, call in enumerate(active):
                result = await execute_one(call)
                results.append(result)
                if result.status == "interaction_required":
                    pending = (*active[index + 1 :], *pending)
                    break
                if result.status == "cancelled":
                    unfinished = (*active[index + 1 :], *pending)
                    for unfinished_call in unfinished:
                        cancelled = self._cancelled_result(unfinished_call)
                        if on_result is not None:
                            async with callback_lock:
                                await on_result(cancelled)
                        results.append(cancelled)
                    pending = ()
                    break
            return ToolBatchResult(tuple(results), tuple(pending))
        results = await asyncio.gather(*(execute_one(call) for call in active))
        return ToolBatchResult(tuple(results), tuple(pending))

    def batch_execution_mode(
        self, calls: Iterable[ToolCall]
    ) -> Literal["parallel", "serial", "mixed"]:
        ordered = tuple(calls)
        if len(ordered) < 2:
            return "serial"
        if all(call.name in {"read", "list_environments"} for call in ordered):
            return "parallel"
        return "serial"

    def _cancelled_result(self, call: ToolCall) -> ToolResult:
        spec = self.tool_spec(call.name)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.name,
            status="cancelled",
            replay_policy=spec.replay_policy if spec is not None else "never",
            error="tool execution was cancelled",
        )

    async def approval_assessment_matches(
        self,
        call: ToolCall,
        interaction: dict[str, Any] | None,
    ) -> bool:
        try:
            return await self._route_value(
                call,
                lambda workspace, routed_call: workspace.approval_assessment_matches(
                    routed_call,
                    interaction,
                ),
            )
        except (EnvironmentRoutingError, ValueError):
            return False

    async def approval_assessment_fingerprint(self, call: ToolCall) -> str:
        return await self._route_value(
            call,
            lambda workspace, routed_call: workspace.approval_assessment_fingerprint(
                routed_call
            ),
        )

    async def verify_recovery(self, call: ToolCall) -> ToolResult:
        async def verify(workspace: Any, routed_call: ToolCall) -> ToolResult:
            self._configure_runtime(workspace)
            return await workspace.verify_recovery(routed_call)

        return await execute_routed_tool_call(
            self.router,
            call,
            execute=verify,
        )

    def recovery_action(self, call: ToolCall, **state):
        if not state.get("execution_started") or state.get("result_committed"):
            return "none"
        spec = self.tool_spec(call.name)
        if spec is None or spec.replay_policy == "never":
            return "require_user"
        if spec.replay_policy == "verify":
            return "verify"
        return "retry"

    async def _route_value(
        self,
        call: ToolCall,
        operation: Callable[[Any, ToolCall], Any],
    ):
        environment_id = call.arguments.get("environment_id", DEFAULT_ENVIRONMENT_ID)
        if not isinstance(environment_id, str) or not environment_id.strip():
            raise ValueError("environment_id is required")
        routed_call = ToolCall(
            call.call_id,
            call.name,
            {
                key: value
                for key, value in call.arguments.items()
                if key != "environment_id"
            },
        )

        async def invoke(workspace: Any):
            self._configure_runtime(workspace)
            result = operation(workspace, routed_call)
            return await result if inspect.isawaitable(result) else result

        return await self.router.execute(environment_id.strip(), invoke)


def _unused_context():
    from app.services.agent_harness.tools.specs import ToolExecutionContext

    return ToolExecutionContext(backend=None)
