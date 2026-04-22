"""Tests for events stream and run watch/logs --follow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from app.cli.client import SSEEvent
from app.cli.main import app
from tests.test_cli.conftest import make_envelope

_R = "app.cli.commands.run"
_E = "app.cli.commands.events"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _run_data(status: str = "running") -> dict:
    return {
        "run_id": "r-42",
        "project_id": "p-1",
        "workflow_id": "wf-1",
        "status": status,
        "current_task": "FASTQC",
        "created_at": "2025-01-01T00:00:00Z",
    }


async def _fake_stream(*_args, **_kwargs):
    """Yield a few SSE events then a terminal status."""
    events = [
        SSEEvent(id="1", event="run.log", data='{"line": "Starting..."}'),
        SSEEvent(id="2", event="run.status", data='{"status": "completed"}'),
    ]
    for e in events:
        yield e


class TestRunWatch:
    def test_watch_terminal_exits_immediately(self, runner: CliRunner) -> None:
        """If run is already completed, just show details and exit."""
        resp = make_envelope(_run_data("completed"))
        with patch(f"{_R}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(app, ["--mode", "remote", "run", "watch", "r-42"])
        assert result.exit_code == 0
        assert "completed" in result.stdout

    def test_watch_streams_events(self, runner: CliRunner) -> None:
        """If run is active, stream events until terminal."""
        resp = make_envelope(_run_data("running"))

        async def mock_watch_stream(*args, **kwargs):
            pass

        with (
            patch(f"{_R}.api_get", new_callable=AsyncMock, return_value=resp),
            patch(f"{_R}._watch_stream", new_callable=AsyncMock) as mock_stream,
        ):
            result = runner.invoke(
                app, ["--mode", "remote", "--project", "p-1", "run", "watch", "r-42"]
            )
        assert result.exit_code == 0
        mock_stream.assert_called_once()


class TestRunLogsFollow:
    def test_logs_without_follow(self, runner: CliRunner) -> None:
        resp = make_envelope(["line 1", "line 2"])
        with patch(f"{_R}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(app, ["--mode", "remote", "run", "logs", "r-42"])
        assert result.exit_code == 0
        assert "line 1" in result.stdout

    def test_logs_with_follow(self, runner: CliRunner) -> None:
        resp = make_envelope(["initial line"])

        with (
            patch(f"{_R}.api_get", new_callable=AsyncMock, return_value=resp),
            patch(f"{_R}._follow_logs", new_callable=AsyncMock) as mock_follow,
        ):
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "remote",
                    "--project",
                    "p-1",
                    "run",
                    "logs",
                    "r-42",
                    "--follow",
                ],
            )
        assert result.exit_code == 0
        assert "initial line" in result.stdout
        mock_follow.assert_called_once()


class TestEventsStream:
    def test_requires_project(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--mode", "remote", "events", "stream"])
        assert result.exit_code != 0

    def test_stream_passes_params(self, runner: CliRunner) -> None:
        async def mock_stream(*args, **kwargs):
            pass

        with patch(f"{_E}._stream", new_callable=AsyncMock) as mock_fn:
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "remote",
                    "--project",
                    "p-1",
                    "events",
                    "stream",
                    "--run",
                    "r-42",
                ],
            )
        assert result.exit_code == 0
        call_args = mock_fn.call_args
        params = call_args[0][2]  # third positional arg is params dict
        assert params["project_id"] == "p-1"
        assert params["run_id"] == "r-42"

    def test_stream_with_conversation_filter(self, runner: CliRunner) -> None:
        with patch(f"{_E}._stream", new_callable=AsyncMock) as mock_fn:
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "remote",
                    "--project",
                    "p-1",
                    "events",
                    "stream",
                    "--conversation",
                    "conv-1",
                ],
            )
        assert result.exit_code == 0
        params = mock_fn.call_args[0][2]
        assert params["conversation_id"] == "conv-1"

    def test_stream_project_only(self, runner: CliRunner) -> None:
        with patch(f"{_E}._stream", new_callable=AsyncMock) as mock_fn:
            result = runner.invoke(
                app,
                ["--mode", "remote", "--project", "p-1", "events", "stream"],
            )
        assert result.exit_code == 0
        params = mock_fn.call_args[0][2]
        assert params == {"project_id": "p-1"}
