"""Tests for code execution tools."""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.services.agent.tools.code_tools import (
    ExecuteCodeTool,
    MAX_CODE_SIZE,
)
from app.services.agent.tools.sandbox import CodeSandbox, _truncate_output


class TestTruncateOutput:
    """Tests for output truncation."""

    def test_short_output_unchanged(self) -> None:
        """Short output should not be truncated."""
        output = "Hello World"
        result, truncated = _truncate_output(output, max_bytes=100)
        assert result == output
        assert truncated is False

    def test_long_output_truncated(self) -> None:
        """Long output should be truncated."""
        output = "x" * 1000
        result, truncated = _truncate_output(output, max_bytes=100)
        assert len(result.encode("utf-8")) <= 100 + len(
            "\n... [output truncated]".encode()
        )
        assert truncated is True
        assert "[output truncated]" in result


class TestCodeSandbox:
    """Tests for CodeSandbox class."""

    @pytest.fixture
    def workspace(self, tmp_path):
        """Create a temporary workspace."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        return workspace

    @pytest.mark.asyncio
    async def test_direct_execution_simple(self, workspace) -> None:
        """Should execute simple Python code."""
        sandbox = CodeSandbox(workspace_root=workspace, enabled=False)

        # Create a simple script
        script = workspace / "test.py"
        script.write_text("print('Hello from sandbox')")

        result = await sandbox.execute(script, timeout=10)

        assert result.exit_code == 0
        assert "Hello from sandbox" in result.stdout
        assert result.timed_out is False

    @pytest.mark.asyncio
    async def test_direct_execution_with_error(self, workspace) -> None:
        """Should capture stderr on error."""
        sandbox = CodeSandbox(workspace_root=workspace, enabled=False)

        # Create script with error
        script = workspace / "test.py"
        script.write_text("raise ValueError('Test error')")

        result = await sandbox.execute(script, timeout=10)

        assert result.exit_code != 0
        assert "ValueError" in result.stderr

    @pytest.mark.asyncio
    async def test_timeout_handling(self, workspace) -> None:
        """Should handle timeout properly."""
        sandbox = CodeSandbox(workspace_root=workspace, enabled=False)

        # Create script that runs too long
        script = workspace / "test.py"
        script.write_text("import time; time.sleep(60)")

        result = await sandbox.execute(script, timeout=1)

        assert result.timed_out is True
        # Exit code may vary by platform, but timed_out should be True


class TestExecuteCodeTool:
    """Tests for ExecuteCodeTool."""

    @pytest_asyncio.fixture
    async def workspace(self, tmp_path):
        """Create a temporary workspace."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        return workspace

    @pytest.mark.asyncio
    async def test_execute_simple_code(self, db_session, workspace) -> None:
        """Should execute simple Python code."""
        tool = ExecuteCodeTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(code="print('Hello World')")

        assert result.success is True
        assert result.data is not None
        assert "Hello World" in result.data["stdout"]
        assert result.data["exit_code"] == 0
        assert result.data["timed_out"] is False

    @pytest.mark.asyncio
    async def test_execute_with_imports(self, db_session, workspace) -> None:
        """Should handle standard library imports."""
        tool = ExecuteCodeTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(code="import os; print(os.getcwd())")

        assert result.success is True
        assert result.data["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_execute_with_error(self, db_session, workspace) -> None:
        """Should capture errors properly."""
        tool = ExecuteCodeTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(code="raise ValueError('Test error')")

        assert result.success is False
        assert result.data is not None
        assert result.data["exit_code"] != 0
        assert "ValueError" in result.data["stderr"]

    @pytest.mark.asyncio
    async def test_execute_creates_artifact(self, db_session, workspace) -> None:
        """Should detect created files as artifacts."""
        tool = ExecuteCodeTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(
            code="with open('output.txt', 'w') as f: f.write('test')"
        )

        assert result.success is True
        assert len(result.data["artifacts"]) == 1
        assert result.data["artifacts"][0]["name"] == "output.txt"
        assert result.data["artifacts"][0]["type"] == "text"

        # Verify file was created
        assert (workspace / "output.txt").exists()

    @pytest.mark.asyncio
    async def test_execute_artifact_type_detection(self, db_session, workspace) -> None:
        """Should detect artifact types correctly."""
        tool = ExecuteCodeTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(
            code="""
with open('data.csv', 'w') as f: f.write('a,b,c')
with open('result.json', 'w') as f: f.write('{}')
"""
        )

        assert result.success is True
        artifacts = {a["name"]: a["type"] for a in result.data["artifacts"]}
        assert artifacts.get("data.csv") == "data"
        assert artifacts.get("result.json") == "data"

    @pytest.mark.asyncio
    async def test_execute_empty_code_fails(self, db_session, workspace) -> None:
        """Should fail with empty code."""
        tool = ExecuteCodeTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(code="")

        assert result.success is False
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_code_too_large(self, db_session, workspace) -> None:
        """Should fail with oversized code."""
        tool = ExecuteCodeTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(code="x" * (MAX_CODE_SIZE + 1))

        assert result.success is False
        assert "too large" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_working_dir(self, db_session, workspace) -> None:
        """Should respect working directory."""
        subdir = workspace / "subdir"
        subdir.mkdir()

        tool = ExecuteCodeTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(
            code="import os; print(os.getcwd())",
            working_dir="subdir",
        )

        assert result.success is True
        assert "subdir" in result.data["stdout"]

    @pytest.mark.asyncio
    async def test_execute_invalid_working_dir(self, db_session, workspace) -> None:
        """Should fail with invalid working directory."""
        tool = ExecuteCodeTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(
            code="print('test')",
            working_dir="nonexistent",
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_path_escape_blocked(self, db_session, workspace) -> None:
        """Should block path escape attempts."""
        tool = ExecuteCodeTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(
            code="print('test')",
            working_dir="../../../etc",
        )

        assert result.success is False
        assert "escapes" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_timeout_short(self, db_session, workspace) -> None:
        """Should timeout long-running code."""
        tool = ExecuteCodeTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(
            code="import time; time.sleep(60)",
            timeout=1,
        )

        assert result.success is False
        assert result.data["timed_out"] is True

    @pytest.mark.asyncio
    async def test_execute_cleans_up_temp_script(self, db_session, workspace) -> None:
        """Should clean up temporary script after execution."""
        tool = ExecuteCodeTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(code="print('test')")

        assert result.success is True
        # Check no _agent_exec_ files remain
        remaining = list(workspace.glob("_agent_exec_*.py"))
        assert len(remaining) == 0

    @pytest.mark.asyncio
    async def test_get_schema(self, db_session, workspace) -> None:
        """Should return valid schema."""
        tool = ExecuteCodeTool(db_session, project_id="test", workspace_root=workspace)
        schema = tool.get_schema()

        assert "code" in schema
        assert schema["code"]["required"] is True
        assert "timeout" in schema
        assert "working_dir" in schema

    @pytest.mark.asyncio
    async def test_get_definition(self, db_session, workspace) -> None:
        """Should return valid tool definition."""
        tool = ExecuteCodeTool(db_session, project_id="test", workspace_root=workspace)
        definition = tool.get_definition()

        assert definition["name"] == "execute_code"
        assert "description" in definition
        assert "args" in definition

    @pytest.mark.asyncio
    async def test_execute_multiline_code(self, db_session, workspace) -> None:
        """Should handle multiline code."""
        tool = ExecuteCodeTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(
            code="""
def add(a, b):
    return a + b

result = add(2, 3)
print(f"Result: {result}")
"""
        )

        assert result.success is True
        assert "Result: 5" in result.data["stdout"]

    @pytest.mark.asyncio
    async def test_execute_stdout_and_stderr(self, db_session, workspace) -> None:
        """Should capture both stdout and stderr."""
        tool = ExecuteCodeTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(
            code="""
import sys
print("to stdout")
print("to stderr", file=sys.stderr)
"""
        )

        assert result.success is True
        assert "to stdout" in result.data["stdout"]
        assert "to stderr" in result.data["stderr"]
