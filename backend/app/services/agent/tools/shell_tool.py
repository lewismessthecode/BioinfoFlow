"""Shell command tool for the agent.

Provides shell execution with command blocking and workspace scoping.
Allows pipes, chains, and redirection — like Claude Code's Bash tool.
Blocks destructive commands (rm, sudo, etc.) at the token level.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.services.agent.tools.base import BaseTool, RiskLevel, ToolResult
from app.services.agent.tools import register_tool

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# Commands that are always blocked — destructive or privilege-escalation.
# Note: this list is defense in depth only. ShellTool runs through
# create_subprocess_shell (full shell interpretation), so any interpreter
# or network-egress binary not in this list can still escape the sandbox.
# The tool's risk_level = ACT_HIGH ensures every invocation is gated by
# the approval workflow regardless of what's on this list.
BLOCKED_TOKENS = {
    "rm",
    "rmdir",
    "dd",
    "mkfs",
    "fdisk",
    "kill",
    "killall",
    "shutdown",
    "reboot",
    "passwd",
    "chown",
    "chmod",
    "su",
    "sudo",
    "systemctl",
    "launchctl",
    # Interpreters that trivially bypass the blocklist:
    "python",
    "python3",
    "bash",
    "sh",
    "zsh",
    "ruby",
    "perl",
    "node",
    # File movers and network clients that can smuggle data out:
    "mv",
    "curl",
    "wget",
    "nc",
    "ncat",
    "scp",
    "rsync",
    "ssh",
    # Package installers:
    "pip",
    "pip3",
    "npm",
    "pnpm",
    "yarn",
    "brew",
    "apt",
    "apt-get",
}

# Output limits
MAX_OUTPUT_CHARS = 50_000
COMMAND_TIMEOUT = 120  # seconds


@register_tool
class ShellTool(BaseTool):
    """Run shell commands inside the workspace.

    Supports full shell syntax: pipes, chains (&&, ||), redirection,
    subshells, and environment variables. Blocked: rm, sudo, and other
    destructive commands.
    """

    name = "shell"
    description = (
        "Run a shell command. Use this only for diagnostics or one-off "
        "commands that don't fit any other tool. For Bioinfoflow platform "
        "operations (projects, workflows, runs) prefer the `platform_*` "
        "tools — they return structured data and skip approval for reads. "
        "Blocked tokens: rm, sudo, kill, chmod, and other destructive ones. "
        "Every shell call goes through the approval flow."
    )
    risk_level = RiskLevel.ACT_HIGH

    def __init__(
        self,
        session: "AsyncSession",
        *,
        project_id: str,
        workspace_root: Path | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> None:
        super().__init__(
            session,
            project_id=project_id,
            workspace_root=workspace_root,
            user_id=user_id,
            workspace_id=workspace_id,
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "command": {
                "type": "string",
                "description": (
                    "Shell command to execute. Supports pipes, chains, "
                    "and redirection. Use `bif --output json` for "
                    "platform operations (workflows, runs, files, etc.)."
                ),
                "required": True,
            },
        }

    async def execute(self, *, command: str) -> ToolResult:
        """Run a shell command inside the workspace."""
        try:
            self._validate_command(command)
            root = await self._get_workspace_root()

            try:
                proc = await asyncio.wait_for(
                    asyncio.create_subprocess_shell(
                        command,
                        cwd=root,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    ),
                    timeout=COMMAND_TIMEOUT,
                )
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=COMMAND_TIMEOUT
                )
                stdout = stdout_bytes.decode(errors="replace") if stdout_bytes else ""
                stderr = stderr_bytes.decode(errors="replace") if stderr_bytes else ""
                returncode = proc.returncode or 0
            except asyncio.TimeoutError:
                stdout, stderr, returncode = "", "Command timed out", 1

            output = (stdout + stderr).strip()
            truncated = False
            if len(output) > MAX_OUTPUT_CHARS:
                output = output[:MAX_OUTPUT_CHARS] + "\n...(truncated)"
                truncated = True

            return ToolResult(
                success=True,
                data={
                    "command": command,
                    "exit_code": returncode,
                    "output": output,
                },
                truncated=truncated,
            )

        except PermissionError as e:
            return ToolResult(success=False, error=str(e))
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"Unexpected error: {e}")

    def _validate_command(self, command: str) -> None:
        """Validate shell command for safety.

        Raises:
            ValueError: If command uses blocked tokens
        """
        if not command or not command.strip():
            raise ValueError("Shell command is empty")

        # Tokenize by whitespace and common shell delimiters to find
        # blocked commands anywhere in a pipeline or chain.
        # Split on spaces, pipes, semicolons, and logical operators.
        import re

        tokens = re.split(r"[\s|;&]+", command)
        for token in tokens:
            # Strip leading path components (e.g., /usr/bin/rm → rm)
            base = token.rsplit("/", 1)[-1]
            if base in BLOCKED_TOKENS:
                raise ValueError(
                    f"Command '{base}' is not permitted (blocked for safety). "
                    f"Blocked commands: {', '.join(sorted(BLOCKED_TOKENS))}"
                )
