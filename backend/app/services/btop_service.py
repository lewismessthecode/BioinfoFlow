from __future__ import annotations

import asyncio
import contextlib
import os
import pty
import shutil
import signal
import struct
import subprocess
import termios
from dataclasses import dataclass, field


DEFAULT_BTOP_ARGV: tuple[str, ...] = ("btop", "-p", "1")
COMMON_BTOP_PATHS: tuple[str, ...] = (
    "/opt/homebrew/bin/btop",
    "/usr/local/bin/btop",
    "/usr/bin/btop",
    "/bin/btop",
)


class BtopUnavailableError(RuntimeError):
    """Raised when the btop binary is not on PATH."""

    def __init__(self, binary: str, attempted_paths: list[str]) -> None:
        self.binary = binary
        self.attempted_paths = attempted_paths
        super().__init__(
            f"{binary} not found. Attempted: {', '.join(attempted_paths)}"
        )


@dataclass
class BtopSession:
    master_fd: int
    process: subprocess.Popen[bytes]
    queue: asyncio.Queue[dict] = field(default_factory=asyncio.Queue)
    reader_task: asyncio.Task | None = None
    status: str = "running"
    exit_code: int | None = None


async def spawn_btop_session(
    *,
    argv: tuple[str, ...] | list[str] | None = None,
    env: dict[str, str] | None = None,
    cols: int = 120,
    rows: int = 32,
) -> BtopSession:
    """Spawn ``btop -p 1`` (or the given argv) attached to a fresh pty.

    Per-connection session: no registry, no backlog. Caller owns the
    lifecycle and must call :func:`terminate_session` when done.
    """
    command = tuple(argv) if argv else DEFAULT_BTOP_ARGV
    resolved_command, _attempted = _resolve_btop_command(command)

    session = await asyncio.to_thread(
        _spawn_sync,
        command=list(resolved_command),
        env=_build_env(env),
        cols=cols,
        rows=rows,
    )
    session.reader_task = asyncio.create_task(_read_output(session))
    return session


async def send_input(session: BtopSession, data: str) -> None:
    if session.status != "running" or not data:
        return
    await asyncio.to_thread(os.write, session.master_fd, data.encode("utf-8"))


async def resize(session: BtopSession, *, cols: int, rows: int) -> None:
    if session.status != "running":
        return
    packed = struct.pack("HHHH", rows, cols, 0, 0)
    await asyncio.to_thread(_set_window_size, session.master_fd, packed)


async def terminate_session(session: BtopSession) -> None:
    session.status = "closed"
    with contextlib.suppress(ProcessLookupError):
        os.killpg(os.getpgid(session.process.pid), signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):
        await asyncio.to_thread(session.process.wait, 1)
    if session.process.poll() is None:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(os.getpgid(session.process.pid), signal.SIGKILL)
    with contextlib.suppress(OSError):
        os.close(session.master_fd)
    if session.reader_task:
        session.reader_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await session.reader_task


def _spawn_sync(
    *,
    command: list[str],
    env: dict[str, str],
    cols: int,
    rows: int,
) -> BtopSession:
    master_fd, slave_fd = pty.openpty()
    _set_window_size(master_fd, struct.pack("HHHH", rows, cols, 0, 0))
    process = subprocess.Popen(
        command,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        preexec_fn=os.setsid,
        close_fds=True,
    )
    os.close(slave_fd)
    return BtopSession(master_fd=master_fd, process=process)


def _build_env(override: dict[str, str] | None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()}
    env["TERM"] = "xterm-256color"
    env.setdefault("LANG", "en_US.UTF-8")
    env.setdefault("LC_ALL", "en_US.UTF-8")
    if override:
        env.update(override)
    return env


def _resolve_btop_command(command: tuple[str, ...]) -> tuple[tuple[str, ...], list[str]]:
    binary = command[0]
    attempted: list[str] = []

    def add_attempt(path: str | None) -> None:
        if path and path not in attempted:
            attempted.append(path)

    def executable(path: str) -> bool:
        return os.path.exists(path) and os.access(path, os.X_OK)

    if os.path.sep in binary:
        add_attempt(binary)
        if executable(binary):
            return command, attempted
        raise BtopUnavailableError(binary, attempted)

    configured = os.getenv("BTOP_BIN", "").strip()
    if configured:
        add_attempt(configured)
        if executable(configured):
            return (configured, *command[1:]), attempted

    found = shutil.which(binary)
    add_attempt(found)
    if found:
        return (found, *command[1:]), attempted

    if binary == DEFAULT_BTOP_ARGV[0]:
        for path in COMMON_BTOP_PATHS:
            add_attempt(path)
            if executable(path):
                return (path, *command[1:]), attempted

    raise BtopUnavailableError(binary, attempted)


def _set_window_size(master_fd: int, packed: bytes) -> None:
    import fcntl

    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, packed)


async def _read_output(session: BtopSession) -> None:
    try:
        while True:
            chunk = await asyncio.to_thread(os.read, session.master_fd, 4096)
            if not chunk:
                break
            decoded = chunk.decode("utf-8", errors="replace")
            await _put(session.queue, {"type": "output", "data": decoded})
    except OSError:
        pass
    finally:
        exit_code = await asyncio.to_thread(session.process.wait)
        session.exit_code = exit_code
        if session.status != "closed":
            session.status = "exited"
            await _put(session.queue, {"type": "exit", "exit_code": exit_code})


async def _put(queue: asyncio.Queue[dict], message: dict) -> None:
    with contextlib.suppress(asyncio.QueueFull):
        queue.put_nowait(message)
