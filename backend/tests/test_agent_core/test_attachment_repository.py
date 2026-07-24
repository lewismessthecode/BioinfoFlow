from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.models.agent_core import AgentAttachmentStatus, AgentSession
from app.models.workspace import Workspace
from app.repositories.agent_core_repo import AgentAttachmentRepository
from app.workspace import DEFAULT_WORKSPACE_ID


async def _create_session(db_session, *, user_id: str = "dev") -> AgentSession:
    workspace = await db_session.get(Workspace, DEFAULT_WORKSPACE_ID)
    if workspace is None:
        db_session.add(
            Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
        )
        await db_session.commit()
    session = AgentSession(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id=user_id,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


@pytest.mark.asyncio
async def test_attachment_repository_enforces_ownership_and_session_listing(
    db_session,
) -> None:
    session = await _create_session(db_session)
    other_session = await _create_session(db_session)
    repo = AgentAttachmentRepository(db_session)
    attachment = await repo.create(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        kind="file",
        source="upload",
        filename="notes.txt",
        storage_path=f"{session.id}/attachment-1",
        mime_type="text/plain",
        size_bytes=12,
        status=AgentAttachmentStatus.READY,
    )

    assert await repo.get_owned(
        str(attachment.id),
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    ) == attachment
    assert await repo.get_owned(
        str(attachment.id),
        session_id=str(other_session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    ) is None
    assert await repo.get_owned(
        str(attachment.id),
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="other-user",
    ) is None
    assert await repo.list_for_session(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    ) == [attachment]


@pytest.mark.asyncio
async def test_attachment_repository_marks_pending_delete(db_session) -> None:
    session = await _create_session(db_session)
    repo = AgentAttachmentRepository(db_session)
    attachment = await repo.create(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        kind="image",
        source="clipboard",
        filename="clipboard.png",
        storage_path=f"{session.id}/attachment-1",
        mime_type="image/png",
        size_bytes=24,
        status=AgentAttachmentStatus.READY,
    )

    marked = await repo.mark_pending_delete(
        str(attachment.id),
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    assert marked is not None
    assert marked.status == AgentAttachmentStatus.PENDING_DELETE


@pytest.mark.asyncio
async def test_attachment_repository_deletes_only_old_orphans(db_session) -> None:
    old_session = await _create_session(db_session)
    recent_session = await _create_session(db_session)
    repo = AgentAttachmentRepository(db_session)
    old_attachment = await repo.create(
        session_id=str(old_session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        kind="file",
        source="upload",
        filename="old.txt",
        storage_path=f"{old_session.id}/old",
        mime_type="text/plain",
        size_bytes=3,
        status=AgentAttachmentStatus.READY,
    )
    recent_attachment = await repo.create(
        session_id=str(recent_session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        kind="file",
        source="upload",
        filename="recent.txt",
        storage_path=f"{recent_session.id}/recent",
        mime_type="text/plain",
        size_bytes=6,
        status=AgentAttachmentStatus.READY,
    )
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    await db_session.execute(
        update(type(old_attachment))
        .where(type(old_attachment).id == old_attachment.id)
        .values(created_at=cutoff - timedelta(seconds=1))
    )
    await db_session.commit()

    deleted_paths = await repo.delete_orphans_before(cutoff)

    assert deleted_paths == [old_attachment.storage_path]
    assert await repo.get(str(old_attachment.id)) is None
    assert await repo.get(str(recent_attachment.id)) is not None
