from __future__ import annotations

import asyncio
import base64
import errno
import json
import os
import secrets
import shlex
import shutil
import signal
import stat
import sys
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from app.services.agent_harness.command_risk import (
    CommandTargetProfile,
    assess_command_risk,
)
from app.services.agent_harness.sandbox import FilesystemPolicy, SandboxRunner
from app.services.agent_harness.token_policy import (
    is_scoped_bif_command,
    scoped_bif_argv,
)
from app.services.remote_execution import RemoteConnectionConfig, RemoteExecutor
from app.utils.exceptions import PermissionDeniedError
from app.services.agent_harness.tools import (
    HarnessTool,
    PermissionMode,
    ToolBatchResult,
    ToolCall,
    ToolExecutor,
    ToolResult,
    WorkspaceAccess,
)


_SECRET_ENV_SUFFIXES = ("_TOKEN", "_KEY", "_API_KEY", "_SECRET", "_PASSWORD")
_SECRET_ENV_NAMES = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "DEEPSEEK_API_KEY",
        "BETTER_AUTH_SECRET",
    }
)
_BASE_ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "HOME",
        "TMPDIR",
        "TMP",
        "TEMP",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "COLORTERM",
        "NO_COLOR",
        "TZ",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
)
_HARNESS_ENV_ALLOWLIST = frozenset(
    {
        "BIOFLOW_API_URL",
        "BIOFLOW_PROJECT",
        "BIOFLOW_OUTPUT",
        "BIOFLOW_AGENT_TOKEN",
    }
)
ArtifactWriter = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
_LOCAL_ARTIFACT_CAPTURE_LIMIT = 30 * 1024 * 1024
_REMOTE_ARTIFACT_CAPTURE_LIMIT = 5 * 1024 * 1024
_LOCAL_STREAM_CHUNK_SIZE = 64 * 1024
_DIRECT_FILE_READ_LIMIT = 20 * 1024 * 1024
_FILE_READ_CHUNK_SIZE = 64 * 1024
_FILE_TOO_LARGE_ERROR = "file exceeds the configured read limit"
_MAX_MUTABLE_TEXT_BYTES = 8 * 1024 * 1024
_MUTABLE_TEXT_TOO_LARGE_ERROR = (
    "existing file exceeds the 8 MiB edit/write limit; "
    "use bash or an appropriate command-line program"
)


@dataclass(frozen=True, slots=True)
class WorkspaceFileRead:
    path: str
    data: bytes
    size: int
    truncated: bool


class _BoundedProcessCapture:
    def __init__(self, limit: int) -> None:
        self.limit = max(1, limit)
        self.stdout = bytearray()
        self.stderr = bytearray()
        self.stdout_truncated = False
        self.stderr_truncated = False
        self.limit_exceeded = asyncio.Event()
        self._lock = asyncio.Lock()

    async def read_stream(
        self,
        stream: asyncio.StreamReader,
        *,
        name: str,
    ) -> None:
        target = self.stdout if name == "stdout" else self.stderr
        while chunk := await stream.read(_LOCAL_STREAM_CHUNK_SIZE):
            async with self._lock:
                remaining = self.limit - len(self.stdout) - len(self.stderr)
                if remaining > 0:
                    target.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    if name == "stdout":
                        self.stdout_truncated = True
                    else:
                        self.stderr_truncated = True
                    self.limit_exceeded.set()
                    return


class LocalWorkspaceBackend:
    def __init__(
        self,
        *,
        working_directory: Path,
        read_roots: tuple[Path, ...],
        write_roots: tuple[Path, ...],
        protected_roots: tuple[Path, ...] = (),
        sandbox_runner: SandboxRunner | None = None,
        base_environment: dict[str, str] | None = None,
        artifact_writer: ArtifactWriter | None = None,
    ) -> None:
        self.policy = FilesystemPolicy(
            read_roots=list(read_roots),
            write_roots=list(write_roots),
            protected_roots=list(protected_roots),
            default_root=working_directory,
        )
        self.working_directory = self.policy.require_allowed_dir(str(working_directory))
        self.protected_roots = tuple(self.policy.sandbox_protected_roots())
        self.protected_read_roots = tuple(self.policy.sandbox_protected_read_roots())
        self.sandbox_runner = sandbox_runner or SandboxRunner.from_settings()
        self.base_environment = dict(base_environment or os.environ)
        self._safe_path = _safe_path(
            self.base_environment.get("PATH", ""),
            write_roots=self.policy.write_roots,
        )
        self._trusted_bif = _trusted_bif_executable(self._safe_path)
        self.artifact_writer = artifact_writer

    def canonical_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = self.working_directory / candidate
        return candidate.resolve(strict=False)

    def resolve_read_path(self, raw_path: Any) -> Path:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("path must be non-empty text")
        candidate = self.canonical_path(raw_path)
        return self.policy.require_allowed_path(
            candidate, must_exist=True, allow_directory=False
        )

    async def read_file(
        self,
        raw_path: Any,
        *,
        max_bytes: int,
        allow_truncated: bool,
    ) -> WorkspaceFileRead:
        path = self.resolve_read_path(raw_path)
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        file_fd = self._open_read_file(path)
        try:
            metadata = os.fstat(file_fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise PermissionDeniedError(f"Expected a regular file: {path}")
            if metadata.st_size > max_bytes and not allow_truncated:
                raise ValueError(_FILE_TOO_LARGE_ERROR)
            chunks: list[bytes] = []
            remaining = max_bytes + 1
            while remaining > 0:
                chunk = os.read(file_fd, min(_FILE_READ_CHUNK_SIZE, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            exceeded_limit = len(data) > max_bytes
            if exceeded_limit:
                if not allow_truncated:
                    raise ValueError(_FILE_TOO_LARGE_ERROR)
                data = data[:max_bytes]
            truncated = exceeded_limit or metadata.st_size > len(data)
            return WorkspaceFileRead(
                path=str(path),
                data=data,
                size=metadata.st_size,
                truncated=truncated,
            )
        finally:
            os.close(file_fd)

    def _open_read_file(self, target: Path) -> int:
        root = max(
            (root for root in self.policy.read_roots if _is_relative_to(target, root)),
            key=lambda candidate: len(candidate.parts),
            default=None,
        )
        if root is None:
            raise PermissionDeniedError(f"Path is outside allowed roots: {target}")
        relative = target.relative_to(root)
        if not relative.parts:
            raise PermissionDeniedError(
                f"Expected a file path, got directory: {target}"
            )

        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        try:
            current_fd = os.open(root, directory_flags)
        except OSError as exc:
            raise PermissionDeniedError(f"Read root is not available: {root}") from exc
        try:
            for component in relative.parts[:-1]:
                try:
                    next_fd = os.open(
                        component,
                        directory_flags,
                        dir_fd=current_fd,
                    )
                except OSError as exc:
                    raise PermissionDeniedError(
                        f"Parent directory is not available: {target.parent}"
                    ) from exc
                os.close(current_fd)
                current_fd = next_fd
            try:
                return os.open(
                    relative.name,
                    os.O_RDONLY | os.O_NOFOLLOW,
                    dir_fd=current_fd,
                )
            except OSError as exc:
                raise PermissionDeniedError(f"File is not available: {target}") from exc
        finally:
            os.close(current_fd)

    async def read_bytes(self, raw_path: Any) -> tuple[str, bytes]:
        result = await self.read_file(
            raw_path,
            max_bytes=_DIRECT_FILE_READ_LIMIT,
            allow_truncated=False,
        )
        return result.path, result.data

    def resolve_write_path(
        self,
        raw_path: Any,
        *,
        must_exist: bool,
        create_parents: bool,
    ) -> Path:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("path must be non-empty text")
        target = self.policy.require_writable_path(
            self.canonical_path(raw_path),
            must_exist=must_exist,
            allow_directory=False,
        )
        parent_fd, _ = self._open_write_parent(
            target,
            create_parents=create_parents,
        )
        os.close(parent_fd)
        return target

    async def edit_text(
        self,
        raw_path: Any,
        *,
        old_text: str,
        new_text: str,
        replace_all: bool,
    ) -> tuple[str, str, str, int]:
        path = self.resolve_write_path(raw_path, must_exist=True, create_parents=False)
        parent_fd, name = self._open_write_parent(path, create_parents=False)
        try:
            original, mode = _read_local_text_at(parent_fd, name, required=True)
            assert original is not None
            assert mode is not None
            updated, replacements = _replace_exact(
                original,
                old_text=old_text,
                new_text=new_text,
                replace_all=replace_all,
            )
            _replace_local_text_at(parent_fd, name, updated, mode=mode)
        finally:
            os.close(parent_fd)
        return str(path), original, updated, replacements

    async def write_text(self, raw_path: Any, content: str) -> tuple[str, str, bool]:
        path = self.resolve_write_path(raw_path, must_exist=False, create_parents=True)
        parent_fd, name = self._open_write_parent(path, create_parents=False)
        try:
            existing, mode = _read_local_text_at(parent_fd, name, required=False)
            original = existing or ""
            changed = original != content
            if changed:
                _replace_local_text_at(parent_fd, name, content, mode=mode)
        finally:
            os.close(parent_fd)
        return str(path), original, changed

    def _open_write_parent(
        self,
        target: Path,
        *,
        create_parents: bool,
    ) -> tuple[int, str]:
        root = max(
            (root for root in self.policy.write_roots if _is_relative_to(target, root)),
            key=lambda candidate: len(candidate.parts),
            default=None,
        )
        if root is None:
            raise PermissionDeniedError(f"Path is outside allowed roots: {target}")
        relative = target.relative_to(root)
        if not relative.parts:
            raise PermissionDeniedError(
                f"Expected a file path, got directory: {target}"
            )

        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        current_fd = os.open(root, directory_flags)
        try:
            for component in relative.parts[:-1]:
                try:
                    next_fd = os.open(
                        component,
                        directory_flags,
                        dir_fd=current_fd,
                    )
                except FileNotFoundError:
                    if not create_parents:
                        raise PermissionDeniedError(
                            f"Parent directory is not available: {target.parent}"
                        ) from None
                    try:
                        os.mkdir(component, mode=0o755, dir_fd=current_fd)
                    except FileExistsError:
                        pass
                    next_fd = os.open(
                        component,
                        directory_flags,
                        dir_fd=current_fd,
                    )
                except OSError as exc:
                    raise PermissionDeniedError(
                        f"Parent directory is not available: {target.parent}"
                    ) from exc
                os.close(current_fd)
                current_fd = next_fd
            return current_fd, relative.name
        except BaseException:
            os.close(current_fd)
            raise

    def assess_command(self, command: str, *, cwd: Any = None):
        working_directory = self.policy.require_allowed_dir(
            cwd if isinstance(cwd, str) else str(self.working_directory)
        )
        adapter = self.sandbox_runner.available_adapter()
        return assess_command_risk(
            command,
            target=CommandTargetProfile(
                kind="local",
                trust_domain="local-machine",
                identity="agent",
                sandbox_strength=(
                    "enforced"
                    if self.sandbox_runner.enabled and adapter is not None
                    else "none"
                ),
                read_roots=tuple(str(root) for root in self.policy.read_roots),
                write_roots=tuple(str(root) for root in self.policy.write_roots),
                working_directory=str(working_directory),
                network_allowed=self.sandbox_runner.allow_network,
            ),
        )

    async def command_cwd_binding(self, cwd: Any) -> dict[str, Any]:
        working_directory = self.policy.require_allowed_dir(
            cwd if isinstance(cwd, str) else str(self.working_directory)
        )
        return _local_cwd_binding(working_directory)

    async def run_command(
        self,
        *,
        command: str,
        cwd: Any,
        timeout_seconds: int,
        output_limit: int,
        cancellation: Any | None,
        environment: dict[str, str],
        expected_cwd_binding: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        working_directory = self.policy.require_allowed_dir(
            cwd if isinstance(cwd, str) else str(self.working_directory)
        )
        if not self.sandbox_runner.enabled:
            raise RuntimeError("agent bash requires operating-system sandboxing")
        scoped_bif = self.allows_scoped_bif_token(command) and bool(
            environment.get("BIOFLOW_AGENT_TOKEN")
        )
        execution_command = (
            self._trusted_bif_command(command) if scoped_bif else command
        )
        cwd_fd = None
        if expected_cwd_binding is not None:
            cwd_fd, current_binding = _open_local_cwd_binding(working_directory)
            try:
                _require_cwd_binding(current_binding, expected_cwd_binding)
            except BaseException:
                os.close(cwd_fd)
                raise
            working_directory = Path(current_binding["path"])
        try:
            sandbox = self.sandbox_runner.build(
                command=execution_command,
                cwd=working_directory,
                cwd_fd=cwd_fd,
                read_roots=list(self.policy.read_roots),
                write_roots=list(self.policy.write_roots),
                protected_roots=list(self.protected_roots),
                protected_read_roots=list(self.protected_read_roots),
                allow_network=(
                    self.sandbox_runner.allow_network
                    or (
                        scoped_bif
                        and bool(environment.get("BIOFLOW_AGENT_TOKEN"))
                        and bool(environment.get("BIOFLOW_API_URL"))
                    )
                ),
            )
            process_argv = sandbox.argv
            process_cwd = str(working_directory)
            process_options: dict[str, Any] = {}
            if cwd_fd is not None and expected_cwd_binding is not None:
                process_argv = _local_cwd_guard_argv(
                    sandbox.argv,
                    cwd_fd=cwd_fd,
                    binding=expected_cwd_binding,
                )
                process_cwd = "/"
                process_options["pass_fds"] = (cwd_fd,)
            process = await asyncio.create_subprocess_exec(
                *process_argv,
                cwd=process_cwd,
                env=self._child_environment(environment),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
                **process_options,
            )
        finally:
            if cwd_fd is not None:
                os.close(cwd_fd)
        if process.stdout is None or process.stderr is None:
            await _kill_process_group(process)
            raise RuntimeError("agent bash did not provide output pipes")
        capture = _BoundedProcessCapture(_LOCAL_ARTIFACT_CAPTURE_LIMIT)
        stdout_reader = asyncio.create_task(
            capture.read_stream(process.stdout, name="stdout"),
            name="agent-bash-stdout-reader",
        )
        stderr_reader = asyncio.create_task(
            capture.read_stream(process.stderr, name="stderr"),
            name="agent-bash-stderr-reader",
        )
        readers = asyncio.gather(stdout_reader, stderr_reader)
        cancelled = asyncio.create_task(_wait_for_cancellation(cancellation))
        capture_limit_reached = asyncio.create_task(capture.limit_exceeded.wait())
        try:
            done, _ = await asyncio.wait(
                {readers, cancelled, capture_limit_reached},
                timeout=timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancelled in done:
                await _kill_process_group(process)
                await asyncio.gather(readers, return_exceptions=True)
                raise asyncio.CancelledError
            if capture_limit_reached in done:
                await _kill_process_group(process)
                await asyncio.gather(readers, return_exceptions=True)
            elif readers in done:
                readers.result()
                await process.wait()
            else:
                await _kill_process_group(process)
                await asyncio.gather(readers, return_exceptions=True)
                raise TimeoutError(f"command timed out after {timeout_seconds}s")
        except asyncio.CancelledError:
            await _kill_process_group(process)
            await asyncio.gather(readers, return_exceptions=True)
            raise
        except BaseException:
            await _kill_process_group(process)
            await asyncio.gather(readers, return_exceptions=True)
            raise
        finally:
            cancelled.cancel()
            capture_limit_reached.cancel()
            await asyncio.gather(
                cancelled,
                capture_limit_reached,
                return_exceptions=True,
            )
        secrets = _secret_values(environment)
        full_stdout = _redact(
            bytes(capture.stdout).decode("utf-8", errors="replace"), secrets
        )
        full_stderr = _redact(
            bytes(capture.stderr).decode("utf-8", errors="replace"), secrets
        )
        if (
            expected_cwd_binding is not None
            and process.returncode == 126
            and _CWD_BINDING_MARKER in full_stderr
        ):
            raise PermissionDeniedError(_CWD_BINDING_ERROR)
        stdout_text, inline_stdout_truncated = _limit_output(full_stdout, output_limit)
        stderr_text, inline_stderr_truncated = _limit_output(full_stderr, output_limit)
        stdout_truncated = capture.stdout_truncated or inline_stdout_truncated
        stderr_truncated = capture.stderr_truncated or inline_stderr_truncated
        output_limit_exceeded = capture.limit_exceeded.is_set()
        result = {
            "exit_code": int(process.returncode or 0),
            "stdout": stdout_text,
            "stderr": stderr_text,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "truncated": stdout_truncated or stderr_truncated,
            "output_limit_exceeded": output_limit_exceeded,
            "cwd": str(working_directory),
            "command": command,
        }
        if self.artifact_writer is not None and (stdout_truncated or stderr_truncated):
            result["artifact"] = await self.artifact_writer(
                {
                    "type": "command_output",
                    "command": command,
                    "cwd": str(working_directory),
                    "stdout": full_stdout,
                    "stderr": full_stderr,
                    "capture_truncated": output_limit_exceeded,
                }
            )
        return result

    def _require_write_root(self, target: Path) -> None:
        if not any(_is_relative_to(target, root) for root in self.policy.write_roots):
            raise ValueError(f"path is outside writable roots: {target}")
        if any(_is_relative_to(target, root) for root in self.protected_roots):
            raise ValueError(f"path is protected: {target}")

    def _child_environment(self, injected: dict[str, str]) -> dict[str, str]:
        allowed = {
            key: value
            for key, value in self.base_environment.items()
            if key in _BASE_ENV_ALLOWLIST
        }
        allowed.update(
            {
                key: value
                for key, value in injected.items()
                if key in _HARNESS_ENV_ALLOWLIST
            }
        )
        if self._safe_path:
            allowed["PATH"] = self._safe_path
        else:
            allowed.pop("PATH", None)
        return allowed

    def allows_scoped_bif_token(self, command: object) -> bool:
        return self._trusted_bif is not None and scoped_bif_argv(command) is not None

    def _trusted_bif_command(self, command: str) -> str:
        argv = scoped_bif_argv(command)
        if argv is None or self._trusted_bif is None:
            raise RuntimeError("scoped bif command is not trusted")
        return shlex.join((str(self._trusted_bif), *argv[1:]))


class RemoteWorkspaceBackend:
    def __init__(
        self,
        *,
        connection: RemoteConnectionConfig,
        executor: RemoteExecutor,
        working_directory: str,
        read_roots: tuple[str, ...],
        write_roots: tuple[str, ...],
        allow_network: bool = False,
        artifact_writer: ArtifactWriter | None = None,
    ) -> None:
        self.connection = connection
        self.executor = executor
        self.working_directory = _normalized_remote_absolute(working_directory)
        self.read_roots = tuple(
            _normalized_remote_absolute(root) for root in read_roots
        )
        self.write_roots = tuple(
            _normalized_remote_absolute(root) for root in write_roots
        )
        self.allow_network = allow_network
        self.artifact_writer = artifact_writer
        self._sandbox_preflight: dict[str, Any] | None = None
        self._sandbox_preflight_lock = asyncio.Lock()
        self._bif_preflight: str | None = None
        self._bif_preflight_lock = asyncio.Lock()
        if not self.read_roots or not self.write_roots:
            raise ValueError("remote workspace requires read and write roots")
        self._require_remote_root(self.working_directory, self.read_roots)

    def canonical_path(self, raw_path: str) -> PurePosixPath:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("path must be non-empty text")
        candidate = PurePosixPath(raw_path)
        if ".." in candidate.parts:
            raise ValueError("path is outside remote workspace roots")
        if not candidate.is_absolute():
            candidate = self.working_directory / candidate
        return _normalized_remote_absolute(str(candidate))

    async def read_file(
        self,
        raw_path: Any,
        *,
        max_bytes: int,
        allow_truncated: bool,
    ) -> WorkspaceFileRead:
        path = self.canonical_path(raw_path)
        self._require_remote_root(path, self.read_roots)
        result = await self._run_helper(
            _REMOTE_READ_SCRIPT,
            [str(path), str(max_bytes), "1" if allow_truncated else "0"],
            output_limit=30 * 1024 * 1024,
            writable=False,
        )
        data = base64.b64decode(result["data"], validate=True)
        size = result.get("size", len(data))
        truncated = result.get("truncated", False)
        if not isinstance(size, int) or isinstance(size, bool) or size < len(data):
            raise ValueError("remote workspace returned invalid file metadata")
        if not isinstance(truncated, bool):
            raise ValueError("remote workspace returned invalid file metadata")
        return WorkspaceFileRead(
            path=str(path),
            data=data,
            size=size,
            truncated=truncated,
        )

    async def read_bytes(self, raw_path: Any) -> tuple[str, bytes]:
        result = await self.read_file(
            raw_path,
            max_bytes=_DIRECT_FILE_READ_LIMIT,
            allow_truncated=False,
        )
        return result.path, result.data

    async def edit_text(
        self,
        raw_path: Any,
        *,
        old_text: str,
        new_text: str,
        replace_all: bool,
    ) -> tuple[str, str, str, int]:
        path = self.canonical_path(raw_path)
        self._require_remote_root(path, self.write_roots)
        result = await self._run_helper(
            _REMOTE_EDIT_SCRIPT,
            [
                str(path),
                _encode_text(old_text),
                _encode_text(new_text),
                "1" if replace_all else "0",
                str(_MAX_MUTABLE_TEXT_BYTES),
            ],
            writable=True,
        )
        return (
            str(path),
            _decode_text(result["before"]),
            _decode_text(result["after"]),
            int(result["replacements"]),
        )

    async def write_text(self, raw_path: Any, content: str) -> tuple[str, str, bool]:
        path = self.canonical_path(raw_path)
        self._require_remote_root(path, self.write_roots)
        result = await self._run_helper(
            _REMOTE_WRITE_SCRIPT,
            [str(path), _encode_text(content), str(_MAX_MUTABLE_TEXT_BYTES)],
            writable=True,
        )
        return str(path), _decode_text(result["before"]), bool(result["changed"])

    def assess_command(self, command: str, *, cwd: Any = None):
        working_directory = self._command_cwd(cwd)
        return assess_command_risk(
            command,
            target=CommandTargetProfile(
                kind="remote_ssh",
                trust_domain=self.connection.host,
                identity=self.connection.username,
                sandbox_strength="enforced",
                read_roots=tuple(str(root) for root in self.read_roots),
                write_roots=tuple(str(root) for root in self.write_roots),
                working_directory=str(working_directory),
                network_allowed=self.allow_network,
                connection_id=self.connection.id,
            ),
            requested_connection_id=self.connection.id,
        )

    async def command_cwd_binding(self, cwd: Any) -> dict[str, Any]:
        working_directory = self._command_cwd(cwd)
        sandbox = await self._trusted_remote_sandbox(timeout_seconds=30)
        command = "{} -c {} {} {}".format(
            shlex.quote(sandbox["python"]),
            shlex.quote(_REMOTE_CWD_IDENTITY_SCRIPT),
            shlex.quote(str(working_directory)),
            " ".join(shlex.quote(str(root)) for root in self.read_roots),
        )
        result = await self.executor.run(
            self.connection,
            command,
            timeout_seconds=30,
            output_limit=4096,
        )
        if result.exit_code != 0:
            raise PermissionDeniedError(
                result.stderr.strip()
                or "Remote Bash working directory identity is unavailable"
            )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise PermissionDeniedError(
                "Remote Bash working directory identity is unavailable"
            ) from exc
        if not _valid_cwd_binding(payload):
            raise PermissionDeniedError(
                "Remote Bash working directory identity is unavailable"
            )
        return payload

    async def run_command(
        self,
        *,
        command: str,
        cwd: Any,
        timeout_seconds: int,
        output_limit: int,
        cancellation: Any | None,
        environment: dict[str, str],
        expected_cwd_binding: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        working_directory = self._command_cwd(cwd)
        if expected_cwd_binding is not None:
            current_binding = await self.command_cwd_binding(cwd)
            _require_cwd_binding(current_binding, expected_cwd_binding)
            working_directory = _normalized_remote_absolute(
                str(current_binding["path"])
            )
        safe_environment = {
            key: value
            for key, value in environment.items()
            if key in _HARNESS_ENV_ALLOWLIST
        }
        token = safe_environment.pop("BIOFLOW_AGENT_TOKEN", None)
        bif_argv = scoped_bif_argv(command) if token else None
        execution_command = command
        if bif_argv is not None:
            trusted_bif = await self._trusted_remote_bif(
                timeout_seconds=_remaining_timeout(deadline)
            )
            execution_command = shlex.join((trusted_bif, *bif_argv[1:]))
        sandbox = await self._trusted_remote_sandbox(
            timeout_seconds=_remaining_timeout(deadline)
        )
        if bif_argv is not None and not _remote_path_is_bound_read_only(
            _normalized_remote_absolute(trusted_bif),
            system_roots=tuple(
                _normalized_remote_absolute(root) for root in sandbox["system_roots"]
            ),
            read_roots=self.read_roots,
            write_roots=self.write_roots,
        ):
            raise RuntimeError(
                "remote bif executable is outside the sandbox runtime roots"
            )
        use_token_stdin = bool(token) and bif_argv is not None
        inner_command = _remote_inner_command(
            execution_command,
            environment=safe_environment,
            read_token_from_stdin=use_token_stdin,
        )
        remote_command = _remote_bubblewrap_command(
            sandbox=sandbox,
            command=inner_command,
            cwd=working_directory,
            read_roots=self.read_roots,
            write_roots=self.write_roots,
            cwd_fd=(
                _REMOTE_APPROVED_CWD_FD if expected_cwd_binding is not None else None
            ),
            allow_network=(
                self.allow_network
                or (use_token_stdin and bool(safe_environment.get("BIOFLOW_API_URL")))
            ),
        )
        if expected_cwd_binding is not None:
            remote_command = _remote_cwd_guard_command(
                python=sandbox["python"],
                shell=sandbox["shell"],
                command=remote_command,
                binding=expected_cwd_binding,
                cwd_fd=_REMOTE_APPROVED_CWD_FD,
            )
        capture_limit = max(output_limit, _REMOTE_ARTIFACT_CAPTURE_LIMIT)
        if use_token_stdin:
            run = self.executor.run_with_stdin(
                self.connection,
                remote_command,
                stdin_data=f"{token}\n".encode(),
                timeout_seconds=_remaining_timeout(deadline),
                output_limit=capture_limit,
            )
        else:
            run = self.executor.run(
                self.connection,
                remote_command,
                timeout_seconds=_remaining_timeout(deadline),
                output_limit=capture_limit,
            )
        task = asyncio.create_task(run)
        cancellation_task = asyncio.create_task(_wait_for_cancellation(cancellation))
        done, _ = await asyncio.wait(
            {task, cancellation_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if cancellation_task in done:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise asyncio.CancelledError
        cancellation_task.cancel()
        result = task.result()
        if (
            expected_cwd_binding is not None
            and result.exit_code == 126
            and _CWD_BINDING_MARKER in result.stderr
        ):
            raise PermissionDeniedError(_CWD_BINDING_ERROR)
        secrets = _secret_values(environment)
        full_stdout = _redact(result.stdout, secrets)
        full_stderr = _redact(result.stderr, secrets)
        stdout, inline_stdout_truncated = _limit_output(full_stdout, output_limit)
        stderr, inline_stderr_truncated = _limit_output(full_stderr, output_limit)
        stdout_truncated = result.stdout_truncated or inline_stdout_truncated
        stderr_truncated = result.stderr_truncated or inline_stderr_truncated
        observation = {
            "exit_code": result.exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "cwd": str(working_directory),
            "command": command,
        }
        if self.artifact_writer is not None and (stdout_truncated or stderr_truncated):
            observation["artifact"] = await self.artifact_writer(
                {
                    "type": "command_output",
                    "command": command,
                    "cwd": str(working_directory),
                    "stdout": full_stdout,
                    "stderr": full_stderr,
                    "capture_truncated": bool(
                        result.stdout_truncated or result.stderr_truncated
                    ),
                }
            )
        return observation

    def allows_scoped_bif_token(self, command: object) -> bool:
        return is_scoped_bif_command(command)

    async def _trusted_remote_bif(self, *, timeout_seconds: int) -> str:
        if self._bif_preflight is not None:
            return self._bif_preflight
        async with self._bif_preflight_lock:
            if self._bif_preflight is not None:
                return self._bif_preflight
            result = await self.executor.run(
                self.connection,
                "python3 -c " + shlex.quote(_REMOTE_BIF_DISCOVERY_SCRIPT),
                timeout_seconds=timeout_seconds,
                output_limit=4096,
            )
            if result.exit_code != 0:
                raise RuntimeError("remote bif executable could not be verified")
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "remote bif verification returned invalid output"
                ) from exc
            path = payload.get("path") if isinstance(payload, dict) else None
            writable = payload.get("writable") if isinstance(payload, dict) else None
            if (
                not isinstance(path, str)
                or not path.startswith("/")
                or writable is not False
            ):
                raise RuntimeError("remote bif executable is not trusted")
            resolved = _normalized_remote_absolute(path)
            if any(
                resolved == root or root in resolved.parents
                for root in self.write_roots
            ):
                raise RuntimeError(
                    "remote bif executable is inside a writable workspace root"
                )
            self._bif_preflight = str(resolved)
            return self._bif_preflight

    async def _trusted_remote_sandbox(
        self, *, timeout_seconds: int = 30
    ) -> dict[str, Any]:
        if self._sandbox_preflight is not None:
            return self._sandbox_preflight
        async with self._sandbox_preflight_lock:
            if self._sandbox_preflight is not None:
                return self._sandbox_preflight
            result = await self.executor.run(
                self.connection,
                "python3 -c " + shlex.quote(_REMOTE_SANDBOX_DISCOVERY_SCRIPT),
                timeout_seconds=timeout_seconds,
                output_limit=8192,
            )
            if result.exit_code != 0:
                raise RuntimeError("remote agent bash requires bubblewrap sandboxing")
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "remote agent bash requires bubblewrap sandboxing"
                ) from exc
            if not isinstance(payload, dict) or payload.get("available") is not True:
                raise RuntimeError("remote agent bash requires bubblewrap sandboxing")
            path = payload.get("path")
            writable = payload.get("writable")
            shell = payload.get("shell")
            python = payload.get("python", "/usr/bin/python3")
            python_writable = payload.get("python_writable", False)
            system_roots = payload.get("system_roots")
            network_roots = payload.get("network_roots", [])
            if (
                not isinstance(path, str)
                or not path.startswith("/")
                or writable is not False
                or not isinstance(shell, str)
                or not shell.startswith("/")
                or not isinstance(python, str)
                or not python.startswith("/")
                or python_writable is not False
                or not isinstance(system_roots, list)
                or not isinstance(network_roots, list)
                or not all(
                    isinstance(root, str) and root.startswith("/")
                    for root in [*system_roots, *network_roots]
                )
            ):
                raise RuntimeError("remote bubblewrap sandbox could not be trusted")
            resolved_path = _normalized_remote_absolute(path)
            resolved_shell = _normalized_remote_absolute(shell)
            resolved_python = _normalized_remote_absolute(python)
            if (
                any(
                    resolved_path == root or root in resolved_path.parents
                    for root in self.write_roots
                )
                or any(
                    resolved_shell == root or root in resolved_shell.parents
                    for root in self.write_roots
                )
                or any(
                    resolved_python == root or root in resolved_python.parents
                    for root in self.write_roots
                )
            ):
                raise RuntimeError(
                    "remote bubblewrap runtime is inside a writable root"
                )
            resolved_system_roots = [
                _normalized_remote_absolute(root) for root in system_roots
            ]
            if not any(
                resolved_python == root or root in resolved_python.parents
                for root in resolved_system_roots
            ):
                raise RuntimeError(
                    "remote Python runtime is outside the sandbox runtime roots"
                )
            self._sandbox_preflight = {
                "path": str(resolved_path),
                "shell": str(resolved_shell),
                "python": str(resolved_python),
                "system_roots": [str(root) for root in resolved_system_roots],
                "network_roots": [
                    str(_normalized_remote_absolute(root)) for root in network_roots
                ],
            }
            return self._sandbox_preflight

    async def _run_helper(
        self,
        script: str,
        arguments: list[str],
        *,
        output_limit: int = 20_000_000,
        writable: bool,
    ) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + 120
        sandbox = await self._trusted_remote_sandbox(
            timeout_seconds=_remaining_timeout(deadline)
        )
        helper_command = "{} -c {} {}".format(
            shlex.quote(sandbox["python"]),
            shlex.quote(script),
            " ".join(shlex.quote(value) for value in arguments),
        )
        command = _remote_bubblewrap_command(
            sandbox=sandbox,
            command=helper_command,
            cwd=self.working_directory,
            read_roots=self.read_roots,
            write_roots=self.write_roots if writable else (),
            allow_network=False,
        )
        result = await self.executor.run(
            self.connection,
            command,
            timeout_seconds=_remaining_timeout(deadline),
            output_limit=output_limit,
        )
        payload: Any = None
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            if result.exit_code != 0:
                raise ValueError(
                    result.stderr.strip() or "remote workspace operation failed"
                ) from None
            raise ValueError("remote workspace returned invalid JSON") from None
        if result.exit_code != 0:
            if isinstance(payload, dict) and payload.get("error"):
                raise ValueError(str(payload["error"]))
            raise ValueError(
                result.stderr.strip() or "remote workspace operation failed"
            )
        if not isinstance(payload, dict):
            raise ValueError("remote workspace returned invalid output")
        if payload.get("error"):
            raise ValueError(str(payload["error"]))
        return payload

    def _command_cwd(self, cwd: Any) -> PurePosixPath:
        selected = self.working_directory if cwd is None else self.canonical_path(cwd)
        self._require_remote_root(selected, self.read_roots)
        return selected

    @staticmethod
    def _require_remote_root(
        path: PurePosixPath, roots: tuple[PurePosixPath, ...]
    ) -> None:
        if not any(path == root or root in path.parents for root in roots):
            raise ValueError(f"path is outside remote workspace roots: {path}")


class WorkspaceRuntime:
    def __init__(
        self,
        backend: LocalWorkspaceBackend | RemoteWorkspaceBackend,
        *,
        permission_mode: PermissionMode = "ask_dangerous",
        workspace_access: WorkspaceAccess = "read_write",
        environment: dict[str, str] | None = None,
        bash_environment: dict[str, str] | None = None,
        bash_environment_provider: Callable[[], Awaitable[dict[str, str]]]
        | None = None,
        extra_tools: Iterable[HarnessTool] = (),
    ) -> None:
        self._executor = ToolExecutor(
            backend,
            permission_mode=permission_mode,
            workspace_access=workspace_access,
            environment=environment,
            bash_environment=bash_environment,
            bash_environment_provider=bash_environment_provider,
            extra_tools=extra_tools,
        )

    def with_bash_environment(self, environment: dict[str, str]) -> WorkspaceRuntime:
        self._executor.bash_environment = dict(environment)
        return self

    def with_bash_environment_provider(
        self, provider: Callable[[], Awaitable[dict[str, str]]]
    ) -> WorkspaceRuntime:
        self._executor.bash_environment_provider = provider
        return self

    @property
    def tools(self):
        return self._executor.tools

    @property
    def model_tools(self):
        return self._executor.model_tools

    async def execute(
        self,
        call: ToolCall,
        *,
        cancellation: Any | None = None,
        interaction_response: dict[str, Any] | None = None,
    ) -> ToolResult:
        return await self._executor.execute(
            call,
            cancellation=cancellation,
            interaction_response=interaction_response,
        )

    async def execute_batch(
        self,
        calls: Iterable[ToolCall],
        *,
        cancellation: Any | None = None,
        on_start: Callable[[ToolCall], Awaitable[None]] | None = None,
        on_result: Callable[[ToolResult], Awaitable[None]] | None = None,
    ) -> ToolBatchResult:
        return await self._executor.execute_batch(
            calls,
            cancellation=cancellation,
            on_start=on_start,
            on_result=on_result,
        )

    def batch_execution_mode(
        self, calls: Iterable[ToolCall]
    ) -> Literal["parallel", "serial", "mixed"]:
        return self._executor.batch_execution_mode(calls)

    def approval_assessment_matches(
        self,
        call: ToolCall,
        interaction: dict[str, Any] | None,
    ) -> bool:
        return self._executor.approval_assessment_matches(call, interaction)

    def approval_assessment_fingerprint(self, call: ToolCall) -> str:
        return self._executor.approval_assessment_fingerprint(call)

    async def verify_recovery(self, call: ToolCall) -> ToolResult:
        """Verify an interrupted edit/write before deciding whether to replay it."""

        if call.name not in {"edit", "write"}:
            raise ValueError(f"tool does not support verified recovery: {call.name}")
        path = call.arguments.get("path")
        try:
            _, data = await self._executor.backend.read_bytes(path)
            current = data.decode("utf-8")
        except Exception:  # noqa: BLE001 - missing/unreadable state is classified below
            current = None
        if call.name == "write":
            expected = call.arguments.get("content")
            if isinstance(expected, str) and current == expected:
                return _verified_recovery_result(call, "already_applied")
            return _recovery_execution_result(await self.execute(call))

        old_text = call.arguments.get("old_text")
        new_text = call.arguments.get("new_text")
        replace_all = call.arguments.get("replace_all") is True
        if not isinstance(old_text, str) or not isinstance(new_text, str):
            return _ambiguous_recovery_result(call)
        if current is not None and old_text not in current and new_text in current:
            return _verified_recovery_result(call, "already_applied")
        old_count = current.count(old_text) if current is not None else 0
        can_prove_not_applied = current is not None and (
            (replace_all and old_count > 0 and new_text not in current)
            or (not replace_all and old_count == 1)
        )
        if can_prove_not_applied:
            return _recovery_execution_result(await self.execute(call))
        return _ambiguous_recovery_result(call)

    def recovery_action(self, call: ToolCall, **state):
        return self._executor.recovery_action(call, **state)


def _verified_recovery_result(call: ToolCall, state: str) -> ToolResult:
    return ToolResult(
        call_id=call.call_id,
        tool_name=call.name,
        status="completed",
        replay_policy="verify",
        output={"recovery_state": state},
    )


def _recovery_execution_result(result: ToolResult) -> ToolResult:
    return ToolResult(
        call_id=result.call_id,
        tool_name=result.tool_name,
        status=result.status,
        replay_policy=result.replay_policy,
        output={**result.output, "recovery_state": "executed_after_verification"},
        error=result.error,
        interaction=result.interaction,
    )


def _ambiguous_recovery_result(call: ToolCall) -> ToolResult:
    return ToolResult.interaction_required(
        call_id=call.call_id,
        tool_name=call.name,
        replay_policy="verify",
        request_id=f"recovery:{call.call_id}",
        kind="recovery",
    )


async def _wait_for_cancellation(cancellation: Any | None) -> None:
    if cancellation is None:
        await asyncio.Future()
    wait = getattr(cancellation, "wait", None)
    if not callable(wait):
        await asyncio.Future()
    await wait()


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


def _limit_output(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + "\n[truncated]", True


def _is_long_lived_secret(name: str) -> bool:
    upper = name.upper()
    return upper in _SECRET_ENV_NAMES or upper.endswith(_SECRET_ENV_SUFFIXES)


def _secret_values(environment: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        value
        for key, value in environment.items()
        if value and (_is_long_lived_secret(key) or key == "BIOFLOW_AGENT_TOKEN")
    )


def _redact(text: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        text = text.replace(secret, "[REDACTED]")
    return text


def _read_local_text_at(
    parent_fd: int,
    name: str,
    *,
    required: bool,
) -> tuple[str | None, int | None]:
    try:
        file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
    except FileNotFoundError:
        if not required:
            return None, None
        raise PermissionDeniedError(f"Path is not available: {name}") from None
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise PermissionDeniedError(
                f"Refusing to follow a changed workspace path: {name}"
            ) from exc
        raise

    try:
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise PermissionDeniedError(f"Expected a regular file: {name}")
        if metadata.st_size > _MAX_MUTABLE_TEXT_BYTES:
            raise ValueError(_MUTABLE_TEXT_TOO_LARGE_ERROR)
        with os.fdopen(file_fd, "rb") as handle:
            file_fd = -1
            data = handle.read(_MAX_MUTABLE_TEXT_BYTES + 1)
            if len(data) > _MAX_MUTABLE_TEXT_BYTES:
                raise ValueError(_MUTABLE_TEXT_TOO_LARGE_ERROR)
            return data.decode("utf-8"), stat.S_IMODE(metadata.st_mode)
    finally:
        if file_fd >= 0:
            os.close(file_fd)


def _replace_local_text_at(
    parent_fd: int,
    name: str,
    content: str,
    *,
    mode: int | None,
) -> None:
    temporary_name = ""
    temporary_fd = -1
    for _ in range(16):
        temporary_name = f".{name}.{secrets.token_hex(8)}.tmp"
        try:
            temporary_fd = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                mode if mode is not None else 0o666,
                dir_fd=parent_fd,
            )
            break
        except FileExistsError:
            continue
    else:
        raise RuntimeError("could not allocate a workspace temporary file")

    try:
        if mode is not None:
            os.fchmod(temporary_fd, mode)
        remaining = memoryview(content.encode("utf-8"))
        while remaining:
            written = os.write(temporary_fd, remaining)
            if written <= 0:
                raise OSError("workspace write made no progress")
            remaining = remaining[written:]
        os.fsync(temporary_fd)
        os.close(temporary_fd)
        temporary_fd = -1
        os.replace(
            temporary_name,
            name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        temporary_name = ""
    finally:
        if temporary_fd >= 0:
            os.close(temporary_fd)
        if temporary_name:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass


def _replace_exact(
    original: str, *, old_text: str, new_text: str, replace_all: bool
) -> tuple[str, int]:
    matches = original.count(old_text)
    if matches == 0:
        raise ValueError("old_text was not found in the file")
    if matches != 1 and not replace_all:
        raise ValueError("old_text must match exactly once unless replace_all is true")
    updated = original.replace(old_text, new_text, -1 if replace_all else 1)
    return updated, matches if replace_all else 1


def _normalized_remote_absolute(path: str) -> PurePosixPath:
    candidate = PurePosixPath(path)
    if not candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("remote workspace paths must be normalized absolute paths")
    return candidate


def _local_cwd_binding(path: Path) -> dict[str, Any]:
    descriptor, binding = _open_local_cwd_binding(path)
    os.close(descriptor)
    return binding


def _open_local_cwd_binding(path: Path) -> tuple[int, dict[str, Any]]:
    resolved = path.resolve(strict=True)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(resolved, flags)
    identity = os.fstat(descriptor)
    return (
        descriptor,
        {
            "path": str(resolved),
            "device": identity.st_dev,
            "inode": identity.st_ino,
        },
    )


def _valid_cwd_binding(binding: Any) -> bool:
    if not isinstance(binding, dict):
        return False
    path = binding.get("path")
    device = binding.get("device")
    inode = binding.get("inode")
    return (
        isinstance(path, str)
        and path.startswith("/")
        and isinstance(device, int)
        and not isinstance(device, bool)
        and isinstance(inode, int)
        and not isinstance(inode, bool)
    )


def _require_cwd_binding(
    current: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    if not _valid_cwd_binding(expected) or current != expected:
        raise PermissionDeniedError("Bash working directory changed after approval")


def _remote_cwd_guard_command(
    *,
    python: str,
    shell: str,
    command: str,
    binding: dict[str, Any],
    cwd_fd: int,
) -> str:
    _require_cwd_binding(binding, binding)
    argv = (
        python,
        "-c",
        _REMOTE_CWD_GUARD_SCRIPT,
        str(binding["path"]),
        str(binding["device"]),
        str(binding["inode"]),
        str(cwd_fd),
        shell,
        command,
    )
    return shlex.join(argv)


def _local_cwd_guard_argv(
    sandbox_argv: list[str],
    *,
    cwd_fd: int,
    binding: dict[str, Any],
) -> list[str]:
    _require_cwd_binding(binding, binding)
    return [
        sys.executable,
        "-I",
        "-c",
        _LOCAL_CWD_GUARD_SCRIPT,
        str(cwd_fd),
        str(binding["device"]),
        str(binding["inode"]),
        *sandbox_argv,
    ]


def _encode_text(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _decode_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("remote workspace returned invalid text")
    return base64.b64decode(value, validate=True).decode("utf-8")


def _valid_environment_name(name: str) -> bool:
    return bool(name) and name.replace("_", "A").isalnum() and not name[0].isdigit()


def _remote_inner_command(
    command: str,
    *,
    environment: dict[str, str],
    read_token_from_stdin: bool,
) -> str:
    statements = [
        f"export {key}={shlex.quote(value)}"
        for key, value in environment.items()
        if _valid_environment_name(key)
    ]
    if read_token_from_stdin:
        statements.extend(
            [
                "IFS= read -r BIOFLOW_AGENT_TOKEN",
                "export BIOFLOW_AGENT_TOKEN",
            ]
        )
    statements.append(command)
    return " && ".join(statements)


def _remote_bubblewrap_command(
    *,
    sandbox: dict[str, Any],
    command: str,
    cwd: PurePosixPath,
    read_roots: tuple[PurePosixPath, ...],
    write_roots: tuple[PurePosixPath, ...],
    allow_network: bool,
    cwd_fd: int | None = None,
) -> str:
    system_roots = tuple(
        _normalized_remote_absolute(root) for root in sandbox["system_roots"]
    )
    network_roots = (
        tuple(
            _normalized_remote_absolute(root)
            for root in sandbox.get("network_roots", [])
        )
        if allow_network
        else ()
    )
    shell = _normalized_remote_absolute(sandbox["shell"])
    argv = [
        str(sandbox["path"]),
        "--die-with-parent",
        "--new-session",
        "--unshare-user",
        "--uid",
        "0",
        "--gid",
        "0",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--unshare-cgroup",
        "--clearenv",
        "--setenv",
        "PATH",
        "/usr/local/bin:/usr/bin:/bin",
        "--setenv",
        "HOME",
        str(cwd),
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
    ]
    if cwd_fd is not None:
        argv.extend(("--sync-fd", str(cwd_fd)))
    if not allow_network:
        argv.append("--unshare-net")
    roots = (
        *system_roots,
        *network_roots,
        *read_roots,
        *write_roots,
        cwd,
        shell.parent,
    )
    for directory in _remote_parent_directories(roots):
        argv.extend(("--dir", str(directory)))
    for root in _dedupe_remote_paths(system_roots):
        argv.extend(("--ro-bind", str(root), str(root)))
    for root in _dedupe_remote_paths(network_roots):
        argv.extend(("--ro-bind", str(root), str(root)))
    for root in _dedupe_remote_paths(read_roots):
        argv.extend(("--ro-bind", str(root), str(root)))
    for root in _dedupe_remote_paths(write_roots):
        argv.extend(("--bind", str(root), str(root)))
    if cwd_fd is not None:
        cwd_bind = (
            "--bind"
            if any(cwd == root or root in cwd.parents for root in write_roots)
            else "--ro-bind"
        )
        argv.extend(
            (
                cwd_bind,
                f"/proc/self/fd/{cwd_fd}",
                str(cwd),
            )
        )
    argv.extend(
        (
            "--chdir",
            str(cwd),
            "--",
            str(shell),
            "--noprofile",
            "--norc",
            "-c",
            command,
        )
    )
    return shlex.join(argv)


def _remote_parent_directories(
    roots: Iterable[PurePosixPath],
) -> tuple[PurePosixPath, ...]:
    directories: set[PurePosixPath] = set()
    for root in roots:
        parent = root.parent
        while parent != PurePosixPath("/"):
            directories.add(parent)
            parent = parent.parent
    return tuple(sorted(directories, key=lambda path: (len(path.parts), str(path))))


def _dedupe_remote_paths(
    roots: Iterable[PurePosixPath],
) -> tuple[PurePosixPath, ...]:
    result: list[PurePosixPath] = []
    for root in roots:
        if root not in result:
            result.append(root)
    return tuple(result)


def _remote_path_is_bound_read_only(
    path: PurePosixPath,
    *,
    system_roots: tuple[PurePosixPath, ...],
    read_roots: tuple[PurePosixPath, ...],
    write_roots: tuple[PurePosixPath, ...],
) -> bool:
    if any(path == root or root in path.parents for root in write_roots):
        return False
    return any(
        path == root or root in path.parents for root in (*system_roots, *read_roots)
    )


def _remaining_timeout(deadline: float) -> int:
    remaining = deadline - asyncio.get_running_loop().time()
    if remaining <= 0:
        raise TimeoutError("remote command timed out during sandbox preflight")
    return max(1, int(remaining))


def _safe_path(value: str, *, write_roots: list[Path]) -> str:
    safe: list[str] = []
    for raw in value.split(os.pathsep):
        if not raw or not Path(raw).is_absolute():
            continue
        path = Path(raw).expanduser().resolve(strict=False)
        if any(_is_relative_to(path, root) for root in write_roots):
            continue
        text = str(path)
        if text not in safe:
            safe.append(text)
    return os.pathsep.join(safe)


def _trusted_bif_executable(path: str) -> Path | None:
    executable = shutil.which("bif", path=path)
    if executable is None:
        return None
    try:
        resolved = Path(executable).resolve(strict=True)
    except OSError:
        return None
    return resolved if resolved.is_file() else None


_REMOTE_READ_SCRIPT = """
import base64, json, os, pathlib, stat, sys
try:
    path = pathlib.Path(sys.argv[1])
    limit = int(sys.argv[2])
    allow_truncated = sys.argv[3] == "1"
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("expected a regular file")
        if metadata.st_size > limit and not allow_truncated:
            raise ValueError("file exceeds the configured read limit")
        chunks = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
    finally:
        os.close(descriptor)
    exceeded_limit = len(data) > limit
    if exceeded_limit:
        if not allow_truncated:
            raise ValueError("file exceeds the configured read limit")
        data = data[:limit]
    print(json.dumps({
        "data": base64.b64encode(data).decode("ascii"),
        "size": metadata.st_size,
        "truncated": exceeded_limit or metadata.st_size > len(data),
    }))
except Exception as exc:
    print(json.dumps({"error": str(exc)}))
    raise SystemExit(1)
""".strip()

_REMOTE_EDIT_SCRIPT = """
import base64, json, os, pathlib, stat, sys
try:
    path = pathlib.Path(sys.argv[1])
    old = base64.b64decode(sys.argv[2]).decode("utf-8")
    new = base64.b64decode(sys.argv[3]).decode("utf-8")
    replace_all = sys.argv[4] == "1"
    limit = int(sys.argv[5])
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("expected a regular file")
        if metadata.st_size > limit:
            raise ValueError("existing file exceeds the 8 MiB edit/write limit; use bash or an appropriate command-line program")
        chunks = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
    finally:
        os.close(descriptor)
    if len(data) > limit:
        raise ValueError("existing file exceeds the 8 MiB edit/write limit; use bash or an appropriate command-line program")
    before = data.decode("utf-8")
    count = before.count(old)
    if count == 0:
        raise ValueError("old_text was not found in the file")
    if count != 1 and not replace_all:
        raise ValueError("old_text must match exactly once unless replace_all is true")
    after = before.replace(old, new, -1 if replace_all else 1)
    path.write_text(after, encoding="utf-8")
    encode = lambda value: base64.b64encode(value.encode("utf-8")).decode("ascii")
    print(json.dumps({"before": encode(before), "after": encode(after), "replacements": count if replace_all else 1}))
except Exception as exc:
    print(json.dumps({"error": str(exc)}))
    raise SystemExit(1)
""".strip()

_REMOTE_WRITE_SCRIPT = """
import base64, json, os, pathlib, stat, sys
try:
    path = pathlib.Path(sys.argv[1])
    content = base64.b64decode(sys.argv[2]).decode("utf-8")
    limit = int(sys.argv[3])
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        before = ""
    else:
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("expected a regular file")
            if metadata.st_size > limit:
                raise ValueError("existing file exceeds the 8 MiB edit/write limit; use bash or an appropriate command-line program")
            chunks = []
            remaining = limit + 1
            while remaining > 0:
                chunk = os.read(descriptor, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
        finally:
            os.close(descriptor)
        if len(data) > limit:
            raise ValueError("existing file exceeds the 8 MiB edit/write limit; use bash or an appropriate command-line program")
        before = data.decode("utf-8")
    changed = before != content
    if changed:
        path.write_text(content, encoding="utf-8")
    encoded = base64.b64encode(before.encode("utf-8")).decode("ascii")
    print(json.dumps({"before": encoded, "changed": changed}))
except Exception as exc:
    print(json.dumps({"error": str(exc)}))
    raise SystemExit(1)
""".strip()

_CWD_BINDING_ERROR = "Bash working directory changed after approval"
_CWD_BINDING_MARKER = "__BIOINFOFLOW_CWD_BINDING_MISMATCH__"
_REMOTE_APPROVED_CWD_FD = 9

_LOCAL_CWD_GUARD_SCRIPT = """
import os, sys
marker = "__BIOINFOFLOW_CWD_BINDING_MISMATCH__"
try:
    descriptor = int(sys.argv[1])
    expected_device = int(sys.argv[2])
    expected_inode = int(sys.argv[3])
    argv = sys.argv[4:]
    identity = os.fstat(descriptor)
    if (identity.st_dev, identity.st_ino) != (expected_device, expected_inode):
        raise PermissionError(marker)
    os.fchdir(descriptor)
except Exception:
    print(marker, file=sys.stderr)
    raise SystemExit(126)
os.set_inheritable(descriptor, True)
os.execvpe(argv[0], argv, os.environ)
""".strip()

_REMOTE_CWD_IDENTITY_SCRIPT = """
import json, os, sys
operation = "cwd_identity"
try:
    selected = os.path.realpath(sys.argv[1])
    roots = [os.path.realpath(root) for root in sys.argv[2:]]
    if not any(os.path.commonpath((selected, root)) == root for root in roots):
        raise PermissionError("working directory is outside remote workspace roots")
    descriptor = os.open(selected, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        identity = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    print(json.dumps({
        "path": selected,
        "device": identity.st_dev,
        "inode": identity.st_ino,
    }))
except Exception as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(1)
""".strip()

_REMOTE_CWD_GUARD_SCRIPT = """
import os, sys
operation = "cwd_guard"
marker = "__BIOINFOFLOW_CWD_BINDING_MISMATCH__"
try:
    path = sys.argv[1]
    expected_device = int(sys.argv[2])
    expected_inode = int(sys.argv[3])
    inherited_descriptor = int(sys.argv[4])
    shell = sys.argv[5]
    command = sys.argv[6]
    if os.path.realpath(path) != path:
        raise PermissionError(marker)
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    identity = os.fstat(descriptor)
    if (identity.st_dev, identity.st_ino) != (expected_device, expected_inode):
        raise PermissionError(marker)
    os.fchdir(descriptor)
    if descriptor != inherited_descriptor:
        os.dup2(descriptor, inherited_descriptor, inheritable=True)
        os.close(descriptor)
    else:
        os.set_inheritable(descriptor, True)
    os.execl(shell, shell, "--noprofile", "--norc", "-c", command)
except Exception:
    print(marker, file=sys.stderr)
    raise SystemExit(126)
""".strip()

_REMOTE_BIF_DISCOVERY_SCRIPT = """
import json, os, shutil
path = shutil.which("bif")
resolved = os.path.realpath(path) if path else None
print(json.dumps({
    "path": resolved,
    "writable": bool(resolved and os.access(resolved, os.W_OK)),
}))
""".strip()

_REMOTE_SANDBOX_DISCOVERY_SCRIPT = """
import json, os, shutil, subprocess, sys
path = shutil.which("bwrap")
resolved = os.path.realpath(path) if path else None
shell_path = shutil.which("bash")
shell = os.path.realpath(shell_path) if shell_path else None
python = os.path.realpath(sys.executable)
system_roots = [
    item for item in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/opt")
    if os.path.exists(item)
]
network_roots = [
    item for item in (
        "/etc/resolv.conf",
        "/etc/hosts",
        "/etc/nsswitch.conf",
        "/etc/gai.conf",
        "/etc/ssl/certs",
        "/etc/pki/tls/certs",
        "/etc/ca-certificates",
    )
    if os.path.exists(item)
]
available = False
failure = None
if resolved and shell:
    try:
        probe = subprocess.run(
            [
                resolved,
                "--unshare-user", "--uid", "0", "--gid", "0",
                "--ro-bind", "/", "/", "--", "/bin/true",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2,
        )
        available = probe.returncode == 0
        failure = None if available else (probe.stderr.strip() or "probe failed")
    except Exception as exc:
        failure = str(exc)
else:
    failure = "bwrap executable not found"
print(json.dumps({
    "path": resolved,
    "writable": bool(resolved and os.access(resolved, os.W_OK)),
    "available": available,
    "failure": failure,
    "system_roots": system_roots,
    "network_roots": network_roots,
    "shell": shell,
    "python": python,
    "python_writable": bool(python and os.access(python, os.W_OK)),
}))
""".strip()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
