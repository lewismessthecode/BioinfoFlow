from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.workspace import Workspace
from app.path_layout import (
    agent_artifact_root,
    agent_attachment_root,
    agent_attachments_root,
    agent_session_artifacts_root,
    agent_session_attachments_root,
    legacy_agent_attachments_root,
)
from app.repositories.agent_harness_repo import (
    AgentHarnessArtifactRepository,
    AgentHarnessAttachmentRepository,
    AgentHarnessRepository,
    RunFence,
)
from app.services.agent_harness.assets import (
    AgentHarnessArtifactService,
    AgentHarnessAttachmentService,
    migrate_legacy_agent_attachments,
    recover_agent_session_file_tombstones,
    stage_agent_session_files_for_delete,
)
from app.services.agent_harness.contracts import OpenSessionRequest
from app.services.agent_harness.contracts import (
    InputAttachmentRefPart,
    InputTextPart,
    MessageCommand,
)
from app.services.agent_harness.message_payload import user_message_payload_builder
from app.utils.exceptions import ConflictError, NotFoundError
from app.workspace import DEFAULT_WORKSPACE_ID
from tests.test_agent_harness.run_test_helpers import (
    agent_turn_execution_config,
    create_agent_run,
)


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
    "AScY42YAAAAASUVORK5CYII="
)


def _payloads(repository: AgentHarnessRepository):
    return user_message_payload_builder(repository.db)


def _upload(name: str, content: bytes) -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(content))


def _attachment_tree(root, content: bytes = b"content"):
    root.mkdir(parents=True)
    (root / "original").write_bytes(content)
    (root / "metadata.json").write_text('{"kind":"file"}', encoding="utf-8")


def test_legacy_attachment_migration_is_empty_and_idempotent(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))

    assert migrate_legacy_agent_attachments() == 0
    assert migrate_legacy_agent_attachments() == 0


def test_legacy_attachment_migration_atomically_moves_attachment(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    source = legacy_agent_attachments_root() / "session-1" / "attachment-1"
    target = agent_attachments_root() / "session-1" / "attachment-1"
    _attachment_tree(source)

    assert migrate_legacy_agent_attachments() == 1
    assert not source.exists()
    assert (target / "original").read_bytes() == b"content"
    assert migrate_legacy_agent_attachments() == 0


def test_legacy_attachment_migration_resumes_partial_completion(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    target = agent_attachments_root() / "session-1" / "attachment-1"
    _attachment_tree(target, b"already-moved")
    tombstone = legacy_agent_attachments_root() / "session-1" / ".migrated-attachment-1"
    _attachment_tree(tombstone, b"already-moved")
    remaining = legacy_agent_attachments_root() / "session-2" / "attachment-2"
    _attachment_tree(remaining, b"remaining")

    assert migrate_legacy_agent_attachments() == 1
    assert not tombstone.exists()
    assert not remaining.exists()
    assert (
        agent_attachments_root() / "session-2" / "attachment-2" / "original"
    ).read_bytes() == b"remaining"


def test_legacy_attachment_migration_preserves_conflicting_tombstone(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    target = agent_attachments_root() / "session-1" / "attachment-1"
    tombstone = legacy_agent_attachments_root() / "session-1" / ".migrated-attachment-1"
    _attachment_tree(target, b"current")
    _attachment_tree(tombstone, b"legacy")

    with pytest.raises(RuntimeError, match="conflict"):
        migrate_legacy_agent_attachments()

    assert (tombstone / "original").read_bytes() == b"legacy"
    assert (target / "original").read_bytes() == b"current"


def test_legacy_attachment_migration_deduplicates_identical_destination(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    source = legacy_agent_attachments_root() / "session-1" / "attachment-1"
    target = agent_attachments_root() / "session-1" / "attachment-1"
    _attachment_tree(source, b"same")
    _attachment_tree(target, b"same")

    assert migrate_legacy_agent_attachments() == 1
    assert not source.exists()
    assert (target / "original").read_bytes() == b"same"


def test_legacy_attachment_migration_fails_closed_on_different_destination(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    source = legacy_agent_attachments_root() / "session-1" / "attachment-1"
    target = agent_attachments_root() / "session-1" / "attachment-1"
    _attachment_tree(source, b"legacy")
    _attachment_tree(target, b"current")

    with pytest.raises(RuntimeError, match="conflict"):
        migrate_legacy_agent_attachments()

    assert (source / "original").read_bytes() == b"legacy"
    assert (target / "original").read_bytes() == b"current"


def test_legacy_attachment_migration_rejects_symlink_escape(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    outside = tmp_path / "outside"
    _attachment_tree(outside, b"secret")
    source = legacy_agent_attachments_root() / "session-1" / "attachment-1"
    source.parent.mkdir(parents=True)
    source.symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="symbolic link"):
        migrate_legacy_agent_attachments()

    assert (outside / "original").read_bytes() == b"secret"
    assert not (agent_attachments_root() / "session-1" / "attachment-1").exists()


def test_legacy_attachment_migration_rejects_nested_symlink_escape(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"secret")
    source = legacy_agent_attachments_root() / "session-1" / "attachment-1"
    source.mkdir(parents=True)
    (source / "original").symlink_to(outside)

    with pytest.raises(RuntimeError, match="symbolic link"):
        migrate_legacy_agent_attachments()

    assert outside.read_bytes() == b"secret"
    assert source.is_dir()
    assert not (agent_attachments_root() / "session-1" / "attachment-1").exists()


def test_legacy_attachment_migration_rejects_root_parent_symlink_escape(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    outside = tmp_path / "outside"
    source = outside / "attachments" / "session-1" / "attachment-1"
    _attachment_tree(source, b"secret")
    legacy_parent = tmp_path / "state" / "agent_core"
    legacy_parent.parent.mkdir(parents=True)
    legacy_parent.symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="escapes"):
        migrate_legacy_agent_attachments()

    assert (source / "original").read_bytes() == b"secret"
    assert not agent_attachments_root().exists()


def test_application_startup_validates_database_before_migrating_attachments() -> None:
    main_source = (Path(__file__).parents[2] / "app" / "main.py").read_text(
        encoding="utf-8"
    )

    assert main_source.index(
        "await verify_database_schema_current()"
    ) < main_source.index("migrate_legacy_agent_attachments()")


async def _session(db_session, *, user_id: str = "dev"):
    if await db_session.get(Workspace, DEFAULT_WORKSPACE_ID) is None:
        db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
        await db_session.commit()
    return await AgentHarnessRepository(db_session).open_session(
        OpenSessionRequest(
            user_id=user_id,
            workspace_id=UUID(DEFAULT_WORKSPACE_ID),
            prompt_snapshot={"text": "test"},
        )
    )


@pytest.mark.asyncio
async def test_attachment_service_ingests_previews_and_deletes_without_agent_core(
    db_session,
) -> None:
    session = await _session(db_session)
    service = AgentHarnessAttachmentService(db_session)

    attachment = await service.ingest_image(
        agent_session=session,
        file=_upload("misleading.txt", PNG_1X1),
        source="clipboard",
    )
    preview, media_type = await service.preview_path(
        attachment_id=str(attachment.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    assert attachment.kind == "image"
    assert attachment.mime_type == "image/png"
    assert preview.read_bytes() == PNG_1X1
    assert media_type == "image/png"
    assert preview.is_relative_to(
        agent_attachment_root(str(session.id), str(attachment.id))
    )

    await service.delete(
        attachment_id=str(attachment.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert not agent_session_attachments_root(str(session.id)).exists()
    assert (
        await AgentHarnessAttachmentRepository(db_session).get(str(attachment.id))
        is None
    )


@pytest.mark.asyncio
async def test_migrated_legacy_attachment_can_preview_model_and_delete(
    db_session,
) -> None:
    session = await _session(db_session)
    service = AgentHarnessAttachmentService(db_session)
    attachment = await service.ingest_image(
        agent_session=session,
        file=_upload("legacy.png", PNG_1X1),
    )
    current = agent_attachment_root(str(session.id), str(attachment.id))
    legacy = legacy_agent_attachments_root() / str(session.id) / str(attachment.id)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(current), str(legacy))
    assert migrate_legacy_agent_attachments() == 1

    preview, media_type = await service.preview_path(
        attachment_id=str(attachment.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    parts = await service.model_parts_for_ids(
        [str(attachment.id)],
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    assert preview == current / "original"
    assert preview.read_bytes() == PNG_1X1
    assert media_type == "image/png"
    assert len(parts[str(attachment.id)]) == 2

    await service.delete(
        attachment_id=str(attachment.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert not current.exists()
    assert (
        await AgentHarnessAttachmentRepository(db_session).get(str(attachment.id))
        is None
    )


@pytest.mark.asyncio
async def test_session_delete_and_orphan_cleanup_use_current_root(
    db_session,
) -> None:
    service = AgentHarnessAttachmentService(db_session)
    first = await _session(db_session)
    second = await _session(db_session)
    current_attachment = (
        await service.ingest_files(
            agent_session=first,
            files=[_upload("current.txt", b"current")],
        )
    )[0]
    legacy_attachment = (
        await service.ingest_files(
            agent_session=second,
            files=[_upload("legacy.txt", b"legacy")],
        )
    )[0]
    service.delete_session_files(str(first.id))
    assert not agent_session_attachments_root(str(first.id)).exists()
    current_root = agent_attachment_root(str(first.id), str(current_attachment.id))
    current_root.mkdir(parents=True)
    (current_root / "original").write_text("current", encoding="utf-8")

    second_root = agent_attachment_root(str(second.id), str(legacy_attachment.id))
    old = datetime.now(timezone.utc) - timedelta(days=2)
    current_attachment.created_at = old
    legacy_attachment.created_at = old
    await db_session.commit()

    removed = await service.cleanup_orphans(cutoff=datetime.now(timezone.utc))

    assert removed == 2
    assert not current_root.exists()
    assert not second_root.exists()


@pytest.mark.asyncio
async def test_orphan_cleanup_removes_unreferenced_attachment_from_existing_history(
    db_session,
) -> None:
    session = await _session(db_session)
    repository = AgentHarnessRepository(db_session)
    session_id = str(session.id)
    await repository.submit_user_command(
        session_id,
        _message("message-1", "existing history"),
        message_payload_builder=_payloads(repository),
        turn_execution_config=await agent_turn_execution_config(repository, session_id),
    )
    service = AgentHarnessAttachmentService(db_session)
    attachment = (
        await service.ingest_files(
            agent_session=session,
            files=[_upload("unused.txt", b"unused")],
        )
    )[0]
    root = agent_attachment_root(str(session.id), str(attachment.id))
    attachment.created_at = datetime.now(timezone.utc) - timedelta(days=2)
    await db_session.commit()

    assert await service.cleanup_orphans(cutoff=datetime.now(timezone.utc)) == 1
    assert (
        await AgentHarnessAttachmentRepository(db_session).get(str(attachment.id))
        is None
    )
    assert not root.exists()


@pytest.mark.asyncio
async def test_orphan_cleanup_preserves_attachment_referenced_by_history(
    db_session,
) -> None:
    session = await _session(db_session)
    service = AgentHarnessAttachmentService(db_session)
    attachment = (
        await service.ingest_files(
            agent_session=session,
            files=[_upload("used.txt", b"used")],
        )
    )[0]
    attachment.created_at = datetime.now(timezone.utc) - timedelta(days=2)
    await db_session.commit()
    repository = AgentHarnessRepository(db_session)
    session_id = str(session.id)
    await repository.submit_user_command(
        session_id,
        _message(
            "message-1",
            "use attachment",
            attachment_ids=[attachment.id],
        ),
        message_payload_builder=_payloads(repository),
        turn_execution_config=await agent_turn_execution_config(repository, session_id),
    )
    attachment_id = str(attachment.id)
    root = agent_attachment_root(str(session.id), attachment_id)

    assert await service.cleanup_orphans(cutoff=datetime.now(timezone.utc)) == 0
    assert (
        await AgentHarnessAttachmentRepository(db_session).get(str(attachment.id))
        is not None
    )
    assert root.is_dir()


@pytest.mark.asyncio
async def test_explicit_delete_rejects_attachment_referenced_by_history(
    db_session,
) -> None:
    session = await _session(db_session)
    service = AgentHarnessAttachmentService(db_session)
    attachment = (
        await service.ingest_files(
            agent_session=session,
            files=[_upload("used.txt", b"used")],
        )
    )[0]
    repository = AgentHarnessRepository(db_session)
    session_id = str(session.id)
    await repository.submit_user_command(
        session_id,
        _message(
            "message-1",
            "keep this attachment in permanent history",
            attachment_ids=[attachment.id],
        ),
        message_payload_builder=_payloads(repository),
        turn_execution_config=await agent_turn_execution_config(repository, session_id),
    )
    attachment_id = str(attachment.id)
    root = agent_attachment_root(str(session.id), attachment_id)

    with pytest.raises(ConflictError, match="permanent session history"):
        await service.delete(
            attachment_id=attachment_id,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )

    assert (
        await AgentHarnessAttachmentRepository(db_session).get(attachment_id)
        is not None
    )
    assert root.is_dir()


@pytest.mark.asyncio
async def test_cross_worker_prompt_and_delete_serialize_attachment_reference(
    db_session,
    monkeypatch,
) -> None:
    session = await _session(db_session)
    session_id = str(session.id)
    attachment = (
        await AgentHarnessAttachmentService(db_session).ingest_files(
            agent_session=session,
            files=[_upload("race.txt", b"keep-or-delete-atomically")],
        )
    )[0]
    attachment_id = str(attachment.id)
    root = agent_attachment_root(session_id, attachment_id)
    turn_execution_config = await agent_turn_execution_config(
        AgentHarnessRepository(db_session), session_id
    )
    factory = async_sessionmaker(
        db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with factory() as prompt_db, factory() as delete_db:
        prompt_repository = AgentHarnessRepository(prompt_db)
        delete_service = AgentHarnessAttachmentService(delete_db)
        prompt_update_ready = asyncio.Event()
        delete_update_ready = asyncio.Event()
        release_updates = asyncio.Event()
        original_prompt_execute = prompt_db.execute
        original_delete_execute = delete_db.execute

        async def pause_prompt_session_update(statement, *args, **kwargs):
            if (
                getattr(getattr(statement, "table", None), "name", None)
                == "agent_sessions"
                and not prompt_update_ready.is_set()
            ):
                prompt_update_ready.set()
                await release_updates.wait()
            return await original_prompt_execute(statement, *args, **kwargs)

        async def pause_delete_session_update(statement, *args, **kwargs):
            if (
                getattr(getattr(statement, "table", None), "name", None)
                == "agent_sessions"
                and not delete_update_ready.is_set()
            ):
                delete_update_ready.set()
                await release_updates.wait()
            return await original_delete_execute(statement, *args, **kwargs)

        monkeypatch.setattr(
            prompt_db,
            "execute",
            pause_prompt_session_update,
        )
        monkeypatch.setattr(
            delete_db,
            "execute",
            pause_delete_session_update,
        )
        prompt_task = asyncio.create_task(
            prompt_repository.submit_user_command(
                session_id,
                _message(
                    "message-race",
                    "Use the attachment if it still exists.",
                    attachment_ids=[attachment_id],
                ),
                message_payload_builder=_payloads(prompt_repository),
                turn_execution_config=turn_execution_config,
            )
        )
        delete_task = asyncio.create_task(
            delete_service.delete(
                attachment_id=attachment_id,
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
            )
        )
        await asyncio.wait_for(
            asyncio.gather(
                prompt_update_ready.wait(),
                delete_update_ready.wait(),
            ),
            timeout=5,
        )
        release_updates.set()
        prompt_result, delete_result = await asyncio.wait_for(
            asyncio.gather(prompt_task, delete_task, return_exceptions=True),
            timeout=10,
        )

    delete_won = isinstance(prompt_result, LookupError) and delete_result is None
    assert delete_won, (prompt_result, delete_result)

    async with factory() as verification_db:
        verification = AgentHarnessRepository(verification_db)
        entries = await verification.list_entries(session_id)
        stored_attachment = await AgentHarnessAttachmentRepository(verification_db).get(
            attachment_id
        )
    assert stored_attachment is None
    assert entries == []
    assert not root.exists()


@pytest.mark.asyncio
async def test_cross_worker_delete_waits_for_prompt_history_commit(
    db_session,
    monkeypatch,
) -> None:
    session = await _session(db_session)
    session_id = str(session.id)
    attachment = (
        await AgentHarnessAttachmentService(db_session).ingest_files(
            agent_session=session,
            files=[_upload("prompt-wins.txt", b"permanent-history")],
        )
    )[0]
    attachment_id = str(attachment.id)
    root = agent_attachment_root(session_id, attachment_id)
    turn_execution_config = await agent_turn_execution_config(
        AgentHarnessRepository(db_session), session_id
    )
    factory = async_sessionmaker(
        db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with factory() as prompt_db, factory() as delete_db:
        prompt_repository = AgentHarnessRepository(prompt_db)
        delete_service = AgentHarnessAttachmentService(delete_db)
        prompt_commit_ready = asyncio.Event()
        allow_prompt_commit = asyncio.Event()
        delete_lock_attempted = asyncio.Event()
        original_prompt_commit = prompt_db.commit
        original_delete_execute = delete_db.execute

        async def pause_prompt_commit() -> None:
            prompt_commit_ready.set()
            await allow_prompt_commit.wait()
            await original_prompt_commit()

        async def observe_delete_reservation(statement, *args, **kwargs):
            if (
                getattr(getattr(statement, "table", None), "name", None)
                == "agent_attachments"
            ):
                delete_lock_attempted.set()
            return await original_delete_execute(statement, *args, **kwargs)

        monkeypatch.setattr(prompt_db, "commit", pause_prompt_commit)
        monkeypatch.setattr(delete_db, "execute", observe_delete_reservation)
        prompt_task = asyncio.create_task(
            prompt_repository.submit_user_command(
                session_id,
                _message(
                    "message-first",
                    "Commit this attachment permanently.",
                    attachment_ids=[attachment_id],
                ),
                message_payload_builder=_payloads(prompt_repository),
                turn_execution_config=turn_execution_config,
            )
        )
        await asyncio.wait_for(prompt_commit_ready.wait(), timeout=5)
        delete_task = asyncio.create_task(
            delete_service.delete(
                attachment_id=attachment_id,
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
            )
        )
        await asyncio.wait_for(delete_lock_attempted.wait(), timeout=5)
        assert not delete_task.done()
        allow_prompt_commit.set()
        prompt_result, delete_result = await asyncio.wait_for(
            asyncio.gather(prompt_task, delete_task, return_exceptions=True),
            timeout=10,
        )

    assert not isinstance(prompt_result, Exception)
    assert isinstance(delete_result, ConflictError)
    async with factory() as verification_db:
        verification = AgentHarnessRepository(verification_db)
        entries = await verification.list_entries(session_id)
        stored_attachment = await AgentHarnessAttachmentRepository(verification_db).get(
            attachment_id
        )
    assert stored_attachment is not None
    assert stored_attachment.status == "ready"
    assert [
        [
            part["attachment_id"]
            for part in entry.payload["parts"]
            if part["type"] == "attachment_ref"
        ]
        for entry in entries
    ] == [[attachment_id]]
    assert root.is_dir()


@pytest.mark.asyncio
async def test_session_file_tombstone_restores_when_database_delete_did_not_commit(
    db_session,
) -> None:
    session = await _session(db_session)
    session_id = str(session.id)
    attachments = agent_session_attachments_root(session_id)
    artifacts = agent_session_artifacts_root(session_id)
    attachments.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    (attachments / "keep").write_text("attachment", encoding="utf-8")
    (artifacts / "keep").write_text("artifact", encoding="utf-8")

    tombstone = stage_agent_session_files_for_delete(session_id)
    assert not attachments.exists()
    assert not artifacts.exists()

    assert await recover_agent_session_file_tombstones(db_session) == 1
    assert (attachments / "keep").read_text(encoding="utf-8") == "attachment"
    assert (artifacts / "keep").read_text(encoding="utf-8") == "artifact"
    assert not tombstone.root.exists()


@pytest.mark.asyncio
async def test_session_file_tombstone_purges_after_database_delete_commits(
    db_session,
) -> None:
    session = await _session(db_session)
    session_id = str(session.id)
    attachments = agent_session_attachments_root(session_id)
    artifacts = agent_session_artifacts_root(session_id)
    attachments.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    (attachments / "remove").write_text("attachment", encoding="utf-8")
    (artifacts / "remove").write_text("artifact", encoding="utf-8")

    tombstone = stage_agent_session_files_for_delete(session_id)
    assert await AgentHarnessRepository(db_session).delete_session(session_id)
    attachments.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    (attachments / "late").write_text("attachment", encoding="utf-8")
    (artifacts / "late").write_text("artifact", encoding="utf-8")

    assert await recover_agent_session_file_tombstones(db_session) == 1
    assert not attachments.exists()
    assert not artifacts.exists()
    assert not tombstone.root.exists()


@pytest.mark.asyncio
async def test_attachment_storage_path_traversal_is_rejected(
    db_session, tmp_path
) -> None:
    session = await _session(db_session)
    service = AgentHarnessAttachmentService(db_session)
    attachment = (
        await service.ingest_files(
            agent_session=session,
            files=[_upload("safe.txt", b"safe")],
        )
    )[0]
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    attachment.storage_path = f"../../{outside.name}"
    await db_session.commit()

    with pytest.raises(NotFoundError, match="storage is invalid"):
        service.validated_root(attachment)

    assert marker.read_text(encoding="utf-8") == "keep"


@pytest.mark.asyncio
async def test_attachment_ids_must_be_ready_and_owned_by_prompt_session(
    db_session,
) -> None:
    first = await _session(db_session)
    second = await _session(db_session)
    attachment = (
        await AgentHarnessAttachmentService(db_session).ingest_files(
            agent_session=first,
            files=[_upload("notes.txt", b"hello")],
        )
    )[0]
    repository = AgentHarnessAttachmentRepository(db_session)

    with pytest.raises(LookupError, match="do not belong"):
        await repository.require_ids_for_session(
            [str(attachment.id)],
            session_id=str(second.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )

    owned = await repository.require_ids_for_session(
        [str(attachment.id)],
        session_id=str(first.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert [str(item.id) for item in owned] == [str(attachment.id)]

    with pytest.raises(LookupError, match="do not belong"):
        await AgentHarnessRepository(db_session).enqueue_command(
            str(second.id),
            _message(
                "wrong-attachment",
                "read it",
                attachment_ids=[attachment.id],
            ),
        )


@pytest.mark.asyncio
async def test_artifact_writer_persists_large_output_and_enforces_ownership(
    db_session,
) -> None:
    session = await _session(db_session)
    session_id = str(session.id)
    repository = AgentHarnessRepository(db_session)
    run = await create_agent_run(repository, session_id)
    run_id = str(run.id)
    generation = await repository.claim_run(
        run_id,
        owner="worker-1",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    assert generation == 1
    service = AgentHarnessArtifactService(db_session)

    result = await service.writer(
        session_id=session_id,
        run_id=run_id,
        fence=RunFence(owner="worker-1", generation=generation),
    )(
        {
            "type": "command_output",
            "command": "python large.py",
            "cwd": "/workspace",
            "stdout": "x" * 1000,
            "stderr": "",
        }
    )
    artifact = await AgentHarnessArtifactRepository(db_session).get(
        result["artifact_id"]
    )

    assert artifact is not None
    assert str(artifact.session_id) == session_id
    assert str(artifact.run_id) == run_id
    assert "stdout" not in artifact.payload
    assert artifact.payload["stdout_bytes"] == 1000
    path, filename, media_type = await service.download_path(
        artifact_id=str(artifact.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["stdout"] == "x" * 1000
    assert filename == "command-output.json"
    assert media_type == "application/json"
    assert path.is_relative_to(agent_session_artifacts_root(str(session.id)))
    assert (
        await service.get(
            artifact_id=str(artifact.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )
        is artifact
    )
    with pytest.raises(NotFoundError):
        await service.get(
            artifact_id=str(artifact.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="other-user",
        )


@pytest.mark.asyncio
async def test_artifact_writer_publishes_a_declared_file_idempotently(
    db_session,
) -> None:
    """A tool-call declaration has one durable artifact and safe public reference."""

    session = await _session(db_session)
    session_id = str(session.id)
    repository = AgentHarnessRepository(db_session)
    run = await create_agent_run(repository, session_id)
    run_id = str(run.id)
    generation = await repository.claim_run(
        run_id,
        owner="worker-1",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    assert generation == 1
    writer = AgentHarnessArtifactService(db_session).writer(
        session_id=session_id,
        run_id=run_id,
        fence=RunFence(owner="worker-1", generation=generation),
    )
    declaration = {
        "type": "published_file",
        "declaration_id": "tool:publish-1",
        "filename": "report.tsv",
        "title": "Final report",
        "summary": "Validated differential expression table.",
        "mime_type": "text/tab-separated-values",
        "content": b"gene\tlog2fc\nTP53\t1.2\n",
    }

    first = await writer(declaration)
    second = await writer(declaration)
    artifact = await AgentHarnessArtifactRepository(db_session).get(
        first["artifact_id"]
    )

    assert first == second
    assert artifact is not None
    assert str(artifact.session_id) == session_id
    assert str(artifact.run_id) == run_id
    assert artifact.type == "published_file"
    assert artifact.title == "Final report"
    assert artifact.payload == {"declaration_id": "tool:publish-1"}
    assert artifact.resource_ref == {
        "kind": "stored_file",
        "filename": "report.tsv",
        "mime_type": "text/tab-separated-values",
        "size_bytes": len(declaration["content"]),
        "sha256": hashlib.sha256(declaration["content"]).hexdigest(),
    }
    path, filename, media_type = await AgentHarnessArtifactService(
        db_session
    ).download_path(
        artifact_id=first["artifact_id"],
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert path.read_bytes() == declaration["content"]
    assert filename == "report.tsv"
    assert media_type == "text/tab-separated-values"
    with pytest.raises(ConflictError, match="conflicts"):
        await writer({**declaration, "content": b"gene\tlog2fc\nTP53\t9.9\n"})


@pytest.mark.asyncio
async def test_declared_artifact_preserves_durable_state_when_refresh_fails(
    db_session, monkeypatch
) -> None:
    session = await _session(db_session)
    session_id = str(session.id)
    repository = AgentHarnessRepository(db_session)
    run = await create_agent_run(repository, session_id)
    generation = await repository.claim_run(
        str(run.id),
        owner="worker-1",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    writer = AgentHarnessArtifactService(db_session).writer(
        session_id=session_id,
        run_id=str(run.id),
        fence=RunFence(owner="worker-1", generation=generation),
    )
    declaration = {
        "type": "published_file",
        "declaration_id": "tool:refresh-fails",
        "filename": "report.tsv",
        "title": "Final report",
        "mime_type": "text/tab-separated-values",
        "content": b"gene\tcount\nTP53\t4\n",
    }

    async def fail_refresh(_artifact) -> None:
        raise RuntimeError("refresh failed")

    monkeypatch.setattr(db_session, "refresh", fail_refresh)

    with pytest.raises(RuntimeError, match="refresh failed"):
        await writer(declaration)

    artifacts = await AgentHarnessArtifactRepository(db_session).list_for_session(
        session_id
    )
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert (
        agent_artifact_root(session_id, str(artifact.id)) / "report.tsv"
    ).read_bytes() == declaration["content"]


@pytest.mark.asyncio
async def test_declared_artifact_rejects_a_stale_run_fence(db_session) -> None:
    session = await _session(db_session)
    session_id = str(session.id)
    repository = AgentHarnessRepository(db_session)
    run = await create_agent_run(repository, session_id)
    first_generation = await repository.claim_run(
        str(run.id),
        owner="worker-1",
        lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    current_generation = await repository.claim_run(
        str(run.id),
        owner="worker-2",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    assert (first_generation, current_generation) == (1, 2)

    writer = AgentHarnessArtifactService(db_session).writer(
        session_id=session_id,
        run_id=str(run.id),
        fence=RunFence(owner="worker-1", generation=first_generation),
    )
    with pytest.raises(ValueError, match="stale Agent run fence"):
        await writer(
            {
                "type": "published_file",
                "declaration_id": "tool:publish-1",
                "filename": "report.tsv",
                "title": "Final report",
                "mime_type": "text/tab-separated-values",
                "content": b"gene\tcount\nTP53\t4\n",
            }
        )

    assert (
        await AgentHarnessArtifactRepository(db_session).list_for_session(session_id)
        == []
    )


@pytest.mark.asyncio
async def test_stale_artifact_writer_leaves_no_database_row_or_file(
    db_session,
) -> None:
    factory = async_sessionmaker(
        db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    session = await _session(db_session)
    session_id = str(session.id)
    repository = AgentHarnessRepository(db_session)
    run = await create_agent_run(repository, session_id)
    first_generation = await repository.claim_run(
        str(run.id),
        owner="worker-1",
        lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    assert first_generation == 1
    stale_fence = RunFence(owner="worker-1", generation=first_generation)

    async with factory() as current_db:
        current = AgentHarnessRepository(current_db)
        second_generation = await current.claim_run(
            str(run.id),
            owner="worker-2",
            lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        )
        assert second_generation == 2

    with pytest.raises(ValueError, match="stale Agent run fence"):
        await AgentHarnessArtifactService(db_session).writer(
            session_id=session_id,
            run_id=str(run.id),
            fence=stale_fence,
        )(
            {
                "type": "command_output",
                "command": "python large.py",
                "stdout": "x" * 1000,
                "stderr": "",
            }
        )

    assert (
        await AgentHarnessArtifactRepository(db_session).list_for_session(session_id)
        == []
    )
    artifact_root = agent_session_artifacts_root(session_id)
    assert not artifact_root.exists() or list(artifact_root.iterdir()) == []


@pytest.mark.asyncio
async def test_artifact_download_rejects_legacy_paths_outside_managed_home(
    db_session,
) -> None:
    session = await _session(db_session)
    repository = AgentHarnessRepository(db_session)
    run = await create_agent_run(repository, str(session.id))
    generation = await repository.claim_run(
        str(run.id),
        owner="worker-1",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    assert generation == 1
    artifact = await AgentHarnessArtifactRepository(db_session).create_for_run(
        session_id=str(session.id),
        run_id=str(run.id),
        fence=RunFence(owner="worker-1", generation=generation),
        type="file",
        title="unsafe",
        file_path="/tmp/outside-agent-artifact.txt",
    )

    with pytest.raises(NotFoundError, match="outside managed storage"):
        await AgentHarnessArtifactService(db_session).download_path(
            artifact_id=str(artifact.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )


def _message(command_id: str, text: str, *, attachment_ids=()) -> MessageCommand:
    return MessageCommand(
        command_id=command_id,
        parts=[
            InputTextPart(text=text),
            *(InputAttachmentRefPart(attachment_id=item) for item in attachment_ids),
        ],
    )
