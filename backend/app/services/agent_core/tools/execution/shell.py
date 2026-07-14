from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.agent_core.permissions.command_risk import (
    CommandRiskAssessment,
    CommandTargetProfile,
    assess_command_risk,
)
from app.services.agent_core.sandbox import FilesystemPolicy, SandboxRunner
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
                "dangerously_disable_sandbox": {"type": "boolean"},
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
            roots = tuple(str(root) for root in FilesystemPolicy().allowed_roots)
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
                working_directory=str(input.get("cwd") or settings.repo_root),
                network_allowed=runner.allow_network,
                sandbox_bypass_requested=bool(
                    input.get("dangerously_disable_sandbox", False)
                ),
            )
        return assess_command_risk(command, target=target)

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        del context
        command = input.get("command")
        if not isinstance(command, str) or not command.strip():
            raise PermissionDeniedError("command must be a non-empty string")
        # Default to the repo root (which the environment prompt advertises as
        # the working directory) so repo-oriented commands like `git status`
        # and `rg --files` run against the code tree, not the data home.
        cwd = FilesystemPolicy().require_allowed_dir(
            input.get("cwd") or str(settings.repo_root)
        )
        timeout = int(input.get("timeout_seconds") or 120)
        output_limit = int(input.get("output_limit") or 16000)

        # The OS sandbox — not the risk classifier — is the real boundary. When
        # enabled it confines the process to the repo and data home; reads of
        # /etc, the wider FS, or the docker socket are blocked at the syscall
        # layer rather than merely flagged for approval.
        bioinfoflow_home = Path(settings.bioinfoflow_home).expanduser().resolve()
        repo_root = Path(settings.repo_root).expanduser().resolve()
        sandbox = SandboxRunner.from_settings().build(
            command=command,
            cwd=cwd,
            read_roots=[repo_root, bioinfoflow_home],
            write_roots=[cwd, bioinfoflow_home],
            disable_requested=bool(input.get("dangerously_disable_sandbox", False)),
        )

        process = await asyncio.create_subprocess_exec(
            *sandbox.argv,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
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
