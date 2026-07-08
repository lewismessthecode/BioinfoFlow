from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
import posixpath
import pty
import re
import shlex
import signal
import struct
import subprocess
import termios
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Awaitable, Callable, Protocol

from app.path_layout import safe_join
from app.services.remote_execution import (
    AsyncSshRemoteExecutor,
    RemoteConnectionConfig,
    SshRemoteExecutor,
)


class TerminalNotInteractiveError(RuntimeError):
    """Raised when a terminal session exists but has no interactive PTY."""


class TerminalTransport(Protocol):
    async def read(self, max_bytes: int) -> bytes: ...

    async def write(self, data: bytes) -> None: ...

    async def resize(self, *, cols: int, rows: int) -> None: ...

    async def wait(self) -> int: ...

    async def terminate(self) -> None: ...


RemoteTerminalFactory = Callable[..., Awaitable[TerminalTransport]]


@dataclass(slots=True)
class _LocalPtyTerminalTransport:
    master_fd: int
    process: subprocess.Popen[bytes]
    closed: bool = False

    async def read(self, max_bytes: int) -> bytes:
        return await asyncio.to_thread(os.read, self.master_fd, max_bytes)

    async def write(self, data: bytes) -> None:
        await asyncio.to_thread(os.write, self.master_fd, data)

    async def resize(self, *, cols: int, rows: int) -> None:
        packed = struct.pack("HHHH", rows, cols, 0, 0)
        await asyncio.to_thread(_set_window_size, self.master_fd, packed)

    async def wait(self) -> int:
        return int(await asyncio.to_thread(self.process.wait))

    async def terminate(self) -> None:
        if self.closed:
            return
        self.closed = True
        with contextlib.suppress(ProcessLookupError):
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
        with contextlib.suppress(subprocess.TimeoutExpired):
            await asyncio.to_thread(self.process.wait, 1)
        if self.process.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
        with contextlib.suppress(OSError):
            os.close(self.master_fd)


@dataclass(slots=True)
class _AsyncSshTerminalTransport:
    client: Any
    process: Any
    client_cm: Any
    closed: bool = False

    async def read(self, max_bytes: int) -> bytes:
        chunk = await self.process.stdout.read(max_bytes)
        if isinstance(chunk, str):
            return chunk.encode("utf-8")
        return chunk or b""

    async def write(self, data: bytes) -> None:
        self.process.stdin.write(data)
        drain = getattr(self.process.stdin, "drain", None)
        if drain is not None:
            result = drain()
            if inspect.isawaitable(result):
                await result

    async def resize(self, *, cols: int, rows: int) -> None:
        self.process.change_terminal_size(cols, rows)

    async def wait(self) -> int:
        await self.process.wait()
        return _asyncssh_exit_code(self.process)

    async def terminate(self) -> None:
        if self.closed:
            return
        self.closed = True
        with contextlib.suppress(Exception):
            self.process.kill()
        close = getattr(self.client, "close", None)
        if close is not None:
            close()
        wait_closed = getattr(self.client, "wait_closed", None)
        if wait_closed is not None:
            with contextlib.suppress(Exception):
                await wait_closed()
        with contextlib.suppress(Exception):
            await self.client_cm.__aexit__(None, None, None)


class DefaultRemoteTerminalFactory:
    def __init__(
        self,
        *,
        ssh_executor: SshRemoteExecutor | None = None,
        async_executor: AsyncSshRemoteExecutor | None = None,
        connect_timeout_seconds: int = 10,
    ) -> None:
        self.ssh_executor = ssh_executor or SshRemoteExecutor()
        self.async_executor = async_executor or AsyncSshRemoteExecutor()
        self.connect_timeout_seconds = connect_timeout_seconds

    async def __call__(
        self,
        *,
        connection: RemoteConnectionConfig,
        remote_root_path: str,
        cols: int,
        rows: int,
        env: dict[str, str],
    ) -> TerminalTransport:
        command = _remote_shell_command(remote_root_path)
        if connection.password or connection.private_key:
            client_cm = self.async_executor._connect(
                connection,
                self.connect_timeout_seconds,
            )
            client = await client_cm.__aenter__()
            try:
                process = await client.create_process(
                    command,
                    request_pty=True,
                    term_type="xterm-256color",
                    term_size=(cols, rows),
                    encoding=None,
                )
            except Exception:
                with contextlib.suppress(Exception):
                    await client_cm.__aexit__(None, None, None)
                raise
            return _AsyncSshTerminalTransport(
                client=client,
                process=process,
                client_cm=client_cm,
            )

        argv = self.ssh_executor.build_interactive_argv(
            connection,
            command,
            connect_timeout_seconds=self.connect_timeout_seconds,
        )
        return await asyncio.to_thread(
            _spawn_pty_process,
            command=argv,
            env=env,
            cwd=None,
            cols=cols,
            rows=rows,
        )


@dataclass(slots=True)
class TerminalSessionSnapshot:
    id: str
    project_id: str
    shell: str
    cwd: str
    status: str
    target_type: str = "local"
    target_label: str = "local"
    remote_connection_id: str | None = None


@dataclass(slots=True)
class _TerminalSession:
    id: str
    project_id: str
    shell: str
    root_path: Path | None
    remote_root_path: str | None
    cwd: str
    transport: TerminalTransport | None
    target_type: str = "local"
    target_label: str = "local"
    remote_connection_id: str | None = None
    status: str = "running"
    exit_code: int | None = None
    subscribers: set[asyncio.Queue[dict]] = field(default_factory=set)
    output_backlog: list[str] = field(default_factory=list)
    reader_task: asyncio.Task | None = None
    last_touched: float = 0.0


class TerminalSessionManager:
    _MAX_OUTPUT_BACKLOG_CHUNKS = 64

    def __init__(
        self,
        *,
        shell: str | None = None,
        idle_timeout_seconds: int = 1800,
        cleanup_interval_seconds: int = 60,
        remote_terminal_factory: RemoteTerminalFactory | None = None,
        transport_shutdown_timeout_seconds: float = 2.0,
    ) -> None:
        self._default_shell = shell or os.environ.get("SHELL") or "/bin/bash"
        self._idle_timeout_seconds = idle_timeout_seconds
        self._cleanup_interval_seconds = cleanup_interval_seconds
        self._transport_shutdown_timeout_seconds = transport_shutdown_timeout_seconds
        self._remote_terminal_factory = (
            remote_terminal_factory or DefaultRemoteTerminalFactory()
        )
        self._sessions_by_id: dict[str, _TerminalSession] = {}
        self._project_index: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None

    async def get_by_project(self, project_id: str) -> TerminalSessionSnapshot | None:
        async with self._lock:
            session_id = self._project_index.get(project_id)
            if not session_id:
                return None
            session = self._sessions_by_id.get(session_id)
            if not session:
                self._project_index.pop(project_id, None)
                return None
            if not self._is_live_session(session):
                self._evict_session_locked(session)
                return None
            return self._snapshot(session)

    async def get_by_id(self, session_id: str) -> TerminalSessionSnapshot | None:
        async with self._lock:
            session = self._sessions_by_id.get(session_id)
            if not session:
                return None
            if not self._is_live_session(session):
                self._evict_session_locked(session)
                return None
            return self._snapshot(session)

    async def create_or_get(
        self,
        *,
        project_id: str,
        root_path: Path,
        shell: str | None = None,
    ) -> TerminalSessionSnapshot:
        async with self._lock:
            existing_id = self._project_index.get(project_id)
            existing = self._sessions_by_id.get(existing_id) if existing_id else None
            if existing and existing.status == "running":
                existing.last_touched = asyncio.get_running_loop().time()
                return self._snapshot(existing)
            if existing:
                self._evict_session_locked(existing)

            root = root_path.expanduser().resolve()
            root.mkdir(parents=True, exist_ok=True)
            session = await asyncio.to_thread(
                self._spawn_session,
                project_id=project_id,
                root_path=root,
                shell=shell or self._default_shell,
            )
            session.last_touched = asyncio.get_running_loop().time()
            session.reader_task = asyncio.create_task(self._read_output(session))
            self._sessions_by_id[session.id] = session
            self._project_index[project_id] = session.id
            self._ensure_cleanup_task()
            return self._snapshot(session)

    async def create_or_get_remote(
        self,
        *,
        project_id: str,
        connection: RemoteConnectionConfig,
        remote_root_path: str,
        target_label: str,
        shell: str | None = None,
        cols: int = 80,
        rows: int = 24,
    ) -> TerminalSessionSnapshot:
        async with self._lock:
            existing_id = self._project_index.get(project_id)
            existing = self._sessions_by_id.get(existing_id) if existing_id else None
            if existing and self._is_live_session(existing):
                existing.last_touched = asyncio.get_running_loop().time()
                return self._snapshot(existing)
            if existing:
                self._evict_session_locked(existing)

        remote_root = _normalize_remote_root(remote_root_path)
        resolved_shell = shell or self._default_shell
        transport: TerminalTransport | None = None
        try:
            transport = await self._remote_terminal_factory(
                connection=connection,
                remote_root_path=remote_root,
                cols=cols,
                rows=rows,
                env=self._build_terminal_environment(shell=resolved_shell),
            )
            session = _TerminalSession(
                id=str(uuid.uuid4()),
                project_id=project_id,
                shell=resolved_shell,
                root_path=None,
                remote_root_path=remote_root,
                cwd=remote_root,
                transport=transport,
                target_type="remote",
                target_label=target_label,
                remote_connection_id=connection.id,
            )
            session.last_touched = asyncio.get_running_loop().time()

            async with self._lock:
                existing_id = self._project_index.get(project_id)
                existing = self._sessions_by_id.get(existing_id) if existing_id else None
                if existing and self._is_live_session(existing):
                    existing.last_touched = asyncio.get_running_loop().time()
                    snapshot = self._snapshot(existing)
                    transport_to_close = transport
                    transport = None
                else:
                    if existing:
                        self._evict_session_locked(existing)
                    session.reader_task = asyncio.create_task(self._read_output(session))
                    self._sessions_by_id[session.id] = session
                    self._project_index[project_id] = session.id
                    self._ensure_cleanup_task()
                    return self._snapshot(session)

            await self._terminate_transport(transport_to_close)
            return snapshot
        except BaseException:
            if transport is not None:
                await self._terminate_transport(transport)
            raise

    async def attach(self, session_id: str) -> asyncio.Queue[dict]:
        async with self._lock:
            session = self._require_session(session_id)
            queue: asyncio.Queue[dict] = asyncio.Queue()
            session.subscribers.add(queue)
            session.last_touched = asyncio.get_running_loop().time()
            queue.put_nowait(
                {"type": "ready", "session": asdict(self._snapshot(session))}
            )
            queue.put_nowait({"type": "cwd", "cwd": session.cwd})
            for chunk in session.output_backlog:
                queue.put_nowait({"type": "output", "data": chunk})
            return queue

    async def detach(self, session_id: str, queue: asyncio.Queue[dict]) -> None:
        async with self._lock:
            session = self._sessions_by_id.get(session_id)
            if not session:
                return
            session.subscribers.discard(queue)
            session.last_touched = asyncio.get_running_loop().time()

    async def send_input(self, session_id: str, data: str) -> None:
        if not data:
            return
        session = await self._interactive_session(session_id)
        if session.transport is None:
            raise TerminalNotInteractiveError(session_id)
        await session.transport.write(data.encode())
        session.last_touched = asyncio.get_running_loop().time()

    async def resize(self, session_id: str, *, cols: int, rows: int) -> None:
        session = await self._interactive_session(session_id)
        if session.transport is None:
            raise TerminalNotInteractiveError(session_id)
        await session.transport.resize(cols=cols, rows=rows)
        session.last_touched = asyncio.get_running_loop().time()

    async def change_directory(self, session_id: str, relative_path: str) -> str:
        session = await self._interactive_session(session_id)
        if session.target_type == "remote":
            candidate = self._resolve_safe_remote_directory(
                session.remote_root_path, relative_path or "."
            )
        else:
            candidate = str(
                self._resolve_safe_directory(
                    session.root_path, relative_path or "."
                )
            )
        session.cwd = str(candidate)
        await self.send_input(session_id, f"cd {shlex.quote(str(candidate))}\n")
        await self._broadcast(session, {"type": "cwd", "cwd": session.cwd})
        return session.cwd

    async def close_session(self, session_id: str) -> bool:
        session: _TerminalSession | None
        async with self._lock:
            session = self._sessions_by_id.pop(session_id, None)
            if not session:
                return False
            self._project_index.pop(session.project_id, None)
            session.status = "closed"
        await self._terminate_session(session)
        return True

    async def shutdown(self) -> None:
        cleanup = self._cleanup_task
        self._cleanup_task = None
        if cleanup:
            cleanup.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cleanup

        async with self._lock:
            sessions = list(self._sessions_by_id.values())
            self._sessions_by_id.clear()
            self._project_index.clear()

        for session in sessions:
            session.status = "closed"
            await self._terminate_session(session)

    def _spawn_session(
        self, *, project_id: str, root_path: Path, shell: str
    ) -> _TerminalSession:
        master_fd, slave_fd = pty.openpty()
        env = self._build_terminal_environment(shell=shell)
        command = self._build_shell_command(shell)
        transport = _spawn_pty_process(
            command=command,
            env=env,
            cwd=str(root_path),
            cols=80,
            rows=24,
            master_fd=master_fd,
            slave_fd=slave_fd,
        )
        return _TerminalSession(
            id=str(uuid.uuid4()),
            project_id=project_id,
            shell=shell,
            root_path=root_path,
            remote_root_path=None,
            cwd=str(root_path),
            transport=transport,
        )

    # Patterns for sensitive environment variable names to exclude
    _SENSITIVE_ENV_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r".*_KEY$", re.IGNORECASE),
        re.compile(r".*_SECRET.*", re.IGNORECASE),
        re.compile(r".*_TOKEN$", re.IGNORECASE),
        re.compile(r".*_PASSWORD.*", re.IGNORECASE),
        re.compile(r".*API.*KEY.*", re.IGNORECASE),
        re.compile(r".*AUTH.*TOKEN.*", re.IGNORECASE),
        re.compile(r".*CREDENTIAL.*", re.IGNORECASE),
    ]

    def _build_terminal_environment(
        self, *, shell: str | None = None
    ) -> dict[str, str]:
        env = {
            k: v
            for k, v in os.environ.items()
            if not any(pat.match(k) for pat in self._SENSITIVE_ENV_PATTERNS)
        }
        shell_name = Path(shell or self._default_shell).name
        managed_shell_dir = self._managed_shell_dir()
        history_dir = self._terminal_runtime_dir()
        history_dir.mkdir(parents=True, exist_ok=True)
        env.update(
            {
                "TERM": "xterm-256color",
                "VIRTUAL_ENV_DISABLE_PROMPT": "1",
                "PYENV_VIRTUALENV_DISABLE_PROMPT": "1",
                "CONDA_CHANGEPS1": "no",
                "HISTFILE": str((history_dir / ".terminal_history").resolve()),
                "STARSHIP_CONFIG": str(
                    Path(__file__).with_name("terminal_starship.toml").resolve()
                ),
            }
        )
        if shell_name == "zsh":
            env["ZDOTDIR"] = str(managed_shell_dir)
        return env

    def _build_shell_command(self, shell: str) -> list[str]:
        shell_name = Path(shell).name
        if shell_name == "bash":
            return [
                shell,
                "--noprofile",
                "--rcfile",
                str((self._managed_shell_dir() / ".bashrc").resolve()),
                "-i",
            ]
        if shell_name == "zsh":
            return [shell, "-i"]
        if shell_name in {"sh", "dash"}:
            return [shell, "-i"]
        return [shell]

    def _managed_shell_dir(self) -> Path:
        return Path(__file__).with_name("terminal_shell").resolve()

    def _terminal_runtime_dir(self) -> Path:
        return Path(os.getenv("TMPDIR", "/tmp")).resolve() / "bioinfoflow-terminal"

    async def _read_output(self, session: _TerminalSession) -> None:
        if session.transport is None:
            return
        try:
            while True:
                chunk = await session.transport.read(4096)
                if not chunk:
                    break
                session.last_touched = asyncio.get_running_loop().time()
                decoded = chunk.decode("utf-8", errors="replace")
                session.output_backlog.append(decoded)
                if len(session.output_backlog) > self._MAX_OUTPUT_BACKLOG_CHUNKS:
                    del session.output_backlog[
                        : len(session.output_backlog) - self._MAX_OUTPUT_BACKLOG_CHUNKS
                    ]
                await self._broadcast(
                    session,
                    {"type": "output", "data": decoded},
                )
        except OSError:
            pass
        finally:
            exit_code = await self._wait_transport(session.transport)
            session.exit_code = exit_code
            await self._terminate_transport(session.transport)
            if session.status != "closed":
                session.status = "exited"
                await self._broadcast(
                    session,
                    {"type": "exit", "exit_code": exit_code},
                )
                async with self._lock:
                    self._evict_session_locked(session)

    async def _running_session(self, session_id: str) -> _TerminalSession:
        async with self._lock:
            session = self._require_session(session_id)
            if session.status != "running":
                raise KeyError(session_id)
            return session

    async def _interactive_session(self, session_id: str) -> _TerminalSession:
        async with self._lock:
            session = self._require_session(session_id)
            if session.status != "running" or session.transport is None:
                raise TerminalNotInteractiveError(session_id)
            return session

    def _require_session(self, session_id: str) -> _TerminalSession:
        session = self._sessions_by_id.get(session_id)
        if not session:
            raise KeyError(session_id)
        return session

    async def _broadcast(self, session: _TerminalSession, message: dict) -> None:
        stale: list[asyncio.Queue[dict]] = []
        for queue in session.subscribers:
            try:
                queue.put_nowait(message)
            except RuntimeError:
                stale.append(queue)
        if stale:
            async with self._lock:
                for queue in stale:
                    session.subscribers.discard(queue)

    async def _terminate_session(self, session: _TerminalSession) -> None:
        if session.transport is None:
            return
        if session.reader_task:
            session.reader_task.cancel()
        await self._terminate_transport(session.transport)
        if session.reader_task:
            with contextlib.suppress(asyncio.CancelledError):
                await self._await_task_with_timeout(session.reader_task)

    async def _wait_transport(self, transport: TerminalTransport) -> int:
        return await self._await_task_with_timeout(transport.wait(), default=-9)

    async def _terminate_transport(self, transport: TerminalTransport) -> None:
        await self._await_task_with_timeout(transport.terminate(), default=None)

    async def _await_task_with_timeout(
        self,
        awaitable: Awaitable[Any] | asyncio.Task[Any],
        *,
        default: Any = None,
    ) -> Any:
        task = (
            awaitable
            if isinstance(awaitable, asyncio.Task)
            else asyncio.create_task(awaitable)
        )
        done, _pending = await asyncio.wait(
            {task},
            timeout=self._transport_shutdown_timeout_seconds,
        )
        if task not in done:
            task.cancel()
            task.add_done_callback(_consume_task_exception)
            return default
        try:
            return await task
        except Exception:
            return default

    def _ensure_cleanup_task(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            return
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._cleanup_interval_seconds)
                now = asyncio.get_running_loop().time()
                stale_ids: list[str] = []
                async with self._lock:
                    for session_id, session in self._sessions_by_id.items():
                        if now - session.last_touched >= self._idle_timeout_seconds:
                            stale_ids.append(session_id)
                for session_id in stale_ids:
                    await self.close_session(session_id)
        except asyncio.CancelledError:
            raise

    def _resolve_safe_directory(self, root: Path, candidate: str) -> Path:
        if root is None:
            raise PermissionError(candidate)
        raw = str(candidate or ".").strip() or "."
        if (
            raw.startswith("~")
            or PurePosixPath(raw).is_absolute()
            or PureWindowsPath(raw).is_absolute()
        ):
            raise PermissionError(raw)
        target = safe_join(
            root,
            raw,
            escape_message="path escapes terminal root",
        )
        if not target.is_dir():
            raise FileNotFoundError(str(target))
        return target

    def _resolve_safe_remote_directory(
        self, remote_root: str | None, candidate: str
    ) -> str:
        if not remote_root:
            raise PermissionError(candidate)
        raw = str(candidate or ".").strip() or "."
        if (
            raw.startswith("~")
            or PurePosixPath(raw).is_absolute()
            or PureWindowsPath(raw).is_absolute()
        ):
            raise PermissionError(raw)
        root = _normalize_remote_root(remote_root)
        target = posixpath.normpath(posixpath.join(root, raw))
        root_prefix = root if root.endswith("/") else f"{root}/"
        if target != root and not target.startswith(root_prefix):
            raise PermissionError(raw)
        return target

    def _snapshot(self, session: _TerminalSession) -> TerminalSessionSnapshot:
        return TerminalSessionSnapshot(
            id=session.id,
            project_id=session.project_id,
            shell=session.shell,
            cwd=session.cwd,
            status=session.status,
            target_type=session.target_type,
            target_label=session.target_label,
            remote_connection_id=session.remote_connection_id,
        )

    def _is_live_session(self, session: _TerminalSession) -> bool:
        return session.status == "running"

    def _evict_session_locked(self, session: _TerminalSession) -> None:
        current_id = self._project_index.get(session.project_id)
        if current_id == session.id:
            self._project_index.pop(session.project_id, None)
        self._sessions_by_id.pop(session.id, None)


def _spawn_pty_process(
    *,
    command: list[str],
    env: dict[str, str],
    cwd: str | None,
    cols: int,
    rows: int,
    master_fd: int | None = None,
    slave_fd: int | None = None,
) -> _LocalPtyTerminalTransport:
    if master_fd is None or slave_fd is None:
        master_fd, slave_fd = pty.openpty()
    with contextlib.suppress(OSError):
        _set_window_size(master_fd, struct.pack("HHHH", rows, cols, 0, 0))
    process = subprocess.Popen(
        command,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        cwd=cwd,
        env=env,
        preexec_fn=os.setsid,
        close_fds=True,
    )
    os.close(slave_fd)
    return _LocalPtyTerminalTransport(master_fd=master_fd, process=process)


def _remote_shell_command(remote_root_path: str) -> str:
    return (
        f"cd {shlex.quote(_normalize_remote_root(remote_root_path))} "
        '&& exec "${SHELL:-/bin/sh}" -i'
    )


def _normalize_remote_root(remote_root_path: str) -> str:
    normalized = posixpath.normpath(str(remote_root_path or "").strip())
    if not normalized or not PurePosixPath(normalized).is_absolute():
        raise PermissionError(remote_root_path)
    return normalized


def _asyncssh_exit_code(process: Any) -> int:
    for attr in ("exit_status", "returncode"):
        value = getattr(process, attr, None)
        if value is not None:
            return int(value)
    return -9


def _set_window_size(master_fd: int, packed: bytes) -> None:
    import fcntl

    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, packed)


def _consume_task_exception(task: asyncio.Task[Any]) -> None:
    with contextlib.suppress(BaseException):
        task.exception()


terminal_manager = TerminalSessionManager()
