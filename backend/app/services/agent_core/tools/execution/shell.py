from __future__ import annotations

import asyncio
from typing import Any

from app.services.agent_core.permissions.risk import RiskLevel
from app.services.agent_core.permissions.shell_risk import classify_shell_command
from app.services.agent_core.sandbox import FilesystemPolicy
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.utils.exceptions import PermissionDeniedError


class ExecuteShellTool:
    """Run a real shell command via ``bash -lc``.

    Unlike a fixed argv runner, this supports pipes, globs, redirects, and
    ``&&`` chains so the agent can use the shell the way a developer would
    (`ls`, `grep`, `rg`, `find`, `git`, `docker`, …). Safety comes from two
    places: the working directory is constrained to the allowed roots, and the
    command string is risk-classified (:func:`classify_shell_command`) so the
    permission policy auto-runs safe commands, asks before dangerous ones, and
    hard-blocks catastrophic ones.
    """

    spec = AgentToolSpec(
        name="bash",
        description=(
            "Run a shell command via bash. Supports pipes, globs, redirects, and "
            "&& chains. Use it for ls, cat, grep, rg, find, git, and docker instead "
            "of asking the user. Dangerous commands are gated for approval."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "minLength": 1},
                "cwd": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 600},
                "output_limit": {"type": "integer", "minimum": 100, "maximum": 50000},
                "description": {"type": "string"},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "exit_code": {"type": "integer"},
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "cwd": {"type": "string"},
                "command": {"type": "string"},
            },
            "required": ["exit_code", "stdout", "stderr", "cwd", "command"],
        },
        risk_level="act_high",
        read_scope=["workspace"],
        write_scope=["workspace"],
        audit="Execute a shell command via bash.",
        rollback_hint="Inspect command output and generated artifacts; reverse any file changes via version control.",
        timeout_seconds=120,
        artifact_policy={"stdout": True, "stderr": True, "type": "command"},
    )

    def assess_risk(self, input: dict[str, Any]) -> RiskLevel | None:
        command = input.get("command")
        if not isinstance(command, str) or not command.strip():
            return None
        return classify_shell_command(command)

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del context
        command = input.get("command")
        if not isinstance(command, str) or not command.strip():
            raise PermissionDeniedError("command must be a non-empty string")
        cwd = FilesystemPolicy().require_allowed_dir(input.get("cwd"))
        timeout = int(input.get("timeout_seconds") or 120)
        output_limit = int(input.get("output_limit") or 16000)

        process = await asyncio.create_subprocess_exec(
            "bash",
            "-lc",
            command,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.wait()
            raise TimeoutError(f"command timed out after {timeout}s") from exc

        return {
            "exit_code": int(process.returncode or 0),
            "stdout": _limit(stdout.decode("utf-8", errors="replace"), output_limit),
            "stderr": _limit(stderr.decode("utf-8", errors="replace"), output_limit),
            "cwd": str(cwd),
            "command": command,
        }


def _limit(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[truncated]"
