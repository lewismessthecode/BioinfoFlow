from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, Literal

from pydantic import BaseModel, Field

from app.models.project import Project
from app.path_layout import project_home
from app.repositories.agent_harness_repo import AgentHarnessAttachmentRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.run_repo import RunRepository
from app.repositories.workflow_repo import WorkflowRepository
from app.utils.authorization import can_access_project
from app.utils.exceptions import BadRequestError, NotFoundError


_MIXED_LIMITS = {"file": 4, "workflow": 2, "run": 2}
_FILE_SCAN_LIMIT = 5000
_FILE_SCAN_DIRECTORY_LIMIT = 1000
_FILE_SCAN_DEPTH_LIMIT = 32
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
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
_DENIED_NAMES = {
    ".env",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "better-auth.db",
    "bioinfoflow.db",
    "credentials",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
}
_DENIED_DIRECTORIES = {".aws", ".ssh"}
_DENIED_SUFFIXES = {".db", ".key", ".pem", ".p12", ".pfx", ".sqlite", ".sqlite3"}


class ContextSearchItem(BaseModel):
    id: str
    kind: Literal["file", "directory", "workflow", "run"]
    label: str
    detail: str | None = None
    input_part: dict


class ContextSearchResult(BaseModel):
    results: list[ContextSearchItem] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    next_cursor: str | None = None


class AgentContextSearch:
    def __init__(self, db) -> None:
        self.projects = ProjectRepository(db)
        self.attachments = AgentHarnessAttachmentRepository(db)
        self.runs = RunRepository(db)
        self.workflows = WorkflowRepository(db)

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
    ) -> ContextSearchResult:
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
                user_id=user_id,
                query=normalized_query,
                project_id=project_id,
                limit=_MIXED_LIMITS["workflow"],
            )
            runs, _ = await self._runs(
                workspace_id=workspace_id,
                user_id=user_id,
                query=normalized_query,
                project_id=project_id,
                limit=_MIXED_LIMITS["run"],
            )
            return ContextSearchResult(
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
            return ContextSearchResult(
                results=files,
                counts={"file": len(files), "workflow": 0, "run": 0},
            )
        if scope == "workflow":
            workflows = await self._workflows(
                workspace_id=workspace_id,
                user_id=user_id,
                query=normalized_query,
                project_id=project_id,
                limit=50,
            )
            return ContextSearchResult(
                results=workflows,
                counts={"file": 0, "workflow": len(workflows), "run": 0},
            )
        runs, next_cursor = await self._runs(
            workspace_id=workspace_id,
            user_id=user_id,
            query=normalized_query,
            project_id=project_id,
            limit=50,
            cursor=cursor,
        )
        return ContextSearchResult(
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
    ) -> list[ContextSearchItem]:
        results: list[ContextSearchItem] = []
        folded = query.casefold()
        if session_id:
            attachments = await self.attachments.search_for_session(
                session_id=session_id,
                workspace_id=workspace_id,
                user_id=user_id,
                query=folded,
                limit=limit,
            )
            for attachment in attachments:
                if attachment.status != "ready" or _is_sensitive_path(
                    Path(attachment.filename)
                ):
                    continue
                if folded and folded not in attachment.filename.casefold():
                    continue
                is_directory = attachment.kind == "folder"
                results.append(
                    ContextSearchItem(
                        id=f"attachment:{attachment.id}",
                        kind="directory" if is_directory else "file",
                        label=attachment.filename,
                        detail="Uploaded attachment",
                        input_part={
                            "type": "directory_ref" if is_directory else "file_ref",
                            "attachment_id": str(attachment.id),
                        },
                    )
                )
                if len(results) >= limit:
                    return results
        if project_id and len(results) < limit:
            project = await self._require_project(project_id, workspace_id, user_id)
            if project.storage_mode != "remote":
                root = project_home(project)
                for path in _search_local_paths(root, folded):
                    relative = path.relative_to(root).as_posix()
                    is_directory = path.is_dir()
                    results.append(
                        ContextSearchItem(
                            id=f"project:{project.id}:{relative}",
                            kind="directory" if is_directory else "file",
                            label=path.name,
                            detail=relative,
                            input_part={
                                "type": "directory_ref" if is_directory else "file_ref",
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
        user_id: str,
        query: str,
        project_id: str | None,
        limit: int,
    ) -> list[ContextSearchItem]:
        if project_id:
            await self._require_project(project_id, workspace_id, user_id)
        workflows = await self.workflows.search_context(
            query=query,
            project_id=project_id,
            limit=limit,
        )
        return [
            ContextSearchItem(
                id=f"workflow:{workflow.id}",
                kind="workflow",
                label=workflow.name,
                detail=(
                    f"{workflow.version} · "
                    f"{getattr(workflow.engine, 'value', workflow.engine)}"
                ),
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
        user_id: str,
        query: str,
        project_id: str | None,
        limit: int,
        cursor: str | None = None,
    ) -> tuple[list[ContextSearchItem], str | None]:
        if project_id:
            await self._require_project(project_id, workspace_id, user_id)
        runs, pagination = await self.runs.search_context(
            workspace_id=workspace_id,
            query=query,
            current_project_id=project_id,
            limit=limit,
            cursor=cursor,
        )
        return (
            [
                ContextSearchItem(
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

    async def _require_project(
        self,
        project_id: str,
        workspace_id: str,
        user_id: str,
    ) -> Project:
        project = await self.projects.get(project_id)
        if (
            project is None
            or str(project.workspace_id) != str(workspace_id)
            or not can_access_project(
                project,
                user_id=user_id,
                workspace_id=workspace_id,
            )
        ):
            raise NotFoundError("Project not found")
        return project


def _is_sensitive_path(path: Path) -> bool:
    parts = {part.casefold() for part in path.parts}
    if parts & _DENIED_DIRECTORIES:
        return True
    if ".config" in parts and "gcloud" in parts:
        return True
    name = path.name.casefold()
    if name in _DENIED_NAMES or name.startswith(".env."):
        return True
    return path.suffix.casefold() in _DENIED_SUFFIXES


def _search_local_paths(root: Path, folded_query: str) -> list[Path]:
    try:
        root_descriptor = os.open(root, _DIRECTORY_FLAGS)
    except OSError:
        return []
    scan_budget = {
        "entries": _FILE_SCAN_LIMIT,
        "directories": _FILE_SCAN_DIRECTORY_LIMIT,
    }
    matches: list[Path] = []
    try:
        for path in _iter_local_paths(
            root,
            root_descriptor,
            (),
            scan_budget,
            depth=0,
        ):
            relative_parts = path.relative_to(root).parts
            if any(part.lower() in _IGNORED_NAMES for part in relative_parts):
                continue
            if _is_sensitive_path(path):
                continue
            relative = path.relative_to(root).as_posix()
            if folded_query and folded_query not in relative.casefold():
                continue
            matches.append(path)
        return matches
    finally:
        os.close(root_descriptor)


def _iter_local_paths(
    root: Path,
    root_descriptor: int,
    relative_directory: tuple[str, ...],
    scan_budget: dict[str, int],
    *,
    depth: int,
) -> Iterator[Path]:
    if scan_budget["directories"] <= 0:
        return
    scan_budget["directories"] -= 1
    directory_descriptor = None
    entries: list[tuple[str, bool]] = []
    try:
        directory_descriptor = _open_local_directory(
            root_descriptor,
            relative_directory,
        )
        with os.scandir(directory_descriptor) as stream:
            while scan_budget["entries"] > 0:
                try:
                    entry = next(stream)
                except StopIteration:
                    break
                scan_budget["entries"] -= 1
                try:
                    if entry.is_symlink():
                        continue
                    entries.append((entry.name, entry.is_dir(follow_symlinks=False)))
                except OSError:
                    continue
    except OSError:
        return
    finally:
        if directory_descriptor is not None:
            os.close(directory_descriptor)
    for name, is_directory in sorted(entries, key=lambda item: item[0]):
        relative_path = (*relative_directory, name)
        path = root.joinpath(*relative_path)
        yield path
        if (
            is_directory
            and depth < _FILE_SCAN_DEPTH_LIMIT
            and scan_budget["entries"] > 0
            and scan_budget["directories"] > 0
        ):
            yield from _iter_local_paths(
                root,
                root_descriptor,
                relative_path,
                scan_budget,
                depth=depth + 1,
            )


def _open_local_directory(
    root_descriptor: int,
    relative_directory: tuple[str, ...],
) -> int:
    descriptor = os.dup(root_descriptor)
    try:
        for part in relative_directory:
            child_descriptor = os.open(
                part,
                _DIRECTORY_FLAGS,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


__all__ = ["AgentContextSearch", "ContextSearchItem", "ContextSearchResult"]
