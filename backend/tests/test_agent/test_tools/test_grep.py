"""Tests for GrepTool (refactored from CodeSearchTool)."""

from __future__ import annotations

import subprocess

import pytest
import pytest_asyncio

from app.services.agent.tools.search_tools import (
    GrepTool,
    _check_ripgrep_available,
    _parse_ripgrep_json,
)


@pytest.fixture(scope="session", autouse=True)
def ensure_ripgrep():
    """Fail early if ripgrep is not installed."""
    result = subprocess.run(["rg", "--version"], capture_output=True)
    if result.returncode != 0:
        pytest.fail(
            "ripgrep not found. Install with:\n"
            "  macOS: brew install ripgrep\n"
            "  Linux: apt install ripgrep\n"
            "  Windows: choco install ripgrep"
        )


class TestRipgrepHelpers:
    """Tests for ripgrep helper functions."""

    def test_check_ripgrep_available(self) -> None:
        """Should find ripgrep when installed."""
        path = _check_ripgrep_available()
        assert path is not None
        assert "rg" in path

    def test_parse_ripgrep_json_match(self) -> None:
        """Should parse match JSON lines."""
        line = '{"type":"match","data":{"path":{"text":"test.py"},"lines":{"text":"def foo():\\n"},"line_number":10,"submatches":[{"start":4,"end":7}]}}'
        result = _parse_ripgrep_json(line)
        assert result is not None
        assert result["type"] == "match"
        assert result["data"]["line_number"] == 10

    def test_parse_ripgrep_json_non_match(self) -> None:
        """Should return None for non-match lines."""
        line = '{"type":"begin","data":{"path":{"text":"test.py"}}}'
        result = _parse_ripgrep_json(line)
        assert result is None

    def test_parse_ripgrep_json_invalid(self) -> None:
        """Should return None for invalid JSON."""
        result = _parse_ripgrep_json("not valid json")
        assert result is None


class TestGrepTool:
    """Tests for GrepTool."""

    @pytest_asyncio.fixture
    async def workspace(self, tmp_path):
        """Create a temporary workspace with test files."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create Python files
        (workspace / "main.py").write_text(
            "def hello_world():\n"
            "    print('Hello World')\n"
            "\n"
            "def foo_bar():\n"
            "    return 42\n"
        )

        (workspace / "utils.py").write_text(
            "def helper_function():\n"
            "    pass\n"
            "\n"
            "class MyClass:\n"
            "    def hello_method(self):\n"
            "        pass\n"
        )

        # Create Nextflow file
        (workspace / "main.nf").write_text(
            "#!/usr/bin/env nextflow\n"
            "\n"
            "process HELLO {\n"
            "    output: stdout\n"
            "    script:\n"
            "    '''\n"
            "    echo Hello World\n"
            "    '''\n"
            "}\n"
        )

        # Create subdirectory with files
        subdir = workspace / "src"
        subdir.mkdir()
        (subdir / "module.py").write_text(
            "# Module with hello function\n"
            "def hello_from_module():\n"
            "    return 'hello'\n"
        )

        return workspace

    @pytest.mark.asyncio
    async def test_grep_tool_name(self, db_session, workspace) -> None:
        """Tool name should be 'grep' (not 'code_search')."""
        tool = GrepTool(db_session, project_id="test", workspace_root=workspace)
        assert tool.name == "grep"

    @pytest.mark.asyncio
    async def test_search_simple_pattern(self, db_session, workspace) -> None:
        """Should find matches for a simple pattern."""
        tool = GrepTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="hello")

        assert result.success is True
        assert result.data is not None
        assert result.data["total_matches"] > 0
        assert result.data["files_with_matches"] > 0

    @pytest.mark.asyncio
    async def test_search_with_glob_filter(self, db_session, workspace) -> None:
        """Should filter by glob pattern."""
        tool = GrepTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="hello", glob="*.py")

        assert result.success is True
        # All results should be .py files
        for file_path in result.data["results"].keys():
            assert file_path.endswith(".py")

    @pytest.mark.asyncio
    async def test_search_with_context_lines(self, db_session, workspace) -> None:
        """Should support context lines parameter."""
        tool = GrepTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="hello", context=3)

        assert result.success is True
        assert result.data["total_matches"] > 0

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, db_session, workspace) -> None:
        """Should support case_insensitive parameter."""
        tool = GrepTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="HELLO", case_insensitive=True)

        assert result.success is True
        assert result.data["total_matches"] > 0

    @pytest.mark.asyncio
    async def test_search_case_sensitive(self, db_session, workspace) -> None:
        """Should support case-sensitive search (default)."""
        tool = GrepTool(db_session, project_id="test", workspace_root=workspace)

        # Case-sensitive search for uppercase
        result = await tool.execute(pattern="HELLO", case_insensitive=False)
        matches_upper = result.data["total_matches"]

        # Should only match the HELLO in main.nf process name
        assert result.success is True
        assert matches_upper >= 1

    @pytest.mark.asyncio
    async def test_search_in_subdirectory(self, db_session, workspace) -> None:
        """Should search in subdirectory."""
        tool = GrepTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="hello", path="src")

        assert result.success is True
        if result.data["total_matches"] > 0:
            for file_path in result.data["results"].keys():
                assert file_path.startswith("src/")

    @pytest.mark.asyncio
    async def test_search_no_matches(self, db_session, workspace) -> None:
        """Should succeed with empty results for no matches."""
        tool = GrepTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="xyznonexistentpatternxyz")

        assert result.success is True
        assert result.data["total_matches"] == 0

    @pytest.mark.asyncio
    async def test_search_empty_pattern_fails(self, db_session, workspace) -> None:
        """Should fail with empty pattern."""
        tool = GrepTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="")

        assert result.success is False
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_search_path_escape_blocked(self, db_session, workspace) -> None:
        """Should block path escape attempts."""
        tool = GrepTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="test", path="../../../etc")

        assert result.success is False
        assert "escapes" in result.error.lower()

    @pytest.mark.asyncio
    async def test_get_schema_has_new_params(self, db_session, workspace) -> None:
        """Schema should include glob, context, and case_insensitive params."""
        tool = GrepTool(db_session, project_id="test", workspace_root=workspace)
        schema = tool.get_schema()

        assert "pattern" in schema
        assert schema["pattern"]["required"] is True
        assert "glob" in schema
        assert "context" in schema
        assert "case_insensitive" in schema

    @pytest.mark.asyncio
    async def test_get_definition(self, db_session, workspace) -> None:
        """Should return valid tool definition with new name."""
        tool = GrepTool(db_session, project_id="test", workspace_root=workspace)
        definition = tool.get_definition()

        assert definition["name"] == "grep"
        assert "description" in definition
        assert "args" in definition

    @pytest.mark.asyncio
    async def test_backward_compat_file_types(self, db_session, workspace) -> None:
        """file_types parameter should still work for backward compat."""
        tool = GrepTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="hello", file_types=["*.py"])

        assert result.success is True
        for file_path in result.data["results"].keys():
            assert file_path.endswith(".py")
