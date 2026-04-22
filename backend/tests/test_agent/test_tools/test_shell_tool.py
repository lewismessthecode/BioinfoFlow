"""Tests for ShellTool — full shell with blocked-command safety."""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.services.agent.tools.shell_tool import ShellTool


class TestShellTool:
    """Tests for ShellTool."""

    @pytest_asyncio.fixture
    async def workspace(self, tmp_path):
        """Create a temporary workspace with test files."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        (workspace / "test.txt").write_text("hello world\n")
        (workspace / "data.csv").write_text("a,b,c\n1,2,3\n")

        subdir = workspace / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("nested content\n")

        return workspace

    @pytest.mark.asyncio
    async def test_tool_name(self, db_session, workspace) -> None:
        """Tool name should be 'shell'."""
        tool = ShellTool(db_session, project_id="test", workspace_root=workspace)
        assert tool.name == "shell"

    @pytest.mark.asyncio
    async def test_ls_command(self, db_session, workspace) -> None:
        """Should execute ls successfully."""
        tool = ShellTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(command="ls")

        assert result.success is True
        assert "test.txt" in result.data["output"]

    @pytest.mark.asyncio
    async def test_cat_command(self, db_session, workspace) -> None:
        """Should execute cat on workspace files."""
        tool = ShellTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(command="cat test.txt")

        assert result.success is True
        assert "hello world" in result.data["output"]

    @pytest.mark.asyncio
    async def test_pipe_allowed(self, db_session, workspace) -> None:
        """Pipes should be allowed for composing commands."""
        tool = ShellTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(command="ls | head -1")

        assert result.success is True
        assert result.data["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_chain_allowed(self, db_session, workspace) -> None:
        """Chain operators (&&) should be allowed."""
        tool = ShellTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(command="echo hello && echo world")

        assert result.success is True
        assert "hello" in result.data["output"]
        assert "world" in result.data["output"]

    @pytest.mark.asyncio
    async def test_redirect_allowed(self, db_session, workspace) -> None:
        """Redirection should be allowed within workspace."""
        tool = ShellTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(command="echo test > output.txt && cat output.txt")

        assert result.success is True
        assert "test" in result.data["output"]

    @pytest.mark.asyncio
    async def test_blocked_command(self, db_session, workspace) -> None:
        """Should block disallowed commands like rm."""
        tool = ShellTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(command="rm test.txt")

        assert result.success is False
        assert "not permitted" in result.error.lower()

    @pytest.mark.asyncio
    async def test_blocked_command_in_pipe(self, db_session, workspace) -> None:
        """Should block destructive commands even inside pipes."""
        tool = ShellTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(command="ls | rm -rf /")

        assert result.success is False
        assert "not permitted" in result.error.lower()

    @pytest.mark.asyncio
    async def test_blocked_command_in_chain(self, db_session, workspace) -> None:
        """Should block destructive commands in chains."""
        tool = ShellTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(command="ls; rm -rf /")

        assert result.success is False
        assert "not permitted" in result.error.lower()

    @pytest.mark.asyncio
    async def test_sudo_blocked(self, db_session, workspace) -> None:
        """Should block sudo."""
        tool = ShellTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(command="sudo ls")

        assert result.success is False
        assert "not permitted" in result.error.lower()

    @pytest.mark.asyncio
    async def test_empty_command_fails(self, db_session, workspace) -> None:
        """Should fail with empty command."""
        tool = ShellTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(command="")

        assert result.success is False

    @pytest.mark.asyncio
    async def test_bif_command(self, db_session, workspace) -> None:
        """Should allow bif commands."""
        tool = ShellTool(db_session, project_id="test", workspace_root=workspace)
        # bif may not be installed in test env, but it should not be blocked
        result = await tool.execute(command="bif --help")
        # Either succeeds or fails with exit_code != 0, but never PermissionError
        assert result.success is True

    @pytest.mark.asyncio
    async def test_output_truncation(self, db_session, workspace) -> None:
        """Should truncate very large output."""
        large_content = "x" * 100_000
        (workspace / "large.txt").write_text(large_content)

        tool = ShellTool(db_session, project_id="test", workspace_root=workspace)
        result = await tool.execute(command="cat large.txt")

        assert result.success is True
        assert len(result.data["output"]) <= 51000

    @pytest.mark.asyncio
    async def test_risk_level_classification(self, db_session, workspace) -> None:
        """Shell tool is ACT_HIGH so every invocation is approval-gated.

        Per the 2026-04-17 review, ACT_LOW was unsafe because
        create_subprocess_shell + a defeatable blocklist let any
        interpreter (python, bash) escape the sandbox with no approval.
        """
        from app.services.agent.tools.base import RiskLevel
        tool = ShellTool(db_session, project_id="test", workspace_root=workspace)
        assert tool.risk_level == RiskLevel.ACT_HIGH

    @pytest.mark.asyncio
    async def test_schema(self, db_session, workspace) -> None:
        """Should return valid schema."""
        tool = ShellTool(db_session, project_id="test", workspace_root=workspace)
        schema = tool.get_schema()

        assert "command" in schema
        assert schema["command"]["required"] is True

    @pytest.mark.asyncio
    async def test_definition(self, db_session, workspace) -> None:
        """Should return valid tool definition."""
        tool = ShellTool(db_session, project_id="test", workspace_root=workspace)
        definition = tool.get_definition()

        assert definition["name"] == "shell"
        assert "description" in definition
        assert "args" in definition
