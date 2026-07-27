from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agent_core import AgentSession, AgentSessionStatus
from app.models.workspace import Workspace
from app.repositories.agent_core_repo import AgentSessionRepository
from app.workspace import DEFAULT_WORKSPACE_ID


async def _seed_workspace(db_session: AsyncSession) -> None:
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    await db_session.commit()


async def _create_session(
    db_session: AsyncSession,
    *,
    user_id: str = "dev",
    parent_session_id: str | None = None,
    root_session_id: str | None = None,
    agent_name: str | None = None,
    collaboration_slot: int | None = None,
) -> AgentSession:
    session = AgentSession(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id=user_id,
        parent_session_id=parent_session_id,
        root_session_id=root_session_id,
        agent_name=agent_name,
        collaboration_slot=collaboration_slot,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


@pytest.mark.asyncio
async def test_root_tree_queries_and_target_resolution_are_root_scoped(db_session) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child = await _create_session(
        db_session,
        parent_session_id=str(root.id),
        root_session_id=str(root.id),
        agent_name="reader",
    )
    other_root = await _create_session(db_session)
    other_child = await _create_session(
        db_session,
        parent_session_id=str(other_root.id),
        root_session_id=str(other_root.id),
        agent_name="reader",
    )
    await _create_session(
        db_session,
        user_id="other-user",
        parent_session_id=str(root.id),
        root_session_id=str(root.id),
        agent_name="outsider",
    )

    repo = AgentSessionRepository(db_session)

    tree = await repo.list_agent_tree(
        str(root.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert tree[0].id == root.id
    assert [session.id for session in tree[1:]] == [child.id]
    assert (
        await repo.list_agent_tree(
            str(root.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="other-user",
        )
        == []
    )
    assert await repo.get_agent_target(
        str(root.id),
        "reader",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    ) == child
    assert await repo.get_agent_target(
        str(root.id),
        f"/root/{child.agent_name}",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    ) == child
    assert await repo.get_agent_target(
        str(root.id),
        str(child.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    ) == child
    assert await repo.get_agent_target(
        str(root.id),
        "/root",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    ) == root
    assert (
        await repo.get_agent_target(
            str(root.id),
            str(other_child.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )
        is None
    )
    assert (
        await repo.get_agent_target(
            str(root.id),
            "outsider",
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )
        is None
    )


@pytest.mark.asyncio
async def test_duplicate_sibling_agent_name_is_permanently_rejected(db_session) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child = await _create_session(
        db_session,
        parent_session_id=str(root.id),
        root_session_id=str(root.id),
        agent_name="reader",
    )
    child.status = AgentSessionStatus.ARCHIVED
    await db_session.commit()

    db_session.add(
        AgentSession(
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            parent_session_id=str(root.id),
            root_session_id=str(root.id),
            agent_name="reader",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_release_child_slot_keeps_name_reserved(db_session) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child = await _create_session(
        db_session,
        parent_session_id=str(root.id),
        root_session_id=str(root.id),
        agent_name="reader",
    )
    repo = AgentSessionRepository(db_session)

    reserved = await repo.reserve_child_slot(child)

    assert reserved is child
    assert reserved.collaboration_slot == 1
    assert await repo.release_child_slot(str(child.id)) is True

    await db_session.refresh(child)
    assert child.collaboration_slot is None
    assert child.agent_name == "reader"


@pytest.mark.asyncio
async def test_last_child_slot_is_acquired_atomically(db_session) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    root_id = str(root.id)
    for slot in range(1, 7):
        await _create_session(
            db_session,
            parent_session_id=str(root.id),
            root_session_id=str(root.id),
            agent_name=f"worker_{slot}",
            collaboration_slot=slot,
        )
    candidates = [
        await _create_session(
            db_session,
            parent_session_id=str(root.id),
            root_session_id=str(root.id),
            agent_name=name,
        )
        for name in ("seven_a", "seven_b")
    ]
    maker = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async def reserve(child_id: str) -> int:
        async with maker() as worker:
            child = await worker.get(AgentSession, child_id)
            assert child is not None
            reserved = await AgentSessionRepository(worker).reserve_child_slot(child)
            await worker.commit()
            assert reserved.collaboration_slot is not None
            return reserved.collaboration_slot

    results = await asyncio.gather(
        *(reserve(str(child.id)) for child in candidates),
        return_exceptions=True,
    )

    assert sum(result == 7 for result in results) == 1
    assert sum(
        isinstance(result, RuntimeError)
        and "collaboration slot" in str(result).lower()
        for result in results
    ) == 1
    db_session.expire_all()
    reserved = await db_session.scalars(
        select(AgentSession).where(
            AgentSession.root_session_id == root_id,
            AgentSession.collaboration_slot == 7,
        )
    )
    assert len(reserved.all()) == 1


@pytest.mark.asyncio
async def test_staged_child_and_slot_share_the_callers_transaction(db_session) -> None:
    await _seed_workspace(db_session)
    root = await _create_session(db_session)
    child = AgentSession(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        parent_session_id=str(root.id),
        root_session_id=str(root.id),
        agent_name="staged_worker",
    )
    db_session.add(child)

    reserved = await AgentSessionRepository(db_session).reserve_child_slot(child)
    child_id = str(child.id)

    assert reserved is child
    assert child.collaboration_slot == 1
    assert await db_session.get(AgentSession, child_id) is child

    await db_session.rollback()

    assert await db_session.get(AgentSession, child_id) is None
