"""Tests for run_dispatch module — scheduler dispatcher and failure marking."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.run_dispatch import (
    SchedulerDispatcher,
    _enqueue_or_mark_failed,
    _mark_run_failed,
    get_run_dispatcher,
    set_run_dispatcher,
)


class TestGetSetHelpers:
    def test_get_run_dispatcher_raises_when_unset(self):
        set_run_dispatcher(None)
        with pytest.raises(RuntimeError, match="not configured"):
            get_run_dispatcher()

    def test_get_run_dispatcher_returns_custom_when_set(self):
        mock = MagicMock()
        try:
            set_run_dispatcher(mock)
            assert get_run_dispatcher() is mock
        finally:
            set_run_dispatcher(None)


class TestSchedulerDispatcher:
    def test_dispatch_creates_async_task(self):
        mock_scheduler = MagicMock()
        dispatcher = SchedulerDispatcher(mock_scheduler)

        loop = asyncio.new_event_loop()
        try:
            async def _run():
                with patch(
                    "app.services.run_dispatch._enqueue_or_mark_failed",
                    new_callable=AsyncMock,
                ) as mock_enqueue:
                    dispatcher.dispatch("run-789", priority="high")
                    await asyncio.sleep(0)
                    mock_enqueue.assert_called_once_with(
                        mock_scheduler, "run-789", priority="high"
                    )

            loop.run_until_complete(_run())
        finally:
            loop.close()


@pytest.mark.asyncio
async def test_mark_run_failed_updates_run_and_publishes():
    mock_run = MagicMock()
    mock_repo = MagicMock()
    mock_repo.mark_failed = AsyncMock(return_value=mock_run)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session_maker = MagicMock(return_value=mock_session)

    with (
        patch("app.services.run_dispatch.app_database") as mock_db,
        patch("app.services.run_dispatch.RunRepository", return_value=mock_repo),
        patch(
            "app.services.run_dispatch.publish_run_status",
            new_callable=AsyncMock,
        ) as mock_publish,
    ):
        mock_db.async_session_maker = mock_session_maker
        await _mark_run_failed("run-fail-1", "scheduler crashed")

    mock_repo.mark_failed.assert_called_once_with("run-fail-1", "scheduler crashed")
    mock_publish.assert_called_once_with(mock_run, message="Run failed")


@pytest.mark.asyncio
async def test_mark_run_failed_skips_publish_when_run_not_found():
    mock_repo = MagicMock()
    mock_repo.mark_failed = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session_maker = MagicMock(return_value=mock_session)

    with (
        patch("app.services.run_dispatch.app_database") as mock_db,
        patch("app.services.run_dispatch.RunRepository", return_value=mock_repo),
        patch(
            "app.services.run_dispatch.publish_run_status",
            new_callable=AsyncMock,
        ) as mock_publish,
    ):
        mock_db.async_session_maker = mock_session_maker
        await _mark_run_failed("run-nonexistent", "oops")

    mock_publish.assert_not_called()


@pytest.mark.asyncio
async def test_enqueue_or_mark_failed_calls_scheduler_enqueue():
    mock_scheduler = MagicMock()
    mock_scheduler.enqueue = AsyncMock()

    await _enqueue_or_mark_failed(mock_scheduler, "run-ok", priority="normal")

    mock_scheduler.enqueue.assert_called_once_with("run-ok", priority="normal")


@pytest.mark.asyncio
async def test_enqueue_or_mark_failed_marks_failed_on_exception():
    mock_scheduler = MagicMock()
    mock_scheduler.enqueue = AsyncMock(side_effect=RuntimeError("queue full"))

    with patch(
        "app.services.run_dispatch._mark_run_failed", new_callable=AsyncMock
    ) as mock_mark:
        await _enqueue_or_mark_failed(mock_scheduler, "run-boom", priority="normal")

    mock_mark.assert_called_once_with("run-boom", "queue full")


@pytest.mark.asyncio
async def test_enqueue_or_mark_failed_skips_terminal_runs():
    mock_scheduler = MagicMock()
    mock_scheduler.enqueue = AsyncMock(side_effect=RuntimeError("queue full"))

    with (
        patch(
            "app.services.run_dispatch._run_is_terminal",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "app.services.run_dispatch._mark_run_failed", new_callable=AsyncMock
        ) as mock_mark,
    ):
        await _enqueue_or_mark_failed(mock_scheduler, "run-done", priority="normal")

    mock_mark.assert_not_called()
