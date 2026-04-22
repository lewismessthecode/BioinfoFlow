from __future__ import annotations

import pytest

from app.services.agent.tools import create_tool, get_all_tools, list_tool_names


@pytest.mark.asyncio
async def test_workflow_validate_tool_is_not_registered(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert "workflow_validate" not in list_tool_names()
    assert (
        create_tool(
            "workflow_validate",
            db_session,
            project_id="test-project",
            workspace_root=workspace,
        )
        is None
    )


@pytest.mark.asyncio
async def test_get_all_tools_excludes_workflow_validate(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    tools = get_all_tools(
        db_session,
        project_id="test-project",
        workspace_root=workspace,
        allow_workspace_tools=True,
    )

    assert "workflow_validate" not in {tool.name for tool in tools}
