from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agent_core import AgentActionStatus
from app.models.workspace import Workspace
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentEventRepository,
)
from app.services.agent_core import AgentCoreService
from app.services.agent_core.tools import AgentToolContext, AgentToolSpec
from app.services.agent_core.tools.executor import AgentToolExecutor
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.workspace import DEFAULT_WORKSPACE_ID


async def _create_claimed_turn(db_session):
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    await db_session.commit()
    service = AgentCoreService(db_session)
    agent_session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(agent_session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Fence stale terminal action writes.",
    )
    first_claim = datetime.now(timezone.utc)
    turn = await service.turn_repo.claim_for_run(
        str(turn.id),
        claimed_at=first_claim,
        lease_until=first_claim + timedelta(seconds=1),
    )
    assert turn is not None
    assert turn.claimed_at is not None
    return agent_session, turn, turn.claimed_at


@dataclass
class _BlockingFailureTool:
    started: asyncio.Event
    release: asyncio.Event

    @property
    def spec(self) -> AgentToolSpec:
        return AgentToolSpec(
            name="test.blocking_failure",
            description="Fail only after a successor takes over the parent turn.",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
            risk_level="read",
        )

    async def run(self, input, context):
        del input, context
        self.started.set()
        await self.release.wait()
        raise RuntimeError("old worker failed after ownership changed")


@pytest.mark.asyncio
async def test_stale_tool_exception_cannot_write_terminal_action_state(
    db_session,
    db_engine,
):
    agent_session, turn, first_claim = await _create_claimed_turn(db_session)
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    tool_started = asyncio.Event()
    release_tool = asyncio.Event()
    tool = _BlockingFailureTool(tool_started, release_tool)

    async def run_old_worker():
        async with maker() as old_worker_db:
            registry = AgentToolRegistry()
            registry.register(tool)
            return await AgentToolExecutor(old_worker_db, registry).execute(
                tool_name=tool.spec.name,
                input={},
                context=AgentToolContext(
                    db=old_worker_db,
                    workspace_id=DEFAULT_WORKSPACE_ID,
                    user_id="dev",
                    session_id=str(agent_session.id),
                    turn_id=str(turn.id),
                    turn_claimed_at=first_claim,
                ),
                toolset_policy={"name": "execution"},
                execution_target={"type": "local"},
                expected_execution_target={"type": "local"},
            )

    old_worker = asyncio.create_task(run_old_worker())
    await tool_started.wait()

    recovery_claim = first_claim + timedelta(seconds=2)
    async with maker() as recovery_db:
        recovered = await AgentCoreService(
            recovery_db
        ).turn_repo.claim_expired_for_recovery(
            str(turn.id),
            expected_claimed_at=first_claim,
            claimed_at=recovery_claim,
            lease_until=recovery_claim + timedelta(minutes=5),
        )
        assert recovered is not None

    release_tool.set()
    old_result = await old_worker

    async with maker() as inspect_db:
        actions = await AgentActionRepository(inspect_db).list_for_turn(str(turn.id))
        events = await AgentEventRepository(inspect_db).list_for_turn(
            turn_id=str(turn.id),
            after_seq=0,
        )

    assert len(actions) == 1
    assert actions[0].status == AgentActionStatus.RUNNING
    assert actions[0].error is None
    assert actions[0].result is None
    assert old_result.status == AgentActionStatus.RUNNING
    assert old_result.error is None
    assert all(event.type != "action.failed" for event in events)

