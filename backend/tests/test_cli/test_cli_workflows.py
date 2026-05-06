"""Tests for workflow commands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from app.cli.main import app
from tests.test_cli.conftest import make_envelope

_W = "app.cli.commands.workflow"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _wf(name: str = "nf-core/rnaseq", **kw) -> dict:
    return {
        "id": kw.get("id", "wf-001"),
        "name": name,
        "source": kw.get("source", "nf-core"),
        "engine": kw.get("engine", "nextflow"),
        "version": kw.get("version", "3.14.0"),
        "description": kw.get("description", ""),
        "source_ref": kw.get("source_ref", ""),
        "created_at": "2025-01-01T00:00:00Z",
    }


class TestWorkflowList:
    def test_lists_workflows(self, runner: CliRunner) -> None:
        resp = make_envelope([_wf("rnaseq"), _wf("sarek")])
        with patch(f"{_W}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(app, ["workflow", "list"])
        assert result.exit_code == 0
        assert "rnaseq" in result.stdout
        assert "sarek" in result.stdout

    def test_json_output(self, runner: CliRunner) -> None:
        resp = make_envelope([_wf()])
        with patch(f"{_W}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--output", "json", "workflow", "list"]
            )
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["success"] is True


class TestWorkflowRegister:
    def test_register_with_flags(self, runner: CliRunner) -> None:
        resp = make_envelope(_wf("my-wf"))
        with patch(f"{_W}.api_post", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app,
                [
                    "workflow",
                    "register",
                    "--source",
                    "local",
                    "--name",
                    "my-wf",
                ],
            )
        assert result.exit_code == 0
        assert "my-wf" in result.stdout


class TestWorkflowShow:
    def test_shows_detail(self, runner: CliRunner) -> None:
        resp = make_envelope(_wf("rnaseq", id="wf-42"))
        with patch(f"{_W}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["workflow", "show", "wf-42"]
            )
        assert result.exit_code == 0
        assert "rnaseq" in result.stdout


class TestWorkflowSource:
    def test_prints_source(self, runner: CliRunner) -> None:
        resp = make_envelope({"content": "nextflow.enable.dsl=2"})
        with patch(f"{_W}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["workflow", "source", "wf-42"]
            )
        assert result.exit_code == 0
        assert "nextflow" in result.stdout


class TestWorkflowBind:
    def test_bind_requires_project(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["workflow", "bind", "wf-42"])
        assert result.exit_code != 0

    def test_bind_with_project(self, runner: CliRunner) -> None:
        resp = make_envelope({"project_id": "p-1", "workflow_id": "wf-42"})
        with patch(f"{_W}.api_post", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app,
                ["--project", "p-1", "workflow", "bind", "wf-42"],
            )
        assert result.exit_code == 0
        assert "bound" in result.stdout


class TestWorkflowUnbind:
    def test_unbind(self, runner: CliRunner) -> None:
        resp = make_envelope(None)
        with patch(f"{_W}.api_delete", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app,
                ["--project", "p-1", "workflow", "unbind", "wf-42"],
            )
        assert result.exit_code == 0


class TestWorkflowPin:
    def test_pin(self, runner: CliRunner) -> None:
        resp = make_envelope({"project_id": "p-1", "pinned_workflow_id": "wf-42"})
        with patch(f"{_W}.api_post", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app,
                ["--project", "p-1", "workflow", "pin", "wf-42"],
            )
        assert result.exit_code == 0
        assert "pinned" in result.stdout
