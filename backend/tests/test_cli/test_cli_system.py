"""Tests for system commands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from app.cli.main import app
from tests.test_cli.conftest import make_envelope

_S = "app.cli.commands.system"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestSystemHealth:
    def test_health(self, runner: CliRunner) -> None:
        resp = make_envelope(
            {
                "status": "healthy",
                "docker": {"available": True, "nvidia_runtime": False},
                "gpu": {"available": False, "parabricks_compatible": False},
                "parabricks": {"image_available": False, "image_name": None},
            }
        )
        with patch(f"{_S}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(app, ["system", "health"])
        assert result.exit_code == 0
        assert "healthy" in result.stdout


class TestSystemStats:
    def test_stats(self, runner: CliRunner) -> None:
        resp = make_envelope(
            {
                "runs": {
                    "total": 10,
                    "running": 2,
                    "completed": 7,
                    "failed": 1,
                    "queued": 0,
                },
                "workflows": {"total": 3},
                "projects": {"total": 2},
            }
        )
        with patch(f"{_S}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(app, ["system", "stats"])
        assert result.exit_code == 0
        assert "10" in result.stdout

    def test_json_output(self, runner: CliRunner) -> None:
        resp = make_envelope(
            {"runs": {"total": 5}, "workflows": {"total": 1}, "projects": {"total": 1}}
        )
        with patch(f"{_S}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--output", "json", "system", "stats"]
            )
        parsed = json.loads(result.stdout)
        assert parsed["data"]["runs"]["total"] == 5


class TestSchedulerStatus:
    def test_status(self, runner: CliRunner) -> None:
        resp = make_envelope(
            {
                "mode": "persistent",
                "effective_mode": "persistent",
                "scheduler_available": True,
                "resource_monitoring_enabled": True,
                "workers": 4,
                "queue_depth": 2,
            }
        )
        with patch(f"{_S}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["system", "scheduler-status"]
            )
        assert result.exit_code == 0
        assert "persistent" in result.stdout


class TestSchedulerResources:
    def test_resources(self, runner: CliRunner) -> None:
        resp = make_envelope(
            {
                "mode": "persistent",
                "enabled": True,
                "sampled_at": "2025-01-01T00:00:00Z",
                "cpu": {"total": 8, "available": 6},
                "memory": {"total_gb": 32, "available_gb": 24},
                "disk": {"total_gb": 500, "available_gb": 300},
            }
        )
        with patch(f"{_S}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["system", "scheduler-resources"]
            )
        assert result.exit_code == 0
        assert "6/8" in result.stdout


class TestGpu:
    def test_gpu(self, runner: CliRunner) -> None:
        resp = make_envelope(
            {
                "available": False,
                "nvidia_smi_found": False,
                "docker_nvidia_runtime": False,
                "parabricks_compatible": False,
                "recommendation": "Install NVIDIA drivers",
                "gpus": [],
            }
        )
        with patch(f"{_S}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(app, ["system", "gpu"])
        assert result.exit_code == 0
        assert "Install NVIDIA" in result.stdout
