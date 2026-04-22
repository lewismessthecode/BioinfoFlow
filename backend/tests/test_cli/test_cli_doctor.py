"""Tests for doctor command."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from app.cli.client import ApiError, ApiResponse, ConnectionFailed
from app.cli.main import app
from tests.test_cli.conftest import make_envelope


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _health_resp() -> ApiResponse:
    return make_envelope({"status": "healthy"})


def _scheduler_resp() -> ApiResponse:
    return make_envelope({"mode": "persistent", "queue_depth": 3})


def _gpu_resp() -> ApiResponse:
    return make_envelope({"available": True})


class TestDoctorHuman:
    def test_all_pass(self, runner: CliRunner) -> None:
        with patch("app.cli.commands.doctor._run_checks") as mock_checks:
            mock_checks.return_value = {
                "backend": {"ok": True, "detail": "healthy"},
                "scheduler": {"ok": True, "detail": "mode=persistent, queue=3"},
                "gpu": {"ok": True, "detail": "available"},
                "nextflow": {"ok": True, "detail": "/usr/bin/nextflow"},
                "docker": {"ok": True, "detail": "/usr/bin/docker"},
            }
            result = runner.invoke(app, ["--mode", "remote", "doctor"])
        assert result.exit_code == 0
        assert "All checks passed" in result.stdout

    def test_with_failures(self, runner: CliRunner) -> None:
        with patch("app.cli.commands.doctor._run_checks") as mock_checks:
            mock_checks.return_value = {
                "backend": {"ok": True, "detail": "healthy"},
                "scheduler": {"ok": False, "detail": "not reachable"},
                "gpu": {"ok": True, "detail": "not detected"},
                "nextflow": {"ok": False, "detail": "not found in PATH"},
            }
            result = runner.invoke(app, ["--mode", "remote", "doctor"])
        assert result.exit_code == 0
        assert "Issues detected" in result.stdout

    def test_json_output(self, runner: CliRunner) -> None:
        with patch("app.cli.commands.doctor._run_checks") as mock_checks:
            mock_checks.return_value = {
                "backend": {"ok": True, "detail": "healthy"},
                "scheduler": {"ok": True, "detail": "persistent"},
            }
            result = runner.invoke(
                app, ["--output", "json", "--mode", "remote", "doctor"]
            )
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["success"] is True
        assert parsed["data"]["backend"]["ok"] is True


class TestRunChecks:
    """Test the _run_checks function directly."""

    @pytest.mark.asyncio
    async def test_backend_healthy(self) -> None:
        from app.cli.commands.doctor import _run_checks

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=[_health_resp(), _scheduler_resp(), _gpu_resp()]
        )
        mock_client.close = AsyncMock()

        from app.cli.context import CliContext
        from rich.console import Console

        ctx = CliContext(
            client=mock_client,
            output_mode="human",
            project_id=None,
            verbose=False,
            console=Console(),
        )
        with patch("shutil.which", return_value="/usr/bin/nextflow"):
            results = await _run_checks(ctx)
        assert results["backend"]["ok"] is True
        assert results["nextflow"]["ok"] is True

    @pytest.mark.asyncio
    async def test_backend_connection_failed(self) -> None:
        from app.cli.commands.doctor import _run_checks

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=ConnectionFailed("refused"))
        mock_client.close = AsyncMock()

        from app.cli.context import CliContext
        from rich.console import Console

        ctx = CliContext(
            client=mock_client,
            output_mode="human",
            project_id=None,
            verbose=False,
            console=Console(),
        )
        with patch("shutil.which", return_value=None):
            results = await _run_checks(ctx)
        assert results["backend"]["ok"] is False
        assert "Cannot connect" in results["backend"]["detail"]

    @pytest.mark.asyncio
    async def test_backend_api_error(self) -> None:
        from app.cli.commands.doctor import _run_checks

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=ApiError(code="ERR", message="broken", status_code=500)
        )
        mock_client.close = AsyncMock()

        from app.cli.context import CliContext
        from rich.console import Console

        ctx = CliContext(
            client=mock_client,
            output_mode="human",
            project_id=None,
            verbose=False,
            console=Console(),
        )
        with patch("shutil.which", return_value=None):
            results = await _run_checks(ctx)
        assert results["backend"]["ok"] is False
        assert "broken" in results["backend"]["detail"]

    @pytest.mark.asyncio
    async def test_scheduler_connection_failed(self) -> None:
        from app.cli.commands.doctor import _run_checks

        mock_client = AsyncMock()
        # Backend OK, scheduler fails, GPU fails
        mock_client.get = AsyncMock(
            side_effect=[
                _health_resp(),
                ConnectionFailed("refused"),
                ConnectionFailed("refused"),
            ]
        )
        mock_client.close = AsyncMock()

        from app.cli.context import CliContext
        from rich.console import Console

        ctx = CliContext(
            client=mock_client,
            output_mode="human",
            project_id=None,
            verbose=False,
            console=Console(),
        )
        with patch("shutil.which", return_value=None):
            results = await _run_checks(ctx)
        assert results["backend"]["ok"] is True
        assert results["scheduler"]["ok"] is False
        assert "not reachable" in results["scheduler"]["detail"]
