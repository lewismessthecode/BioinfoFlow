"""Tests for SBPL profile injection prevention in CodeSandbox."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.agent.tools.sandbox import CodeSandbox


class TestSbplSanitization:
    def test_sanitize_rejects_double_quotes(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            CodeSandbox._sanitize_sbpl_path('/tmp/workspace"injection')

    def test_sanitize_rejects_single_quotes(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            CodeSandbox._sanitize_sbpl_path("/tmp/workspace'injection")

    def test_sanitize_rejects_parentheses(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            CodeSandbox._sanitize_sbpl_path("/tmp/workspace(injection)")

    def test_sanitize_rejects_semicolons(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            CodeSandbox._sanitize_sbpl_path("/tmp/workspace;injection")

    def test_sanitize_rejects_backslashes(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            CodeSandbox._sanitize_sbpl_path("/tmp/workspace\\injection")

    def test_sanitize_allows_normal_path(self):
        result = CodeSandbox._sanitize_sbpl_path("/home/user/workspace")
        assert result == "/home/user/workspace"

    def test_sanitize_allows_path_with_dashes_and_dots(self):
        result = CodeSandbox._sanitize_sbpl_path("/home/user/my-project.v2")
        assert result == "/home/user/my-project.v2"

    @pytest.mark.asyncio
    async def test_execute_macos_rejects_unsafe_workspace(self, tmp_path: Path):
        """_execute_macos must raise ValueError for unsafe workspace paths."""
        unsafe_path = tmp_path / 'bad"path'
        # We don't need the directory to exist; the check happens before execution
        sandbox = CodeSandbox(workspace_root=unsafe_path, enabled=True)

        script = tmp_path / "test.py"
        script.write_text("print('hello')")

        result = await sandbox._execute_macos(script, timeout=5)
        # The error should be caught and returned as an ExecutionResult
        assert result.exit_code == -1
        assert (
            "unsafe characters" in result.stderr
            or "Sandbox execution error" in result.stderr
        )
