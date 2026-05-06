"""Tests for project commands via CliRunner + mocked ApiClient."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from app.cli.main import app
from tests.test_cli.conftest import make_envelope, make_project

_P = "app.cli.commands.project"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestProjectList:
    def test_human_output(self, runner: CliRunner) -> None:
        projects = [make_project(name="Alpha"), make_project(name="Beta")]
        resp = make_envelope(
            projects, pagination={"limit": 20, "has_more": False, "total_count": 2}
        )

        with patch(f"{_P}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(app, ["project", "list"])
        assert result.exit_code == 0
        assert "Alpha" in result.stdout
        assert "Beta" in result.stdout

    def test_json_output(self, runner: CliRunner) -> None:
        projects = [make_project(name="Gamma")]
        resp = make_envelope(projects)

        with patch(f"{_P}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--output", "json", "project", "list"]
            )
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["success"] is True
        assert len(parsed["data"]) == 1

    def test_empty_list(self, runner: CliRunner) -> None:
        resp = make_envelope([])

        with patch(f"{_P}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(app, ["project", "list"])
        assert result.exit_code == 0
        assert "No results" in result.stdout


class TestProjectCreate:
    def test_creates_project(self, runner: CliRunner) -> None:
        project = make_project(name="New One")
        resp = make_envelope(project)

        with patch(f"{_P}.api_post", new_callable=AsyncMock, return_value=resp) as mock_post:
            result = runner.invoke(
                app,
                [
                    "project",
                    "create",
                    "--name",
                    "New One",
                ],
            )
        assert result.exit_code == 0
        assert "New One" in result.stdout
        assert mock_post.call_args[0][2] == {"name": "New One"}


class TestProjectShow:
    def test_shows_detail(self, runner: CliRunner) -> None:
        project = make_project(id="p-123", name="Detail")
        resp = make_envelope(project)

        with patch(f"{_P}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["project", "show", "p-123"]
            )
        assert result.exit_code == 0
        assert "Detail" in result.stdout

    def test_json_output(self, runner: CliRunner) -> None:
        project = make_project(id="p-123")
        resp = make_envelope(project)

        with patch(f"{_P}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app,
                ["--output", "json", "project", "show", "p-123"],
            )
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["data"]["id"] == "p-123"


class TestProjectDelete:
    def test_delete_with_force(self, runner: CliRunner) -> None:
        resp = make_envelope(None)

        with patch(f"{_P}.api_delete", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["project", "delete", "p-123", "--force"]
            )
        assert result.exit_code == 0
        assert "deleted" in result.stdout


class TestProjectUse:
    def test_use_sets_default(self, runner: CliRunner, monkeypatch) -> None:
        from app.cli.config_store import ConfigStore

        monkeypatch.setattr(ConfigStore, "set", lambda self, k, v: None)

        project = make_project(id="p-999", name="MyProject")
        resp = make_envelope(project)
        with patch(f"{_P}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(app, ["project", "use", "p-999"])
        assert result.exit_code == 0
        assert "MyProject" in result.stdout


class TestProjectCreateDescription:
    def test_create_with_description(self, runner: CliRunner) -> None:
        project = make_project(name="Described")
        project["description"] = "A test project"
        resp = make_envelope(project)
        with patch(
            f"{_P}.api_post", new_callable=AsyncMock, return_value=resp
        ) as mock_post:
            result = runner.invoke(
                app,
                [
                    "project",
                    "create",
                    "--name",
                    "Described",
                    "--description",
                    "A test project",
                ],
            )
        assert result.exit_code == 0
        payload = mock_post.call_args[0][2]
        assert payload["description"] == "A test project"


class TestProjectListFilters:
    def test_list_with_cursor(self, runner: CliRunner) -> None:
        resp = make_envelope([make_project()])
        with patch(
            f"{_P}.api_get", new_callable=AsyncMock, return_value=resp
        ) as mock_get:
            result = runner.invoke(
                app, ["project", "list", "--cursor", "abc"]
            )
        assert result.exit_code == 0
        params = mock_get.call_args[0][2]
        assert params["cursor"] == "abc"

    def test_list_with_search(self, runner: CliRunner) -> None:
        resp = make_envelope([make_project()])
        with patch(
            f"{_P}.api_get", new_callable=AsyncMock, return_value=resp
        ) as mock_get:
            result = runner.invoke(
                app, ["project", "list", "--search", "viral"]
            )
        assert result.exit_code == 0
        params = mock_get.call_args[0][2]
        assert params["search"] == "viral"
