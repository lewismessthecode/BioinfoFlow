from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import asyncssh

from app.config import settings
from app.utils.exceptions import BadRequestError


ProcessFactory = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class RemoteConnectionConfig:
    id: str
    name: str
    host: str
    username: str | None = None
    port: int | None = None
    ssh_alias: str | None = None
    key_path: str | None = None
    password: str | None = None
    private_key: str | None = None
    passphrase: str | None = None
    ssh_config_path: str | None = None
    status: str = "unknown"
    skill_summary: str | None = None
    extra_ssh_options: dict[str, str] = field(default_factory=dict)

    def summary(self) -> dict[str, str | None]:
        return {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "username": self.username,
            "status": self.status,
            "skill_summary": self.skill_summary,
        }

    @property
    def display_target(self) -> str:
        return _format_target(self.host, self.username)

    @property
    def ssh_target(self) -> str:
        if self.ssh_alias:
            return self.ssh_alias
        return _format_target(self.ssh_alias or self.host, self.username)


@dataclass(frozen=True)
class RemoteCommandResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool
    stdout_truncated: bool
    stderr_truncated: bool

    def observation(self) -> dict[str, int | str | bool]:
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "truncated": self.truncated,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
        }


@dataclass(frozen=True)
class RemoteOutputFrame:
    type: str
    data: str | None = None
    exit_code: int | None = None
    timed_out: bool = False


class RemoteExecutor(Protocol):
    async def run(
        self,
        connection: RemoteConnectionConfig,
        command: str,
        *,
        timeout_seconds: int,
        output_limit: int,
    ) -> RemoteCommandResult:
        """Run a bounded command on a remote connection."""

    def stream(
        self,
        connection: RemoteConnectionConfig,
        command: str,
        *,
        timeout_seconds: int,
        output_limit: int,
    ) -> AsyncIterator[RemoteOutputFrame]:
        """Stream stdout/stderr frames from a remote command."""


class SshRemoteExecutor:
    def __init__(
        self,
        *,
        ssh_bin: str = "ssh",
        process_factory: ProcessFactory | None = None,
        async_executor: AsyncSshRemoteExecutor | None = None,
    ) -> None:
        self.ssh_bin = ssh_bin
        self.process_factory = process_factory or asyncio.create_subprocess_exec
        self.async_executor = async_executor or AsyncSshRemoteExecutor()

    def build_argv(
        self,
        connection: RemoteConnectionConfig,
        command: str,
        *,
        connect_timeout_seconds: int,
    ) -> list[str]:
        if not command.strip():
            raise BadRequestError("remote command must be a non-empty string")
        target = connection.ssh_target
        if not target.strip():
            raise BadRequestError("remote connection target must be configured")

        argv = [self.ssh_bin]
        if connection.ssh_config_path:
            argv.extend(["-F", connection.ssh_config_path])
        if connection.key_path:
            argv.extend(["-i", connection.key_path])
        if connection.port is not None and not connection.ssh_alias:
            argv.extend(["-p", str(connection.port)])
        argv.extend(["-o", "BatchMode=yes"])
        argv.extend(["-o", f"ConnectTimeout={connect_timeout_seconds}"])
        for key, value in sorted(connection.extra_ssh_options.items()):
            argv.extend(["-o", f"{key}={value}"])
        argv.extend(["--", target, command])
        return argv

    async def run(
        self,
        connection: RemoteConnectionConfig,
        command: str,
        *,
        timeout_seconds: int,
        output_limit: int,
    ) -> RemoteCommandResult:
        if timeout_seconds < 1:
            raise BadRequestError("timeout_seconds must be >= 1")
        if output_limit < 1:
            raise BadRequestError("output_limit must be >= 1")
        if _uses_stored_credential(connection):
            return await self.async_executor.run(
                connection,
                command,
                timeout_seconds=timeout_seconds,
                output_limit=output_limit,
            )

        argv = self.build_argv(
            connection,
            command,
            connect_timeout_seconds=timeout_seconds,
        )
        process = await self.process_factory(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_task = asyncio.create_task(_read_limited(process.stdout, output_limit))
        stderr_task = asyncio.create_task(_read_limited(process.stderr, output_limit))

        timed_out = False
        completed = False
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
            completed = True
        except asyncio.TimeoutError:
            timed_out = True
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
        finally:
            if not completed and not timed_out and process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                await process.wait()

        stdout, stdout_truncated = await stdout_task
        stderr, stderr_truncated = await stderr_task
        exit_code = process.returncode if process.returncode is not None else -1
        return RemoteCommandResult(
            exit_code=int(exit_code),
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            truncated=stdout_truncated or stderr_truncated,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )

    async def stream(
        self,
        connection: RemoteConnectionConfig,
        command: str,
        *,
        timeout_seconds: int,
        output_limit: int,
    ) -> AsyncIterator[RemoteOutputFrame]:
        if timeout_seconds < 1:
            raise BadRequestError("timeout_seconds must be >= 1")
        if output_limit < 1:
            raise BadRequestError("output_limit must be >= 1")
        if _uses_stored_credential(connection):
            async for frame in self.async_executor.stream(
                connection,
                command,
                timeout_seconds=timeout_seconds,
                output_limit=output_limit,
            ):
                yield frame
            return

        argv = self.build_argv(
            connection,
            command,
            connect_timeout_seconds=timeout_seconds,
        )
        process = await self.process_factory(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        queue: asyncio.Queue[RemoteOutputFrame] = asyncio.Queue(maxsize=32)
        output_budget = _StreamOutputBudget(output_limit)
        stdout_task = asyncio.create_task(
            _pump_stream(process.stdout, "stdout", queue, output_budget)
        )
        stderr_task = asyncio.create_task(
            _pump_stream(process.stderr, "stderr", queue, output_budget)
        )
        wait_task = asyncio.create_task(process.wait())
        timed_out = False
        completed = False
        deadline = asyncio.get_running_loop().time() + timeout_seconds

        try:
            while True:
                if not wait_task.done() and asyncio.get_running_loop().time() >= deadline:
                    timed_out = True
                    with contextlib.suppress(ProcessLookupError):
                        process.kill()
                    await wait_task
                if (
                    wait_task.done()
                    and stdout_task.done()
                    and stderr_task.done()
                    and queue.empty()
                ):
                    completed = True
                    break
                try:
                    frame = await asyncio.wait_for(queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                if frame.type == "truncated" and process.returncode is None:
                    with contextlib.suppress(ProcessLookupError):
                        process.kill()
                    await wait_task
                yield frame
        finally:
            if not completed and process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                with contextlib.suppress(asyncio.CancelledError):
                    await wait_task
            for task in (stdout_task, stderr_task):
                if not task.done():
                    task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            if not wait_task.done():
                wait_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await wait_task

        yield RemoteOutputFrame(
            type="exit",
            exit_code=int(process.returncode if process.returncode is not None else -1),
            timed_out=timed_out,
        )


class AsyncSshRemoteExecutor:
    def __init__(
        self,
        *,
        connect_factory: Callable[..., Any] | None = None,
        known_hosts_path: Path | None = None,
    ) -> None:
        self.connect_factory = connect_factory or asyncssh.connect
        self.known_hosts_path = known_hosts_path or _default_known_hosts_path()

    async def run(
        self,
        connection: RemoteConnectionConfig,
        command: str,
        *,
        timeout_seconds: int,
        output_limit: int,
    ) -> RemoteCommandResult:
        if not command.strip():
            raise BadRequestError("remote command must be a non-empty string")
        if timeout_seconds < 1:
            raise BadRequestError("timeout_seconds must be >= 1")
        if output_limit < 1:
            raise BadRequestError("output_limit must be >= 1")

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        exit_code = -9
        timed_out = False
        truncated = False
        async for frame in self.stream(
            connection,
            command,
            timeout_seconds=timeout_seconds,
            output_limit=output_limit,
        ):
            if frame.type == "stdout" and frame.data:
                stdout_parts.append(frame.data)
            elif frame.type == "stderr" and frame.data:
                stderr_parts.append(frame.data)
            elif frame.type == "truncated":
                truncated = True
            elif frame.type == "exit":
                exit_code = int(frame.exit_code if frame.exit_code is not None else -9)
                timed_out = frame.timed_out

        stdout = "".join(stdout_parts)
        stderr = "".join(stderr_parts)
        return RemoteCommandResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            truncated=truncated,
            stdout_truncated=truncated,
            stderr_truncated=truncated,
        )

    async def stream(
        self,
        connection: RemoteConnectionConfig,
        command: str,
        *,
        timeout_seconds: int,
        output_limit: int,
    ) -> AsyncIterator[RemoteOutputFrame]:
        if not command.strip():
            raise BadRequestError("remote command must be a non-empty string")
        if timeout_seconds < 1:
            raise BadRequestError("timeout_seconds must be >= 1")
        if output_limit < 1:
            raise BadRequestError("output_limit must be >= 1")

        queue: asyncio.Queue[RemoteOutputFrame] = asyncio.Queue()
        output_budget = _StreamOutputBudget(output_limit)
        process = None
        wait_task: asyncio.Task[Any] | None = None
        stdout_task: asyncio.Task[Any] | None = None
        stderr_task: asyncio.Task[Any] | None = None
        timed_out = False
        completed = False
        deadline = asyncio.get_running_loop().time() + timeout_seconds

        async with self._connect(connection, timeout_seconds) as client:
            process = await client.create_process(command, encoding=None)
            stdout_task = asyncio.create_task(
                _pump_stream(process.stdout, "stdout", queue, output_budget)
            )
            stderr_task = asyncio.create_task(
                _pump_stream(process.stderr, "stderr", queue, output_budget)
            )
            wait_task = asyncio.create_task(process.wait())

            try:
                while True:
                    if (
                        not wait_task.done()
                        and asyncio.get_running_loop().time() >= deadline
                    ):
                        timed_out = True
                        _terminate_asyncssh_process(process)
                        await wait_task
                    if (
                        wait_task.done()
                        and stdout_task.done()
                        and stderr_task.done()
                        and queue.empty()
                    ):
                        completed = True
                        break
                    try:
                        frame = await asyncio.wait_for(queue.get(), timeout=0.1)
                    except asyncio.TimeoutError:
                        continue
                    if frame.type == "truncated" and not wait_task.done():
                        _terminate_asyncssh_process(process)
                        await wait_task
                    yield frame
            finally:
                if not completed and wait_task is not None and not wait_task.done():
                    _terminate_asyncssh_process(process)
                    with contextlib.suppress(asyncio.CancelledError):
                        await wait_task
                for task in (stdout_task, stderr_task):
                    if task is None:
                        continue
                    if not task.done():
                        task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

        exit_code = _asyncssh_exit_code(process)
        yield RemoteOutputFrame(
            type="exit",
            exit_code=exit_code,
            timed_out=timed_out,
        )

    def _connect(
        self,
        connection: RemoteConnectionConfig,
        timeout_seconds: int,
    ):
        client_keys = None
        if connection.private_key:
            client_keys = [
                asyncssh.import_private_key(
                    connection.private_key,
                    passphrase=connection.passphrase,
                )
            ]
        client_factory = lambda: _TofuHostKeyClient(  # noqa: E731
            host=connection.host,
            port=connection.port or 22,
            known_hosts_path=self.known_hosts_path,
        )
        return self.connect_factory(
            connection.host,
            port=connection.port or 22,
            username=connection.username,
            password=connection.password,
            client_keys=client_keys,
            client_factory=client_factory,
            known_hosts=asyncssh.import_known_hosts(""),
            server_host_key_algs="default",
            login_timeout=timeout_seconds,
        )


class _TofuHostKeyClient(asyncssh.SSHClient):
    """Trust the first seen host key, then require it to remain stable."""

    def __init__(self, *, host: str, port: int, known_hosts_path: Path) -> None:
        self.host = host
        self.port = port
        self.known_hosts_path = known_hosts_path

    def validate_host_public_key(
        self,
        host: str,
        addr: str,
        port: int,
        key: asyncssh.SSHKey,
    ) -> bool:
        del addr
        record_key = f"{host or self.host}:{port or self.port}"
        public_key = key.export_public_key("openssh").decode("utf-8").strip()
        records = _load_tofu_known_hosts(self.known_hosts_path)
        existing = records.get(record_key)
        if existing is None:
            records[record_key] = public_key
            _save_tofu_known_hosts(self.known_hosts_path, records)
            return True
        return existing == public_key


def _default_known_hosts_path() -> Path:
    configured = os.getenv("BIOINFOFLOW_SSH_KNOWN_HOSTS")
    if configured:
        return Path(configured).expanduser()
    return Path(settings.bioinfoflow_home) / "state" / "ssh_known_hosts.json"


def _load_tofu_known_hosts(path: Path) -> dict[str, str]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(host): str(public_key)
        for host, public_key in data.items()
        if isinstance(host, str) and isinstance(public_key, str)
    }


def _save_tofu_known_hosts(path: Path, records: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(records, handle, sort_keys=True)
        handle.write("\n")
    temp_path.replace(path)


def _terminate_asyncssh_process(process: Any) -> None:
    with contextlib.suppress(Exception):
        process.kill()


def _asyncssh_exit_code(process: Any) -> int:
    for attr in ("exit_status", "returncode"):
        value = getattr(process, attr, None)
        if value is not None:
            return int(value)
    return -9


async def _read_limited(stream: Any, output_limit: int) -> tuple[str, bool]:
    if stream is None:
        return "", False
    chunks: list[bytes] = []
    remaining = output_limit
    truncated = False
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            break
        if remaining > 0:
            kept = chunk[:remaining]
            chunks.append(kept)
            remaining -= len(kept)
            if len(kept) < len(chunk):
                truncated = True
        else:
            truncated = True
    return b"".join(chunks).decode("utf-8", errors="replace"), truncated


async def _pump_stream(
    stream: Any,
    stream_type: str,
    queue: asyncio.Queue[RemoteOutputFrame],
    output_budget: _StreamOutputBudget,
) -> None:
    if stream is None:
        return
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            return
        kept, truncated = await output_budget.take(chunk)
        if kept:
            await queue.put(
                RemoteOutputFrame(
                    type=stream_type,
                    data=kept.decode("utf-8", errors="replace"),
                )
            )
        if truncated:
            await queue.put(
                RemoteOutputFrame(
                    type="truncated",
                    data=f"remote output truncated after {output_budget.limit} bytes",
                )
            )
            return


class _StreamOutputBudget:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.remaining = limit
        self.truncated = False
        self.lock = asyncio.Lock()

    async def take(self, chunk: bytes) -> tuple[bytes, bool]:
        async with self.lock:
            if self.truncated:
                return b"", False
            if len(chunk) <= self.remaining:
                self.remaining -= len(chunk)
                return chunk, False
            kept = chunk[: self.remaining]
            self.remaining = 0
            self.truncated = True
            return kept, True


def _limit_text(value: str, output_limit: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= output_limit:
        return value, False
    return encoded[:output_limit].decode("utf-8", errors="replace"), True


def _uses_stored_credential(connection: RemoteConnectionConfig) -> bool:
    return bool(connection.password or connection.private_key)


def _format_target(host: str, username: str | None) -> str:
    return f"{username}@{host}" if username else host
