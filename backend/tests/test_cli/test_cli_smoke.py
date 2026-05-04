"""Smoke tests — bif --help, subcommand --help, and basic flag validation."""

from __future__ import annotations


import pytest
from typer.testing import CliRunner

from app.cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestHelp:
    def test_root_help(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Bioinfoflow CLI" in result.stdout
        for cmd in [
            "project",
            "workflow",
            "run",
            "file",
            "agent",
            "system",
            "events",
            "doctor",
            "config",
            "open",
        ]:
            assert cmd in result.stdout

    def test_project_help(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["project", "--help"])
        assert result.exit_code == 0
        assert "list" in result.stdout
        assert "create" in result.stdout
        assert "show" in result.stdout
        assert "delete" in result.stdout

    def test_config_help(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        assert "init" in result.stdout
        assert "set" in result.stdout
        assert "get" in result.stdout
        assert "show" in result.stdout

    def test_run_help(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        for sub in [
            "list",
            "submit",
            "show",
            "watch",
            "logs",
            "cancel",
            "retry",
            "resume",
        ]:
            assert sub in result.stdout

    def test_agent_help(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["agent", "--help"])
        assert result.exit_code == 0
        for sub in ["send", "chat", "history", "status", "cancel", "trace"]:
            assert sub in result.stdout


class TestFlagValidation:
    def test_invalid_output_mode(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--output", "xml", "project", "list"])
        assert result.exit_code == 2

    def test_invalid_transport_mode(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--mode", "magic", "project", "list"])
        assert result.exit_code == 2


class TestNoArgsShowsHelp:
    def test_no_args(self, runner: CliRunner) -> None:
        result = runner.invoke(app, [])
        # Typer returns exit code 0 for help display with no_args_is_help
        assert result.exit_code in (0, 2)
        assert "Usage" in result.stdout or "Bioinfoflow" in result.stdout


class TestVersion:
    def test_version_long(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "bif" in result.stdout

    def test_version_short(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0
        assert "bif" in result.stdout


class TestShortFlags:
    def test_short_help(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["-h"])
        assert result.exit_code == 0
        assert "Usage" in result.stdout

    def test_short_project_flag(self, runner: CliRunner) -> None:
        # -p is the short for --project at the root level. Just verify
        # that it's accepted (will fail downstream without auth/server,
        # but the parser must recognise it).
        result = runner.invoke(app, ["-p", "p-x", "--help"])
        assert result.exit_code == 0
