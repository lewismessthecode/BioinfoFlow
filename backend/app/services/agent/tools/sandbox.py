"""Code execution sandbox for safe script execution.

Provides sandboxed execution on macOS (sandbox-exec) and Linux (bubblewrap)
with fallback to direct execution when sandboxing is disabled.
"""

from __future__ import annotations

import asyncio
import platform
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecutionResult:
    """Result from code execution."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


# Output truncation limit
MAX_OUTPUT_BYTES = 10 * 1024  # 10KB


def _truncate_output(
    output: str, max_bytes: int = MAX_OUTPUT_BYTES
) -> tuple[str, bool]:
    """Truncate output to max_bytes, returning (output, was_truncated)."""
    encoded = output.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return output, False

    # Truncate at byte boundary
    truncated = encoded[:max_bytes].decode("utf-8", errors="replace")
    return truncated + "\n... [output truncated]", True


class CodeSandbox:
    """Sandbox for executing Python code with optional OS-level isolation.

    When sandbox is enabled:
    - macOS: Uses sandbox-exec with restricted profile
    - Linux: Uses bubblewrap (bwrap) if available

    When sandbox is disabled:
    - Direct execution with timeout only
    """

    # Characters that are special in SBPL sandbox profiles and must be rejected
    _SBPL_UNSAFE_CHARS = frozenset("\"'();\\")

    @staticmethod
    def _sanitize_sbpl_path(path: str) -> str:
        """Validate a path is safe for SBPL profile interpolation.

        Raises ValueError if the path contains SBPL-special characters.
        """
        unsafe_found = CodeSandbox._SBPL_UNSAFE_CHARS.intersection(path)
        if unsafe_found:
            raise ValueError(
                f"Workspace path contains unsafe characters for sandbox profile: {sorted(unsafe_found)}"
            )
        return path

    def __init__(self, workspace_root: Path, enabled: bool = False) -> None:
        """Initialize sandbox.

        Args:
            workspace_root: Root directory for workspace access
            enabled: Whether to enable OS-level sandboxing
        """
        self.workspace_root = workspace_root
        self.enabled = enabled
        self._system = platform.system()

    def _python_executable(self) -> str:
        """Resolve the interpreter used for code execution."""
        candidates = [
            sys.executable,
            shutil.which("python3"),
            shutil.which("python"),
        ]
        for candidate in candidates:
            if candidate:
                return candidate
        return "python"

    async def execute(
        self,
        script_path: Path,
        timeout: int = 30,
        working_dir: Path | None = None,
    ) -> ExecutionResult:
        """Execute a Python script.

        Args:
            script_path: Path to Python script to execute
            timeout: Maximum execution time in seconds
            working_dir: Working directory for execution

        Returns:
            ExecutionResult with stdout, stderr, exit_code
        """
        if not self.enabled:
            return await self._execute_direct(script_path, timeout, working_dir)

        if self._system == "Darwin":
            return await self._execute_macos(script_path, timeout, working_dir)
        elif self._system == "Linux":
            return await self._execute_linux(script_path, timeout, working_dir)
        else:
            # Fallback to direct execution on unsupported platforms
            return await self._execute_direct(script_path, timeout, working_dir)

    async def _execute_direct(
        self,
        script_path: Path,
        timeout: int,
        working_dir: Path | None = None,
    ) -> ExecutionResult:
        """Execute script directly without sandboxing."""
        cwd = working_dir or self.workspace_root

        cmd = [self._python_executable(), str(script_path)]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
                timed_out = False
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                stdout_bytes = b""
                stderr_bytes = b"Execution timed out"
                timed_out = True

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            # Truncate outputs
            stdout, _ = _truncate_output(stdout)
            stderr, _ = _truncate_output(stderr)

            return ExecutionResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=proc.returncode if proc.returncode is not None else -1,
                timed_out=timed_out,
            )

        except Exception as e:
            return ExecutionResult(
                stdout="",
                stderr=f"Execution error: {e}",
                exit_code=-1,
            )

    async def _execute_macos(
        self,
        script_path: Path,
        timeout: int,
        working_dir: Path | None = None,
    ) -> ExecutionResult:
        """Execute script with macOS sandbox-exec."""
        cwd = working_dir or self.workspace_root

        try:
            # Validate workspace_root is safe for SBPL interpolation
            safe_workspace = self._sanitize_sbpl_path(str(self.workspace_root))
        except ValueError as e:
            return ExecutionResult(
                stdout="",
                stderr=f"Sandbox execution error: {e}",
                exit_code=-1,
            )

        # Create sandbox profile that allows:
        # - Read access to Python and standard libraries
        # - Read/write access to workspace
        # - Network access disabled by default
        sandbox_profile = f"""
(version 1)
(deny default)
(allow process-exec)
(allow process-fork)
(allow signal)
(allow sysctl-read)

; Allow read access to system
(allow file-read*
    (subpath "/usr")
    (subpath "/System")
    (subpath "/Library")
    (subpath "/bin")
    (subpath "/sbin")
    (subpath "/var")
    (subpath "/private/var")
    (subpath "/dev")
    (literal "/etc/hosts")
    (literal "/etc/resolv.conf")
)

; Allow Python execution
(allow file-read* (subpath "/opt/homebrew"))
(allow file-read* (subpath "/usr/local"))

; Allow workspace access (read/write)
(allow file-read* (subpath "{safe_workspace}"))
(allow file-write* (subpath "{safe_workspace}"))

; Allow temp files
(allow file-read* (subpath "/tmp"))
(allow file-write* (subpath "/tmp"))
(allow file-read* (subpath "/private/tmp"))
(allow file-write* (subpath "/private/tmp"))

; Allow process info
(allow mach-lookup)
(allow ipc-posix-shm-read-data)
"""

        # Write profile to temp file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".sb",
            delete=False,
        ) as profile_file:
            profile_file.write(sandbox_profile)
            profile_path = profile_file.name

        try:
            cmd = [
                "sandbox-exec",
                "-f",
                profile_path,
                self._python_executable(),
                str(script_path),
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
                timed_out = False
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                stdout_bytes = b""
                stderr_bytes = b"Execution timed out"
                timed_out = True

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            # Truncate outputs
            stdout, _ = _truncate_output(stdout)
            stderr, _ = _truncate_output(stderr)

            return ExecutionResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=proc.returncode if proc.returncode is not None else -1,
                timed_out=timed_out,
            )

        except Exception as e:
            return ExecutionResult(
                stdout="",
                stderr=f"Sandbox execution error: {e}",
                exit_code=-1,
            )
        finally:
            # Clean up profile file
            Path(profile_path).unlink(missing_ok=True)

    async def _execute_linux(
        self,
        script_path: Path,
        timeout: int,
        working_dir: Path | None = None,
    ) -> ExecutionResult:
        """Execute script with Linux bubblewrap (bwrap)."""
        cwd = working_dir or self.workspace_root

        # Check if bubblewrap is available
        bwrap_path = shutil.which("bwrap")
        if not bwrap_path:
            # Fallback to direct execution
            return await self._execute_direct(script_path, timeout, working_dir)

        try:
            cmd = [
                bwrap_path,
                # Basic isolation
                "--unshare-net",  # No network
                "--die-with-parent",  # Kill on parent exit
                # Mount necessary paths read-only
                "--ro-bind",
                "/usr",
                "/usr",
                "--ro-bind",
                "/lib",
                "/lib",
                "--ro-bind",
                "/lib64",
                "/lib64",
                "--ro-bind",
                "/bin",
                "/bin",
                "--ro-bind",
                "/etc",
                "/etc",
                # Mount workspace read-write
                "--bind",
                str(self.workspace_root),
                str(self.workspace_root),
                # Create tmp
                "--tmpfs",
                "/tmp",
                # Set working directory
                "--chdir",
                str(cwd),
                # Execute Python
                self._python_executable(),
                str(script_path),
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
                timed_out = False
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                stdout_bytes = b""
                stderr_bytes = b"Execution timed out"
                timed_out = True

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            # Truncate outputs
            stdout, _ = _truncate_output(stdout)
            stderr, _ = _truncate_output(stderr)

            return ExecutionResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=proc.returncode if proc.returncode is not None else -1,
                timed_out=timed_out,
            )

        except Exception as e:
            return ExecutionResult(
                stdout="",
                stderr=f"Sandbox execution error: {e}",
                exit_code=-1,
            )
