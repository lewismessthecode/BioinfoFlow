from __future__ import annotations

import base64
from io import BytesIO

import pytest
from fastapi import UploadFile
from PIL import Image

from app.models.agent_core import AgentSession
from app.models.workspace import Workspace
from app.path_layout import agent_session_attachments_root
from app.repositories.agent_core_repo import AgentAttachmentRepository
from app.services.agent_core.attachments import AgentAttachmentService
from app.utils.exceptions import BadRequestError
from app.workspace import DEFAULT_WORKSPACE_ID


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
    "AScY42YAAAAASUVORK5CYII="
)


def _upload(name: str, content: bytes, content_type: str | None = None) -> UploadFile:
    return UploadFile(
        filename=name,
        file=BytesIO(content),
        headers={"content-type": content_type or "application/octet-stream"},
    )


async def _session(db_session) -> AgentSession:
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    await db_session.commit()
    session = AgentSession(workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev")
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


@pytest.mark.asyncio
async def test_image_signature_overrides_extension_and_preview_is_validated(
    db_session,
) -> None:
    session = await _session(db_session)
    service = AgentAttachmentService(db_session)

    attachment = await service.ingest_image(
        agent_session=session,
        file=_upload("misleading.txt", PNG_1X1, "text/plain"),
        source="clipboard",
    )
    preview_path, media_type = await service.preview_path(
        attachment_id=str(attachment.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    assert attachment.mime_type == "image/png"
    assert attachment.image_width == 1
    assert attachment.image_height == 1
    assert attachment.attachment_metadata["sha256"]
    assert preview_path.read_bytes() == PNG_1X1
    assert media_type == "image/png"


@pytest.mark.asyncio
async def test_image_derivative_applies_orientation_and_size_limit(db_session) -> None:
    session = await _session(db_session)
    service = AgentAttachmentService(db_session)
    source = Image.new("RGB", (3000, 1000), "white")
    exif = source.getexif()
    exif[274] = 6
    buffer = BytesIO()
    source.save(buffer, format="JPEG", exif=exif)

    attachment = await service.ingest_image(
        agent_session=session,
        file=_upload("rotated.jpg", buffer.getvalue(), "image/jpeg"),
    )
    model_path = (
        agent_session_attachments_root(str(session.id))
        / str(attachment.id)
        / attachment.attachment_metadata["model_relpath"]
    )

    with Image.open(model_path) as derivative:
        assert derivative.size == (683, 2048)
    assert (attachment.image_width, attachment.image_height) == (683, 2048)


@pytest.mark.asyncio
async def test_unsupported_binary_file_is_rejected_without_committed_record(
    db_session,
) -> None:
    session = await _session(db_session)
    service = AgentAttachmentService(db_session)

    with pytest.raises(BadRequestError, match="Unsupported attachment type"):
        await service.ingest_files(
            agent_session=session,
            files=[_upload("sample.bin", b"\x00\x01\x02\xff")],
        )

    assert await AgentAttachmentRepository(db_session).list_for_session(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    ) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "relative_paths",
    [
        ["folder/../escape.txt"],
        ["/absolute.txt"],
        ["folder//empty.txt"],
        ["folder/a.txt", "folder/a.txt"],
    ],
)
async def test_folder_rejects_unsafe_or_duplicate_paths(
    db_session,
    relative_paths: list[str],
) -> None:
    session = await _session(db_session)
    service = AgentAttachmentService(db_session)
    files = [_upload(f"file-{index}.txt", b"hello") for index in range(len(relative_paths))]

    with pytest.raises(BadRequestError):
        await service.ingest_folder(
            agent_session=session,
            files=files,
            relative_paths=relative_paths,
        )


@pytest.mark.asyncio
async def test_folder_omits_cache_and_credential_files(db_session) -> None:
    session = await _session(db_session)
    service = AgentAttachmentService(db_session)

    attachment = await service.ingest_folder(
        agent_session=session,
        files=[
            _upload("main.py", b"print('ok')\n"),
            _upload("cache.pyc", b"\x00binary"),
            _upload("id_rsa", b"private key"),
            _upload("env", b"SECRET=value"),
        ],
        relative_paths=[
            "project/main.py",
            "project/__pycache__/cache.pyc",
            "project/id_rsa",
            "project/.env",
        ],
    )

    assert attachment.file_count == 1
    assert attachment.attachment_metadata["ignored_count"] == 3
    assert attachment.attachment_metadata["manifest"] == ["project/main.py"]


@pytest.mark.asyncio
async def test_failed_folder_is_atomic(db_session) -> None:
    session = await _session(db_session)
    service = AgentAttachmentService(db_session)

    with pytest.raises(BadRequestError, match="Unsupported attachment type"):
        await service.ingest_folder(
            agent_session=session,
            files=[
                _upload("ok.txt", b"hello"),
                _upload("bad.bin", b"\x00\x01\xff"),
            ],
            relative_paths=["folder/ok.txt", "folder/bad.bin"],
        )

    session_root = agent_session_attachments_root(str(session.id))
    assert not session_root.exists() or list(session_root.iterdir()) == []
    assert await AgentAttachmentRepository(db_session).list_for_session(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    ) == []


@pytest.mark.asyncio
async def test_delete_pending_attachment_removes_directory_and_row(db_session) -> None:
    session = await _session(db_session)
    service = AgentAttachmentService(db_session)
    attachment = (
        await service.ingest_files(
            agent_session=session,
            files=[_upload("notes.txt", b"hello")],
        )
    )[0]
    attachment_root = agent_session_attachments_root(str(session.id)) / str(
        attachment.id
    )

    await service.delete_pending(
        attachment_id=str(attachment.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    assert not attachment_root.exists()
    assert await AgentAttachmentRepository(db_session).get(str(attachment.id)) is None
