"""Tests for code search tools."""

from __future__ import annotations

import subprocess

import pytest
import pytest_asyncio

from app.services.agent.tools.search_tools import (
    CodeSearchTool,
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


class TestCodeSearchTool:
    """Tests for CodeSearchTool."""

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
    async def test_search_simple_pattern(self, db_session, workspace) -> None:
        """Should find matches for a simple pattern."""
        tool = CodeSearchTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="hello")

        assert result.success is True
        assert result.data is not None
        assert result.data["total_matches"] > 0
        assert result.data["files_with_matches"] > 0

    @pytest.mark.asyncio
    async def test_search_regex_pattern(self, db_session, workspace) -> None:
        """Should support regex patterns."""
        tool = CodeSearchTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern=r"def \w+_\w+")

        assert result.success is True
        assert result.data["total_matches"] > 0
        # Should match hello_world, foo_bar, helper_function, etc.

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, db_session, workspace) -> None:
        """Should be case-insensitive by default."""
        tool = CodeSearchTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="HELLO")

        assert result.success is True
        assert result.data["total_matches"] > 0

    @pytest.mark.asyncio
    async def test_search_case_sensitive(self, db_session, workspace) -> None:
        """Should support case-sensitive search (default, case_insensitive=False)."""
        tool = CodeSearchTool(db_session, project_id="test", workspace_root=workspace)

        # Default is case-sensitive; case_insensitive=False for lowercase
        result = await tool.execute(pattern="hello", case_insensitive=False)
        matches_lower = result.data["total_matches"]

        # Case-sensitive search for uppercase
        result = await tool.execute(pattern="HELLO", case_insensitive=False)
        matches_upper = result.data["total_matches"]

        # Should have different results
        assert (
            matches_lower != matches_upper or matches_lower == 0 or matches_upper == 0
        )

    @pytest.mark.asyncio
    async def test_search_file_types(self, db_session, workspace) -> None:
        """Should filter by file types."""
        tool = CodeSearchTool(db_session, project_id="test", workspace_root=workspace)

        # Search only Python files
        result = await tool.execute(pattern="hello", file_types=["*.py"])

        assert result.success is True
        # All results should be .py files
        for file_path in result.data["results"].keys():
            assert file_path.endswith(".py")

    @pytest.mark.asyncio
    async def test_search_in_subdirectory(self, db_session, workspace) -> None:
        """Should search in subdirectory."""
        tool = CodeSearchTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="hello", path="src")

        assert result.success is True
        # Should only find matches in src directory
        if result.data["total_matches"] > 0:
            for file_path in result.data["results"].keys():
                assert file_path.startswith("src/")

    @pytest.mark.asyncio
    async def test_search_max_results(self, db_session, workspace) -> None:
        """Should respect max_results limit."""
        tool = CodeSearchTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern=".", max_results=2)

        assert result.success is True
        assert result.data["total_matches"] <= 2

    @pytest.mark.asyncio
    async def test_search_no_matches(self, db_session, workspace) -> None:
        """Should succeed with empty results for no matches."""
        tool = CodeSearchTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="xyznonexistentpatternxyz")

        assert result.success is True
        assert result.data["total_matches"] == 0
        assert result.data["files_with_matches"] == 0

    @pytest.mark.asyncio
    async def test_search_empty_pattern_fails(self, db_session, workspace) -> None:
        """Should fail with empty pattern."""
        tool = CodeSearchTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="")

        assert result.success is False
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_search_path_escape_blocked(self, db_session, workspace) -> None:
        """Should block path escape attempts."""
        tool = CodeSearchTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="test", path="../../../etc")

        assert result.success is False
        assert "escapes" in result.error.lower()

    @pytest.mark.asyncio
    async def test_search_nonexistent_path(self, db_session, workspace) -> None:
        """Should fail for nonexistent path."""
        tool = CodeSearchTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="test", path="nonexistent_dir")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_search_results_structure(self, db_session, workspace) -> None:
        """Should return properly structured results."""
        tool = CodeSearchTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(pattern="hello")

        assert result.success is True
        data = result.data

        # Check required fields
        assert "pattern" in data
        assert "search_path" in data
        assert "total_matches" in data
        assert "files_with_matches" in data
        assert "results" in data
        assert "truncated" in data

        # Check results structure
        for file_path, file_matches in data["results"].items():
            assert isinstance(file_path, str)
            assert isinstance(file_matches, list)
            for match in file_matches:
                assert "line" in match
                assert "content" in match

    @pytest.mark.asyncio
    async def test_get_schema(self, db_session, workspace) -> None:
        """Should return valid schema."""
        tool = CodeSearchTool(db_session, project_id="test", workspace_root=workspace)
        schema = tool.get_schema()

        assert "pattern" in schema
        assert schema["pattern"]["required"] is True
        assert "path" in schema
        assert "file_types" in schema
        assert "case_insensitive" in schema
        assert "max_results" in schema
        assert "context" in schema

    @pytest.mark.asyncio
    async def test_get_definition(self, db_session, workspace) -> None:
        """Should return valid tool definition."""
        tool = CodeSearchTool(db_session, project_id="test", workspace_root=workspace)
        definition = tool.get_definition()

        assert definition["name"] == "grep"
        assert "description" in definition
        assert "args" in definition
