from __future__ import annotations

import base64

import pytest

from app.models.agent_core import AgentAttachment, AgentAttachmentStatus
from app.models.workspace import Workspace
from app.path_layout import agent_attachment_root
from app.repositories.agent_core_repo import AgentMessageRepository
from app.services.agent_core import AgentCoreService
from app.services.agent_core.context import AgentContextAssembler
from app.services.model_runtime.contracts import ImagePart, TextPart
from app.utils.exceptions import BadRequestError, NotFoundError
from app.workspace import DEFAULT_WORKSPACE_ID


async def _session(db_session):
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    await db_session.commit()
    return await AgentCoreService(db_session).create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )


async def _image_attachment(db_session, session) -> AgentAttachment:
    attachment = AgentAttachment(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        kind="image",
        source="clipboard",
        filename="shot.png",
        storage_path="placeholder",
        mime_type="image/png",
        size_bytes=9,
        image_width=1,
        image_height=1,
        status=AgentAttachmentStatus.READY,
        attachment_metadata={
            "sha256": "a" * 64,
            "model_relpath": "model",
            "model_mime_type": "image/png",
        },
    )
    db_session.add(attachment)
    await db_session.commit()
    await db_session.refresh(attachment)
    root = agent_attachment_root(str(session.id), str(attachment.id))
    root.mkdir(parents=True)
    (root / "model").write_bytes(b"png-bytes")
    attachment.storage_path = f"{session.id}/{attachment.id}"
    await db_session.commit()
    await db_session.refresh(attachment)
    return attachment


@pytest.mark.asyncio
async def test_image_ref_stays_out_of_transcript_base64_and_resolves_for_model(
    db_session,
) -> None:
    session = await _session(db_session)
    attachment = await _image_attachment(db_session, session)
    service = AgentCoreService(db_session)

    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Inspect this screenshot.",
        input_parts=[
            {"type": "text", "text": "Inspect this screenshot."},
            {"type": "image_ref", "attachment_id": str(attachment.id)},
        ],
    )
    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    stored = messages[0].content_parts
    context = await AgentContextAssembler(db_session).model_context(
        agent_session=session,
        turn=turn,
    )

    assert stored[-1] == {
        "type": "image_ref",
        "attachment_id": str(attachment.id),
        "mime_type": "image/png",
        "sha256": "a" * 64,
        "detail": "high",
    }
    assert base64.b64encode(b"png-bytes").decode() not in repr(stored)
    assert context.input_items == (
        TextPart(
            text=(
                "<environment_context>\n"
                f"  <current_date>{turn.model_profile_snapshot['temporal_context']['current_date']}</current_date>\n"
                "  <timezone>Etc/UTC</timezone>\n"
                "</environment_context>\n\n"
                "Inspect this screenshot."
            )
        ),
        ImagePart(
            mime_type="image/png",
            data=base64.b64encode(b"png-bytes").decode(),
            sha256="a" * 64,
            detail="high",
        ),
    )


@pytest.mark.asyncio
async def test_image_model_context_rejects_a_derivative_path_outside_attachment_root(
    db_session,
    tmp_path,
) -> None:
    session = await _session(db_session)
    attachment = await _image_attachment(db_session, session)
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"secret")
    attachment.attachment_metadata = {
        **(attachment.attachment_metadata or {}),
        "model_relpath": str(outside),
    }
    await db_session.commit()
    service = AgentCoreService(db_session)
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Inspect.",
        input_parts=[{"type": "image_ref", "attachment_id": str(attachment.id)}],
    )

    with pytest.raises(NotFoundError, match="escapes its storage root"):
        await AgentContextAssembler(db_session).model_context(
            agent_session=session,
            turn=turn,
        )


@pytest.mark.asyncio
async def test_stale_attachment_fails_before_turn_is_created(db_session) -> None:
    session = await _session(db_session)
    service = AgentCoreService(db_session)

    with pytest.raises(NotFoundError, match="Attachment not found"):
        await service.create_turn_record(
            session_id=str(session.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text="Inspect.",
            input_parts=[
                {
                    "type": "image_ref",
                    "attachment_id": "00000000-0000-0000-0000-000000000000",
                }
            ],
        )

    assert await service.turn_repo.list_for_session(str(session.id)) == []


@pytest.mark.asyncio
async def test_known_non_vision_model_rejects_image_before_turn_is_created(
    db_session,
) -> None:
    session = await _session(db_session)
    attachment = await _image_attachment(db_session, session)
    service = AgentCoreService(db_session)

    with pytest.raises(BadRequestError, match="does not support image input"):
        await service.create_turn_record(
            session_id=str(session.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text="Inspect.",
            input_parts=[
                {"type": "image_ref", "attachment_id": str(attachment.id)}
            ],
            model_selection={"provider": "deepseek", "model": "deepseek-chat"},
        )

    assert await service.turn_repo.list_for_session(str(session.id)) == []
