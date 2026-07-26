from __future__ import annotations

import asyncio
import os
import signal
from typing import Any

from app.services.agent_core.permissions.command_risk import (
    CommandRiskAssessment,
    CommandTargetProfile,
    assess_command_risk,
)
from app.services.agent_core.sandbox import (
    FilesystemPolicy,
    SandboxRunner,
    SandboxUnavailableError,
    local_boundary_from_tool_context,
)
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
            "&& chains. rg/rg --files, jq, and sed are ordinary commands executed "
            "inside this tool; grep and glob also have focused read tools. Prefer "
            "structured Bioinfoflow platform tools for projects, workflows, runs, "
            "images, and remote connections. Dangerous commands require approval."
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

    def assess_risk(
        self,
        input: dict[str, Any],
        *,
        target: CommandTargetProfile | None = None,
    ) -> CommandRiskAssessment | None:
        command = input.get("command")
        if not isinstance(command, str) or not command.strip():
            return None
        if target is None:
            policy = FilesystemPolicy()
            roots = tuple(str(root) for root in policy.allowed_roots)
            runner = SandboxRunner.from_settings()
            target = CommandTargetProfile(
                kind="local",
                trust_domain="local-machine",
                identity="local-user",
                sandbox_strength="enforced"
                if runner.enabled and runner.available_adapter()
                else "none",
                read_roots=roots,
                write_roots=roots,
                working_directory=str(input.get("cwd") or policy.default_root),
                network_allowed=runner.allow_network,
                sandbox_bypass_requested=False,
            )
        return assess_command_risk(command, target=target)

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        boundary = await local_boundary_from_tool_context(context)
        command = input.get("command")
        if not isinstance(command, str) or not command.strip():
            raise PermissionDeniedError("command must be a non-empty string")
        cwd = boundary.policy.require_allowed_dir(
            input.get("cwd") or str(boundary.working_directory)
        )
        timeout = int(input.get("timeout_seconds") or 120)
        output_limit = int(input.get("output_limit") or 16000)

        # The OS sandbox — not the risk classifier — is the real boundary. When
        # enabled it confines writes to session capability roots. Bubblewrap also
        # confines reads to those roots; macOS Seatbelt applies permanent deny
        # rules for product source, internal state, and the Docker socket.
        runner = SandboxRunner.from_settings()
        if not runner.enabled:
            raise SandboxUnavailableError(
                "agent bash requires OS sandboxing; AGENT_SANDBOX_ENABLED cannot be false"
            )
        sandbox = runner.build(
            command=command,
            cwd=cwd,
            read_roots=list(boundary.read_roots),
            write_roots=list(boundary.write_roots),
            deny_read_roots=list(boundary.protected_roots),
        )

        process = await asyncio.create_subprocess_exec(
            *sandbox.argv,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError as exc:
            await _kill_process_group(process)
            raise TimeoutError(f"command timed out after {timeout}s") from exc
        except asyncio.CancelledError:
            await _kill_process_group(process)
            raise

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


async def _kill_process_group(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass
    await process.wait()
