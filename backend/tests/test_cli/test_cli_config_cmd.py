"""Tests for config commands via CliRunner."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from app.cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def _patched_store(tmp_path, monkeypatch):
    """Point ConfigStore at a temp directory."""
    config_dir = tmp_path / "bioinfoflow"
    config_dir.mkdir()
    monkeypatch.setattr("app.cli.config_store._DEFAULT_CONFIG_DIR", config_dir)

    def _patched_init(self):
        self._dir = config_dir
        self._path = config_dir / "cli.toml"
        self._cache = None

    monkeypatch.setattr(
        "app.cli.commands.config_cmd.ConfigStore.__init__", _patched_init
    )
    return config_dir


class TestConfigInit:
    def test_init_human(self, runner: CliRunner, _patched_store) -> None:
        result = runner.invoke(app, ["--mode", "remote", "config", "init"])
        assert result.exit_code == 0
        assert "Config created" in result.stdout or "cli.toml" in result.stdout

    def test_init_json(self, runner: CliRunner, _patched_store) -> None:
        result = runner.invoke(
            app, ["--output", "json", "--mode", "remote", "config", "init"]
        )
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["success"] is True
        assert "path" in parsed["data"]


class TestConfigSet:
    def test_set_valid_key(self, runner: CliRunner, _patched_store) -> None:
        # Init first
        runner.invoke(app, ["--mode", "remote", "config", "init"])
        result = runner.invoke(
            app, ["--mode", "remote", "config", "set", "mode", "local"]
        )
        assert result.exit_code == 0
        assert "mode" in result.stdout

    def test_set_invalid_key(self, runner: CliRunner, _patched_store) -> None:
        runner.invoke(app, ["--mode", "remote", "config", "init"])
        result = runner.invoke(
            app, ["--mode", "remote", "config", "set", "invalid_key", "val"]
        )
        # Click usage error → exit code 2 (must NOT be repackaged as
        # `[UNEXPECTED] BadParameter` by handle_errors).
        assert result.exit_code == 2

    def test_set_json_output(self, runner: CliRunner, _patched_store) -> None:
        runner.invoke(app, ["--mode", "remote", "config", "init"])
        result = runner.invoke(
            app,
            ["--output", "json", "--mode", "remote", "config", "set", "output", "json"],
        )
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["data"]["output"] == "json"


class TestConfigGet:
    def test_get_unset_key(self, runner: CliRunner, _patched_store) -> None:
        runner.invoke(app, ["--mode", "remote", "config", "init"])
        result = runner.invoke(app, ["--mode", "remote", "config", "get", "project_id"])
        assert result.exit_code == 0
        # project_id has no default, so should show "not set"
        assert "not set" in result.stdout

    def test_get_set_key(self, runner: CliRunner, _patched_store) -> None:
        runner.invoke(app, ["--mode", "remote", "config", "init"])
        runner.invoke(app, ["--mode", "remote", "config", "set", "mode", "local"])
        result = runner.invoke(app, ["--mode", "remote", "config", "get", "mode"])
        assert result.exit_code == 0
        assert "local" in result.stdout

    def test_get_json(self, runner: CliRunner, _patched_store) -> None:
        runner.invoke(app, ["--mode", "remote", "config", "init"])
        result = runner.invoke(
            app, ["--output", "json", "--mode", "remote", "config", "get", "base_url"]
        )
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["success"] is True


class TestConfigShow:
    def test_show_empty(self, runner: CliRunner, _patched_store) -> None:
        runner.invoke(app, ["--mode", "remote", "config", "init"])
        result = runner.invoke(app, ["--mode", "remote", "config", "show"])
        assert result.exit_code == 0

    def test_show_with_data(self, runner: CliRunner, _patched_store) -> None:
        runner.invoke(app, ["--mode", "remote", "config", "init"])
        runner.invoke(app, ["--mode", "remote", "config", "set", "mode", "remote"])
        result = runner.invoke(app, ["--mode", "remote", "config", "show"])
        assert result.exit_code == 0
        assert "remote" in result.stdout

    def test_show_json(self, runner: CliRunner, _patched_store) -> None:
        runner.invoke(app, ["--mode", "remote", "config", "init"])
        runner.invoke(
            app, ["--mode", "remote", "config", "set", "base_url", "http://example.com"]
        )
        result = runner.invoke(
            app, ["--output", "json", "--mode", "remote", "config", "show"]
        )
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["success"] is True


class TestConfigSetValidation:
    def test_set_invalid_mode_value(
        self, runner: CliRunner, _patched_store
    ) -> None:
        runner.invoke(app, ["--mode", "remote", "config", "init"])
        result = runner.invoke(
            app, ["--mode", "remote", "config", "set", "mode", "magic"]
        )
        assert result.exit_code == 2

    def test_set_invalid_output_value(
        self, runner: CliRunner, _patched_store
    ) -> None:
        runner.invoke(app, ["--mode", "remote", "config", "init"])
        result = runner.invoke(
            app, ["--mode", "remote", "config", "set", "output", "xml"]
        )
        assert result.exit_code == 2


class TestConfigUnset:
    def test_unset_existing(self, runner: CliRunner, _patched_store) -> None:
        runner.invoke(app, ["--mode", "remote", "config", "init"])
        runner.invoke(app, ["--mode", "remote", "config", "set", "mode", "remote"])
        result = runner.invoke(app, ["--mode", "remote", "config", "unset", "mode"])
        assert result.exit_code == 0
        assert "Unset" in result.stdout

    def test_unset_missing(self, runner: CliRunner, _patched_store) -> None:
        runner.invoke(app, ["--mode", "remote", "config", "init"])
        result = runner.invoke(
            app, ["--mode", "remote", "config", "unset", "project_id"]
        )
        assert result.exit_code == 0
        assert "not set" in result.stdout

    def test_unset_invalid_key(self, runner: CliRunner, _patched_store) -> None:
        runner.invoke(app, ["--mode", "remote", "config", "init"])
        result = runner.invoke(
            app, ["--mode", "remote", "config", "unset", "bogus"]
        )
        assert result.exit_code != 0


class TestConfigUseProject:
    def test_use_project(self, runner: CliRunner, _patched_store) -> None:
        runner.invoke(app, ["--mode", "remote", "config", "init"])
        result = runner.invoke(
            app, ["--mode", "remote", "config", "use-project", "proj-123"]
        )
        assert result.exit_code == 0
        assert "proj-123" in result.stdout

    def test_use_project_json(self, runner: CliRunner, _patched_store) -> None:
        runner.invoke(app, ["--mode", "remote", "config", "init"])
        result = runner.invoke(
            app,
            [
                "--output",
                "json",
                "--mode",
                "remote",
                "config",
                "use-project",
                "proj-456",
            ],
        )
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["data"]["project_id"] == "proj-456"
