from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.models.agent_core import AgentAttachmentStatus
from app.models.project import Project
from app.models.project_workflow_binding import ProjectWorkflowBinding
from app.models.workflow import Workflow
from app.path_layout import project_home
from app.repositories.agent_core_repo import AgentAttachmentRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.run_repo import RunRepository
from app.schemas.agent_core import (
    AgentContextSearchItem,
    AgentContextSearchRead,
)
from app.utils.exceptions import BadRequestError, NotFoundError


_MIXED_LIMITS = {"file": 4, "workflow": 2, "run": 2}
_FILE_SCAN_LIMIT = 5000
_IGNORED_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".env",
    "__pycache__",
    "node_modules",
    "id_rsa",
    "id_ed25519",
}


class AgentContextPicker:
    def __init__(self, db) -> None:
        self.db = db
        self.projects = ProjectRepository(db)
        self.attachments = AgentAttachmentRepository(db)
        self.runs = RunRepository(db)

    async def search(
        self,
        *,
        workspace_id: str,
        user_id: str,
        query: str,
        scope: str,
        project_id: str | None = None,
        session_id: str | None = None,
        cursor: str | None = None,
    ) -> AgentContextSearchRead:
        normalized_query = query.strip()
        if scope not in {"mixed", "file", "workflow", "run"}:
            raise BadRequestError("Unsupported context search scope")
        if cursor and scope != "run":
            raise BadRequestError("Only run search accepts a cursor")
        if scope == "mixed":
            files = await self._files(
                workspace_id=workspace_id,
                user_id=user_id,
                query=normalized_query,
                project_id=project_id,
                session_id=session_id,
                limit=_MIXED_LIMITS["file"],
            )
            workflows = await self._workflows(
                workspace_id=workspace_id,
                query=normalized_query,
                project_id=project_id,
                limit=_MIXED_LIMITS["workflow"],
            )
            runs, _ = await self._runs(
                workspace_id=workspace_id,
                query=normalized_query,
                project_id=project_id,
                limit=_MIXED_LIMITS["run"],
            )
            return AgentContextSearchRead(
                results=[*files, *workflows, *runs],
                counts={
                    "file": len(files),
                    "workflow": len(workflows),
                    "run": len(runs),
                },
            )
        if scope == "file":
            files = await self._files(
                workspace_id=workspace_id,
                user_id=user_id,
                query=normalized_query,
                project_id=project_id,
                session_id=session_id,
                limit=50,
            )
            return AgentContextSearchRead(
                results=files,
                counts={"file": len(files), "workflow": 0, "run": 0},
            )
        if scope == "workflow":
            workflows = await self._workflows(
                workspace_id=workspace_id,
                query=normalized_query,
                project_id=project_id,
                limit=50,
            )
            return AgentContextSearchRead(
                results=workflows,
                counts={"file": 0, "workflow": len(workflows), "run": 0},
            )
        runs, next_cursor = await self._runs(
            workspace_id=workspace_id,
            query=normalized_query,
            project_id=project_id,
            limit=50,
            cursor=cursor,
        )
        return AgentContextSearchRead(
            results=runs,
            counts={"file": 0, "workflow": 0, "run": len(runs)},
            next_cursor=next_cursor,
        )

    async def _files(
        self,
        *,
        workspace_id: str,
        user_id: str,
        query: str,
        project_id: str | None,
        session_id: str | None,
        limit: int,
    ) -> list[AgentContextSearchItem]:
        results: list[AgentContextSearchItem] = []
        folded = query.casefold()
        if session_id:
            attachments = await self.attachments.list_for_session(
                session_id=session_id,
                workspace_id=workspace_id,
                user_id=user_id,
            )
            for attachment in attachments:
                if attachment.status != AgentAttachmentStatus.READY:
                    continue
                if folded and folded not in attachment.filename.casefold():
                    continue
                kind = "directory" if attachment.kind == "folder" else "file"
                part_type = "directory_ref" if kind == "directory" else "file_ref"
                results.append(
                    AgentContextSearchItem(
                        id=f"attachment:{attachment.id}",
                        kind=kind,
                        label=attachment.filename,
                        detail="Uploaded attachment",
                        input_part={
                            "type": part_type,
                            "attachment_id": str(attachment.id),
                        },
                    )
                )
                if len(results) >= limit:
                    return results
        if project_id and len(results) < limit:
            project = await self._require_project(project_id, workspace_id)
            if project.storage_mode != "remote":
                root = project_home(project)
                for path in _search_local_paths(root, folded):
                    relative = path.relative_to(root).as_posix()
                    is_directory = path.is_dir()
                    results.append(
                        AgentContextSearchItem(
                            id=f"project:{project.id}:{relative}",
                            kind="directory" if is_directory else "file",
                            label=path.name,
                            detail=relative,
                            input_part={
                                "type": (
                                    "directory_ref" if is_directory else "file_ref"
                                ),
                                "project_id": str(project.id),
                                "path": relative,
                            },
                        )
                    )
                    if len(results) >= limit:
                        break
        return results

    async def _workflows(
        self,
        *,
        workspace_id: str,
        query: str,
        project_id: str | None,
        limit: int,
    ) -> list[AgentContextSearchItem]:
        stmt = select(Workflow)
        if project_id:
            await self._require_project(project_id, workspace_id)
            stmt = stmt.join(
                ProjectWorkflowBinding,
                ProjectWorkflowBinding.workflow_id == Workflow.id,
            ).where(ProjectWorkflowBinding.project_id == project_id)
        if query:
            escaped = _like_query(query)
            stmt = stmt.where(Workflow.name.ilike(f"%{escaped}%", escape="\\"))
        workflows = list(
            (
                await self.db.execute(
                    stmt.order_by(Workflow.created_at.desc(), Workflow.id.desc()).limit(
                        limit
                    )
                )
            )
            .scalars()
            .all()
        )
        return [
            AgentContextSearchItem(
                id=f"workflow:{workflow.id}",
                kind="workflow",
                label=workflow.name,
                detail=f"{workflow.version} · {getattr(workflow.engine, 'value', workflow.engine)}",
                input_part={
                    "type": "workflow_ref",
                    "workflow_id": str(workflow.id),
                    **(
                        {"project_id": project_id, "scope": "project"}
                        if project_id
                        else {"scope": "global"}
                    ),
                },
            )
            for workflow in workflows
        ]

    async def _runs(
        self,
        *,
        workspace_id: str,
        query: str,
        project_id: str | None,
        limit: int,
        cursor: str | None = None,
    ) -> tuple[list[AgentContextSearchItem], str | None]:
        runs, pagination = await self.runs.search_context(
            workspace_id=workspace_id,
            query=query,
            current_project_id=project_id,
            limit=limit,
            cursor=cursor,
        )
        return (
            [
                AgentContextSearchItem(
                    id=f"run:{run.run_id}",
                    kind="run",
                    label=run.run_id,
                    detail=" · ".join(
                        value
                        for value in (
                            str(getattr(run.status, "value", run.status)),
                            run.workflow.name if run.workflow else None,
                            run.project.name if run.project else None,
                        )
                        if value
                    ),
                    input_part={"type": "run_ref", "run_id": run.run_id},
                )
                for run in runs
            ],
            pagination.next_cursor,
        )

    async def _require_project(self, project_id: str, workspace_id: str) -> Project:
        project = await self.projects.get(project_id)
        if project is None or str(project.workspace_id) != str(workspace_id):
            raise NotFoundError("Project not found")
        return project


def _search_local_paths(root: Path, folded_query: str):
    if not root.exists():
        return []
    matches = []
    scanned = 0
    for path in sorted(root.rglob("*")):
        scanned += 1
        if scanned > _FILE_SCAN_LIMIT:
            break
        relative_parts = path.relative_to(root).parts
        if path.is_symlink() or any(
            part.lower() in _IGNORED_NAMES for part in relative_parts
        ):
            continue
        relative = path.relative_to(root).as_posix()
        if folded_query and folded_query not in relative.casefold():
            continue
        matches.append(path)
    return matches


def _like_query(query: str) -> str:
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
