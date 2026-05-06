"""Tests for file commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from app.cli.main import app
from tests.test_cli.conftest import make_envelope

_F = "app.cli.commands.file"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestFileLs:
    def test_lists_files(self, runner: CliRunner) -> None:
        resp = make_envelope(
            {
                "path": ".",
                "files": [
                    {"name": "data.fastq", "type": "file", "size_bytes": 1000},
                    {"name": "results", "type": "directory", "size_bytes": None},
                ],
            }
        )
        with patch(f"{_F}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--project", "p-1", "file", "ls"]
            )
        assert result.exit_code == 0
        assert "data.fastq" in result.stdout

    def test_requires_project(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["file", "ls"])
        assert result.exit_code != 0


class TestFileCat:
    def test_reads_file(self, runner: CliRunner) -> None:
        resp = make_envelope(
            {"content": "hello world\n", "total_lines": 1, "truncated": False}
        )
        with patch(f"{_F}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app,
                ["--project", "p-1", "file", "cat", "readme.txt"],
            )
        assert result.exit_code == 0
        assert "hello world" in result.stdout

    def test_json_output(self, runner: CliRunner) -> None:
        resp = make_envelope({"content": "data", "total_lines": 1, "truncated": False})
        with patch(f"{_F}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app,
                [
                    "--output",
                    "json",
                    "--project",
                    "p-1",
                    "file",
                    "cat",
                    "f.txt",
                ],
            )
        parsed = json.loads(result.stdout)
        assert parsed["data"]["content"] == "data"


class TestFileUpload:
    def test_upload(self, runner: CliRunner, tmp_path: Path) -> None:
        local = tmp_path / "test.txt"
        local.write_text("content")
        resp = make_envelope({"path": "test.txt", "size_bytes": 7})
        with patch(f"{_F}.api_upload", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app,
                ["--project", "p-1", "file", "upload", str(local)],
            )
        assert result.exit_code == 0
        assert "Uploaded" in result.stdout

    def test_upload_missing_file(self, runner: CliRunner) -> None:
        result = runner.invoke(
            app,
            ["--project", "p-1", "file", "upload", "/nonexistent"],
        )
        assert result.exit_code != 0


class TestFileScan:
    def test_scan_finds_samples(self, runner: CliRunner) -> None:
        resp = make_envelope(
            {
                "detected_samples": [
                    {"sample_id": "S1", "files": [{"type": "fastq", "path": "s1.fq"}]},
                ],
                "total_samples": 1,
            }
        )
        with patch(f"{_F}.api_post", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--project", "p-1", "file", "scan"]
            )
        assert result.exit_code == 0
        assert "S1" in result.stdout


class TestFileRm:
    def test_rm_with_force(self, runner: CliRunner) -> None:
        resp = make_envelope(None)
        with patch(f"{_F}.api_delete", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app,
                [
                    "--project",
                    "p-1",
                    "file",
                    "rm",
                    "old.txt",
                    "--force",
                ],
            )
        assert result.exit_code == 0
        assert "Deleted" in result.stdout
