"""Tests for agent commands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from app.cli.main import app
from tests.test_cli.conftest import make_envelope

_A = "app.cli.commands.agent"
_AA = "app.cli.commands.agent_approvals"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestAgentSend:
    def test_send_requires_project(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--mode", "remote", "agent", "send", "hello"])
        assert result.exit_code != 0

    def test_send_streams(self, runner: CliRunner) -> None:
        with patch(f"{_A}._send", new_callable=AsyncMock) as mock_send:
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "remote",
                    "--project",
                    "p-1",
                    "agent",
                    "send",
                    "list projects",
                ],
            )
        assert result.exit_code == 0
        mock_send.assert_called_once()


class TestAgentChat:
    def test_chat_requires_project(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--mode", "remote", "agent", "chat"])
        assert result.exit_code != 0

    def test_chat_starts_loop(self, runner: CliRunner) -> None:
        with patch(f"{_A}._chat_loop", new_callable=AsyncMock) as mock_loop:
            result = runner.invoke(
                app,
                ["--mode", "remote", "--project", "p-1", "agent", "chat"],
            )
        assert result.exit_code == 0
        mock_loop.assert_called_once()


class TestAgentHistory:
    def test_shows_history(self, runner: CliRunner) -> None:
        resp = make_envelope(
            {
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "hi there"},
                ]
            }
        )
        with patch(f"{_A}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--mode", "remote", "agent", "history", "conv-1"]
            )
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert "hi there" in result.stdout

    def test_json_output(self, runner: CliRunner) -> None:
        resp = make_envelope({"messages": [{"role": "user", "content": "test"}]})
        with patch(f"{_A}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app,
                ["--output", "json", "--mode", "remote", "agent", "history", "conv-1"],
            )
        parsed = json.loads(result.stdout)
        assert parsed["success"] is True


class TestAgentStatus:
    def test_shows_status(self, runner: CliRunner) -> None:
        resp = make_envelope({"running": True})
        with patch(f"{_A}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--mode", "remote", "agent", "status", "conv-1"]
            )
        assert result.exit_code == 0
        assert "True" in result.stdout


class TestAgentCancel:
    def test_cancels(self, runner: CliRunner) -> None:
        resp = make_envelope({"cancelled": True})
        with patch(f"{_A}.api_post", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--mode", "remote", "agent", "cancel", "conv-1"]
            )
        assert result.exit_code == 0
        assert "cancelled" in result.stdout


class TestAgentTrace:
    def test_shows_trace(self, runner: CliRunner) -> None:
        resp = make_envelope(
            [
                {
                    "type": "tool_call",
                    "tool": "scan_dir",
                    "duration_ms": 150,
                    "timestamp": "2025-01-01T00:00:00Z",
                },
            ]
        )
        with patch(f"{_A}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--mode", "remote", "agent", "trace", "conv-1"]
            )
        assert result.exit_code == 0
        assert "scan_dir" in result.stdout


class TestApprovalsList:
    def test_lists_approvals(self, runner: CliRunner) -> None:
        resp = make_envelope(
            [
                {
                    "id": "a-1",
                    "tool": "execute_code",
                    "status": "pending",
                    "created_at": "2025-01-01T00:00:00Z",
                },
            ]
        )
        with patch(f"{_AA}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--mode", "remote", "agent", "approvals", "list", "conv-1"]
            )
        assert result.exit_code == 0
        assert "execute_code" in result.stdout


class TestApprovalsResolve:
    def test_approves(self, runner: CliRunner) -> None:
        resp = make_envelope({"resolved": True})
        with patch(f"{_AA}.api_post", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app,
                ["--mode", "remote", "agent", "approvals", "resolve", "a-1", "approve"],
            )
        assert result.exit_code == 0
        assert "approved" in result.stdout

    def test_rejects(self, runner: CliRunner) -> None:
        resp = make_envelope({"resolved": True})
        with patch(f"{_AA}.api_post", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app,
                ["--mode", "remote", "agent", "approvals", "resolve", "a-1", "reject"],
            )
        assert result.exit_code == 0
        assert "rejected" in result.stdout

    def test_invalid_action(self, runner: CliRunner) -> None:
        result = runner.invoke(
            app, ["--mode", "remote", "agent", "approvals", "resolve", "a-1", "maybe"]
        )
        assert result.exit_code != 0
