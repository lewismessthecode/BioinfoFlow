from __future__ import annotations

import asyncio
import contextlib
import os
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

from app.path_layout import safe_join


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
    cwd: str
    master_fd: int | None
    process: subprocess.Popen[bytes] | None
    target_type: str = "local"
    target_label: str = "local"
    remote_connection_id: str | None = None
    status: str = "running"
    unsupported_message: str | None = None
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
    ) -> None:
        self._default_shell = shell or os.environ.get("SHELL") or "/bin/bash"
        self._idle_timeout_seconds = idle_timeout_seconds
        self._cleanup_interval_seconds = cleanup_interval_seconds
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

    async def create_or_get_unsupported_remote(
        self,
        *,
        project_id: str,
        remote_root_path: str,
        remote_connection_id: str,
        target_label: str,
        shell: str | None = None,
        message: str = "Remote interactive terminals are not supported yet.",
    ) -> TerminalSessionSnapshot:
        async with self._lock:
            existing_id = self._project_index.get(project_id)
            existing = self._sessions_by_id.get(existing_id) if existing_id else None
            if existing and self._is_live_session(existing):
                existing.last_touched = asyncio.get_running_loop().time()
                return self._snapshot(existing)
            if existing:
                self._evict_session_locked(existing)

            session = _TerminalSession(
                id=str(uuid.uuid4()),
                project_id=project_id,
                shell=shell or self._default_shell,
                root_path=None,
                cwd=remote_root_path,
                master_fd=None,
                process=None,
                target_type="remote",
                target_label=target_label,
                remote_connection_id=remote_connection_id,
                status="unsupported",
                unsupported_message=message,
            )
            session.last_touched = asyncio.get_running_loop().time()
            self._sessions_by_id[session.id] = session
            self._project_index[project_id] = session.id
            self._ensure_cleanup_task()
            return self._snapshot(session)

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
            if session.unsupported_message:
                queue.put_nowait({"type": "error", "message": session.unsupported_message})
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
        session = await self._running_session(session_id)
        if not data:
            return
        if session.master_fd is None:
            raise KeyError(session_id)
        await asyncio.to_thread(os.write, session.master_fd, data.encode())
        session.last_touched = asyncio.get_running_loop().time()

    async def resize(self, session_id: str, *, cols: int, rows: int) -> None:
        session = await self._running_session(session_id)
        if session.master_fd is None:
            raise KeyError(session_id)
        packed = struct.pack("HHHH", rows, cols, 0, 0)
        await asyncio.to_thread(self._set_window_size, session.master_fd, packed)
        session.last_touched = asyncio.get_running_loop().time()

    async def change_directory(self, session_id: str, relative_path: str) -> str:
        session = await self._running_session(session_id)
        if session.root_path is None:
            raise KeyError(session_id)
        candidate = self._resolve_safe_directory(
            session.root_path, relative_path or "."
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
        process = subprocess.Popen(
            command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=str(root_path),
            env=env,
            preexec_fn=os.setsid,
            close_fds=True,
        )
        os.close(slave_fd)
        return _TerminalSession(
            id=str(uuid.uuid4()),
            project_id=project_id,
            shell=shell,
            root_path=root_path,
            cwd=str(root_path),
            master_fd=master_fd,
            process=process,
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
        if session.master_fd is None or session.process is None:
            return
        try:
            while True:
                chunk = await asyncio.to_thread(os.read, session.master_fd, 4096)
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
            exit_code = await asyncio.to_thread(session.process.wait)
            session.exit_code = exit_code
            if session.status != "closed":
                session.status = "exited"
                await self._broadcast(
                    session,
                    {"type": "exit", "exit_code": exit_code},
                )
                async with self._lock:
                    self._evict_session_locked(session)
                with contextlib.suppress(OSError):
                    if session.master_fd is not None:
                        os.close(session.master_fd)

    async def _running_session(self, session_id: str) -> _TerminalSession:
        async with self._lock:
            session = self._require_session(session_id)
            if session.status != "running":
                raise KeyError(session_id)
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
        if session.process is None:
            return
        with contextlib.suppress(ProcessLookupError):
            os.killpg(os.getpgid(session.process.pid), signal.SIGTERM)
        with contextlib.suppress(subprocess.TimeoutExpired):
            await asyncio.to_thread(session.process.wait, 1)
        if session.process.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(session.process.pid), signal.SIGKILL)
        with contextlib.suppress(OSError):
            if session.master_fd is not None:
                os.close(session.master_fd)
        if session.reader_task:
            session.reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await session.reader_task

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
        return session.status in {"running", "unsupported"}

    def _evict_session_locked(self, session: _TerminalSession) -> None:
        current_id = self._project_index.get(session.project_id)
        if current_id == session.id:
            self._project_index.pop(session.project_id, None)
        self._sessions_by_id.pop(session.id, None)

    @staticmethod
    def _set_window_size(master_fd: int, packed: bytes) -> None:
        import fcntl

        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, packed)


terminal_manager = TerminalSessionManager()
