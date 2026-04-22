"""Agent run tools smoke tests — verifies registration and interface."""

from __future__ import annotations

import pytest

from app.services.agent.tools import (
    RunGetDagTool,
    RunGetResultsTool,
    RunGetTool,
    RunSubmitTool,
    get_tool_class,
    get_tool_risk_level,
)


@pytest.mark.unit
def test_run_submit_registered_as_act_high():
    assert get_tool_class("run_submit") is RunSubmitTool
    assert get_tool_risk_level("run_submit") == "act_high"


@pytest.mark.unit
def test_run_read_tools_registered_as_read():
    for name, cls in (
        ("run_get", RunGetTool),
        ("run_get_dag", RunGetDagTool),
        ("run_get_results", RunGetResultsTool),
    ):
        assert get_tool_class(name) is cls
        assert get_tool_risk_level(name) == "read"


@pytest.mark.unit
def test_run_tools_publish_json_schemas():
    for cls in (RunSubmitTool, RunGetTool, RunGetDagTool, RunGetResultsTool):
        tool = cls.__new__(cls)
        schema = tool.get_schema()
        assert isinstance(schema, dict)
        assert schema  # non-empty
