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


def _readiness_resp() -> ApiResponse:
    return make_envelope(
        {
            "severity": "blocked",
            "next_action": {
                "label": "Configure providers",
                "href": "/settings?section=providers",
            },
            "checks": [
                {
                    "id": "backend",
                    "status": "pass",
                    "facts": {"available": True},
                },
                {
                    "id": "provider_key",
                    "status": "fail",
                    "facts": {"configured": False},
                },
            ],
        }
    )


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
            result = runner.invoke(app, ["doctor"])
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
            result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "Issues detected" in result.stdout

    def test_skipped_checks_are_reported_separately(self, runner: CliRunner) -> None:
        with patch("app.cli.commands.doctor._run_checks") as mock_checks:
            mock_checks.return_value = {
                "backend": {
                    "ok": False,
                    "status": "fail",
                    "detail": "Cannot connect to backend",
                    "hint": "Start backend: uv run uvicorn app.main:app --reload --reload-dir app --port 8000",
                },
                "scheduler": {
                    "ok": True,
                    "status": "skip",
                    "detail": "requires backend",
                },
                "gpu": {
                    "ok": True,
                    "status": "skip",
                    "detail": "requires backend",
                },
                "nextflow": {"ok": True, "status": "pass", "detail": "/usr/bin/nextflow"},
            }
            result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "skip" in result.stdout
        assert "Skipped checks: scheduler, gpu" in result.stdout
        assert "Start backend: uv run uvicorn" in result.stdout

    def test_json_output(self, runner: CliRunner) -> None:
        with patch("app.cli.commands.doctor._run_checks") as mock_checks:
            mock_checks.return_value = {
                "backend": {"ok": True, "detail": "healthy"},
                "scheduler": {"ok": True, "detail": "persistent"},
            }
            result = runner.invoke(
                app, ["--output", "json", "doctor"]
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
            side_effect=[_readiness_resp()]
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
        assert results["provider_key"]["ok"] is False
        assert results["provider_key"]["hint"].startswith("Configure a supported AI provider")
        assert results["nextflow"]["ok"] is True

    @pytest.mark.asyncio
    async def test_falls_back_when_readiness_endpoint_is_missing(self) -> None:
        from app.cli.commands.doctor import _run_checks

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=[
                ApiError(
                    code="NOT_FOUND",
                    message="not found",
                    status_code=404,
                ),
                _health_resp(),
                _scheduler_resp(),
                _gpu_resp(),
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
        with patch("shutil.which", return_value="/usr/bin/nextflow"):
            results = await _run_checks(ctx)
        assert results["backend"]["ok"] is True
        assert results["scheduler"]["ok"] is True
        assert results["gpu"]["ok"] is True

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
        assert results["backend"]["status"] == "fail"
        assert "Cannot connect" in results["backend"]["detail"]
        assert (
            "uv run uvicorn app.main:app --reload --reload-dir app --port 8000"
            in results["backend"]["hint"]
        )
        assert results["scheduler"]["ok"] is True
        assert results["scheduler"]["status"] == "skip"
        assert results["scheduler"]["detail"] == "requires backend"

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
        assert results["backend"]["status"] == "fail"
        assert "broken" in results["backend"]["detail"]
        assert results["scheduler"]["ok"] is True
        assert results["scheduler"]["status"] == "skip"
        assert results["scheduler"]["detail"] == "requires backend"

    @pytest.mark.asyncio
    async def test_scheduler_connection_failed(self) -> None:
        from app.cli.commands.doctor import _run_checks

        mock_client = AsyncMock()
        # Backend OK, scheduler fails, GPU fails
        mock_client.get = AsyncMock(
            side_effect=[
                ApiError(code="NOT_FOUND", message="not found", status_code=404),
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
