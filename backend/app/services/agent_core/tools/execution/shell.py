from __future__ import annotations

import asyncio
from typing import Any

from app.services.agent_core.sandbox import FilesystemPolicy
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.utils.exceptions import PermissionDeniedError


_BLOCKED_COMMANDS = {
    "bif",
    "curl",
    "docker",
    "git",
    "rm",
    "scp",
    "ssh",
    "sudo",
    "wget",
}


class ExecuteShellTool:
    spec = AgentToolSpec(
        name="execution.shell",
        description="Execute a controlled local command in argv form.",
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "array", "items": {"type": "string"}},
                "cwd": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 120},
                "output_limit": {"type": "integer", "minimum": 100, "maximum": 20000},
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
            },
            "required": ["exit_code", "stdout", "stderr", "cwd"],
        },
        risk_level="act_high",
        read_scope=["workspace"],
        write_scope=["workspace"],
        audit="Execute controlled shell command.",
        rollback_hint="Inspect command output and generated artifacts before reuse.",
        timeout_seconds=120,
        artifact_policy={"stdout": True, "stderr": True},
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del context
        command = input.get("command")
        if not isinstance(command, list) or not command or not all(
            isinstance(part, str) and part for part in command
        ):
            raise PermissionDeniedError("command must be a non-empty argv list")
        executable = command[0]
        if executable in _BLOCKED_COMMANDS:
            raise PermissionDeniedError(f"command is blocked: {executable}")
        cwd = FilesystemPolicy().require_allowed_dir(input.get("cwd"))
        timeout = int(input.get("timeout_seconds") or 30)
        output_limit = int(input.get("output_limit") or 8000)

        process = await asyncio.create_subprocess_exec(
            *command,
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
        }


def _limit(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[truncated]"
