from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agent_core import (
    AgentActionStatus,
    AgentToolCallBatchStatus,
    AgentTurnStatus,
)
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentEventRepository,
    AgentSessionRepository,
    AgentToolCallBatchRepository,
    AgentTurnRepository,
)
from app.services.agent_core import AgentCoreService
from app.services.agent_core.core.lease import LEASE_LOSS_CANCELLATION
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.permissions.risk import RiskAssessment
from app.services.agent_core.tools import (
    AgentToolContext,
    AgentToolDispatcher,
    build_default_tool_registry,
)
from app.services.agent_core.tools.execution import ExecuteShellTool
from app.utils.exceptions import ConflictError
from app.workspace import DEFAULT_WORKSPACE_ID


async def _seed_session_turn(db_session):
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        permission_mode="guarded_auto",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Exercise approval concurrency.",
    )
    return session, turn


@pytest.mark.asyncio
async def test_concurrent_identical_decisions_are_idempotent_and_wake_once(
    db_session, monkeypatch
):
    session, turn = await _seed_session_turn(db_session)
    action = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        kind="tool",
        name="bash",
        input={"command": "printf approved"},
        normalized_input={"command": "printf approved"},
        risk_level="act_high",
        permission_decision={"decision": "ask"},
        status=AgentActionStatus.WAITING_DECISION,
    )
    wakeups: list[str] = []
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume",
        lambda action_id, *_: wakeups.append(action_id),
    )
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as first, maker() as second:
        results = await asyncio.gather(
            AgentCoreService(first).decide_action(
                action_id=str(action.id),
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                decision="approve",
                note="same",
            ),
            AgentCoreService(second).decide_action(
                action_id=str(action.id),
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                decision="approve",
                note="same",
            ),
        )

    assert {result.status for result in results} == {AgentActionStatus.REQUESTED}
    assert wakeups == [str(action.id)]
    events = await AgentEventRepository(db_session).list_for_turn(turn_id=str(turn.id))
    assert Counter(event.type for event in events)["action.decision_recorded"] == 1


@pytest.mark.asyncio
async def test_conflicting_duplicate_decision_returns_stable_conflict(db_session):
    session, turn = await _seed_session_turn(db_session)
    action = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        kind="tool",
        name="bash",
        input={"command": "printf approved"},
        risk_level="act_high",
        permission_decision={"decision": "ask"},
        status=AgentActionStatus.WAITING_DECISION,
    )
    await AgentCoreService(db_session).decide_action(
        action_id=str(action.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )

    with pytest.raises(ConflictError, match="already has a different decision"):
        await AgentCoreService(db_session).decide_action(
            action_id=str(action.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            decision="reject",
        )


@pytest.mark.asyncio
async def test_decision_api_replays_identical_request_and_conflicts_on_change(
    async_client, db_session, monkeypatch
):
    created = (await async_client.post("/api/v1/agent/sessions", json={})).json()[
        "data"
    ]
    turn = await AgentCoreService(db_session).create_turn_record(
        session_id=created["id"],
        workspace_id=created["workspace_id"],
        user_id=created["user_id"],
        input_text="Replay one decision.",
    )
    action = await AgentActionRepository(db_session).create(
        session_id=created["id"],
        turn_id=str(turn.id),
        kind="tool",
        name="bash",
        input={"command": "printf approved"},
        risk_level="act_high",
        permission_decision={"decision": "ask"},
        status=AgentActionStatus.WAITING_DECISION,
    )
    wakeups: list[str] = []
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume",
        lambda action_id, *_: wakeups.append(action_id),
    )

    first = await async_client.post(
        f"/api/v1/agent/actions/{action.id}/decision",
        json={"decision": "approve", "note": "stable"},
    )
    replay = await async_client.post(
        f"/api/v1/agent/actions/{action.id}/decision",
        json={"decision": "approve", "note": "stable"},
    )
    conflict = await async_client.post(
        f"/api/v1/agent/actions/{action.id}/decision",
        json={"decision": "reject", "note": "changed"},
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert conflict.status_code == 409
    assert "already has a different decision" in conflict.json()["error"]["message"]
    assert wakeups == [str(action.id)]


@pytest.mark.asyncio
async def test_two_workers_claim_requested_action_before_side_effect(
    db_session, monkeypatch
):
    session, turn = await _seed_session_turn(db_session)
    action = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        kind="tool",
        name="bash",
        input={"command": "printf once"},
        normalized_input={"command": "printf once"},
        risk_level="act_high",
        permission_decision={"decision": "approve"},
        status=AgentActionStatus.REQUESTED,
        requires_resume=True,
    )
    side_effects = 0
    entered = asyncio.Event()
    release = asyncio.Event()

    async def counted_run(self, input, context):
        del self, input, context
        nonlocal side_effects
        side_effects += 1
        entered.set()
        await release.wait()
        return {
            "exit_code": 0,
            "stdout": "once",
            "stderr": "",
            "cwd": ".",
            "command": "printf once",
        }

    monkeypatch.setattr(ExecuteShellTool, "run", counted_run)
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )

    async def resume(worker: AsyncSession):
        return await AgentToolDispatcher(
            worker, build_default_tool_registry()
        ).resume_action(
            action_id=str(action.id),
            context=AgentToolContext(
                db=worker,
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                session_id=str(session.id),
                turn_id=str(turn.id),
            ),
        )

    async with maker() as first, maker() as second:
        first_task = asyncio.create_task(resume(first))
        await entered.wait()
        second_result = await resume(second)
        release.set()
        first_result = await first_task

    assert side_effects == 1
    assert {first_result.status, second_result.status} <= {
        AgentActionStatus.RUNNING,
        AgentActionStatus.COMPLETED,
    }
    events = await AgentEventRepository(db_session).list_for_turn(turn_id=str(turn.id))
    assert Counter(event.type for event in events)["action.started"] == 1


@pytest.mark.asyncio
async def test_cross_session_cancel_wins_over_running_tool_completion(
    db_session, monkeypatch
):
    session, turn = await _seed_session_turn(db_session)
    action = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        kind="tool",
        name="bash",
        input={"command": "printf too-late"},
        normalized_input={"command": "printf too-late"},
        risk_level="act_high",
        permission_decision={"decision": "approve", "source": "user"},
        status=AgentActionStatus.REQUESTED,
        requires_resume=True,
    )
    entered = asyncio.Event()
    release = asyncio.Event()

    async def delayed_run(self, input, context):
        del self, input, context
        entered.set()
        await release.wait()
        return {
            "exit_code": 0,
            "stdout": "too late",
            "stderr": "",
            "cwd": ".",
            "command": "printf too-late",
        }

    monkeypatch.setattr(ExecuteShellTool, "run", delayed_run)
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as worker, maker() as canceller:
        worker_task = asyncio.create_task(
            AgentToolDispatcher(worker, build_default_tool_registry()).resume_action(
                action_id=str(action.id),
                context=AgentToolContext(
                    db=worker,
                    workspace_id=DEFAULT_WORKSPACE_ID,
                    user_id="dev",
                    session_id=str(session.id),
                    turn_id=str(turn.id),
                ),
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=1)
        running = await AgentActionRepository(canceller).get_fresh(str(action.id))
        assert running.status == AgentActionStatus.RUNNING
        await AgentActionRepository(canceller).update_all(
            running,
            status=AgentActionStatus.CANCELLED,
            error={"type": "CancelledError", "message": "cancelled externally"},
        )
        release.set()
        result = await asyncio.wait_for(worker_task, timeout=2)

    async with maker() as observer:
        current = await AgentActionRepository(observer).get_fresh(str(action.id))
        events = await AgentEventRepository(observer).list_for_turn(
            turn_id=str(turn.id)
        )

    assert result.status == AgentActionStatus.CANCELLED
    assert current.status == AgentActionStatus.CANCELLED
    assert Counter(event.type for event in events)["action.completed"] == 0
    assert Counter(event.type for event in events)["action.failed"] == 0


@pytest.mark.asyncio
async def test_lease_loss_leaves_running_action_for_recovery(
    db_session, monkeypatch
):
    session, turn = await _seed_session_turn(db_session)
    owner_token = "execution-owner"
    await AgentTurnRepository(db_session).update_all(
        turn,
        status=AgentTurnStatus.RUNNING,
        owner_token=owner_token,
        lease_until=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    action = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        kind="tool",
        name="bash",
        input={"command": "printf fenced"},
        normalized_input={"command": "printf fenced"},
        risk_level="act_high",
        permission_decision={"decision": "approve", "source": "user"},
        status=AgentActionStatus.REQUESTED,
        requires_resume=True,
    )
    entered = asyncio.Event()

    async def blocked_run(self, input, context):
        del self, input, context
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(ExecuteShellTool, "run", blocked_run)
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as worker, maker() as takeover:
        worker_task = asyncio.create_task(
            AgentToolDispatcher(worker, build_default_tool_registry()).resume_action(
                action_id=str(action.id),
                context=AgentToolContext(
                    db=worker,
                    workspace_id=DEFAULT_WORKSPACE_ID,
                    user_id="dev",
                    session_id=str(session.id),
                    turn_id=str(turn.id),
                    expected_owner_token=owner_token,
                ),
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=1)
        replacement = await AgentTurnRepository(takeover).get_fresh(str(turn.id))
        await AgentTurnRepository(takeover).update_all(
            replacement,
            owner_token="replacement-owner",
            lease_until=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        worker_task.cancel(LEASE_LOSS_CANCELLATION)
        with pytest.raises(asyncio.CancelledError):
            await worker_task

        running = await AgentActionRepository(takeover).get_fresh(str(action.id))
        assert running.status == AgentActionStatus.RUNNING
        summary = await AgentCoreService(takeover).recover_orphaned_turns()
        reconciled = await AgentActionRepository(takeover).get_fresh(str(action.id))
        recovered_turn = await AgentTurnRepository(takeover).get_fresh(str(turn.id))

    assert summary["failed"] == 1
    assert reconciled.status == AgentActionStatus.CANCELLED
    assert recovered_turn.status == AgentTurnStatus.FAILED
    assert recovered_turn.error_code == "recovery_inflight_action"


@pytest.mark.asyncio
async def test_stale_owner_cannot_complete_tool_that_swallows_lease_loss(
    db_session, monkeypatch
):
    session, turn = await _seed_session_turn(db_session)
    owner_token = "execution-owner"
    await AgentTurnRepository(db_session).update_all(
        turn,
        status=AgentTurnStatus.RUNNING,
        owner_token=owner_token,
        lease_until=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    action = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        kind="tool",
        name="bash",
        input={"command": "printf swallowed"},
        normalized_input={"command": "printf swallowed"},
        risk_level="act_high",
        permission_decision={"decision": "approve", "source": "user"},
        status=AgentActionStatus.REQUESTED,
        requires_resume=True,
    )
    entered = asyncio.Event()

    async def swallowing_run(self, input, context):
        del self, input, context
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        return {
            "exit_code": 0,
            "stdout": "too late",
            "stderr": "",
            "cwd": ".",
            "command": "printf swallowed",
        }

    monkeypatch.setattr(ExecuteShellTool, "run", swallowing_run)
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as worker, maker() as takeover:
        worker_task = asyncio.create_task(
            AgentToolDispatcher(worker, build_default_tool_registry()).resume_action(
                action_id=str(action.id),
                context=AgentToolContext(
                    db=worker,
                    workspace_id=DEFAULT_WORKSPACE_ID,
                    user_id="dev",
                    session_id=str(session.id),
                    turn_id=str(turn.id),
                    expected_owner_token=owner_token,
                ),
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=1)
        replacement = await AgentTurnRepository(takeover).get_fresh(str(turn.id))
        await AgentTurnRepository(takeover).update_all(
            replacement,
            owner_token="replacement-owner",
            lease_until=datetime.now(timezone.utc) + timedelta(minutes=1),
        )
        worker_task.cancel(LEASE_LOSS_CANCELLATION)
        result = await asyncio.wait_for(worker_task, timeout=2)
        current = await AgentActionRepository(takeover).get_fresh(str(action.id))
        events = await AgentEventRepository(takeover).list_for_turn(
            turn_id=str(turn.id)
        )

    assert result.status == AgentActionStatus.RUNNING
    assert current.status == AgentActionStatus.RUNNING
    assert Counter(event.type for event in events)["action.completed"] == 0
    assert Counter(event.type for event in events)["action.failed"] == 0
    assert Counter(event.type for event in events)["action.cancelled"] == 0


@pytest.mark.asyncio
async def test_owner_fenced_action_transition_locks_turn_before_action_update(
    db_session,
):
    session, turn = await _seed_session_turn(db_session)
    owner_token = "execution-owner"
    await AgentTurnRepository(db_session).update_all(
        turn,
        status=AgentTurnStatus.RUNNING,
        owner_token=owner_token,
        lease_until=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    action = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        kind="tool",
        name="bash",
        input={"command": "printf locked"},
        normalized_input={"command": "printf locked"},
        risk_level="act_high",
        status=AgentActionStatus.RUNNING,
    )
    statements: list[str] = []

    def record_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(" ".join(statement.lower().split()))

    sqlalchemy_event.listen(
        db_session.bind.sync_engine,
        "before_cursor_execute",
        record_sql,
    )
    try:
        completed = await AgentActionRepository(db_session).transition_running(
            str(action.id),
            status=AgentActionStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
            expected_turn_owner_token=owner_token,
        )
        await db_session.commit()
    finally:
        sqlalchemy_event.remove(
            db_session.bind.sync_engine,
            "before_cursor_execute",
            record_sql,
        )

    turn_lock_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.startswith("update agent_turns")
            and "owner_token" in statement
        and "status" in statement
    )
    action_update_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.startswith("update agent_actions")
    )
    assert completed is not None
    assert turn_lock_index < action_update_index


@pytest.mark.asyncio
async def test_owner_fenced_action_transaction_serializes_replacement_claim(
    db_session,
):
    session, turn = await _seed_session_turn(db_session)
    owner_token = "execution-owner"
    await AgentTurnRepository(db_session).update_all(
        turn,
        status=AgentTurnStatus.RUNNING,
        owner_token=owner_token,
        lease_until=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    action = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        kind="tool",
        name="bash",
        input={"command": "printf serialized"},
        risk_level="act_high",
        status=AgentActionStatus.RUNNING,
    )
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as stale_worker, maker() as replacement_worker:
        completed = await AgentActionRepository(stale_worker).transition_running(
            str(action.id),
            status=AgentActionStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
            expected_turn_owner_token=owner_token,
        )
        replacement_claim = asyncio.create_task(
            AgentTurnRepository(replacement_worker).claim_execution(
                str(turn.id),
                owner_token="replacement-owner",
                claimed_at=datetime.now(timezone.utc),
                lease_until=datetime.now(timezone.utc) + timedelta(minutes=1),
            )
        )
        await asyncio.sleep(0.05)
        assert not replacement_claim.done()

        await stale_worker.commit()
        replacement = await asyncio.wait_for(replacement_claim, timeout=2)

    assert completed is not None
    assert replacement is not None
    assert replacement.owner_token == "replacement-owner"


@pytest.mark.asyncio
async def test_stale_owner_cannot_fail_or_cancel_open_actions(db_session):
    session, turn = await _seed_session_turn(db_session)
    await AgentTurnRepository(db_session).update_all(
        turn,
        status=AgentTurnStatus.RUNNING,
        owner_token="replacement-owner",
        lease_until=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    failed_candidate = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        kind="tool",
        name="bash",
        input={"command": "printf fail"},
        risk_level="act_high",
        status=AgentActionStatus.REQUESTED,
    )
    cancelled_candidate = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        kind="tool",
        name="bash",
        input={"command": "printf cancel"},
        risk_level="act_high",
        status=AgentActionStatus.RUNNING,
    )
    failed_candidate_id = str(failed_candidate.id)
    cancelled_candidate_id = str(cancelled_candidate.id)
    repo = AgentActionRepository(db_session)

    failed = await repo.fail_requested(
        failed_candidate_id,
        error={"type": "test", "message": "stale"},
        completed_at=datetime.now(timezone.utc),
        expected_turn_owner_token="stale-owner",
    )
    await db_session.rollback()
    cancelled = await repo.cancel_open(
        cancelled_candidate_id,
        error={"type": "test", "message": "stale"},
        completed_at=datetime.now(timezone.utc),
        expected_turn_owner_token="stale-owner",
    )
    await db_session.rollback()

    assert failed is None
    assert cancelled is None
    assert (
        await repo.get_fresh(failed_candidate_id)
    ).status == AgentActionStatus.REQUESTED
    assert (
        await repo.get_fresh(cancelled_candidate_id)
    ).status == AgentActionStatus.RUNNING


@pytest.mark.asyncio
async def test_requested_action_rechecks_fresh_catastrophic_hard_block(
    db_session, monkeypatch
):
    session, turn = await _seed_session_turn(db_session)
    action = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        kind="tool",
        name="bash",
        input={"command": "rm -rf /"},
        normalized_input={"command": "rm -rf /"},
        risk_level="act_high",
        permission_decision={"decision": "approve"},
        status=AgentActionStatus.REQUESTED,
        requires_resume=True,
    )
    side_effects = 0

    async def forbidden_run(self, input, context):
        del self, input, context
        nonlocal side_effects
        side_effects += 1
        return {}

    monkeypatch.setattr(ExecuteShellTool, "run", forbidden_run)
    result = await AgentToolDispatcher(
        db_session, build_default_tool_registry()
    ).resume_action(
        action_id=str(action.id),
        context=AgentToolContext(
            db=db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            session_id=str(session.id),
            turn_id=str(turn.id),
        ),
    )

    assert result.status == AgentActionStatus.FAILED
    assert result.error["type"] == "PermissionDeniedError"
    assert "hard-blocked" in result.error["message"]
    assert side_effects == 0


@pytest.mark.asyncio
async def test_requested_action_rechecks_fresh_policy_before_side_effect_claim(
    db_session, monkeypatch
):
    session, turn = await _seed_session_turn(db_session)
    action = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        kind="tool",
        name="bash",
        input={"command": "touch policy-recheck"},
        normalized_input={"command": "touch policy-recheck"},
        risk_level="act_high",
        permission_decision={"decision": "allow", "source": "policy"},
        evaluated_policy_version=session.permission_policy_version,
        status=AgentActionStatus.REQUESTED,
        requires_resume=True,
    )
    await AgentCoreService(db_session).update_session(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        updates={"permission_mode": "ask_each_action"},
    )
    side_effects = 0

    async def forbidden_run(self, input, context):
        del self, input, context
        nonlocal side_effects
        side_effects += 1
        return {}

    monkeypatch.setattr(ExecuteShellTool, "run", forbidden_run)
    result = await AgentToolDispatcher(
        db_session, build_default_tool_registry()
    ).resume_action(
        action_id=str(action.id),
        context=AgentToolContext(
            db=db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            session_id=str(session.id),
            turn_id=str(turn.id),
        ),
    )

    assert result.status == AgentActionStatus.WAITING_DECISION
    assert side_effects == 0
    refreshed = await AgentActionRepository(db_session).get_fresh(str(action.id))
    assert refreshed.requires_resume is True
    assert refreshed.evaluated_policy_version == 2
    assert refreshed.permission_decision["decision"] == "ask"


@pytest.mark.asyncio
async def test_requested_action_requires_real_user_approval_when_risk_demands_it(
    db_session, monkeypatch
):
    session, turn = await _seed_session_turn(db_session)
    action = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        kind="tool",
        name="bash",
        input={"command": "touch explicit-approval"},
        normalized_input={"command": "touch explicit-approval"},
        risk_level="act_low",
        permission_decision={"decision": "allow", "source": "policy"},
        evaluated_policy_version=session.permission_policy_version,
        status=AgentActionStatus.REQUESTED,
        requires_resume=True,
    )
    side_effects = 0

    def require_explicit_approval(self, input, *, target=None):
        del self, input, target
        return RiskAssessment(
            level="act_high",
            reasons=["protected resource requires explicit approval"],
            requires_explicit_approval=True,
        )

    async def forbidden_run(self, input, context):
        del self, input, context
        nonlocal side_effects
        side_effects += 1
        return {}

    monkeypatch.setattr(ExecuteShellTool, "assess_risk", require_explicit_approval)
    monkeypatch.setattr(ExecuteShellTool, "run", forbidden_run)
    result = await AgentToolDispatcher(
        db_session, build_default_tool_registry()
    ).resume_action(
        action_id=str(action.id),
        context=AgentToolContext(
            db=db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            session_id=str(session.id),
            turn_id=str(turn.id),
        ),
    )

    assert result.status == AgentActionStatus.WAITING_DECISION
    assert side_effects == 0


@pytest.mark.asyncio
async def test_policy_row_lock_serializes_pending_reconciliation(db_session):
    session, _turn = await _seed_session_turn(db_session)
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as preparing, maker() as updating:
        locked = await AgentSessionRepository(preparing).lock_policy(str(session.id))
        assert locked.permission_policy_version == 1

        update_task = asyncio.create_task(
            AgentCoreService(updating).update_session(
                session_id=str(session.id),
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                updates={
                    "permission_mode": "bypass",
                    "pending_strategy": "approve_pending_tools",
                },
            )
        )
        await asyncio.sleep(0.05)
        assert update_task.done() is False
        await preparing.rollback()
        updated = await update_task

    assert updated.permission_policy_version == 2


@pytest.mark.asyncio
async def test_locked_batch_action_cannot_commit_after_bulk_reconciliation(
    db_session, monkeypatch
):
    session, turn = await _seed_session_turn(db_session)
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )
    wakeups: list[str] = []
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume",
        lambda action_id, *_: wakeups.append(action_id),
    )

    async with maker() as preparing, maker() as updating:
        locked = await AgentSessionRepository(preparing).lock_policy(str(session.id))
        batch = await AgentToolCallBatchRepository(preparing).add(
            session_id=str(session.id),
            turn_id=str(turn.id),
            status=AgentToolCallBatchStatus.WAITING,
            tool_call_count=1,
            batch_ordinal=1,
        )
        action = await AgentActionRepository(preparing).add(
            session_id=str(session.id),
            turn_id=str(turn.id),
            tool_batch_id=str(batch.id),
            tool_call_ordinal=0,
            tool_call_id="locked-policy-action",
            kind="tool",
            name="bash",
            input={"command": "printf locked"},
            normalized_input={"command": "printf locked"},
            risk_level="act_high",
            permission_decision={"decision": "ask", "source": "policy"},
            evaluated_policy_version=locked.permission_policy_version,
            status=AgentActionStatus.WAITING_DECISION,
        )
        update_task = asyncio.create_task(
            AgentCoreService(updating).update_session(
                session_id=str(session.id),
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                updates={
                    "permission_mode": "bypass",
                    "pending_strategy": "approve_pending_tools",
                },
            )
        )
        await asyncio.sleep(0.05)
        assert update_task.done() is False
        await preparing.commit()
        updated = await update_task

    async with maker() as observer:
        refreshed = await AgentActionRepository(observer).get_fresh(str(action.id))
    assert updated.pending_reconciliation["affected_count"] == 1
    assert refreshed.status == AgentActionStatus.REQUESTED
    assert wakeups == [str(action.id)]


@pytest.mark.asyncio
async def test_pending_strategy_reconciles_legacy_waiting_tool_without_batch(
    db_session, monkeypatch
):
    session, turn = await _seed_session_turn(db_session)
    action = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        kind="tool",
        name="bash",
        input={"command": "printf legacy"},
        normalized_input={"command": "printf legacy"},
        risk_level="act_high",
        permission_decision={"decision": "ask"},
        evaluated_policy_version=session.permission_policy_version,
        status=AgentActionStatus.WAITING_DECISION,
    )
    wakeups: list[str] = []
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume",
        lambda action_id, *_: wakeups.append(action_id),
    )

    updated = await AgentCoreService(db_session).update_session(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        updates={
            "permission_mode": "bypass",
            "pending_strategy": "approve_pending_tools",
        },
    )

    assert updated.pending_reconciliation == {
        "affected_count": 1,
        "excluded_count": 0,
        "already_resolved_count": 0,
    }
    assert (
        await AgentActionRepository(db_session).get_fresh(str(action.id))
    ).status == AgentActionStatus.REQUESTED
    assert wakeups == [str(action.id)]


@pytest.mark.asyncio
async def test_pending_strategy_defaults_future_only_and_approves_eligible_active_batch(
    async_client, db_session, monkeypatch
):
    created = (
        await async_client.post(
            "/api/v1/agent/sessions", json={"permission_mode": "guarded_auto"}
        )
    ).json()["data"]
    service = AgentCoreService(db_session)
    turn = await service.create_turn_record(
        session_id=created["id"],
        workspace_id=created["workspace_id"],
        user_id=created["user_id"],
        input_text="Reconcile active approvals.",
    )
    batch = await AgentToolCallBatchRepository(db_session).create(
        session_id=created["id"],
        turn_id=str(turn.id),
        status=AgentToolCallBatchStatus.WAITING,
        tool_call_count=4,
        batch_ordinal=1,
    )
    actions = []
    for ordinal, (name, status) in enumerate(
        [
            ("bash", AgentActionStatus.WAITING_DECISION),
            ("ask_user", AgentActionStatus.WAITING_DECISION),
            ("exit_plan_mode", AgentActionStatus.WAITING_DECISION),
            ("bash", AgentActionStatus.REQUESTED),
        ]
    ):
        actions.append(
            await AgentActionRepository(db_session).create(
                session_id=created["id"],
                turn_id=str(turn.id),
                tool_batch_id=str(batch.id),
                tool_call_ordinal=ordinal,
                tool_call_id=f"pending-{ordinal}",
                kind="tool",
                name=name,
                input={"command": "printf ok"} if name == "bash" else {},
                risk_level="act_high",
                permission_decision={"decision": "ask"},
                status=status,
            )
        )
    wakeups: list[str] = []
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume",
        lambda action_id, *_: wakeups.append(action_id),
    )

    future = await async_client.patch(
        f"/api/v1/agent/sessions/{created['id']}",
        json={"permission_mode": "bypass"},
    )
    assert future.status_code == 200
    assert future.json()["data"]["pending_strategy"] == "future_only"
    assert future.json()["data"]["pending_reconciliation"] == {
        "affected_count": 0,
        "excluded_count": 0,
        "already_resolved_count": 0,
    }
    assert (
        await AgentActionRepository(db_session).get_fresh(str(actions[0].id))
    ).status == AgentActionStatus.WAITING_DECISION

    approve = await async_client.patch(
        f"/api/v1/agent/sessions/{created['id']}",
        json={
            "permission_mode": "bypass",
            "pending_strategy": "approve_pending_tools",
        },
    )
    assert approve.status_code == 200
    data = approve.json()["data"]
    assert data["permission_policy_version"] == 2
    assert data["pending_strategy"] == "approve_pending_tools"
    assert data["pending_reconciliation"] == {
        "affected_count": 1,
        "excluded_count": 2,
        "already_resolved_count": 1,
    }
    assert (
        await AgentActionRepository(db_session).get_fresh(str(actions[0].id))
    ).status == AgentActionStatus.REQUESTED
    assert wakeups == [str(actions[0].id)]


@pytest.mark.asyncio
async def test_pending_policy_update_and_reconciliation_roll_back_together(
    db_session, monkeypatch
):
    session, turn = await _seed_session_turn(db_session)
    batch = await AgentToolCallBatchRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        status=AgentToolCallBatchStatus.WAITING,
        tool_call_count=1,
        batch_ordinal=1,
    )
    action = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        tool_batch_id=str(batch.id),
        tool_call_ordinal=0,
        tool_call_id="atomic",
        kind="tool",
        name="bash",
        input={"command": "printf ok"},
        risk_level="act_high",
        permission_decision={"decision": "ask"},
        status=AgentActionStatus.WAITING_DECISION,
    )

    async def fail_event(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("ledger unavailable")

    service = AgentCoreService(db_session)
    session_id = str(session.id)
    action_id = str(action.id)
    monkeypatch.setattr(service.ledger, "append", fail_event)
    with pytest.raises(RuntimeError, match="ledger unavailable"):
        await service.update_session(
            session_id=session_id,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            updates={
                "permission_mode": "bypass",
                "pending_strategy": "approve_pending_tools",
            },
        )
    await db_session.rollback()

    assert (
        await service.session_repo.get_fresh(session_id)
    ).permission_mode == "guarded_auto"
    assert (
        await AgentActionRepository(db_session).get_fresh(action_id)
    ).status == AgentActionStatus.WAITING_DECISION


@pytest.mark.asyncio
async def test_transactional_ledger_retry_preserves_outer_state(
    db_session, monkeypatch
):
    session, turn = await _seed_session_turn(db_session)
    session.title = "preserve outer transaction"
    ledger = AgentEventLedger(db_session)
    original_add = ledger.event_repo.add
    attempts = 0

    async def collide_once(**values):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise IntegrityError("duplicate seq", values, Exception("collision"))
        return await original_add(**values)

    monkeypatch.setattr(ledger.event_repo, "add", collide_once)
    await ledger.append(
        session_id=str(session.id),
        turn_id=str(turn.id),
        type="test.transactional_event",
        commit=False,
    )
    await db_session.commit()

    assert attempts == 2
    assert (
        await AgentCoreService(db_session).session_repo.get_fresh(str(session.id))
    ).title == ("preserve outer transaction")
    events = await AgentEventRepository(db_session).list_for_turn(turn_id=str(turn.id))
    assert [event.type for event in events].count("test.transactional_event") == 1
