from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.services.agent_harness.environment_scope import EnvironmentDescriptor
from app.services.agent_harness.tools.specs import ToolExecutionContext, ToolSpec


class ListEnvironmentsTool:
    spec = ToolSpec(
        name="list_environments",
        description=(
            "List the local and SSH execution environments visible to this run. "
            "Use the opaque environment_id in workspace tool calls."
        ),
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        replay_policy="safe",
        display_name="List environments",
        category="read",
        summary="List execution environments",
    )

    def __init__(
        self,
        environments: tuple[EnvironmentDescriptor, ...]
        | Callable[[], Awaitable[tuple[EnvironmentDescriptor, ...]]],
    ) -> None:
        self.environments = environments

    async def run(
        self, arguments: dict[str, Any], context: ToolExecutionContext
    ) -> dict[str, Any]:
        del arguments, context
        environments = (
            await self.environments()
            if callable(self.environments)
            else self.environments
        )
        return {
            "environments": [
                {
                    "environment_id": environment.environment_id,
                    "kind": environment.kind,
                    "display_name": environment.display_name,
                    "description": environment.description,
                    "status": environment.status,
                }
                for environment in environments
            ]
        }
