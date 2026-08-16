from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from app.services.agent_harness.environment_scope import ResolvedEnvironmentScope


WorkspaceT = TypeVar("WorkspaceT")
ResultT = TypeVar("ResultT")


class EnvironmentRoutingError(RuntimeError):
    code: str

    def __init__(self, environment_id: str, message: str) -> None:
        self.environment_id = environment_id
        super().__init__(message)


class EnvironmentOutOfScopeError(EnvironmentRoutingError):
    code = "environment_out_of_scope"


class EnvironmentUnavailableError(EnvironmentRoutingError):
    code = "environment_unavailable"


@dataclass(slots=True)
class WorkspaceRouter(Generic[WorkspaceT]):
    scope: ResolvedEnvironmentScope
    authorize: Callable[[str], Awaitable[bool]]
    resolve: Callable[[str], Awaitable[WorkspaceT | None]]

    async def _resolve_workspace(self, environment_id: str) -> WorkspaceT:
        if environment_id not in self.scope.environments:
            raise EnvironmentOutOfScopeError(
                environment_id,
                f"environment is outside this run's scope: {environment_id}",
            )
        if not await self.authorize(environment_id):
            raise EnvironmentOutOfScopeError(
                environment_id,
                f"environment authorization is no longer valid: {environment_id}",
            )
        workspace = await self.resolve(environment_id)
        if workspace is None:
            raise EnvironmentUnavailableError(
                environment_id,
                f"environment is unavailable: {environment_id}",
            )
        return workspace

    async def execute(
        self,
        environment_id: str,
        operation: Callable[[WorkspaceT], Awaitable[ResultT]],
    ) -> ResultT:
        workspace = await self._resolve_workspace(environment_id)
        return await operation(workspace)
