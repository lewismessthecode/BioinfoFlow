from __future__ import annotations

import pytest

from app.models.agent_core import (
    AgentAttachment,
    AgentAttachmentStatus,
    AgentSession,
)
from app.models.workspace import Workspace
from app.path_layout import agent_attachment_root
from app.services.agent_core.tools.attachments import (
    AttachmentReadTool,
    AttachmentSearchTool,
)
from app.services.agent_core.tools.specs import AgentToolContext
from app.utils.exceptions import BadRequestError, NotFoundError
from app.workspace import DEFAULT_WORKSPACE_ID


async def _context(db_session) -> tuple[AgentToolContext, AgentSession]:
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    await db_session.commit()
    session = AgentSession(workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev")
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return (
        AgentToolContext(
            db=db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            session_id=str(session.id),
            turn_id="turn-1",
        ),
        session,
    )


async def _attachment(
    db_session,
    session: AgentSession,
    *,
    kind: str,
    filename: str,
    files: dict[str, bytes],
) -> AgentAttachment:
    manifest = sorted(files) if kind == "folder" else None
    attachment = AgentAttachment(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        kind=kind,
        source="upload",
        filename=filename,
        storage_path="placeholder",
        mime_type=(
            "application/x-directory" if kind == "folder" else "text/plain"
        ),
        size_bytes=sum(len(content) for content in files.values()),
        file_count=len(files) if kind == "folder" else None,
        status=AgentAttachmentStatus.READY,
        attachment_metadata=(
            {"manifest": manifest, "files_relpath": "files"}
            if kind == "folder"
            else {"preview_relpath": "original"}
        ),
    )
    db_session.add(attachment)
    await db_session.commit()
    await db_session.refresh(attachment)
    root = agent_attachment_root(str(session.id), str(attachment.id))
    root.mkdir(parents=True)
    if kind == "folder":
        for path, content in files.items():
            target = root / "files" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    else:
        (root / "original").write_bytes(next(iter(files.values())))
    attachment.storage_path = f"{session.id}/{attachment.id}"
    await db_session.commit()
    await db_session.refresh(attachment)
    return attachment


@pytest.mark.asyncio
async def test_attachment_search_supports_empty_and_filtered_bounded_results(
    db_session,
) -> None:
    context, session = await _context(db_session)
    folder = await _attachment(
        db_session,
        session,
        kind="folder",
        filename="project",
        files={
            "src/main.py": b"print('ok')\n",
            "src/utils.py": b"pass\n",
            "README.md": b"docs\n",
        },
    )
    tool = AttachmentSearchTool()

    listed = await tool.run(
        {"attachment_id": str(folder.id), "query": "", "limit": 2},
        context,
    )
    filtered = await tool.run(
        {"attachment_id": str(folder.id), "query": "src", "limit": 10},
        context,
    )

    assert len(listed["matches"]) == 2
    assert listed["truncated"] is True
    assert [item["path"] for item in filtered["matches"]] == [
        "src/main.py",
        "src/utils.py",
    ]


@pytest.mark.asyncio
async def test_attachment_search_is_owned_and_folder_only(db_session) -> None:
    context, session = await _context(db_session)
    file_attachment = await _attachment(
        db_session,
        session,
        kind="file",
        filename="notes.txt",
        files={"notes.txt": b"hello"},
    )
    tool = AttachmentSearchTool()

    with pytest.raises(BadRequestError, match="folder"):
        await tool.run(
            {"attachment_id": str(file_attachment.id), "query": ""}, context
        )
    foreign_context = AgentToolContext(
        db=db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="other",
        session_id=str(session.id),
        turn_id="turn-2",
    )
    with pytest.raises(NotFoundError):
        await tool.run(
            {"attachment_id": str(file_attachment.id), "query": ""},
            foreign_context,
        )


@pytest.mark.asyncio
async def test_attachment_read_supports_offsets_and_rejects_escapes(db_session) -> None:
    context, session = await _context(db_session)
    folder = await _attachment(
        db_session,
        session,
        kind="folder",
        filename="project",
        files={"notes.txt": b"zero\none\ntwo\nthree\n"},
    )
    tool = AttachmentReadTool()

    result = await tool.run(
        {
            "attachment_id": str(folder.id),
            "path": "notes.txt",
            "offset": 1,
            "limit": 2,
        },
        context,
    )

    assert result["content"] == "one\ntwo"
    assert result["line_count"] == 4
    with pytest.raises(BadRequestError):
        await tool.run(
            {"attachment_id": str(folder.id), "path": "../escape.txt"},
            context,
        )
    with pytest.raises(NotFoundError):
        await tool.run(
            {"attachment_id": str(folder.id), "path": "unlisted.txt"},
            context,
        )


@pytest.mark.asyncio
async def test_attachment_read_rejects_non_utf8_and_directory_requests(
    db_session,
) -> None:
    context, session = await _context(db_session)
    binary = await _attachment(
        db_session,
        session,
        kind="file",
        filename="bad.txt",
        files={"bad.txt": b"\xff\xfe"},
    )
    folder = await _attachment(
        db_session,
        session,
        kind="folder",
        filename="project",
        files={"nested/file.txt": b"hello"},
    )
    tool = AttachmentReadTool()

    with pytest.raises(BadRequestError, match="UTF-8"):
        await tool.run({"attachment_id": str(binary.id)}, context)
    with pytest.raises(BadRequestError, match="file path"):
        await tool.run({"attachment_id": str(folder.id)}, context)
