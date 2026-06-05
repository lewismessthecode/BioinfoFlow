"""Tests for AgentCore CLI commands."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import ANY, AsyncMock, patch

import pytest
from typer.testing import CliRunner

from app.cli.client import SSEEvent
from app.cli.main import app
from tests.test_cli.conftest import make_envelope

_A = "app.cli.commands.agent"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class _AsyncIter:
    def __init__(self, items: list[SSEEvent]):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


def _stream(items: list[SSEEvent]):
    def _factory(*_args: Any, **_kwargs: Any) -> _AsyncIter:
        return _AsyncIter(items)

    return _factory


def _session_payload(session_id: str = "session-1") -> dict[str, Any]:
    return {
        "id": session_id,
        "project_id": "p-1",
        "title": "QC triage",
        "role_profile": "bioinformatician",
        "permission_mode": "guarded_auto",
        "automation_mode": "assisted",
        "status": "active",
        "created_at": "2026-06-04T00:00:00Z",
        "updated_at": "2026-06-04T00:00:00Z",
    }


def _turn_payload(turn_id: str = "turn-1") -> dict[str, Any]:
    return {
        "id": turn_id,
        "session_id": "session-1",
        "project_id": "p-1",
        "input_text": "hello",
        "status": "completed",
        "final_text": "AgentCore session is active.",
        "created_at": "2026-06-04T00:00:00Z",
        "updated_at": "2026-06-04T00:00:00Z",
    }


class TestAgentSession:
    def test_creates_session(self, runner: CliRunner) -> None:
        resp = make_envelope(_session_payload())

        with patch(f"{_A}.api_post", new_callable=AsyncMock, return_value=resp) as post:
            result = runner.invoke(
                app,
                [
                    "--project",
                    "p-1",
                    "agent",
                    "session",
                    "create",
                    "--title",
                    "QC triage",
                ],
            )

        assert result.exit_code == 0
        assert "session-1" in result.stdout
        post.assert_awaited_once()
        assert post.await_args.args[1] == "/agent/sessions"
        assert post.await_args.args[2]["project_id"] == "p-1"
        assert post.await_args.args[2]["title"] == "QC triage"

    def test_lists_sessions(self, runner: CliRunner) -> None:
        resp = make_envelope([_session_payload()])

        with patch(f"{_A}.api_get", new_callable=AsyncMock, return_value=resp) as get:
            result = runner.invoke(app, ["agent", "session", "list"])

        assert result.exit_code == 0
        assert "session-1" in result.stdout
        get.assert_awaited_once_with(ANY, "/agent/sessions", {})

    def test_shows_session(self, runner: CliRunner) -> None:
        resp = make_envelope(_session_payload())

        with patch(f"{_A}.api_get", new_callable=AsyncMock, return_value=resp) as get:
            result = runner.invoke(app, ["agent", "session", "show", "session-1"])

        assert result.exit_code == 0
        assert "QC triage" in result.stdout
        get.assert_awaited_once()
        assert get.await_args.args[1] == "/agent/sessions/session-1"

    def test_deletes_session(self, runner: CliRunner) -> None:
        resp = make_envelope({})

        with patch(
            f"{_A}.api_delete", new_callable=AsyncMock, return_value=resp
        ) as delete:
            result = runner.invoke(app, ["agent", "session", "delete", "session-1"])

        assert result.exit_code == 0
        assert "deleted" in result.stdout
        delete.assert_awaited_once()
        assert delete.await_args.args[1] == "/agent/sessions/session-1"


class TestAgentSend:
    def test_send_requires_project_when_session_is_missing(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(app, ["agent", "send", "hello"])

        assert result.exit_code != 0

    def test_send_uses_existing_session_and_turn_endpoint(
        self, runner: CliRunner
    ) -> None:
        turn_resp = make_envelope(_turn_payload())

        with patch(
            "app.cli.client.ApiClient.post",
            new_callable=AsyncMock,
            return_value=turn_resp,
        ) as post:
            result = runner.invoke(
                app,
                ["agent", "send", "hello", "--session", "session-1"],
            )

        assert result.exit_code == 0
        assert "AgentCore session is active." in result.stdout
        post.assert_awaited_once()
        assert post.await_args.args[0] == "/agent/sessions/session-1/turns"
        assert post.await_args.args[1] == {"input_text": "hello"}
        assert "/agent/message" not in str(post.await_args_list)
        assert "/agent/conversations" not in str(post.await_args_list)

    def test_send_creates_session_then_turn(self, runner: CliRunner) -> None:
        session_resp = make_envelope(_session_payload())
        turn_resp = make_envelope(_turn_payload())

        with patch(
            "app.cli.client.ApiClient.post",
            new_callable=AsyncMock,
            side_effect=[session_resp, turn_resp],
        ) as post:
            result = runner.invoke(
                app,
                ["--project", "p-1", "agent", "send", "hello"],
            )

        assert result.exit_code == 0
        assert "session-1" in result.stdout
        assert "--session session-1" in result.stdout
        assert [call.args[0] for call in post.await_args_list] == [
            "/agent/sessions",
            "/agent/sessions/session-1/turns",
        ]
        assert post.await_args_list[0].args[1]["project_id"] == "p-1"
        assert post.await_args_list[1].args[1] == {"input_text": "hello"}


class TestAgentChat:
    def test_chat_requires_project_when_session_is_missing(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(app, ["agent", "chat"])

        assert result.exit_code != 0

    def test_chat_starts_loop(self, runner: CliRunner) -> None:
        with patch(f"{_A}._chat_loop", new_callable=AsyncMock) as loop:
            result = runner.invoke(app, ["--project", "p-1", "agent", "chat"])

        assert result.exit_code == 0
        loop.assert_called_once()


class TestAgentEvents:
    def test_lists_turn_events(self, runner: CliRunner) -> None:
        resp = make_envelope(
            [
                {
                    "id": "event-1",
                    "turn_id": "turn-1",
                    "seq": 1,
                    "type": "turn.created",
                    "visibility": "user",
                    "payload": {"input_text": "hello"},
                    "created_at": "2026-06-04T00:00:00Z",
                }
            ]
        )

        with patch(f"{_A}.api_get", new_callable=AsyncMock, return_value=resp) as get:
            result = runner.invoke(app, ["agent", "events", "turn-1"])

        assert result.exit_code == 0
        assert "turn.created" in result.stdout
        get.assert_awaited_once()
        assert get.await_args.args[1] == "/agent/turns/turn-1/events"
        assert get.await_args.args[2] == {"after_seq": 0}

    def test_stream_outputs_sse_events(self, runner: CliRunner) -> None:
        events = [
            SSEEvent(
                id="event-1",
                event="assistant.text.completed",
                data=json.dumps(
                    {
                        "type": "assistant.text.completed",
                        "payload": {"text": "done"},
                    }
                ),
            ),
            SSEEvent(id=None, event="ready", data='{"status":"replayed"}'),
        ]

        with patch(
            "app.cli.client.ApiClient.stream_sse",
            side_effect=_stream(events),
        ) as stream:
            result = runner.invoke(
                app,
                ["--output", "json", "agent", "stream", "session-1"],
            )

        assert result.exit_code == 0
        lines = [json.loads(line) for line in result.stdout.splitlines()]
        assert lines[0]["event"] == "assistant.text.completed"
        assert lines[1]["event"] == "ready"
        stream.assert_called_once_with(
            "/agent/sessions/session-1/stream", {"after_seq": 0}
        )


class TestAgentTurn:
    def test_lists_session_turns(self, runner: CliRunner) -> None:
        resp = make_envelope([_turn_payload()])

        with patch(f"{_A}.api_get", new_callable=AsyncMock, return_value=resp) as get:
            result = runner.invoke(app, ["agent", "turn", "list", "session-1"])

        assert result.exit_code == 0
        assert "turn-1" in result.stdout
        get.assert_awaited_once()
        assert get.await_args.args[1] == "/agent/sessions/session-1/turns"

    def test_cancels_turn(self, runner: CliRunner) -> None:
        resp = make_envelope({**_turn_payload(), "status": "cancelled"})

        with patch(f"{_A}.api_post", new_callable=AsyncMock, return_value=resp) as post:
            result = runner.invoke(app, ["agent", "turn", "cancel", "turn-1"])

        assert result.exit_code == 0
        assert "cancelled" in result.stdout
        post.assert_awaited_once()
        assert post.await_args.args[1] == "/agent/turns/turn-1/cancel"


class TestAgentAction:
    def test_approves_action(self, runner: CliRunner) -> None:
        resp = make_envelope({"id": "action-1", "status": "completed"})

        with patch(f"{_A}.api_post", new_callable=AsyncMock, return_value=resp) as post:
            result = runner.invoke(
                app, ["agent", "action", "approve", "action-1", "--note", "ok"]
            )

        assert result.exit_code == 0
        assert "approved" in result.stdout
        post.assert_awaited_once()
        assert post.await_args.args[1] == "/agent/actions/action-1/decision"
        assert post.await_args.args[2] == {"decision": "approve", "note": "ok"}

    def test_rejects_action(self, runner: CliRunner) -> None:
        resp = make_envelope({"id": "action-1", "status": "rejected"})

        with patch(f"{_A}.api_post", new_callable=AsyncMock, return_value=resp) as post:
            result = runner.invoke(app, ["agent", "action", "reject", "action-1"])

        assert result.exit_code == 0
        assert "rejected" in result.stdout
        post.assert_awaited_once()
        assert post.await_args.args[2] == {"decision": "reject"}


class TestAgentArtifacts:
    def test_lists_turn_artifacts(self, runner: CliRunner) -> None:
        resp = make_envelope(
            [
                {
                    "id": "artifact-1",
                    "turn_id": "turn-1",
                    "type": "log_summary",
                    "title": "Shell output",
                    "summary": "exit 0",
                    "created_at": "2026-06-04T00:00:00Z",
                }
            ]
        )

        with patch(f"{_A}.api_get", new_callable=AsyncMock, return_value=resp) as get:
            result = runner.invoke(app, ["agent", "artifacts", "list", "turn-1"])

        assert result.exit_code == 0
        assert "Shell output" in result.stdout
        get.assert_awaited_once()
        assert get.await_args.args[1] == "/agent/turns/turn-1/artifacts"

    def test_lists_session_artifacts(self, runner: CliRunner) -> None:
        resp = make_envelope([])

        with patch(f"{_A}.api_get", new_callable=AsyncMock, return_value=resp) as get:
            result = runner.invoke(
                app,
                ["agent", "artifacts", "list", "session-1", "--scope", "session"],
            )

        assert result.exit_code == 0
        get.assert_awaited_once()
        assert get.await_args.args[1] == "/agent/sessions/session-1/artifacts"

    def test_shows_artifact(self, runner: CliRunner) -> None:
        resp = make_envelope(
            {
                "id": "artifact-1",
                "type": "report",
                "title": "Run summary",
                "summary": "All samples passed.",
                "payload": {"sample_count": 12},
            }
        )

        with patch(f"{_A}.api_get", new_callable=AsyncMock, return_value=resp) as get:
            result = runner.invoke(app, ["agent", "artifacts", "show", "artifact-1"])

        assert result.exit_code == 0
        assert "Run summary" in result.stdout
        get.assert_awaited_once()
        assert get.await_args.args[1] == "/agent/artifacts/artifact-1"


class TestLegacyAgentCommands:
    def test_legacy_approvals_group_is_removed(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["agent", "approvals", "list", "conv-1"])

        assert result.exit_code != 0

    def test_legacy_history_command_is_removed(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["agent", "history", "conv-1"])

        assert result.exit_code != 0
