from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.config import settings
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
        level = classify_shell_command(command)
        # A command the classifier would auto-run, but which reaches an absolute
        # path outside the allowed roots (e.g. `cat /etc/passwd`, `find /`),
        # must still ask: the cwd check alone does not constrain path arguments.
        if level in {"read", "act_low"} and _references_out_of_root_path(command):
            return "act_high"
        return level

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
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


def _references_out_of_root_path(command: str) -> bool:
    """True if the command names an absolute/home path outside allowed roots.

    Heuristic and conservative: any token that looks like an absolute path
    (`/…`) or a home path (`~…`) and does not resolve under an allowed root
    means the command can read or write outside the sandbox, so it should ask
    for approval rather than auto-run.
    """
    roots = FilesystemPolicy().allowed_roots
    for raw in command.split():
        token = raw.strip("\"'")
        # An env-var path (e.g. `$HOME/.ssh`) can't be resolved statically, so
        # it can't be vouched for as in-root — ask.
        if token.startswith("$") and "/" in token:
            return True
        if not (token.startswith("/") or token.startswith("~")):
            continue
        try:
            candidate = Path(token).expanduser().resolve()
        except (OSError, RuntimeError, ValueError):
            return True
        if not any(_is_relative_to(candidate, root) for root in roots):
            return True
    return False


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _limit(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[truncated]"
