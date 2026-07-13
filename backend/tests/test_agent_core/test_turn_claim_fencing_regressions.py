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
    AgentArtifactRepository,
    AgentEventRepository,
    AgentTurnRepository,
)
from app.services.agent_core import AgentCoreService
from app.services.agent_core.core import AgentLoopController
from app.services.agent_core.tools import AgentToolContext, AgentToolSpec
from app.services.agent_core.tools.executor import AgentToolExecutor
from app.services.agent_core.tools.platform.projects import ListProjectsTool
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.workspace import DEFAULT_WORKSPACE_ID


async def _claimed_turn(db_session):
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
        input_text="Fence stale turn ownership.",
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
class _BlockingReadArtifactTool:
    started: asyncio.Event
    release: asyncio.Event

    @property
    def spec(self) -> AgentToolSpec:
        return AgentToolSpec(
            name="test.blocking_read_artifact",
            description="Pause a read result before durable action completion.",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={
                "type": "object",
                "properties": {
                    "ok": {"type": "boolean"},
                    "bytes_written": {"type": "integer"},
                },
                "required": ["ok", "bytes_written"],
                "additionalProperties": False,
            },
            risk_level="read",
            artifact_policy={"type": "file"},
        )

    async def run(self, input, context):
        del input, context
        self.started.set()
        await self.release.wait()
        return {"ok": True, "bytes_written": 1}


@pytest.mark.asyncio
async def test_action_completion_after_recovery_takeover_commits_no_aggregate(
    db_session,
    db_engine,
):
    agent_session, turn, first_claim = await _claimed_turn(db_session)
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    tool_started = asyncio.Event()
    successor_claimed = asyncio.Event()
    release_tool = asyncio.Event()
    tool = _BlockingReadArtifactTool(tool_started, release_tool)

    async def run_old_worker():
        async with maker() as old_worker_db:
            registry = AgentToolRegistry()
            registry.register(tool)
            result = await AgentToolExecutor(old_worker_db, registry).execute(
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
            assert successor_claimed.is_set()
            return result

    async def claim_successor():
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
        successor_claimed.set()
        release_tool.set()

    old_result, _ = await asyncio.gather(run_old_worker(), claim_successor())

    async with maker() as inspect_db:
        actions = await AgentActionRepository(inspect_db).list_for_turn(str(turn.id))
        artifacts = await AgentArtifactRepository(inspect_db).list_for_turn(
            str(turn.id)
        )
        events = await AgentEventRepository(inspect_db).list_for_turn(
            turn_id=str(turn.id), after_seq=0
        )

    assert old_result.status == AgentActionStatus.RUNNING
    assert len(actions) == 1
    assert actions[0].status == AgentActionStatus.RUNNING
    assert actions[0].result is None
    assert artifacts == []
    assert all(event.type != "artifact.created" for event in events)
    assert all(event.type != "action.completed" for event in events)


@pytest.mark.asyncio
async def test_isolated_read_only_worker_does_not_adopt_successor_turn_claim(
    db_session,
    db_engine,
    monkeypatch,
):
    agent_session, turn, first_claim = await _claimed_turn(db_session)
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    reload_started = asyncio.Event()
    allow_reload = asyncio.Event()
    executed_claims: list[datetime | None] = []
    original_get = AgentTurnRepository.get

    async def gated_get(self, turn_id):
        if str(turn_id) == str(turn.id):
            reload_started.set()
            await allow_reload.wait()
        return await original_get(self, turn_id)

    async def record_run(self, input, context):
        del self, input
        executed_claims.append(context.turn_claimed_at)
        return {"projects": [], "total_count": 0}

    monkeypatch.setattr(AgentTurnRepository, "get", gated_get)
    monkeypatch.setattr(ListProjectsTool, "run", record_run)
    controller = AgentLoopController(db_session)
    isolated_call = asyncio.create_task(
        controller._execute_tool_call_isolated(
            agent_session=agent_session,
            turn=turn,
            tool_call={
                "id": "stale-isolated-read",
                "name": "projects.list",
                "arguments": {},
            },
            tool_name="projects.list",
        )
    )

    await reload_started.wait()
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
    allow_reload.set()
    result = await isolated_call

    async with maker() as inspect_db:
        actions = await AgentActionRepository(inspect_db).list_for_turn(str(turn.id))

    assert result.status == AgentActionStatus.CANCELLED
    assert executed_claims == []
    assert actions == []
