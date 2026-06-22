from __future__ import annotations

import pytest

from app.models.workspace import Workspace
from app.services.agent_core import AgentCoreService
from app.services.agent_core.tools import (
    AgentToolContext,
    AgentToolDispatcher,
    build_default_tool_registry,
)
from app.workspace import DEFAULT_WORKSPACE_ID


async def _interaction_context(db_session, *, mode: str = "execution"):
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()

    core = AgentCoreService(db_session)
    session = await core.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        title="Interaction",
        toolset_policy={"name": mode},
    )
    turn = await core.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Ask me something.",
    )
    dispatcher = AgentToolDispatcher(db_session, build_default_tool_registry())
    context = AgentToolContext(
        db=db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        session_id=str(session.id),
        turn_id=str(turn.id),
    )
    return core, dispatcher, context, str(session.id), str(turn.id)


@pytest.mark.asyncio
async def test_ask_user_pauses_even_under_bypass_then_resumes_with_answer(db_session, monkeypatch):
    monkeypatch.setattr("app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None)
    core, dispatcher, context, _session_id, turn_id = await _interaction_context(db_session)

    pending = await dispatcher.dispatch(
        tool_name="ask_user",
        input={
            "questions": [
                {
                    "question": "Which database?",
                    "header": "DB",
                    "options": [
                        {"label": "Postgres", "description": "Relational", "recommended": True},
                        {"label": "SQLite", "description": "Embedded"},
                    ],
                }
            ]
        },
        context=context,
        # bypass would normally auto-allow, but interaction tools always pause.
        permission_mode="bypass",
    )
    assert pending.status == "waiting_decision"
    assert pending.permission_decision["decision"] == "ask"

    # The waiting_decision event carries the questions so the UI can render
    # without a second fetch.
    events = await core.list_events_for_turn(
        turn_id=turn_id, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    waiting = [e for e in events if e.type == "action.waiting_decision"]
    assert waiting and waiting[-1].payload["name"] == "ask_user"
    assert waiting[-1].payload["interaction"]["kind"] == "user_input"
    assert waiting[-1].payload["interaction"]["questions"][0]["header"] == "DB"
    assert waiting[-1].payload["interaction"]["questions"][0]["options"][0]["recommended"] is True

    decided = await core.decide_action(
        action_id=pending.action_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="answer",
        answer={"DB": "SQLite"},
    )
    assert decided.status == "requested"

    resumed = await dispatcher.resume_action(action_id=pending.action_id, context=context)
    assert resumed.status == "completed"
    assert resumed.result == {"answers": {"DB": "SQLite"}}


@pytest.mark.asyncio
async def test_exit_plan_mode_flips_session_to_execution_on_approve(db_session, monkeypatch):
    monkeypatch.setattr("app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None)
    core, dispatcher, context, session_id, _turn_id = await _interaction_context(
        db_session, mode="plan"
    )

    session = await core.session_repo.get(session_id)
    assert session.toolset_policy == {"name": "plan"}

    pending = await dispatcher.dispatch(
        tool_name="exit_plan_mode",
        input={"plan": "1. Read code\n2. Make the change\n3. Run tests"},
        context=context,
        permission_mode="bypass",
    )
    assert pending.status == "waiting_decision"

    decided = await core.decide_action(
        action_id=pending.action_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )
    assert decided.status == "requested"

    # Toolset must flip to execution BEFORE resume so the resume worker sees it.
    session = await core.session_repo.get(session_id)
    assert session.toolset_policy == {"name": "execution"}

    resumed = await dispatcher.resume_action(action_id=pending.action_id, context=context)
    assert resumed.status == "completed"
    assert resumed.result == {"approved": True}
