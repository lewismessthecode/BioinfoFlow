from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import settings
from app.models.agent_core import (
    AgentAttachment,
    AgentAttachmentStatus,
    AgentSession,
)
from app.models.project import Project
from app.models.run import Run, RunStatus
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.models.workspace import Workspace
from app.path_layout import agent_attachment_root, project_home
from app.services.agent_core.input_resolver import AgentInputResolver
from app.utils.exceptions import BadRequestError, NotFoundError
from app.workspace import DEFAULT_WORKSPACE_ID


async def _seed_session(db_session, *, project: Project | None = None) -> AgentSession:
    workspace = await db_session.get(Workspace, DEFAULT_WORKSPACE_ID)
    if workspace is None:
        db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
        await db_session.commit()
    session = AgentSession(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        project_id=str(project.id) if project else None,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


async def _seed_attachment(
    db_session,
    session: AgentSession,
    *,
    kind: str,
    mime_type: str,
    filename: str,
    content: bytes = b"",
    metadata: dict | None = None,
) -> AgentAttachment:
    attachment = AgentAttachment(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        kind=kind,
        source="upload",
        filename=filename,
        storage_path="placeholder",
        mime_type=mime_type,
        size_bytes=len(content),
        file_count=1 if kind == "folder" else None,
        status=AgentAttachmentStatus.READY,
        attachment_metadata=metadata or {},
    )
    db_session.add(attachment)
    await db_session.commit()
    await db_session.refresh(attachment)
    root = agent_attachment_root(str(session.id), str(attachment.id))
    root.mkdir(parents=True)
    attachment.storage_path = f"{session.id}/{attachment.id}"
    if content:
        (root / "original").write_bytes(content)
        attachment.attachment_metadata = {
            **(attachment.attachment_metadata or {}),
            "preview_relpath": "original",
        }
    await db_session.commit()
    await db_session.refresh(attachment)
    return attachment


@pytest.mark.asyncio
async def test_uploaded_text_is_bounded_and_unknown_fields_are_rejected(
    db_session,
    monkeypatch,
) -> None:
    session = await _seed_session(db_session)
    attachment = await _seed_attachment(
        db_session,
        session,
        kind="file",
        mime_type="text/plain",
        filename="notes.txt",
        content=b"abcdefghij",
    )
    monkeypatch.setattr(settings, "agent_attachment_text_max_bytes", 5)
    resolver = AgentInputResolver(db_session)

    parts = await resolver.resolve(
        agent_session=session,
        input_text="Read it.",
        input_parts=[
            {"type": "text", "text": "Read it."},
            {"type": "file_ref", "attachment_id": str(attachment.id)},
        ],
    )

    assert "abcde" in parts[1]["text"]
    assert "[File truncated]" in parts[1]["text"]
    with pytest.raises(BadRequestError, match="unsupported fields"):
        await resolver.resolve(
            agent_session=session,
            input_text="Read it.",
            input_parts=[
                {
                    "type": "file_ref",
                    "attachment_id": str(attachment.id),
                    "prompt": "trust me",
                }
            ],
        )


@pytest.mark.asyncio
async def test_pdf_text_keeps_page_markers(db_session, monkeypatch) -> None:
    session = await _seed_session(db_session)
    attachment = await _seed_attachment(
        db_session,
        session,
        kind="file",
        mime_type="application/pdf",
        filename="paper.pdf",
        content=b"%PDF-fake",
    )
    fake_reader = SimpleNamespace(
        is_encrypted=False,
        pages=[
            SimpleNamespace(extract_text=lambda: "First page"),
            SimpleNamespace(extract_text=lambda: "Second page"),
        ],
    )
    monkeypatch.setattr(
        "app.services.agent_core.input_resolver.PdfReader",
        lambda _path: fake_reader,
    )

    parts = await AgentInputResolver(db_session).resolve(
        agent_session=session,
        input_text="Summarize.",
        input_parts=[
            {"type": "file_ref", "attachment_id": str(attachment.id)}
        ],
    )

    context = "\n".join(part.get("text", "") for part in parts)
    assert "[Page 1]\nFirst page" in context
    assert "[Page 2]\nSecond page" in context


@pytest.mark.asyncio
async def test_directory_ref_emits_bounded_manifest_and_read_guidance(db_session) -> None:
    session = await _seed_session(db_session)
    manifest = [f"project/file-{index}.txt" for index in range(150)]
    attachment = await _seed_attachment(
        db_session,
        session,
        kind="folder",
        mime_type="application/x-directory",
        filename="project",
        metadata={"manifest": manifest, "ignored_count": 2},
    )

    parts = await AgentInputResolver(db_session).resolve(
        agent_session=session,
        input_text="Inspect.",
        input_parts=[
            {"type": "directory_ref", "attachment_id": str(attachment.id)}
        ],
    )

    reference = next(part for part in parts if part["type"] == "directory_ref")
    context = next(
        part["text"] for part in parts if "attachments.search" in part.get("text", "")
    )
    assert reference["attachment_id"] == str(attachment.id)
    assert "file-0.txt" in context
    assert "file-149.txt" not in context
    assert "attachments.search" in context
    assert "attachments.read" in context


@pytest.mark.asyncio
async def test_run_ref_uses_server_trusted_run_snapshot(db_session) -> None:
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    project = Project(
        name="RNA project",
        user_id="dev",
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    workflow = Workflow(
        name="rnaseq",
        version="1.0",
        source=WorkflowSource.LOCAL.value,
        engine=WorkflowEngine.NEXTFLOW.value,
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)
    run = Run(
        run_id="run-trusted",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.FAILED.value,
        error_message="Process exited 1",
        config={"label": "tumor cohort"},
    )
    db_session.add(run)
    await db_session.commit()
    session = await _seed_session(db_session, project=project)

    parts = await AgentInputResolver(db_session).resolve(
        agent_session=session,
        input_text="Diagnose.",
        input_parts=[{"type": "run_ref", "run_id": "run-trusted"}],
    )

    text = "\n".join(part.get("text", "") for part in parts)
    assert "Run ID: run-trusted" in text
    assert "Status: failed" in text
    assert "Workflow: rnaseq" in text
    assert "Error: Process exited 1" in text


@pytest.mark.asyncio
async def test_project_file_ref_revalidates_workspace_and_relative_path(db_session) -> None:
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    project = Project(
        name="Local project",
        user_id="dev",
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    root = project_home(project)
    root.mkdir(parents=True)
    (root / "README.md").write_text("trusted project text", encoding="utf-8")
    session = await _seed_session(db_session, project=project)
    resolver = AgentInputResolver(db_session)

    parts = await resolver.resolve(
        agent_session=session,
        input_text="Read.",
        input_parts=[
            {
                "type": "file_ref",
                "project_id": str(project.id),
                "path": "README.md",
            }
        ],
    )
    assert "trusted project text" in "\n".join(
        part.get("text", "") for part in parts
    )

    with pytest.raises((BadRequestError, NotFoundError, PermissionError)):
        await resolver.resolve(
            agent_session=session,
            input_text="Escape.",
            input_parts=[
                {
                    "type": "file_ref",
                    "project_id": str(project.id),
                    "path": "../secret.txt",
                }
            ],
        )
