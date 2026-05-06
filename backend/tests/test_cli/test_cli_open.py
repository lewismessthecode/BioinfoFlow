"""Tests for `bif open` — frontend URL launcher."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from app.cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def _no_config(tmp_path, monkeypatch):
    """Point ConfigStore at a temp dir so tests don't read user state."""
    cfg = tmp_path / "bioinfoflow"
    cfg.mkdir()
    monkeypatch.setattr("app.cli.config_store._DEFAULT_CONFIG_DIR", cfg)
    monkeypatch.delenv("BIOFLOW_WEB_URL", raising=False)


class TestOpenRun:
    def test_opens_run_with_default_root(
        self, runner: CliRunner, _no_config
    ) -> None:
        with patch("webbrowser.open", return_value=True) as mock_open:
            result = runner.invoke(
                app, ["open", "run", "r-42"]
            )
        assert result.exit_code == 0
        mock_open.assert_called_once_with("http://localhost:3000/runs/r-42")

    def test_no_browser_prints_url(self, runner: CliRunner, _no_config) -> None:
        with patch("webbrowser.open") as mock_open:
            result = runner.invoke(
                app,
                ["open", "run", "r-42", "--no-browser"],
            )
        assert result.exit_code == 0
        assert "http://localhost:3000/runs/r-42" in result.stdout
        mock_open.assert_not_called()

    def test_web_url_flag_overrides_default(
        self, runner: CliRunner, _no_config
    ) -> None:
        with patch("webbrowser.open", return_value=True) as mock_open:
            result = runner.invoke(
                app,
                [
                    "open",
                    "run",
                    "r-42",
                    "--web-url",
                    "https://bioinfoflow.example.com",
                ],
            )
        assert result.exit_code == 0
        mock_open.assert_called_once_with(
            "https://bioinfoflow.example.com/runs/r-42"
        )

    def test_env_var_overrides_default(
        self, runner: CliRunner, _no_config, monkeypatch
    ) -> None:
        monkeypatch.setenv("BIOFLOW_WEB_URL", "https://bf.example.com:8443/app")
        with patch("webbrowser.open", return_value=True) as mock_open:
            result = runner.invoke(
                app, ["open", "run", "r-42"]
            )
        assert result.exit_code == 0
        mock_open.assert_called_once_with(
            "https://bf.example.com:8443/app/runs/r-42"
        )

    def test_strips_trailing_slash(self, runner: CliRunner, _no_config) -> None:
        with patch("webbrowser.open", return_value=True) as mock_open:
            result = runner.invoke(
                app,
                [
                    "open",
                    "run",
                    "r-42",
                    "--web-url",
                    "http://localhost:3000/",
                ],
            )
        assert result.exit_code == 0
        mock_open.assert_called_once_with("http://localhost:3000/runs/r-42")

    def test_invalid_web_url_exits_2(
        self, runner: CliRunner, _no_config
    ) -> None:
        result = runner.invoke(
            app,
            [
                "open",
                "run",
                "r-42",
                "--web-url",
                "ftp://nope",
            ],
        )
        assert result.exit_code == 2

    def test_browser_open_failure_falls_back_to_message(
        self, runner: CliRunner, _no_config
    ) -> None:
        with patch("webbrowser.open", return_value=False):
            result = runner.invoke(
                app, ["open", "run", "r-42"]
            )
        # webbrowser.open returning False is benign — we surface the URL.
        assert result.exit_code == 0
        assert "http://localhost:3000/runs/r-42" in result.stdout


class TestOpenWorkflow:
    def test_opens_workflow(self, runner: CliRunner, _no_config) -> None:
        with patch("webbrowser.open", return_value=True) as mock_open:
            result = runner.invoke(
                app,
                ["open", "workflow", "wf-7", "--no-browser"],
            )
        assert result.exit_code == 0
        assert "http://localhost:3000/workflows/wf-7" in result.stdout
        mock_open.assert_not_called()


class TestOpenStaticPages:
    @pytest.mark.parametrize(
        "subcommand,suffix",
        [
            ("dashboard", "dashboard"),
            ("agent", "agent"),
            ("scheduler", "scheduler"),
        ],
    )
    def test_opens(
        self, runner: CliRunner, _no_config, subcommand: str, suffix: str
    ) -> None:
        with patch("webbrowser.open", return_value=True) as mock_open:
            result = runner.invoke(
                app, ["open", subcommand]
            )
        assert result.exit_code == 0
        mock_open.assert_called_once_with(f"http://localhost:3000/{suffix}")


class TestOpenJsonOutput:
    def test_emits_envelope_and_skips_browser_text(
        self, runner: CliRunner, _no_config
    ) -> None:
        with patch("webbrowser.open", return_value=True) as mock_open:
            result = runner.invoke(
                app,
                [
                    "--output",
                    "json",
                    "open",
                    "run",
                    "r-42",
                    "--no-browser",
                ],
            )
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["success"] is True
        assert parsed["data"]["kind"] == "run"
        assert parsed["data"]["url"] == "http://localhost:3000/runs/r-42"
        assert parsed["data"]["opened"] is False
        mock_open.assert_not_called()


class TestOpenConfigKey:
    def test_web_url_is_a_valid_config_key(
        self, runner: CliRunner, tmp_path, monkeypatch
    ) -> None:
        cfg = tmp_path / "bioinfoflow"
        cfg.mkdir()
        monkeypatch.setattr("app.cli.config_store._DEFAULT_CONFIG_DIR", cfg)

        def _patched_init(self):
            self._dir = cfg
            self._path = cfg / "cli.toml"
            self._cache = None

        monkeypatch.setattr(
            "app.cli.commands.config_cmd.ConfigStore.__init__", _patched_init
        )
        monkeypatch.setattr(
            "app.cli.commands.open_cmd.ConfigStore.__init__", _patched_init
        )
        monkeypatch.delenv("BIOFLOW_WEB_URL", raising=False)

        runner.invoke(app, ["config", "init"])
        result = runner.invoke(
            app,
            [
                "config",
                "set",
                "web_url",
                "https://configured.example.com",
            ],
        )
        assert result.exit_code == 0

        with patch("webbrowser.open", return_value=True) as mock_open:
            result = runner.invoke(
                app, ["open", "dashboard"]
            )
        assert result.exit_code == 0
        mock_open.assert_called_once_with(
            "https://configured.example.com/dashboard"
        )
