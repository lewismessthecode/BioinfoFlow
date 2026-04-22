"""Tests for file operation tools."""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.services.agent.tools.file_tools import (
    FileEditTool,
    FileReadTool,
    FileWriteTool,
    _is_path_blocked,
)


class TestIsPathBlocked:
    """Tests for path blocking logic."""

    def test_git_directory_blocked(self) -> None:
        assert _is_path_blocked(".git/config") is True
        assert _is_path_blocked(".git/objects/abc") is True
        assert _is_path_blocked("subdir/.git/HEAD") is True

    def test_pyc_blocked(self) -> None:
        assert _is_path_blocked("module.pyc") is True
        assert _is_path_blocked("dir/file.pyc") is True

    def test_pycache_blocked(self) -> None:
        assert _is_path_blocked("__pycache__/module.cpython-311.pyc") is True

    def test_env_blocked(self) -> None:
        assert _is_path_blocked(".env") is True
        assert _is_path_blocked(".env.local") is True
        assert _is_path_blocked(".env.production") is True

    def test_normal_paths_allowed(self) -> None:
        assert _is_path_blocked("config.yaml") is False
        assert _is_path_blocked("src/main.py") is False
        assert _is_path_blocked("data/samples.csv") is False


class TestFileReadTool:
    """Tests for FileReadTool."""

    @pytest_asyncio.fixture
    async def workspace(self, tmp_path):
        """Create a temporary workspace with test files."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create test files
        (workspace / "test.txt").write_text("line 1\nline 2\nline 3\nline 4\nline 5\n")
        (workspace / "empty.txt").write_text("")
        (workspace / "binary.bin").write_bytes(b"\x00\x01\x02\x03")
        (workspace / "large.txt").write_text("x" * (60 * 1024))  # 60KB - too large

        subdir = workspace / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("nested content\n")

        return workspace

    @pytest.mark.asyncio
    async def test_file_read_success(self, db_session, workspace) -> None:
        tool = FileReadTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(path="test.txt")

        assert result.success is True
        assert result.data is not None
        assert result.data["path"] == "test.txt"
        assert result.data["total_lines"] == 5
        assert "line 1" in result.data["content"]
        assert result.data["truncated"] is False

    @pytest.mark.asyncio
    async def test_file_read_with_offset_limit(self, db_session, workspace) -> None:
        tool = FileReadTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(path="test.txt", offset=1, limit=2)

        assert result.success is True
        assert result.data is not None
        assert result.data["offset"] == 1
        assert result.data["limit"] == 2
        # Should contain lines 2 and 3 (0-indexed offset=1)
        assert "line 2" in result.data["content"]
        assert "line 3" in result.data["content"]
        assert result.data["truncated"] is True  # More lines exist

    @pytest.mark.asyncio
    async def test_file_read_binary_rejected(self, db_session, workspace) -> None:
        tool = FileReadTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(path="binary.bin")

        assert result.success is False
        assert "binary" in result.error.lower()

    @pytest.mark.asyncio
    async def test_file_read_path_escape_blocked(self, db_session, workspace) -> None:
        tool = FileReadTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(path="../../../etc/passwd")

        assert result.success is False
        assert "escapes" in result.error.lower()

    @pytest.mark.asyncio
    async def test_file_read_nonexistent_file(self, db_session, workspace) -> None:
        tool = FileReadTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(path="nonexistent.txt")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_file_read_nested_path(self, db_session, workspace) -> None:
        tool = FileReadTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(path="subdir/nested.txt")

        assert result.success is True
        assert "nested content" in result.data["content"]

    @pytest.mark.asyncio
    async def test_file_read_too_large(self, db_session, workspace) -> None:
        tool = FileReadTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(path="large.txt")

        assert result.success is False
        assert "too large" in result.error.lower()


class TestFileWriteTool:
    """Tests for FileWriteTool."""

    @pytest_asyncio.fixture
    async def workspace(self, tmp_path):
        """Create a temporary workspace."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "existing.txt").write_text("original content\n")
        return workspace

    @pytest.mark.asyncio
    async def test_file_write_create_new(self, db_session, workspace) -> None:
        tool = FileWriteTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(path="new_file.txt", content="hello world\n")

        assert result.success is True
        assert result.data["created"] is True
        assert result.data["overwritten"] is False
        assert (workspace / "new_file.txt").read_text() == "hello world\n"

    @pytest.mark.asyncio
    async def test_file_write_create_with_dirs(self, db_session, workspace) -> None:
        tool = FileWriteTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(
            path="deep/nested/dir/file.txt",
            content="deep content\n",
            create_dirs=True,
        )

        assert result.success is True
        assert (workspace / "deep" / "nested" / "dir" / "file.txt").exists()

    @pytest.mark.asyncio
    async def test_file_write_overwrite_protection(self, db_session, workspace) -> None:
        tool = FileWriteTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(path="existing.txt", content="new content\n")

        assert result.success is False
        assert "already exists" in result.error.lower()
        # Original content unchanged
        assert (workspace / "existing.txt").read_text() == "original content\n"

    @pytest.mark.asyncio
    async def test_file_write_overwrite_explicit(self, db_session, workspace) -> None:
        tool = FileWriteTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(
            path="existing.txt",
            content="new content\n",
            overwrite=True,
        )

        assert result.success is True
        assert result.data["overwritten"] is True
        assert (workspace / "existing.txt").read_text() == "new content\n"

    @pytest.mark.asyncio
    async def test_file_write_blocked_path_git(self, db_session, workspace) -> None:
        tool = FileWriteTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(path=".git/config", content="bad config\n")

        assert result.success is False
        assert "not allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_file_write_blocked_path_env(self, db_session, workspace) -> None:
        tool = FileWriteTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(path=".env", content="SECRET=bad\n")

        assert result.success is False
        assert "not allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_file_write_size_limit(self, db_session, workspace) -> None:
        tool = FileWriteTool(db_session, project_id="test", workspace_root=workspace)
        large_content = "x" * (2 * 1024 * 1024)  # 2MB
        result = await tool.execute(path="large.txt", content=large_content)

        assert result.success is False
        assert "too large" in result.error.lower()


class TestFileEditTool:
    """Tests for FileEditTool."""

    @pytest_asyncio.fixture
    async def workspace(self, tmp_path):
        """Create a temporary workspace with test files."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "config.yaml").write_text("max_memory: 32GB\nmax_cpu: 8\n")
        (workspace / "repeated.txt").write_text("foo foo foo\n")
        return workspace

    @pytest.mark.asyncio
    async def test_file_edit_single_replacement(self, db_session, workspace) -> None:
        tool = FileEditTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(
            path="config.yaml",
            old_content="32GB",
            new_content="64GB",
        )

        assert result.success is True
        assert result.data["replacements"] == 1
        assert "64GB" in (workspace / "config.yaml").read_text()
        assert result.data["diff"]  # Has diff output

    @pytest.mark.asyncio
    async def test_file_edit_multiple_replacements(self, db_session, workspace) -> None:
        tool = FileEditTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(
            path="repeated.txt",
            old_content="foo",
            new_content="bar",
            expected_count=3,
        )

        assert result.success is True
        assert result.data["replacements"] == 3
        assert (workspace / "repeated.txt").read_text() == "bar bar bar\n"

    @pytest.mark.asyncio
    async def test_file_edit_count_mismatch_error(self, db_session, workspace) -> None:
        tool = FileEditTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(
            path="repeated.txt",
            old_content="foo",
            new_content="bar",
            expected_count=2,  # Actually 3 occurrences
        )

        assert result.success is False
        assert "expected 2" in result.error.lower()
        # File unchanged
        assert "foo foo foo" in (workspace / "repeated.txt").read_text()

    @pytest.mark.asyncio
    async def test_file_edit_content_not_found(self, db_session, workspace) -> None:
        tool = FileEditTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(
            path="config.yaml",
            old_content="nonexistent_text",
            new_content="replacement",
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_file_edit_diff_output(self, db_session, workspace) -> None:
        tool = FileEditTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(
            path="config.yaml",
            old_content="max_cpu: 8",
            new_content="max_cpu: 16",
        )

        assert result.success is True
        diff = result.data["diff"]
        assert "-max_cpu: 8" in diff or "- max_cpu: 8" in diff
        assert "+max_cpu: 16" in diff or "+ max_cpu: 16" in diff

    @pytest.mark.asyncio
    async def test_file_edit_blocked_path(self, db_session, workspace) -> None:
        # Create a .env file first
        (workspace / ".env").write_text("SECRET=old\n")

        tool = FileEditTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(
            path=".env",
            old_content="old",
            new_content="new",
        )

        assert result.success is False
        assert "not allowed" in result.error.lower()
