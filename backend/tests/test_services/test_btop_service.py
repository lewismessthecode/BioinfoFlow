from __future__ import annotations

import asyncio
import os
import signal
import struct
import subprocess

import pytest

from app.services.btop_service import (
    BtopUnavailableError,
    BtopSession,
    _build_env,
    _read_output,
    _resolve_btop_command,
    resize,
    send_input,
    spawn_btop_session,
    terminate_session,
)


class FakeProcess:
    def __init__(self, *, pid: int = 123, poll_result: int | None = 0) -> None:
        self.pid = pid
        self._poll_result = poll_result

    def poll(self) -> int | None:
        return self._poll_result

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        return 0


@pytest.mark.asyncio
async def test_spawn_btop_session_passes_command_env_and_terminal_size(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    session = BtopSession(
        master_fd=11,
        process=FakeProcess(poll_result=None),
    )

    monkeypatch.setattr("app.services.btop_service.shutil.which", lambda binary: f"/usr/bin/{binary}")

    def fake_spawn_sync(*, command: list[str], env: dict[str, str], cols: int, rows: int) -> BtopSession:
        captured["command"] = command
        captured["env"] = env
        captured["cols"] = cols
        captured["rows"] = rows
        return session

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    async def fake_read_output(active_session: BtopSession) -> None:
        captured["reader_session"] = active_session

    monkeypatch.setattr("app.services.btop_service._spawn_sync", fake_spawn_sync)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr("app.services.btop_service._read_output", fake_read_output)

    spawned = await spawn_btop_session(
        argv=("btop", "--utf-force"),
        env={"EXTRA_FLAG": "1"},
        cols=160,
        rows=48,
    )

    assert spawned is session
    assert captured["command"] == ["/usr/bin/btop", "--utf-force"]
    assert captured["cols"] == 160
    assert captured["rows"] == 48
    assert isinstance(captured["env"], dict)
    assert captured["env"]["TERM"] == "xterm-256color"
    assert captured["env"]["EXTRA_FLAG"] == "1"
    assert session.reader_task is not None


def test_build_env_sets_terminal_defaults_and_preserves_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANG", "C.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)

    env = _build_env({"LC_ALL": "zh_CN.UTF-8", "CUSTOM": "enabled"})

    assert env["TERM"] == "xterm-256color"
    assert env["LANG"] == "C.UTF-8"
    assert env["LC_ALL"] == "zh_CN.UTF-8"
    assert env["CUSTOM"] == "enabled"


def test_resolve_btop_command_prefers_explicit_env_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BTOP_BIN", "/srv/tools/btop")
    monkeypatch.setattr(
        "app.services.btop_service.os.path.exists",
        lambda path: path == "/srv/tools/btop",
    )
    monkeypatch.setattr(
        "app.services.btop_service.os.access",
        lambda path, mode: path == "/srv/tools/btop",
    )
    monkeypatch.setattr("app.services.btop_service.shutil.which", lambda binary: None)

    resolved, attempted = _resolve_btop_command(("btop", "-p", "1"))

    assert resolved == ("/srv/tools/btop", "-p", "1")
    assert attempted[0] == "/srv/tools/btop"


def test_resolve_btop_command_checks_common_install_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BTOP_BIN", raising=False)
    monkeypatch.setattr("app.services.btop_service.shutil.which", lambda binary: None)
    monkeypatch.setattr(
        "app.services.btop_service.os.path.exists",
        lambda path: path == "/opt/homebrew/bin/btop",
    )
    monkeypatch.setattr(
        "app.services.btop_service.os.access",
        lambda path, mode: path == "/opt/homebrew/bin/btop",
    )

    resolved, attempted = _resolve_btop_command(("btop", "-p", "1"))

    assert resolved == ("/opt/homebrew/bin/btop", "-p", "1")
    assert "/opt/homebrew/bin/btop" in attempted


def test_resolve_btop_command_reports_attempted_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BTOP_BIN", "/missing/btop")
    monkeypatch.setattr("app.services.btop_service.shutil.which", lambda binary: None)
    monkeypatch.setattr("app.services.btop_service.os.path.exists", lambda path: False)
    monkeypatch.setattr("app.services.btop_service.os.access", lambda path, mode: False)

    with pytest.raises(BtopUnavailableError) as exc:
        _resolve_btop_command(("btop", "-p", "1"))

    assert exc.value.binary == "btop"
    assert "/missing/btop" in exc.value.attempted_paths
    assert "/usr/local/bin/btop" in exc.value.attempted_paths


@pytest.mark.asyncio
async def test_send_input_writes_utf8_only_for_running_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[tuple[int, bytes]] = []

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(os, "write", lambda fd, data: writes.append((fd, data)) or len(data))

    session = BtopSession(master_fd=7, process=FakeProcess(poll_result=None))

    await send_input(session, "q\n")
    assert writes == [(7, b"q\n")]

    session.status = "closed"
    await send_input(session, "ignored")
    assert writes == [(7, b"q\n")]


@pytest.mark.asyncio
async def test_resize_packs_rows_and_columns_for_the_pty(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, bytes]] = []

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(
        "app.services.btop_service._set_window_size",
        lambda master_fd, packed: calls.append((master_fd, packed)),
    )

    session = BtopSession(master_fd=9, process=FakeProcess(poll_result=None))

    await resize(session, cols=132, rows=40)

    assert len(calls) == 1
    assert calls[0][0] == 9
    assert struct.unpack("HHHH", calls[0][1]) == (40, 132, 0, 0)

    session.status = "closed"
    await resize(session, cols=80, rows=24)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_read_output_emits_output_and_exit_for_running_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = iter([b"cpu: 50%\n", b"mem: 20%\n", b""])

    class ProcessWithExit(FakeProcess):
        def wait(self, timeout: float | None = None) -> int:
            del timeout
            return 17

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(os, "read", lambda fd, size: next(chunks))

    session = BtopSession(master_fd=5, process=ProcessWithExit(poll_result=None))

    await _read_output(session)

    output_one = await session.queue.get()
    output_two = await session.queue.get()
    exit_message = await session.queue.get()

    assert output_one == {"type": "output", "data": "cpu: 50%\n"}
    assert output_two == {"type": "output", "data": "mem: 20%\n"}
    assert exit_message == {"type": "exit", "exit_code": 17}
    assert session.status == "exited"
    assert session.exit_code == 17


@pytest.mark.asyncio
async def test_terminate_session_escalates_after_timeout_and_cancels_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    kill_calls: list[tuple[int, int]] = []
    closed_fds: list[int] = []

    class HungProcess(FakeProcess):
        def __init__(self) -> None:
            super().__init__(pid=321, poll_result=None)

        def wait(self, timeout: float | None = None) -> int:
            raise subprocess.TimeoutExpired(cmd="btop", timeout=timeout or 1)

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(os, "getpgid", lambda pid: 999)
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: kill_calls.append((pgid, sig)))
    monkeypatch.setattr(os, "close", lambda fd: closed_fds.append(fd))

    session = BtopSession(master_fd=13, process=HungProcess())
    session.reader_task = asyncio.create_task(asyncio.sleep(60))

    await terminate_session(session)

    assert session.status == "closed"
    assert kill_calls == [
        (999, signal.SIGTERM),
        (999, signal.SIGKILL),
    ]
    assert closed_fds == [13]
    assert session.reader_task.cancelled() is True
