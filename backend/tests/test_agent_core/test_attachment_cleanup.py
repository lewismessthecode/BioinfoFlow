from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from fastapi import UploadFile
from sqlalchemy import update

from app.models.agent_core import AgentAttachment
from app.models.workspace import Workspace
from app.path_layout import agent_session_attachments_root
from app.repositories.agent_core_repo import AgentAttachmentRepository
from app.services.agent_core import AgentCoreService
from app.services.agent_core.attachments import AgentAttachmentService
from app.workspace import DEFAULT_WORKSPACE_ID


async def _session(db_session):
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    await db_session.commit()
    return await AgentCoreService(db_session).create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )


def _upload(name: str, content: bytes) -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(content))


@pytest.mark.asyncio
async def test_orphan_cleanup_removes_only_drafts_older_than_the_cutoff(
    db_session,
) -> None:
    old_session = await _session(db_session)
    recent_session = await AgentCoreService(db_session).create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    service = AgentAttachmentService(db_session)
    old = (await service.ingest_files(
        agent_session=old_session,
        files=[_upload("old.txt", b"old")],
    ))[0]
    recent = (await service.ingest_files(
        agent_session=recent_session,
        files=[_upload("recent.txt", b"recent")],
    ))[0]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    await db_session.execute(
        update(AgentAttachment)
        .where(AgentAttachment.id == old.id)
        .values(created_at=cutoff - timedelta(seconds=1))
    )
    await db_session.commit()

    removed = await service.cleanup_orphans(cutoff=cutoff)

    assert removed == 1
    assert not agent_session_attachments_root(str(old_session.id)).exists()
    assert agent_session_attachments_root(str(recent_session.id)).exists()
    repo = AgentAttachmentRepository(db_session)
    assert await repo.get(str(old.id)) is None
    assert await repo.get(str(recent.id)) is not None


@pytest.mark.asyncio
async def test_deleting_a_session_removes_its_attachment_files_immediately(
    db_session,
) -> None:
    session = await _session(db_session)
    attachment = (await AgentAttachmentService(db_session).ingest_files(
        agent_session=session,
        files=[_upload("notes.txt", b"notes")],
    ))[0]
    root = agent_session_attachments_root(str(session.id))
    assert root.exists()

    await AgentCoreService(db_session).delete_session(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    assert not root.exists()
    assert await AgentAttachmentRepository(db_session).get(str(attachment.id)) is not None


@pytest.mark.asyncio
async def test_archiving_a_session_preserves_its_attachment_files(db_session) -> None:
    session = await _session(db_session)
    attachment = (await AgentAttachmentService(db_session).ingest_files(
        agent_session=session,
        files=[_upload("notes.txt", b"notes")],
    ))[0]
    root = agent_session_attachments_root(str(session.id))

    await AgentCoreService(db_session).update_session(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        updates={"status": "archived"},
    )

    assert root.exists()
    assert await AgentAttachmentRepository(db_session).get(str(attachment.id)) is not None
