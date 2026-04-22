"""Shared fixtures for CLI tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from app.cli.client import ApiResponse


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def tmp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Provide a temporary config directory, patching ConfigStore default."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr("app.cli.config_store._DEFAULT_CONFIG_DIR", config_dir)

    def _patched_init(self, config_dir=None):
        self._dir = config_dir or tmp_path / "config"
        self._path = self._dir / "cli.toml"
        self._cache = None

    monkeypatch.setattr("app.cli.main.ConfigStore.__init__", _patched_init)
    return config_dir


def make_envelope(
    data: Any,
    pagination: dict[str, Any] | None = None,
) -> ApiResponse:
    """Build a valid API response for testing."""
    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": str(uuid4()),
    }
    if pagination:
        meta["pagination"] = pagination
    return ApiResponse(
        success=True,
        data=data,
        error=None,
        meta=meta,
        status_code=200,
    )


def make_error(
    code: str,
    message: str,
    status_code: int = 400,
) -> ApiResponse:
    """Build an error response for testing."""
    return ApiResponse(
        success=False,
        data=None,
        error={"code": code, "message": message},
        meta={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": str(uuid4()),
        },
        status_code=status_code,
    )


def make_project(
    id: str | None = None,
    name: str = "Test Project",
    workspace: str = "/tmp/test",
) -> dict[str, Any]:
    """Build a project dict for testing."""
    return {
        "id": id or str(uuid4()),
        "name": name,
        "workspace": workspace,
        "description": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
