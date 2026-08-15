from __future__ import annotations

from typing import Any

from app.services.agent_harness.command_risk import CommandRiskAssessment
from app.services.agent_harness.tools.specs import ToolExecutionContext, ToolSpec


class BashTool:
    spec = ToolSpec(
        name="bash",
        description=(
            "Run a shell command in the workspace under the operating-system "
            "sandbox. Use it for rg, find, jq, git, tests, workflow programs and "
            "the authenticated bif --output json CLI."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "minLength": 1},
                "cwd": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 600},
                "output_limit": {"type": "integer", "minimum": 100, "maximum": 50_000},
                "description": {"type": "string"},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
        replay_policy="never",
        display_name="Bash",
        category="command",
        summary="Run command",
        input_summary_fields=("description",),
        mutates_workspace=True,
    )

    def assess_risk(
        self, arguments: dict[str, Any], context: ToolExecutionContext
    ) -> CommandRiskAssessment:
        command = arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("command must be non-empty text")
        return context.backend.assess_command(command, cwd=arguments.get("cwd"))

    async def run(
        self, arguments: dict[str, Any], context: ToolExecutionContext
    ) -> dict[str, Any]:
        command = arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("command must be non-empty text")
        timeout = _bounded_int(
            arguments.get("timeout_seconds"), default=120, minimum=1, maximum=600
        )
        output_limit = _bounded_int(
            arguments.get("output_limit"), default=16_000, minimum=100, maximum=50_000
        )
        return await context.backend.run_command(
            command=command,
            cwd=arguments.get("cwd"),
            timeout_seconds=timeout,
            output_limit=output_limit,
            cancellation=context.cancellation,
            environment=context.environment,
        )


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("numeric bash limits must be integers")
    if not minimum <= value <= maximum:
        raise ValueError(f"value must be between {minimum} and {maximum}")
    return value
