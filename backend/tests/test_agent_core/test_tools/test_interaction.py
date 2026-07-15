from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agent_core import AgentActionStatus
from app.models.workspace import Workspace
from app.repositories.agent_core_repo import AgentActionRepository, AgentEventRepository
from app.services.agent_core import AgentCoreService
from app.services.agent_core.tools import (
    AgentToolContext,
    AgentToolDispatcher,
    build_default_tool_registry,
)
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.services.agent_core.tools.specs import AgentToolSpec
from app.utils.exceptions import ConflictError
from app.workspace import DEFAULT_WORKSPACE_ID


class _CountingApprovalTool:
    spec = AgentToolSpec(
        name="count_approved_execution",
        description="Count executions of an approved side effect.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={
            "type": "object",
            "properties": {"execution": {"type": "integer"}},
            "required": ["execution"],
            "additionalProperties": False,
        },
        risk_level="act_high",
        write_scope=["test-counter"],
    )

    def __init__(self) -> None:
        self.execution_count = 0

    async def run(self, input, context):
        del input, context
        self.execution_count += 1
        execution = self.execution_count
        await asyncio.sleep(0.05)
        return {"execution": execution}


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
    events = await core.list_events_for_turn(
        turn_id=turn_id, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    decisions = [e for e in events if e.type == "action.decision_recorded"]
    assert decisions and decisions[-1].payload["answer"] == {"DB": "SQLite"}

    resumed = await dispatcher.resume_action(action_id=pending.action_id, context=context)
    assert resumed.status == "completed"
    assert resumed.result == {"answers": {"DB": "SQLite"}}


@pytest.mark.asyncio
async def test_ask_user_truncates_overlong_question_header(db_session, monkeypatch):
    monkeypatch.setattr("app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None)
    core, dispatcher, context, _session_id, turn_id = await _interaction_context(db_session)

    pending = await dispatcher.dispatch(
        tool_name="ask_user",
        input={
            "questions": [
                {
                    "question": "Which files should I inspect next?",
                    "header": "需要确认的问题和下一步操作",
                    "options": [
                        {"label": "Continue", "description": "Inspect remote files"},
                        {"label": "Stop", "description": "Wait for more context"},
                    ],
                }
            ]
        },
        context=context,
        permission_mode="bypass",
    )

    assert pending.status == "waiting_decision"
    assert pending.error is None
    events = await core.list_events_for_turn(
        turn_id=turn_id, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    waiting = [e for e in events if e.type == "action.waiting_decision"]
    assert waiting[-1].payload["interaction"]["questions"][0]["header"] == "需要确认的问题和下一步操"


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


@pytest.mark.asyncio
async def test_concurrent_restart_workers_execute_approved_action_once(
    db_engine,
    db_session,
    monkeypatch,
):
    monkeypatch.setattr("app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None)
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()

    core = AgentCoreService(db_session)
    session = await core.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        title="Concurrent approval resume",
        toolset_policy={"name": "execution"},
    )
    turn = await core.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Run the approved side effect exactly once.",
    )
    tool = _CountingApprovalTool()
    registry = AgentToolRegistry()
    registry.register(tool)
    initial_dispatcher = AgentToolDispatcher(db_session, registry)
    context_data = {
        "workspace_id": DEFAULT_WORKSPACE_ID,
        "user_id": "dev",
        "session_id": str(session.id),
        "turn_id": str(turn.id),
    }

    pending = await initial_dispatcher.dispatch(
        tool_name=tool.spec.name,
        input={},
        context=AgentToolContext(db=db_session, **context_data),
        permission_mode="ask_each_action",
    )
    assert pending.status == AgentActionStatus.WAITING_DECISION
    decided = await core.decide_action(
        action_id=pending.action_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )
    assert decided.status == AgentActionStatus.REQUESTED
    assert decided.requires_resume is True

    original_get = AgentActionRepository.get
    both_workers_loaded = asyncio.Event()
    load_lock = asyncio.Lock()
    loaded_workers = 0

    async def synchronized_requested_get(repo, action_id):
        nonlocal loaded_workers
        action = await original_get(repo, action_id)
        if (
            action is not None
            and action.status == AgentActionStatus.REQUESTED
            and action.requires_resume
        ):
            async with load_lock:
                loaded_workers += 1
                if loaded_workers == 2:
                    both_workers_loaded.set()
            await asyncio.wait_for(both_workers_loaded.wait(), timeout=1)
        return action

    monkeypatch.setattr(AgentActionRepository, "get", synchronized_requested_get)
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async def resume_from_fresh_worker():
        async with session_factory() as worker_session:
            dispatcher = AgentToolDispatcher(worker_session, registry)
            return await dispatcher.resume_action(
                action_id=pending.action_id,
                context=AgentToolContext(db=worker_session, **context_data),
            )

    worker_results = await asyncio.gather(
        resume_from_fresh_worker(),
        resume_from_fresh_worker(),
    )

    assert tool.execution_count == 1
    assert sum(result.status == AgentActionStatus.COMPLETED for result in worker_results) == 1
    loser = next(
        result
        for result in worker_results
        if result.status != AgentActionStatus.COMPLETED
    )
    assert loser.status == AgentActionStatus.FAILED
    assert loser.error["type"] == "ActionAlreadyClaimed"
    async with session_factory() as verification_session:
        action = await AgentActionRepository(verification_session).get(pending.action_id)
        assert action is not None
        assert action.status == AgentActionStatus.COMPLETED
        events = await AgentEventRepository(verification_session).list_for_turn(
            turn_id=str(turn.id)
        )
    assert sum(event.type == "action.started" for event in events) == 1
    assert sum(event.type == "action.completed" for event in events) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("existing_status", "existing_result"),
    [
        (AgentActionStatus.RUNNING, None),
        (AgentActionStatus.COMPLETED, {"execution": 1}),
    ],
)
async def test_late_restart_worker_observes_existing_resume_without_execution(
    db_engine,
    db_session,
    monkeypatch,
    existing_status,
    existing_result,
):
    monkeypatch.setattr("app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None)
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()
    core = AgentCoreService(db_session)
    session = await core.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        toolset_policy={"name": "execution"},
    )
    turn = await core.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Resume once.",
    )
    tool = _CountingApprovalTool()
    registry = AgentToolRegistry()
    registry.register(tool)
    context_data = {
        "workspace_id": DEFAULT_WORKSPACE_ID,
        "user_id": "dev",
        "session_id": str(session.id),
        "turn_id": str(turn.id),
    }
    pending = await AgentToolDispatcher(db_session, registry).dispatch(
        tool_name=tool.spec.name,
        input={},
        context=AgentToolContext(db=db_session, **context_data),
        permission_mode="ask_each_action",
    )
    decided = await core.decide_action(
        action_id=pending.action_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )
    await AgentActionRepository(db_session).update_all(
        decided,
        status=existing_status,
        result=existing_result,
        requires_resume=False,
        started_at=datetime.now(timezone.utc),
        completed_at=(
            datetime.now(timezone.utc)
            if existing_status == AgentActionStatus.COMPLETED
            else None
        ),
    )
    before_events = await AgentEventRepository(db_session).list_for_turn(
        turn_id=str(turn.id)
    )
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with session_factory() as worker_session:
        observed = await AgentToolDispatcher(worker_session, registry).resume_action(
            action_id=pending.action_id,
            context=AgentToolContext(db=worker_session, **context_data),
        )

    assert observed.status == existing_status
    assert observed.result == existing_result
    assert tool.execution_count == 0
    async with session_factory() as verification_session:
        after_events = await AgentEventRepository(verification_session).list_for_turn(
            turn_id=str(turn.id)
        )
    assert [event.type for event in after_events] == [
        event.type for event in before_events
    ]


@pytest.mark.asyncio
async def test_resume_rejects_requested_action_that_was_not_marked_for_resume(
    db_session,
    monkeypatch,
):
    monkeypatch.setattr("app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None)
    core, dispatcher, context, _session_id, _turn_id = await _interaction_context(db_session)
    pending = await dispatcher.dispatch(
        tool_name="ask_user",
        input={"questions": []},
        context=context,
        permission_mode="bypass",
    )
    action = await AgentActionRepository(db_session).get(pending.action_id)
    assert action is not None
    await AgentActionRepository(db_session).update_all(
        action,
        status=AgentActionStatus.REQUESTED,
        requires_resume=False,
        permission_decision={"decision": "approve"},
    )

    with pytest.raises(ConflictError, match="not awaiting resume"):
        await dispatcher.resume_action(action_id=pending.action_id, context=context)


@pytest.mark.asyncio
async def test_action_claim_refuses_to_commit_unrelated_pending_writes(
    db_engine,
    db_session,
    monkeypatch,
):
    monkeypatch.setattr("app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None)
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()
    core = AgentCoreService(db_session)
    session = await core.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        toolset_policy={"name": "execution"},
    )
    turn = await core.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Resume safely.",
    )
    tool = _CountingApprovalTool()
    registry = AgentToolRegistry()
    registry.register(tool)
    pending = await AgentToolDispatcher(db_session, registry).dispatch(
        tool_name=tool.spec.name,
        input={},
        context=AgentToolContext(
            db=db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            session_id=str(session.id),
            turn_id=str(turn.id),
        ),
        permission_mode="ask_each_action",
    )
    await core.decide_action(
        action_id=pending.action_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with session_factory() as worker_session:
        pending_workspace = await worker_session.get(Workspace, DEFAULT_WORKSPACE_ID)
        assert pending_workspace is not None
        pending_workspace.name = "Must not be committed"
        with pytest.raises(RuntimeError, match="clean session"):
            await AgentActionRepository(worker_session).claim_requested_resume(
                pending.action_id,
                started_at=datetime.now(timezone.utc),
            )
        await worker_session.rollback()

    async with session_factory() as verification_session:
        persisted_workspace = await verification_session.get(
            Workspace,
            DEFAULT_WORKSPACE_ID,
        )
        persisted_action = await AgentActionRepository(verification_session).get(
            pending.action_id
        )
    assert persisted_workspace is not None
    assert persisted_workspace.name == "Team"
    assert persisted_action is not None
    assert persisted_action.status == AgentActionStatus.REQUESTED
    assert persisted_action.requires_resume is True
