from __future__ import annotations

import pytest

from app.models.agent_core import AgentAttachment, AgentAttachmentStatus, AgentSession
from app.models.project_workflow_binding import ProjectWorkflowBinding
from app.models.run import Run, RunStatus
from app.models.workspace import Workspace
from app.path_layout import project_home
from app.services.agent_core.context_picker import AgentContextPicker
from app.workspace import DEFAULT_WORKSPACE_ID
from tests.support.path_contract import create_project, create_workflow


@pytest.mark.asyncio
async def test_mixed_context_search_uses_fixed_source_quotas(db_session) -> None:
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    await db_session.commit()
    project = await create_project(
        db_session,
        name="Context project",
        storage_mode="managed",
    )
    root = project_home(project)
    root.mkdir(parents=True, exist_ok=True)
    for index in range(8):
        (root / f"match-file-{index}.txt").write_text("content", encoding="utf-8")
    for index in range(4):
        workflow = await create_workflow(
            db_session,
            name=f"match-workflow-{index}",
            content="workflow { }\n",
        )
        db_session.add(
            ProjectWorkflowBinding(
                project_id=str(project.id),
                workflow_id=str(workflow.id),
            )
        )
        db_session.add(
            Run(
                run_id=f"match-run-{index}",
                project_id=str(project.id),
                workflow_id=str(workflow.id),
                status=RunStatus.COMPLETED.value,
                config={},
                samples_count=0,
                tasks_total=0,
                tasks_completed=0,
            )
        )
    await db_session.commit()

    result = await AgentContextPicker(db_session).search(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        query="match",
        scope="mixed",
        project_id=str(project.id),
    )

    assert result.counts == {"file": 4, "workflow": 2, "run": 2}
    assert [item.kind for item in result.results].count("file") == 4
    assert [item.kind for item in result.results].count("workflow") == 2
    assert [item.kind for item in result.results].count("run") == 2


@pytest.mark.asyncio
async def test_file_scope_includes_uploaded_files_and_folders(db_session) -> None:
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    await db_session.commit()
    session = AgentSession(workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev")
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    db_session.add_all(
        [
            AgentAttachment(
                session_id=str(session.id),
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                kind="file",
                source="upload",
                filename="uploaded-notes.txt",
                storage_path=f"{session.id}/file",
                mime_type="text/plain",
                size_bytes=4,
                status=AgentAttachmentStatus.READY,
            ),
            AgentAttachment(
                session_id=str(session.id),
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                kind="folder",
                source="upload",
                filename="uploaded-folder",
                storage_path=f"{session.id}/folder",
                mime_type="application/x-directory",
                size_bytes=4,
                file_count=1,
                status=AgentAttachmentStatus.READY,
            ),
        ]
    )
    await db_session.commit()

    result = await AgentContextPicker(db_session).search(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        query="uploaded",
        scope="file",
        session_id=str(session.id),
    )

    assert {item.kind for item in result.results} == {"file", "directory"}
    assert all("attachment_id" in item.input_part for item in result.results)
