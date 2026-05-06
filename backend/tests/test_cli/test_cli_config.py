"""Tests for CLI config store and resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cli.config_store import ConfigStore


class TestConfigStore:
    def test_init_creates_dir_and_file(self, tmp_path: Path) -> None:
        store = ConfigStore(config_dir=tmp_path / "cfg")
        store.init()
        assert store.path.exists()
        # Defaults written
        data = store.load()
        assert "mode" not in data
        assert "base_url" in data

    def test_init_idempotent(self, tmp_path: Path) -> None:
        store = ConfigStore(config_dir=tmp_path / "cfg")
        store.init()
        store.set("base_url", "http://example.com/api/v1")
        store.init()  # should NOT overwrite
        assert store.get("base_url") == "http://example.com/api/v1"

    def test_set_and_get(self, tmp_path: Path) -> None:
        store = ConfigStore(config_dir=tmp_path / "cfg")
        store.init()
        store.set("project_id", "abc-123")
        assert store.get("project_id") == "abc-123"

    def test_get_missing_key(self, tmp_path: Path) -> None:
        store = ConfigStore(config_dir=tmp_path / "cfg")
        store.init()
        assert store.get("nonexistent") is None

    def test_load_missing_file(self, tmp_path: Path) -> None:
        store = ConfigStore(config_dir=tmp_path / "no_such_dir")
        assert store.load() == {}

    def test_resolve_priority_cli_first(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = ConfigStore(config_dir=tmp_path / "cfg")
        store.init()
        store.set("base_url", "http://config.example/api/v1")
        monkeypatch.setenv("BIOFLOW_API_URL", "http://env.example/api/v1")
        assert (
            store.resolve(
                "base_url",
                "http://cli.example/api/v1",
                "BIOFLOW_API_URL",
            )
            == "http://cli.example/api/v1"
        )

    def test_resolve_priority_env_second(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = ConfigStore(config_dir=tmp_path / "cfg")
        store.init()
        store.set("base_url", "http://config.example/api/v1")
        monkeypatch.setenv("BIOFLOW_API_URL", "http://env.example/api/v1")
        assert (
            store.resolve("base_url", None, "BIOFLOW_API_URL")
            == "http://env.example/api/v1"
        )

    def test_resolve_priority_config_third(self, tmp_path: Path) -> None:
        store = ConfigStore(config_dir=tmp_path / "cfg")
        store.init()
        store.set("base_url", "http://config.example/api/v1")
        # No env var, no CLI flag
        assert (
            store.resolve("base_url", None, "BIOFLOW_API_URL_NOT_SET")
            == "http://config.example/api/v1"
        )

    def test_resolve_falls_to_default(self, tmp_path: Path) -> None:
        store = ConfigStore(config_dir=tmp_path / "empty")
        # No file, no env, no CLI → default
        assert (
            store.resolve("base_url", None, "BIOFLOW_API_URL_NOT_SET")
            == "http://localhost:8000/api/v1"
        )

    def test_file_permissions(self, tmp_path: Path) -> None:
        store = ConfigStore(config_dir=tmp_path / "cfg")
        store.init()
        stat = store.path.stat()
        assert oct(stat.st_mode)[-3:] == "600"

    def test_unset_existing_key(self, tmp_path: Path) -> None:
        store = ConfigStore(config_dir=tmp_path / "cfg")
        store.init()
        store.set("project_id", "p-1")
        assert store.unset("project_id") is True
        assert store.get("project_id") is None

    def test_unset_missing_key(self, tmp_path: Path) -> None:
        store = ConfigStore(config_dir=tmp_path / "cfg")
        store.init()
        assert store.unset("project_id") is False
