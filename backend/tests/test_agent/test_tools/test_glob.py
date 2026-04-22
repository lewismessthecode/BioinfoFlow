"""Tests for GlobTool."""

from __future__ import annotations

import time

import pytest
import pytest_asyncio

from app.services.agent.tools.file_tools import GlobTool


class TestGlobTool:
    """Tests for GlobTool."""

    @pytest_asyncio.fixture
    async def workspace(self, tmp_path):
        """Create a temporary workspace with test files."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create test files with slight mtime differences
        (workspace / "main.py").write_text("print('hello')\n")
        (workspace / "utils.py").write_text("def helper(): pass\n")
        (workspace / "config.yaml").write_text("key: value\n")
        (workspace / "README.md").write_text("# Readme\n")

        # Create subdirectory with files
        subdir = workspace / "src"
        subdir.mkdir()
        (subdir / "module.py").write_text("# module\n")
        (subdir / "data.csv").write_text("a,b,c\n")

        # Create nested subdirectory
        nested = subdir / "deep"
        nested.mkdir()
        (nested / "inner.py").write_text("# inner\n")

        return workspace

    @pytest.mark.asyncio
    async def test_glob_all_files(self, db_session, workspace) -> None:
        """Should find all files with **/* pattern."""
        tool = GlobTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="**/*")

        assert result.success is True
        assert result.data is not None
        assert result.data["total_matches"] == 7  # all files

    @pytest.mark.asyncio
    async def test_glob_python_files(self, db_session, workspace) -> None:
        """Should find only Python files."""
        tool = GlobTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="**/*.py")

        assert result.success is True
        paths = result.data["matches"]
        assert all(p.endswith(".py") for p in paths)
        assert result.data["total_matches"] == 4

    @pytest.mark.asyncio
    async def test_glob_top_level_only(self, db_session, workspace) -> None:
        """Should find only top-level files with *.py pattern."""
        tool = GlobTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="*.py")

        assert result.success is True
        paths = result.data["matches"]
        assert result.data["total_matches"] == 2
        for p in paths:
            assert "/" not in p  # top-level only

    @pytest.mark.asyncio
    async def test_glob_in_subdirectory(self, db_session, workspace) -> None:
        """Should find files in a specific subdirectory."""
        tool = GlobTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="src/**/*.py")

        assert result.success is True
        paths = result.data["matches"]
        assert all(p.startswith("src/") for p in paths)

    @pytest.mark.asyncio
    async def test_glob_no_matches(self, db_session, workspace) -> None:
        """Should succeed with zero matches."""
        tool = GlobTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="**/*.xyz")

        assert result.success is True
        assert result.data["total_matches"] == 0
        assert result.data["matches"] == []

    @pytest.mark.asyncio
    async def test_glob_empty_pattern_fails(self, db_session, workspace) -> None:
        """Should fail with empty pattern."""
        tool = GlobTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="")

        assert result.success is False
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_glob_path_escape_blocked(self, db_session, workspace) -> None:
        """Should block path traversal in pattern."""
        tool = GlobTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="../../../etc/*")

        assert result.success is False
        assert "escapes" in result.error.lower()

    @pytest.mark.asyncio
    async def test_glob_sorted_by_mtime(self, db_session, workspace) -> None:
        """Results should be sorted by modification time (newest first)."""
        # Touch files with different mtimes
        import os

        file1 = workspace / "old.txt"
        file1.write_text("old\n")
        old_time = time.time() - 100
        os.utime(file1, (old_time, old_time))

        file2 = workspace / "new.txt"
        file2.write_text("new\n")

        tool = GlobTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="*.txt")

        assert result.success is True
        paths = result.data["matches"]
        assert len(paths) == 2
        # Newest first
        assert paths[0] == "new.txt"
        assert paths[1] == "old.txt"

    @pytest.mark.asyncio
    async def test_glob_schema(self, db_session, workspace) -> None:
        """Should return valid schema."""
        tool = GlobTool(db_session, project_id="test", workspace_root=workspace)
        schema = tool.get_schema()

        assert "pattern" in schema
        assert schema["pattern"]["required"] is True

    @pytest.mark.asyncio
    async def test_glob_definition(self, db_session, workspace) -> None:
        """Should return valid tool definition."""
        tool = GlobTool(db_session, project_id="test", workspace_root=workspace)
        definition = tool.get_definition()

        assert definition["name"] == "glob"
        assert "description" in definition
        assert "args" in definition
