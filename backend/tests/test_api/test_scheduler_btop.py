"""Tests for the btop pty bridge.

The WebSocket route is a thin shim over :mod:`app.services.btop_service`,
so most tests drive the service functions directly — no WS gymnastics.
A real ``btop`` binary is not assumed; we use short-lived Unix commands
as stand-ins because they share the pty contract with btop.

The last test exercises the full WS route with the binary forced
"unavailable" to prove the fallback message reaches the client.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import settings
from app.main import app
from app.services.btop_service import (
    BtopUnavailableError,
    resize as btop_resize,
    send_input,
    spawn_btop_session,
    terminate_session,
)
from tests.support.auth import create_better_auth_db


@pytest.mark.asyncio
async def test_spawn_raises_when_binary_missing() -> None:
    with pytest.raises(BtopUnavailableError):
        await spawn_btop_session(argv=["/definitely/not/a/binary-xyz"])


@pytest.mark.asyncio
async def test_spawn_attaches_pty_and_reader_task() -> None:
    """Spawning creates a live pty and starts the reader task."""
    session = await spawn_btop_session(argv=["cat"])
    try:
        assert session.process.poll() is None
        assert session.reader_task is not None
        assert not session.reader_task.done()
        assert session.status == "running"
    finally:
        await terminate_session(session)


@pytest.mark.asyncio
async def test_resize_is_idempotent() -> None:
    session = await spawn_btop_session(argv=["cat"])
    try:
        await btop_resize(session, cols=120, rows=32)
        await btop_resize(session, cols=80, rows=24)
    finally:
        await terminate_session(session)


@pytest.mark.asyncio
async def test_send_input_is_noop_when_closed() -> None:
    """Late send after terminate must not raise or write to a closed fd."""
    session = await spawn_btop_session(argv=["cat"])
    await terminate_session(session)
    await send_input(session, "ignored\n")


@pytest.mark.asyncio
async def test_terminate_kills_process_and_clears_status() -> None:
    session = await spawn_btop_session(argv=["cat"])
    pid = session.process.pid
    await terminate_session(session)
    # Give the OS a beat to reap the process.
    for _ in range(20):
        if _pid_is_gone(pid):
            break
        await asyncio.sleep(0.05)
    assert _pid_is_gone(pid)
    assert session.status == "closed"


@pytest.mark.asyncio
async def test_terminate_safe_when_process_already_exited() -> None:
    """`true` exits immediately — terminate must still clean up the fd."""
    session = await spawn_btop_session(argv=["true"])
    # Wait for the reader task to surface the exit event.
    async with asyncio.timeout(2):
        while session.status == "running":
            await asyncio.sleep(0.02)
    await terminate_session(session)


def test_ws_sends_unavailable_message_when_btop_missing() -> None:
    """End-to-end WS fallback: server → error frame → close 4404.

    Regressed against the user-facing failure mode where btop is not
    installed on the host. The frontend reads ``code == 'btop_unavailable'``
    and renders install instructions instead of a generic error.
    """
    client = TestClient(app)
    with patch("app.services.btop_service.shutil.which", return_value=None):
        with client.websocket_connect("/api/v1/scheduler/btop/ws") as ws:
            # Backend waits 0.5 s for an initial resize; send one so it
            # proceeds to the spawn step quickly instead of timing out.
            ws.send_json({"type": "resize", "cols": 80, "rows": 24})
            message = ws.receive_json()
            assert message == {
                "type": "error",
                "code": "btop_unavailable",
                "message": "btop binary not found: btop",
            }
            # Server closes the socket immediately after the error.
            with pytest.raises(Exception):
                ws.receive_json()


def test_ws_requires_auth_when_enabled(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth_db_path = tmp_path / "better-auth.db"
    create_better_auth_db(auth_db_path)
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_mode", "")
    monkeypatch.setattr(settings, "better_auth_db_path", str(auth_db_path))

    client = TestClient(app)
    with client.websocket_connect("/api/v1/scheduler/btop/ws") as ws:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.send_json({"type": "resize", "cols": 80, "rows": 24})
            ws.receive_json()
    assert exc_info.value.code == 4401


def _pid_is_gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False
