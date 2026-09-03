"""CLI contract tests for the complete Agent Harness."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from app.cli.main import app
from tests.test_cli.conftest import make_envelope


_COMMAND = "app.cli.commands.agent"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_session_create_uses_snapshot_contract(runner: CliRunner) -> None:
    response = make_envelope(
        {
            "session": {"id": "session-1"},
            "current_run": None,
            "entries": [],
            "revision": 0,
        }
    )

    with patch(
        f"{_COMMAND}.api_post", new_callable=AsyncMock, return_value=response
    ) as post:
        result = runner.invoke(
            app,
            [
                "agent",
                "session",
                "create",
                "--project",
                "project-1",
                "--title",
                "QC triage",
            ],
        )

    assert result.exit_code == 0
    assert "session-1" in result.stdout
    assert post.await_args.args[1] == "/agent/sessions"
    assert post.await_args.args[2] == {
        "project_id": "project-1",
        "title": "QC triage",
        "permission_mode": "ask_dangerous",
        "workspace_access": "read_write",
    }


def test_send_dispatches_message_command(runner: CliRunner) -> None:
    response = make_envelope({"session": {"id": "session-1"}})

    with patch(
        f"{_COMMAND}.api_post", new_callable=AsyncMock, return_value=response
    ) as post:
        result = runner.invoke(
            app,
            ["agent", "send", "Inspect the workflow", "--session", "session-1"],
        )

    assert result.exit_code == 0
    assert "message accepted" in result.stdout
    assert post.await_args.args[1] == "/agent/sessions/session-1/commands"
    payload = post.await_args.args[2]
    assert payload["type"] == "message"
    assert payload["parts"] == [{"type": "text", "text": "Inspect the workflow"}]
    assert isinstance(payload["command_id"], str) and payload["command_id"]


def test_follow_up_dispatches_follow_up_command(runner: CliRunner) -> None:
    response = make_envelope({"session": {"id": "session-1"}})

    with patch(
        f"{_COMMAND}.api_post", new_callable=AsyncMock, return_value=response
    ) as post:
        result = runner.invoke(
            app,
            [
                "agent",
                "follow-up",
                "session-1",
                "Continue after this run",
            ],
        )

    assert result.exit_code == 0
    assert "follow_up accepted" in result.stdout
    payload = post.await_args.args[2]
    assert payload["type"] == "follow_up"
    assert payload["parts"] == [{"type": "text", "text": "Continue after this run"}]


def test_respond_requires_a_json_object(runner: CliRunner) -> None:
    result = runner.invoke(
        app,
        [
            "agent",
            "respond",
            "session-1",
            "interaction-1",
            "--response-json",
            "[]",
        ],
    )

    assert result.exit_code == 2
    assert "must be a JSON object" in result.stdout


@pytest.mark.parametrize("legacy_command", ["turn", "action"])
def test_removed_agent_state_machine_commands_are_not_exposed(
    runner: CliRunner,
    legacy_command: str,
) -> None:
    result = runner.invoke(app, ["agent", legacy_command, "--help"])

    assert result.exit_code != 0
