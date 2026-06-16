from __future__ import annotations

import pytest

from app.models.workspace import Workspace
from app.repositories.agent_core_repo import AgentActionRepository
from app.services.agent_core import AgentCoreService
from app.services.agent_core.tools import (
    AgentToolContext,
    AgentToolDispatcher,
    build_default_tool_registry,
)
from app.services.agent_core.tools.middleware import normalize_tool_input
from app.utils.exceptions import BadRequestError
from app.workspace import DEFAULT_WORKSPACE_ID


def test_normalize_tool_input_coerces_common_model_argument_shapes():
    result = normalize_tool_input(
        {
            "limit": "10",
            "force_sync": "false",
            "values": "{\"sample\":\"S1\"}",
            "status": "[\"completed\",\"failed\"]",
        },
        {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "force_sync": {"type": "boolean"},
                "values": {"type": "object"},
                "status": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
    )

    assert result == {
        "limit": 10,
        "force_sync": False,
        "values": {"sample": "S1"},
        "status": ["completed", "failed"],
    }


def test_normalize_tool_input_rejects_unparseable_object_string():
    with pytest.raises(BadRequestError, match="values must be object"):
        normalize_tool_input(
            {"values": "not-json"},
            {
                "type": "object",
                "properties": {"values": {"type": "object"}},
                "additionalProperties": False,
            },
        )


def test_normalize_tool_input_enforces_enum_and_min_length():
    with pytest.raises(BadRequestError, match="source must be one of: local, github, nf-core"):
        normalize_tool_input(
            {"source": "nfcore"},
            {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "enum": ["local", "github", "nf-core"]}
                },
                "additionalProperties": False,
            },
        )

    with pytest.raises(BadRequestError, match="command must have length >= 1"):
        normalize_tool_input(
            {"command": ""},
            {
                "type": "object",
                "properties": {"command": {"type": "string", "minLength": 1}},
                "additionalProperties": False,
            },
        )


def test_normalize_tool_input_enforces_array_size():
    with pytest.raises(BadRequestError, match="questions must have at least 1 item"):
        normalize_tool_input(
            {"questions": []},
            {
                "type": "object",
                "properties": {"questions": {"type": "array", "minItems": 1}},
                "additionalProperties": False,
            },
        )

    with pytest.raises(BadRequestError, match="questions must have at most 3 items"):
        normalize_tool_input(
            {"questions": [{}, {}, {}, {}]},
            {
                "type": "object",
                "properties": {"questions": {"type": "array", "maxItems": 3}},
                "additionalProperties": False,
            },
        )


@pytest.mark.asyncio
async def test_tool_argument_validation_failure_is_recorded_as_failed_action(db_session):
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()
    core = AgentCoreService(db_session)
    session = await core.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await core.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Submit a run.",
    )
    context = AgentToolContext(
        db=db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        session_id=str(session.id),
        turn_id=str(turn.id),
    )

    result = await AgentToolDispatcher(
        db_session, build_default_tool_registry()
    ).dispatch(
        tool_name="runs.submit",
        input={
            "project_id": "project-1",
            "workflow_id": "workflow-1",
            "values": "not-json",
        },
        context=context,
    )

    assert result.status == "failed"
    assert result.error == {"type": "BadRequestError", "message": "values must be object"}

    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    assert len(actions) == 1
    assert actions[0].name == "runs.submit"
    assert actions[0].status == "failed"
    assert actions[0].error == result.error


@pytest.mark.asyncio
async def test_enum_validation_failure_is_recorded_before_tool_execution(
    db_session, monkeypatch
):
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()
    core = AgentCoreService(db_session)
    session = await core.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await core.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Create a workflow.",
    )
    context = AgentToolContext(
        db=db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        session_id=str(session.id),
        turn_id=str(turn.id),
    )
    create_called = False

    async def fake_create_workflow(self, payload):
        nonlocal create_called
        create_called = True
        return None

    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.workflows.WorkflowService.create_workflow",
        fake_create_workflow,
    )

    result = await AgentToolDispatcher(
        db_session, build_default_tool_registry()
    ).dispatch(
        tool_name="workflows.create",
        input={"source": "nfcore"},
        context=context,
        permission_mode="bypass",
    )

    assert result.status == "failed"
    assert result.error == {
        "type": "BadRequestError",
        "message": "source must be one of: local, github, nf-core",
    }
    assert create_called is False
