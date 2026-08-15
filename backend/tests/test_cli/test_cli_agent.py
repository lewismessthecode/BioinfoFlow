"""CLI acceptance tests for the complete Agent Harness surface."""

from __future__ import annotations

import json
from pathlib import Path
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


def _session(session_id: str = "session-1") -> dict[str, Any]:
    return {
        "id": session_id,
        "user_id": "user-1",
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "project_id": "00000000-0000-0000-0000-000000000002",
        "title": "QC triage",
        "permission_mode": "ask_dangerous",
        "status": "active",
        "created_at": "2026-08-14T00:00:00Z",
        "updated_at": "2026-08-14T00:00:00Z",
    }


def _snapshot(session_id: str = "session-1") -> dict[str, Any]:
    return {
        "session": _session(session_id),
        "current_run": None,
        "entries": [],
        "revision": 0,
    }


def _artifact(artifact_id: str = "artifact-1") -> dict[str, Any]:
    return {
        "id": artifact_id,
        "session_id": "session-1",
        "run_id": "run-1",
        "type": "file",
        "title": "QC report",
        "summary": "All samples passed.",
        "payload": {"sample_count": 12},
        "file_path": "/results/qc-report.html",
        "resource_ref": None,
        "created_at": "2026-08-14T00:00:00Z",
        "updated_at": "2026-08-14T00:00:00Z",
    }


class TestAgentSession:
    def test_creates_session_and_prints_snapshot_session_id(
        self, runner: CliRunner
    ) -> None:
        with patch(
            f"{_A}.api_post",
            new_callable=AsyncMock,
            return_value=make_envelope(_snapshot()),
        ) as post:
            result = runner.invoke(
                app,
                [
                    "--project",
                    "00000000-0000-0000-0000-000000000002",
                    "agent",
                    "session",
                    "create",
                    "--title",
                    "QC triage",
                    "--permission-mode",
                    "full_access",
                    "--provider",
                    "openai",
                    "--model",
                    "gpt-5.6",
                ],
            )

        assert result.exit_code == 0
        assert "session-1" in result.stdout
        post.assert_awaited_once()
        assert post.await_args.args[1] == "/agent/sessions"
        assert post.await_args.args[2] == {
            "project_id": "00000000-0000-0000-0000-000000000002",
            "title": "QC triage",
            "permission_mode": "full_access",
            "workspace_access": "read_write",
            "provider": "openai",
            "model": "gpt-5.6",
        }

    def test_lists_sessions(self, runner: CliRunner) -> None:
        with patch(
            f"{_A}.api_get",
            new_callable=AsyncMock,
            return_value=make_envelope([_session()]),
        ) as get:
            result = runner.invoke(app, ["agent", "session", "list"])

        assert result.exit_code == 0
        assert "session-1" in result.stdout
        get.assert_awaited_once_with(ANY, "/agent/sessions")

    def test_shows_session_snapshot(self, runner: CliRunner) -> None:
        with patch(
            f"{_A}.api_get",
            new_callable=AsyncMock,
            return_value=make_envelope(_snapshot()),
        ) as get:
            result = runner.invoke(
                app, ["--output", "json", "agent", "session", "show", "session-1"]
            )

        assert result.exit_code == 0
        assert json.loads(result.stdout)["data"]["session"]["id"] == "session-1"
        get.assert_awaited_once_with(ANY, "/agent/sessions/session-1/snapshot")

    def test_deletes_session(self, runner: CliRunner) -> None:
        with patch(
            f"{_A}.api_delete",
            new_callable=AsyncMock,
            return_value=make_envelope(None),
        ) as delete:
            result = runner.invoke(app, ["agent", "session", "delete", "session-1"])

        assert result.exit_code == 0
        assert "deleted" in result.stdout
        delete.assert_awaited_once_with(ANY, "/agent/sessions/session-1")


class TestAgentMessage:
    def test_send_dispatches_message_to_existing_session(
        self, runner: CliRunner
    ) -> None:
        with patch(
            f"{_A}.api_post",
            new_callable=AsyncMock,
            return_value=make_envelope(_snapshot()),
        ) as post:
            result = runner.invoke(
                app,
                [
                    "agent",
                    "send",
                    "inspect the samples",
                    "--session",
                    "session-1",
                    "--attachment",
                    "00000000-0000-0000-0000-000000000003",
                ],
            )

        assert result.exit_code == 0
        post.assert_awaited_once()
        assert post.await_args.args[1] == "/agent/sessions/session-1/commands"
        payload = post.await_args.args[2]
        assert payload["type"] == "message"
        assert payload["parts"] == [
            {"type": "text", "text": "inspect the samples"},
            {
                "type": "attachment_ref",
                "attachment_id": "00000000-0000-0000-0000-000000000003",
            },
        ]
        assert payload["command_id"]

    def test_send_creates_session_before_message_when_session_is_omitted(
        self, runner: CliRunner
    ) -> None:
        with patch(
            f"{_A}.api_post",
            new_callable=AsyncMock,
            side_effect=[make_envelope(_snapshot()), make_envelope(_snapshot())],
        ) as post:
            result = runner.invoke(
                app,
                [
                    "--project",
                    "00000000-0000-0000-0000-000000000002",
                    "agent",
                    "send",
                    "hello",
                    "--title",
                    "Fresh session",
                ],
            )

        assert result.exit_code == 0
        assert "session-1" in result.stdout
        assert [call.args[1] for call in post.await_args_list] == [
            "/agent/sessions",
            "/agent/sessions/session-1/commands",
        ]
        assert post.await_args_list[0].args[2] == {
            "project_id": "00000000-0000-0000-0000-000000000002",
            "title": "Fresh session",
            "permission_mode": "ask_dangerous",
            "workspace_access": "read_write",
        }
        assert post.await_args_list[1].args[2]["type"] == "message"


class TestAgentCommands:
    @pytest.mark.parametrize(
        ("argv", "expected"),
        [
            (
                ["agent", "steer", "session-1", "focus on RNA"],
                {
                    "type": "steer",
                    "parts": [{"type": "text", "text": "focus on RNA"}],
                },
            ),
            (
                ["agent", "cancel", "session-1", "--reason", "user stopped"],
                {"type": "cancel", "reason": "user stopped"},
            ),
        ],
    )
    def test_dispatches_commands(
        self, runner: CliRunner, argv: list[str], expected: dict[str, Any]
    ) -> None:
        with patch(
            f"{_A}.api_post",
            new_callable=AsyncMock,
            return_value=make_envelope(_snapshot()),
        ) as post:
            result = runner.invoke(app, argv)

        assert result.exit_code == 0
        payload = post.await_args.args[2]
        command_id = payload.pop("command_id")
        assert command_id
        assert payload == expected

    def test_respond_dispatches_structured_interaction_response(
        self, runner: CliRunner
    ) -> None:
        with patch(
            f"{_A}.api_post",
            new_callable=AsyncMock,
            return_value=make_envelope(_snapshot()),
        ) as post:
            result = runner.invoke(
                app,
                [
                    "agent",
                    "respond",
                    "session-1",
                    "interaction-1",
                    "--response-json",
                    '{"approved": true}',
                ],
            )

        assert result.exit_code == 0
        payload = post.await_args.args[2]
        assert payload["type"] == "respond"
        assert payload["interaction_id"] == "interaction-1"
        assert payload["response"] == {"approved": True}

    def test_respond_rejects_non_object_json(self, runner: CliRunner) -> None:
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
        assert "JSON object" in result.stdout


class TestAgentSnapshotAndEvents:
    def test_snapshot_reads_authoritative_snapshot(self, runner: CliRunner) -> None:
        with patch(
            f"{_A}.api_get",
            new_callable=AsyncMock,
            return_value=make_envelope(_snapshot()),
        ) as get:
            result = runner.invoke(
                app, ["--output", "json", "agent", "snapshot", "session-1"]
            )

        assert result.exit_code == 0
        assert json.loads(result.stdout)["data"]["revision"] == 0
        get.assert_awaited_once_with(ANY, "/agent/sessions/session-1/snapshot")

    def test_events_streams_session_sse(self, runner: CliRunner) -> None:
        events = [
            SSEEvent(
                id=None,
                event="snapshot",
                data=json.dumps({"type": "snapshot", "snapshot": _snapshot()}),
            ),
            SSEEvent(
                id=None,
                event="assistant.delta",
                data='{"type":"assistant.delta","run_id":"run-1","delta":"done"}',
            ),
        ]

        with patch(
            "app.cli.client.ApiClient.stream_sse",
            side_effect=_stream(events),
        ) as stream:
            result = runner.invoke(
                app,
                ["--output", "json", "agent", "events", "session-1"],
            )

        assert result.exit_code == 0
        lines = [json.loads(line) for line in result.stdout.splitlines()]
        assert [line["event"] for line in lines] == ["snapshot", "assistant.delta"]
        stream.assert_called_once_with("/agent/sessions/session-1/events")


class TestAgentArtifact:
    def test_lists_session_artifacts(self, runner: CliRunner) -> None:
        with patch(
            f"{_A}.api_get",
            new_callable=AsyncMock,
            return_value=make_envelope([_artifact()]),
        ) as get:
            result = runner.invoke(app, ["agent", "artifact", "list", "session-1"])

        assert result.exit_code == 0
        assert "QC report" in result.stdout
        get.assert_awaited_once_with(ANY, "/agent/sessions/session-1/artifacts")

    def test_shows_artifact(self, runner: CliRunner) -> None:
        with patch(
            f"{_A}.api_get",
            new_callable=AsyncMock,
            return_value=make_envelope(_artifact()),
        ) as get:
            result = runner.invoke(
                app, ["--output", "json", "agent", "artifact", "show", "artifact-1"]
            )

        assert result.exit_code == 0
        assert json.loads(result.stdout)["data"]["id"] == "artifact-1"
        get.assert_awaited_once_with(ANY, "/agent/artifacts/artifact-1")

    def test_downloads_artifact(self, runner: CliRunner, tmp_path: Path) -> None:
        destination = tmp_path / "qc-report.html"
        with patch(
            f"{_A}.api_download",
            new_callable=AsyncMock,
            return_value=destination,
        ) as download:
            result = runner.invoke(
                app,
                [
                    "--output",
                    "json",
                    "agent",
                    "artifact",
                    "download",
                    "artifact-1",
                    "--output",
                    str(destination),
                ],
            )

        assert result.exit_code == 0
        assert json.loads(result.stdout)["data"] == {
            "artifact_id": "artifact-1",
            "path": str(destination),
        }
        download.assert_awaited_once_with(
            ANY, "/agent/artifacts/artifact-1/download", destination
        )


class TestRemovedAgentCoreCommands:
    @pytest.mark.parametrize(
        "argv",
        [
            ["agent", "turn", "list", "session-1"],
            ["agent", "action", "approve", "action-1"],
            ["agent", "approvals", "list", "session-1"],
            ["agent", "history", "session-1"],
        ],
    )
    def test_legacy_command_is_removed(
        self, runner: CliRunner, argv: list[str]
    ) -> None:
        assert runner.invoke(app, argv).exit_code == 2
