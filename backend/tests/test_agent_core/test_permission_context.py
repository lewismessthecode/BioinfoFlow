from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agent_core import AgentAction, AgentSession
from app.models.remote_connection import RemoteConnection
from app.models.workspace import Workspace
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentEventRepository,
    AgentSessionRepository,
)
from app.schemas.agent_core import AgentActionRead, AgentSessionRead
from app.services.agent_core import AgentCoreService
from app.services.agent_core.tools.executor import AgentToolExecutor
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.workspace import DEFAULT_WORKSPACE_ID


class _HighRiskTool:
    spec = AgentToolSpec(
        name="test.high",
        description="High-risk test tool.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
        risk_level="act_high",
    )

    async def run(self, input, context):
        del input, context
        return {"ok": True}


async def _create_session_and_turn(db_session, *, permission_mode: str = "guarded_auto"):
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    await db_session.commit()
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        permission_mode=permission_mode,
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Evaluate a high-risk tool.",
    )
    return session, turn


def _registry() -> AgentToolRegistry:
    registry = AgentToolRegistry()
    registry.register(_HighRiskTool())
    return registry


def test_permission_audit_models_default_to_initial_policy_version() -> None:
    action = AgentAction()

    assert AgentSession.__table__.c.permission_policy_version.default.arg == 1
    assert action.evaluated_policy_version is None
    assert action.permission_context_snapshot is None


@pytest.mark.parametrize(
    ("schema", "field_name"),
    [
        (AgentSessionRead, "permission_policy_version"),
        (AgentActionRead, "evaluated_policy_version"),
        (AgentActionRead, "permission_context_snapshot"),
    ],
)
def test_permission_audit_fields_are_exposed_by_read_schemas(schema, field_name: str) -> None:
    assert field_name in schema.model_fields


@pytest.mark.asyncio
async def test_executor_observes_guarded_to_bypass_update_during_active_turn(db_engine) -> None:
    sessions = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with sessions() as loop_db:
        session, turn = await _create_session_and_turn(loop_db)
        stale = await AgentSessionRepository(loop_db).get(str(session.id))
        assert stale.permission_mode == "guarded_auto"

        async with sessions() as update_db:
            updated = await AgentCoreService(update_db).update_session(
                session_id=str(session.id),
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                updates={"permission_mode": "bypass"},
            )
            assert updated.permission_policy_version == 2

        executor = AgentToolExecutor(loop_db, _registry())
        result = await executor.execute(
            tool_name="test.high",
            input={},
            context=AgentToolContext(
                db=loop_db,
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                session_id=str(session.id),
                turn_id=str(turn.id),
            ),
            toolset_policy=stale.toolset_policy,
            permission_mode=stale.permission_mode,
            automation_mode=stale.automation_mode,
        )

        assert result.status == "completed"
        action = await AgentActionRepository(loop_db).get(result.action_id)
        assert action.evaluated_policy_version == 2
        assert action.permission_context_snapshot["permission_mode"] == "bypass"


@pytest.mark.asyncio
async def test_executor_observes_bypass_to_guarded_update_during_active_turn(db_engine) -> None:
    sessions = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with sessions() as loop_db:
        session, turn = await _create_session_and_turn(loop_db, permission_mode="bypass")
        stale = await AgentSessionRepository(loop_db).get(str(session.id))

        async with sessions() as update_db:
            await AgentCoreService(update_db).update_session(
                session_id=str(session.id),
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                updates={"permission_mode": "guarded_auto"},
            )

        result = await AgentToolExecutor(loop_db, _registry()).execute(
            tool_name="test.high",
            input={},
            context=AgentToolContext(
                db=loop_db,
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                session_id=str(session.id),
                turn_id=str(turn.id),
            ),
            toolset_policy=stale.toolset_policy,
            permission_mode=stale.permission_mode,
            automation_mode=stale.automation_mode,
        )

        assert result.status == "waiting_decision"
        action = await AgentActionRepository(loop_db).get(result.action_id)
        assert action.evaluated_policy_version == 2
        assert action.permission_context_snapshot["permission_mode"] == "guarded_auto"
        events = await AgentEventRepository(loop_db).list_for_turn(turn_id=str(turn.id))
        authorization_events = [
            event
            for event in events
            if event.type
            in {"action.requested", "action.risk_assessed", "action.waiting_decision"}
        ]
        assert authorization_events
        assert all(event.payload["evaluated_policy_version"] == 2 for event in authorization_events)


@pytest.mark.asyncio
async def test_authorization_update_increments_once_and_resolves_coherent_snapshot(db_session) -> None:
    from app.services.agent_core.permissions.context import PermissionContextResolver

    session, _turn = await _create_session_and_turn(db_session)
    service = AgentCoreService(db_session)

    renamed = await service.update_session(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        updates={"title": "No policy change"},
    )
    assert renamed.permission_policy_version == 1

    updated = await service.update_session(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        updates={
            "permission_mode": "bypass",
            "automation_mode": "autonomous",
            "mode": "plan",
            "role_profile": "worker",
            "execution_target": {"type": "remote_ssh", "connection_id": "conn-1"},
        },
    )
    assert updated.permission_policy_version == 2

    context = await PermissionContextResolver(db_session).resolve(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    assert context.policy_version == 2
    assert context.permission_mode == "bypass"
    assert context.automation_mode == "autonomous"
    assert context.toolset_policy == {"name": "plan"}
    assert context.role == "worker"
    assert context.execution_target == {"type": "remote_ssh", "connection_id": "conn-1"}


@pytest.mark.asyncio
async def test_turn_level_execution_target_change_increments_policy_version(db_session) -> None:
    session, _turn = await _create_session_and_turn(db_session)

    await AgentCoreService(db_session).create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Switch target for this turn.",
        execution_target={"type": "remote_ssh", "connection_id": "conn-2"},
    )

    refreshed = await AgentSessionRepository(db_session).get_fresh(str(session.id))
    assert refreshed.permission_policy_version == 2


@pytest.mark.asyncio
async def test_validation_failure_records_fresh_permission_context(db_session) -> None:
    session, turn = await _create_session_and_turn(db_session, permission_mode="bypass")

    result = await AgentToolExecutor(db_session, _registry()).execute(
        tool_name="test.high",
        input={"unexpected": True},
        context=AgentToolContext(
            db=db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            session_id=str(session.id),
            turn_id=str(turn.id),
        ),
        toolset_policy={"name": "default"},
    )

    action = await AgentActionRepository(db_session).get(result.action_id)
    assert action.status == "failed"
    assert action.evaluated_policy_version == 1
    assert action.permission_context_snapshot["permission_mode"] == "bypass"


@pytest.mark.asyncio
async def test_resume_rechecks_exposure_with_fresh_permission_context(db_engine) -> None:
    sessions = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with sessions() as loop_db:
        session, turn = await _create_session_and_turn(loop_db)
        executor = AgentToolExecutor(loop_db, _registry())
        context = AgentToolContext(
            db=loop_db,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            session_id=str(session.id),
            turn_id=str(turn.id),
        )
        waiting = await executor.execute(
            tool_name="test.high",
            input={},
            context=context,
            toolset_policy=session.toolset_policy,
        )
        action = await AgentActionRepository(loop_db).get(waiting.action_id)
        await AgentActionRepository(loop_db).update_all(
            action,
            status="requested",
            permission_decision={"decision": "approve"},
        )

        async with sessions() as update_db:
            await AgentCoreService(update_db).update_session(
                session_id=str(session.id),
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                updates={"mode": "plan"},
            )

        resumed = await executor.resume_action(action_id=waiting.action_id, context=context)

        assert resumed.status == "failed"
        assert resumed.error["type"] == "PermissionDeniedError"


@pytest.mark.asyncio
async def test_legacy_remote_connection_alias_change_increments_policy_version(db_session) -> None:
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    await db_session.commit()
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        metadata={"remote_connection_id": "conn-1"},
    )

    updated = await service.update_session(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        updates={"metadata": {"remote_connection_id": "conn-2"}},
    )

    assert updated.permission_policy_version == 2


@pytest.mark.asyncio
async def test_permission_context_is_deeply_immutable_and_snapshot_isolated(db_session) -> None:
    from app.services.agent_core.permissions.context import PermissionContextResolver

    session, _turn = await _create_session_and_turn(db_session)
    session.toolset_policy = {
        "name": "execution",
        "allowed_tools": ["test.high"],
        "credential": "must-not-leak",
        "nested": {"mutable": True},
    }
    await db_session.commit()

    context = await PermissionContextResolver(db_session).resolve(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    snapshot = context.snapshot()

    with pytest.raises(TypeError):
        context.toolset_policy["name"] = "plan"
    snapshot["toolset_policy"]["name"] = "plan"
    session.toolset_policy["allowed_tools"].append("other")

    assert context.toolset_policy["name"] == "execution"
    assert context.snapshot()["toolset_policy"] == {
        "name": "execution",
        "allowed_tools": ["test.high"],
    }
    assert "credential" not in context.snapshot()["toolset_policy"]
    assert context.boundary["enforcement"] != "workspace"
    assert context.snapshot()["effective_roots"]


@pytest.mark.asyncio
async def test_remote_permission_snapshot_contains_safe_identity_without_credentials(db_session) -> None:
    from app.services.agent_core.permissions.context import PermissionContextResolver

    session, _turn = await _create_session_and_turn(db_session)
    connection = RemoteConnection(
        workspace_id=DEFAULT_WORKSPACE_ID,
        name="Compute node",
        host="compute.internal",
        port=2222,
        username="analyst",
        auth_method="password",
        encrypted_password="ciphertext-secret",
        key_path="/secret/id_ed25519",
    )
    db_session.add(connection)
    await db_session.commit()
    await db_session.refresh(connection)
    await AgentCoreService(db_session).update_session(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        updates={
            "execution_target": {
                "type": "remote_ssh",
                "connection_id": str(connection.id),
            }
        },
    )

    snapshot = (
        await PermissionContextResolver(db_session).resolve(
            session_id=str(session.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )
    ).snapshot()

    assert snapshot["remote_identity"] == {
        "connection_id": str(connection.id),
        "name": "Compute node",
        "host": "compute.internal",
        "port": 2222,
        "username": "analyst",
    }
    assert snapshot["boundary"] == {
        "kind": "remote_ssh",
        "enforcement": "remote_account",
        "sandboxed": False,
    }
    assert "ciphertext-secret" not in str(snapshot)
    assert "/secret/id_ed25519" not in str(snapshot)
