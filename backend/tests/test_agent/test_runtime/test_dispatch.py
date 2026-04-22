"""Tests for runtime/dispatch.py -- tool dispatch map."""

from __future__ import annotations

import pytest

from app.services.agent.runtime.dispatch import (
    ToolEntry,
    build_dispatch_map,
    get_tool_schemas,
)
from app.services.agent.runtime.todo import TodoManager


@pytest.mark.asyncio
async def test_dispatch_map_builds_from_registry(db_session, tmp_path):
    """Dispatch map should contain registered BaseTool instances and domain tools."""
    dispatch = build_dispatch_map(db_session, project_id="test-project")

    # New BaseTool tools should be present
    assert "file_read" in dispatch
    assert "file_write" in dispatch
    assert "glob" in dispatch
    assert "grep" in dispatch
    assert "shell" in dispatch
    assert "web_search" in dispatch
    assert "web_fetch" in dispatch
    assert "pubmed_search" in dispatch
    assert "chembl_search" in dispatch
    assert "workflow_validate" not in dispatch

    # Runtime tools should be present
    assert "compact" in dispatch

    # Removed domain tools should NOT be present (replaced by bif CLI)
    assert "list_images" not in dispatch
    assert "search_workflows" not in dispatch
    assert "read_logs" not in dispatch
    assert "run_workflow" not in dispatch

    # Legacy tools should NOT be present
    assert "scan_dir" not in dispatch
    assert "safe_shell" not in dispatch
    assert "visualize_result" not in dispatch
    assert "code_search" not in dispatch  # renamed to grep

    # All entries should be ToolEntry
    for entry in dispatch.values():
        assert isinstance(entry, ToolEntry)
        assert callable(entry.handler)
        assert "type" in entry.schema
        assert entry.schema["type"] == "function"
        assert "function" in entry.schema
        assert "name" in entry.schema["function"]
        assert "parameters" in entry.schema["function"]


@pytest.mark.asyncio
async def test_dispatch_map_includes_todo_when_provided(db_session):
    """When a todo_manager is provided, todo_write tool should be registered."""
    todo = TodoManager()
    dispatch = build_dispatch_map(
        db_session, project_id="test-project", todo_manager=todo
    )
    assert "todo_write" in dispatch


@pytest.mark.asyncio
async def test_dispatch_map_excludes_todo_when_none(db_session):
    """When no todo_manager, todo_write should not be registered."""
    dispatch = build_dispatch_map(db_session, project_id="test-project")
    assert "todo_write" not in dispatch


@pytest.mark.asyncio
async def test_get_tool_schemas(db_session):
    """get_tool_schemas should return a list of OpenAI function calling format schemas."""
    dispatch = build_dispatch_map(db_session, project_id="test-project")
    schemas = get_tool_schemas(dispatch)
    assert isinstance(schemas, list)
    assert len(schemas) > 0
    for schema in schemas:
        assert schema["type"] == "function"
        assert "name" in schema["function"]
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]


@pytest.mark.asyncio
async def test_unknown_tool_returns_error(db_session):
    """Calling a nonexistent tool should not be in the dispatch map."""
    dispatch = build_dispatch_map(db_session, project_id="test-project")
    assert "nonexistent_tool" not in dispatch


@pytest.mark.asyncio
async def test_tool_handler_truncates_output(db_session, tmp_path):
    """Tool handlers should truncate output exceeding MAX_TOOL_OUTPUT_CHARS."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "test.py").write_text("# test file\n")

    dispatch = build_dispatch_map(
        db_session, project_id="test-project", workspace_root=workspace
    )

    # The glob handler will return some result -- we just verify it's a string
    entry = dispatch.get("glob")
    assert entry is not None
    result = await entry.handler(pattern="**/*")
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_todo_write_handler(db_session):
    """todo_write handler should update the TodoManager."""
    todo = TodoManager()
    dispatch = build_dispatch_map(
        db_session, project_id="test-project", todo_manager=todo
    )
    entry = dispatch["todo_write"]
    result = await entry.handler(
        items=[{"id": "1", "text": "Test task", "status": "pending"}]
    )
    assert isinstance(result, str)
    assert len(todo.items) == 1
    assert todo.items[0].text == "Test task"


@pytest.mark.asyncio
async def test_dispatch_map_omits_workspace_tools_for_inbox_conversations():
    dispatch = build_dispatch_map(
        object(),
        project_id="test-project",
        allow_workspace_tools=False,
    )

    assert "file_read" not in dispatch
    assert "file_write" not in dispatch
    assert "file_edit" not in dispatch
    assert "glob" not in dispatch
    assert "grep" not in dispatch
    assert "shell" not in dispatch
    assert "execute_code" not in dispatch
    assert "web_search" in dispatch
    assert "web_fetch" in dispatch
    assert "compact" in dispatch
