"""Tests for JSON spec input helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cli.jsonio import SpecError, read_spec


class TestReadSpec:
    def test_none_returns_none(self) -> None:
        assert read_spec(None) is None

    def test_reads_file(self, tmp_path: Path) -> None:
        f = tmp_path / "spec.json"
        f.write_text('{"name": "test"}')
        result = read_spec(str(f))
        assert result == {"name": "test"}

    def test_reads_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO('{"key": "val"}'))
        result = read_spec("-")
        assert result == {"key": "val"}

    def test_missing_file_raises(self) -> None:
        with pytest.raises(SpecError, match="not found"):
            read_spec("/nonexistent/file.json")

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("not json")
        with pytest.raises(SpecError, match="Invalid JSON"):
            read_spec(str(f))

    def test_non_object_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "arr.json"
        f.write_text("[1, 2, 3]")
        with pytest.raises(SpecError, match="must be a JSON object"):
            read_spec(str(f))
