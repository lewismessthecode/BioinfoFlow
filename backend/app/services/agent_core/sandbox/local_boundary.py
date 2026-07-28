from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BACKEND_ROOT, settings
from app.path_layout import database_root, deliveries_root, project_home, reference_root
from app.repositories.project_repo import ProjectRepository
from app.services.agent_core.sandbox.filesystem_policy import FilesystemPolicy


@dataclass(frozen=True, slots=True)
class LocalFilesystemBoundary:
    working_directory: Path
    read_roots: tuple[Path, ...]
    write_roots: tuple[Path, ...]
    sandbox_read_roots: tuple[Path, ...]
    sandbox_write_roots: tuple[Path, ...]
    protected_roots: tuple[Path, ...]
    policy: FilesystemPolicy


class LocalFilesystemBoundaryResolver:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def resolve(self, agent_session) -> LocalFilesystemBoundary:
        working_directory = deliveries_root()
        working_directory.mkdir(parents=True, exist_ok=True)
        project_id = getattr(agent_session, "project_id", None)
        if project_id:
            project = await ProjectRepository(self.db).get_fresh(str(project_id))
            if (
                project is not None
                and str(project.workspace_id) == str(agent_session.workspace_id)
                and project.storage_mode != "remote"
            ):
                working_directory = project_home(project)

        write_roots = _dedupe([working_directory, *_configured_roots()])
        read_roots = _dedupe([*write_roots, reference_root(), database_root()])
        protected_roots = _protected_roots()
        docker_socket = _existing_unix_docker_socket()
        policy = FilesystemPolicy(
            read_roots=read_roots,
            write_roots=write_roots,
            protected_roots=_dedupe(
                [*protected_roots, *([docker_socket] if docker_socket else [])]
            ),
            default_root=working_directory,
        )
        sandbox_read_roots = _dedupe(
            [*policy.read_roots, *([docker_socket] if docker_socket else [])]
        )
        sandbox_write_roots = _dedupe(
            [*policy.write_roots, *([docker_socket] if docker_socket else [])]
        )
        return LocalFilesystemBoundary(
            working_directory=working_directory.resolve(),
            read_roots=tuple(policy.read_roots),
            write_roots=tuple(policy.write_roots),
            sandbox_read_roots=tuple(sandbox_read_roots),
            sandbox_write_roots=tuple(sandbox_write_roots),
            protected_roots=tuple(protected_roots),
            policy=policy,
        )


async def local_boundary_from_tool_context(context) -> LocalFilesystemBoundary:
    if getattr(context, "db", None) is not None and hasattr(context, "workspace_id"):
        return await LocalFilesystemBoundaryResolver(context.db).resolve(context)
    protected_roots = _protected_roots()
    docker_socket = _existing_unix_docker_socket()
    policy = FilesystemPolicy(
        protected_roots=_dedupe(
            [*protected_roots, *([docker_socket] if docker_socket else [])]
        )
    )
    sandbox_read_roots = _dedupe(
        [*policy.read_roots, *([docker_socket] if docker_socket else [])]
    )
    sandbox_write_roots = _dedupe(
        [*policy.write_roots, *([docker_socket] if docker_socket else [])]
    )
    return LocalFilesystemBoundary(
        working_directory=policy.default_root,
        read_roots=tuple(policy.read_roots),
        write_roots=tuple(policy.write_roots),
        sandbox_read_roots=tuple(sandbox_read_roots),
        sandbox_write_roots=tuple(sandbox_write_roots),
        protected_roots=tuple(protected_roots),
        policy=policy,
    )


def _configured_roots() -> list[Path]:
    value = str(getattr(settings, "agent_filesystem_roots", "") or "")
    repo_root = Path(settings.repo_root).expanduser().resolve()
    roots: list[Path] = []
    for raw in value.split(os.pathsep):
        if not raw.strip():
            continue
        root = Path(raw.strip()).expanduser().resolve()
        # A broad capability that contains the product checkout would make the
        # source visible to shell processes. Operators must declare narrower
        # sibling roots instead.
        if _is_relative_to(repo_root, root):
            continue
        docker_socket = _docker_socket_path()
        if docker_socket is not None and _is_relative_to(docker_socket, root):
            continue
        if root.is_dir():
            roots.append(root)
    return _dedupe(roots)


def _protected_roots() -> list[Path]:
    repo_root = Path(settings.repo_root).expanduser().resolve()
    data_root = Path(settings.bioinfoflow_home).expanduser().resolve()
    protected = [Path(settings.state_root).expanduser().resolve()]

    backend_root = Path(BACKEND_ROOT).resolve()
    for name in ("app", "alembic", "scripts", "tests"):
        candidate = backend_root / name
        if candidate.exists():
            protected.append(candidate.resolve())
    if backend_root.is_dir():
        for child in backend_root.iterdir():
            if child.is_file() and child.name not in {".python-version"}:
                protected.append(child.resolve())

    if repo_root != Path("/") and repo_root.is_dir():
        for child in repo_root.iterdir():
            resolved = child.resolve()
            if child.is_file():
                protected.append(resolved)
                continue
            if resolved == backend_root or _is_relative_to(data_root, resolved):
                continue
            if child.name in {".venv", ".next", "node_modules"}:
                continue
            protected.append(resolved)
    return _dedupe(protected)


def _dedupe(roots: list[Path]) -> list[Path]:
    result: list[Path] = []
    for root in roots:
        resolved = Path(root).expanduser().resolve()
        if resolved not in result:
            result.append(resolved)
    return result


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _docker_socket_path() -> Path | None:
    value = str(getattr(settings, "docker_socket", "") or "")
    if not value.startswith("unix://"):
        return None
    return Path(value.removeprefix("unix://")).expanduser().resolve()


def _existing_unix_docker_socket() -> Path | None:
    docker_socket = _docker_socket_path()
    if docker_socket is None:
        return None
    try:
        mode = docker_socket.stat().st_mode
    except OSError:
        return None
    return docker_socket if stat.S_ISSOCK(mode) else None
