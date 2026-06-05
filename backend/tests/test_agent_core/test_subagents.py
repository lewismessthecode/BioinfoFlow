from __future__ import annotations

import pytest

from app.services.agent_core.subagents import ReadOnlySubagentRunner
from app.services.agent_core.tools import build_default_tool_registry
from app.utils.exceptions import PermissionDeniedError


@pytest.mark.asyncio
async def test_read_only_subagent_accepts_read_only_tools():
    result = await ReadOnlySubagentRunner(build_default_tool_registry()).analyze(
        task="Summarize available project context.",
        context={"project_id": "project-1"},
        allowed_tools=["projects.list", "skills.list"],
    )

    assert result["mode"] == "read_only"
    assert result["task"] == "Summarize available project context."
    assert result["allowed_tools"] == ["projects.list", "skills.list"]
    assert result["write_handoff_required"] is True


@pytest.mark.asyncio
async def test_read_only_subagent_rejects_write_capable_tools():
    with pytest.raises(PermissionDeniedError, match="write-capable"):
        await ReadOnlySubagentRunner(build_default_tool_registry()).analyze(
            task="Remember the reference genome.",
            context={"project_id": "project-1"},
            allowed_tools=["memory.propose"],
        )
