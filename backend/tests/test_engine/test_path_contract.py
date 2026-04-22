"""Path Contract v3 — identity mount invariant tests."""

from __future__ import annotations

import pytest

from app import path_layout
from app.config import settings


def test_assert_identity_mount_passes_when_host_home_unset(monkeypatch):
    """Bare-metal backend (`uv run uvicorn`) has no host/container boundary,
    so an empty BIOINFOFLOW_HOME_HOST must skip the check."""
    monkeypatch.setattr(settings, "bioinfoflow_home_host", "")
    # Should not raise.
    path_layout.assert_identity_mount()


def test_assert_identity_mount_passes_when_host_equals_container(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    monkeypatch.setattr(settings, "bioinfoflow_home_host", str(tmp_path))
    # Should not raise.
    path_layout.assert_identity_mount()


def test_assert_identity_mount_fails_when_host_differs(monkeypatch, tmp_path):
    container_home = tmp_path / "container"
    container_home.mkdir()
    host_home = tmp_path / "host"
    host_home.mkdir()

    monkeypatch.setattr(settings, "bioinfoflow_home", str(container_home))
    monkeypatch.setattr(settings, "bioinfoflow_home_host", str(host_home))

    with pytest.raises(RuntimeError) as exc_info:
        path_layout.assert_identity_mount()

    message = str(exc_info.value)
    assert "Path Contract v3 violated" in message
    assert str(container_home) in message
    assert str(host_home) in message
    # Error message must include the compose fix hint.
    assert f"-v {container_home}:{container_home}" in message


def test_assert_identity_mount_tolerates_trailing_whitespace(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    monkeypatch.setattr(settings, "bioinfoflow_home_host", f"  {tmp_path}  ")
    # Should strip whitespace and pass.
    path_layout.assert_identity_mount()
