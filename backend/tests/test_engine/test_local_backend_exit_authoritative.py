"""LocalBackend exit-code authority regression test.

Non-zero exit must always emit an ERROR with code=ENGINE_NONZERO_EXIT,
even when a COMPLETED event was previously parsed from stdout.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.engine.backend import EngineEvent, EngineEventType
from app.engine.local import LocalBackend


class _FakeProcess:
    def __init__(self, *, returncode: int, stdout_lines, stderr_lines):
        self.returncode = returncode
        self.pid = 4242
        self.stdout = _FakeStream(stdout_lines)
        self.stderr = _FakeStream(stderr_lines)

    async def wait(self):
        return self.returncode


class _FakeStream:
    def __init__(self, lines):
        self._lines = list(lines)

    async def readline(self):
        if not self._lines:
            return b""
        return self._lines.pop(0)


class _FakeAdapter:
    display_name = "fake-engine"
    binary = "fake"
    engine_name = "fake"

    async def pre_submit(self, config, workspace):
        return config

    async def build_command(self, config, workspace):
        return ("fake-binary", "run")

    def parse_event(self, text, kind):
        if text == "DONE":
            return EngineEvent(EngineEventType.COMPLETED, {"success": True})
        return None

    async def post_complete(self, config, workspace, status):
        return None

    async def cancel(self, *, pid=None, **kwargs):
        return True


async def _make_proc(proc):
    async def _spawner(*args, **kwargs):
        return proc

    return _spawner


@pytest.mark.asyncio
async def test_nonzero_exit_emits_error_even_after_completed_event():
    proc = _FakeProcess(
        returncode=2,
        stdout_lines=[b"DONE\n"],
        stderr_lines=[b"permission denied\n"],
    )
    spawner = await _make_proc(proc)

    events = []
    with patch("asyncio.create_subprocess_exec", spawner):
        async for event in LocalBackend().submit(_FakeAdapter(), {}, "/tmp"):
            events.append(event)

    types = [e.type for e in events]
    assert EngineEventType.COMPLETED in types
    assert EngineEventType.ERROR in types
    error = next(e for e in events if e.type == EngineEventType.ERROR)
    assert error.data["code"] == "ENGINE_NONZERO_EXIT"
    assert error.data["exit_code"] == 2


@pytest.mark.asyncio
async def test_zero_exit_still_emits_completed_on_success():
    proc = _FakeProcess(returncode=0, stdout_lines=[b"DONE\n"], stderr_lines=[])
    spawner = await _make_proc(proc)

    events = []
    with patch("asyncio.create_subprocess_exec", spawner):
        async for event in LocalBackend().submit(_FakeAdapter(), {}, "/tmp"):
            events.append(event)

    types = [e.type for e in events]
    assert EngineEventType.COMPLETED in types
    assert EngineEventType.ERROR not in types
