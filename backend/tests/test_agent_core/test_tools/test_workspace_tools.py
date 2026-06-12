from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.config import settings
from app.models.workspace import Workspace
from app.services.agent_core import AgentCoreService
from app.services.agent_core.tools import AgentToolContext, AgentToolDispatcher, AgentToolRegistry
from app.services.agent_core.tools.executor import AgentToolExecutor
from app.services.agent_core.tools.files import EditFileTool, ListFilesTool, ReadFileTool, WriteFileTool
from app.services.agent_core.tools.search import WorkspaceSearchTool
from app.services.agent_core.tools.specs import AgentToolSpec
from app.services.agent_core.tools.web import FetchWebPageTool, SearchWebTool
from app.workspace import DEFAULT_WORKSPACE_ID


class SlowTool:
    spec = AgentToolSpec(
        name="test.slow",
        description="Sleep past the executor timeout.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        },
        risk_level="read",
        read_scope=["workspace"],
        timeout_seconds=1,
    )

    async def run(self, input, context):
        del input, context
        await asyncio.sleep(2)
        return {"ok": True}


async def _workspace(db_session) -> Workspace:
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()
    return workspace


async def _tool_context(db_session) -> tuple[AgentToolContext, Path]:
    await _workspace(db_session)
    core = AgentCoreService(db_session)
    session = await core.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    session = await core.session_repo.update_all(session, toolset_policy={"name": "execution"})
    turn = await core.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Run workspace tools.",
    )
    root = Path(settings.repo_root)
    return (
        AgentToolContext(
            db=db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            session_id=str(session.id),
            turn_id=str(turn.id),
        ),
        root,
    )


@pytest.mark.asyncio
async def test_file_tools_can_write_edit_read_and_list(db_session):
    context, _root = await _tool_context(db_session)
    dispatcher = AgentToolDispatcher(db_session, AgentToolRegistry())
    dispatcher.executor.registry.register(ListFilesTool())
    dispatcher.executor.registry.register(ReadFileTool())
    dispatcher.executor.registry.register(WriteFileTool())
    dispatcher.executor.registry.register(EditFileTool())

    workspace_dir = Path(settings.bioinfoflow_home) / "workspace-tools"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    file_path = workspace_dir / "notes.txt"

    written = await dispatcher.dispatch(
        tool_name="files.write",
        input={"path": str(file_path), "content": "alpha\nbeta\n"},
        context=context,
        permission_mode="bypass",
    )
    assert written.status == "completed"

    edited = await dispatcher.dispatch(
        tool_name="files.edit",
        input={"path": str(file_path), "old_text": "beta", "new_text": "gamma"},
        context=context,
        permission_mode="bypass",
    )
    assert edited.status == "completed"

    read_result = await dispatcher.dispatch(
        tool_name="files.read",
        input={"path": str(file_path)},
        context=context,
        permission_mode="bypass",
    )
    assert read_result.result["content"] == "alpha\ngamma"

    listed = await dispatcher.dispatch(
        tool_name="files.list",
        input={"path": str(workspace_dir)},
        context=context,
        permission_mode="bypass",
    )
    assert listed.result["entries"][0]["name"] == "notes.txt"


@pytest.mark.asyncio
async def test_workspace_search_tool_finds_matches(db_session):
    context, _root = await _tool_context(db_session)
    dispatcher = AgentToolDispatcher(db_session, AgentToolRegistry())
    dispatcher.executor.registry.register(WorkspaceSearchTool())

    workspace_dir = Path(settings.bioinfoflow_home) / "workspace-search"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "a.txt").write_text("first\nneedle here\n", encoding="utf-8")
    (workspace_dir / "b.txt").write_text("needle there\n", encoding="utf-8")

    result = await dispatcher.dispatch(
        tool_name="search.workspace",
        input={"path": str(workspace_dir), "query": "needle"},
        context=context,
        permission_mode="bypass",
    )

    assert result.status == "completed"
    assert len(result.result["matches"]) == 2


@pytest.mark.asyncio
async def test_executor_enforces_tool_timeout(db_session):
    context, _root = await _tool_context(db_session)
    registry = AgentToolRegistry()
    registry.register(SlowTool())
    executor = AgentToolExecutor(db_session, registry)

    result = await executor.execute(
        tool_name="test.slow",
        input={},
        context=context,
        toolset_policy={"name": "execution"},
        permission_mode="bypass",
    )

    assert result.status == "failed"
    assert result.error["type"] == "TimeoutError"


@pytest.mark.asyncio
async def test_web_tools_fetch_and_search(db_session, monkeypatch):
    context, _root = await _tool_context(db_session)
    dispatcher = AgentToolDispatcher(db_session, AgentToolRegistry())
    dispatcher.executor.registry.register(FetchWebPageTool())
    dispatcher.executor.registry.register(SearchWebTool())

    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query, max_results):
            return [{"title": "Result", "href": "https://example.com", "body": query}]

    monkeypatch.setattr(
        "app.services.agent_core.tools.web.resources._fetch_url",
        lambda url: {
            "url": url,
            "status_code": 200,
            "text": "<html><body>Hello <b>world</b></body></html>",
        },
    )
    monkeypatch.setattr("app.services.agent_core.tools.web.resources.DDGS", FakeDDGS)

    fetched = await dispatcher.dispatch(
        tool_name="web.fetch",
        input={"url": "https://example.com/page"},
        context=context,
        permission_mode="bypass",
    )
    searched = await dispatcher.dispatch(
        tool_name="web.search",
        input={"query": "rna seq"},
        context=context,
        permission_mode="bypass",
    )

    assert fetched.result["content"] == "Hello world"
    assert searched.result["results"][0]["title"] == "Result"
