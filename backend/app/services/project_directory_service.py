from __future__ import annotations

import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.path_layout import ensure_project_layout, projects_root
from app.repositories.project_repo import ProjectRepository
from app.utils.exceptions import ValidationError
from app.utils.project_directory_names import (
    normalize_project_directory_name,
    project_directory_candidate,
)


MAX_CANDIDATES = 10_000
_DIRECTORY_NAME_CONSTRAINT = "uq_projects_directory_name"
_SQLITE_DIRECTORY_NAME_CONFLICT = "unique constraint failed: projects.directory_name"


@dataclass(frozen=True, slots=True)
class ManagedProjectReservation:
    project: Project
    root: Path
    root_device: int
    root_inode: int


class ProjectDirectoryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ProjectRepository(session)

    async def add_pending(self, data: dict[str, Any]) -> ManagedProjectReservation:
        project_data = dict(data)
        project_name = str(project_data.get("name") or "")
        base_name = normalize_project_directory_name(project_name)
        parent = projects_root()
        parent.mkdir(parents=True, exist_ok=True)
        await self._ensure_outer_transaction()

        for ordinal in range(1, MAX_CANDIDATES + 1):
            directory_name = project_directory_candidate(base_name, ordinal)
            root = parent / directory_name
            if _path_entry_exists(root):
                continue

            project_data["directory_name"] = directory_name
            try:
                async with self.session.begin_nested():
                    project = await self.repo.add(**project_data)
            except IntegrityError as exc:
                if is_project_directory_name_conflict(exc):
                    continue
                raise

            try:
                root.mkdir(parents=False, exist_ok=False)
            except FileExistsError:
                await self.repo.delete_pending(project)
                continue

            try:
                root_stat = root.lstat()
            except FileNotFoundError:
                await self.repo.delete_pending(project)
                continue
            except OSError:
                await self.repo.delete_pending(project)
                raise
            if not stat.S_ISDIR(root_stat.st_mode):
                await self.repo.delete_pending(project)
                continue
            reservation = ManagedProjectReservation(
                project=project,
                root=root,
                root_device=root_stat.st_dev,
                root_inode=root_stat.st_ino,
            )
            try:
                ensure_project_layout(project)
            except Exception:
                await self._discard_after_failure(reservation)
                raise
            return reservation

        raise ValidationError(
            "Unable to allocate a project directory after checking 10,000 candidates"
        )

    async def commit(self, reservation: ManagedProjectReservation) -> Project:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            _cleanup_owned_root(reservation)
            raise

        await self.session.refresh(reservation.project)
        return reservation.project

    async def discard(self, reservation: ManagedProjectReservation) -> None:
        await self.repo.delete_pending(reservation.project)
        _cleanup_owned_root(reservation)

    async def _discard_after_failure(
        self,
        reservation: ManagedProjectReservation,
    ) -> None:
        try:
            await self.repo.delete_pending(reservation.project)
        except Exception:
            await self.session.rollback()
        _cleanup_owned_root(reservation)

    async def _ensure_outer_transaction(self) -> None:
        if self.session.in_transaction():
            return
        bind = self.session.get_bind()
        if bind.dialect.name == "sqlite":
            await self.session.execute(text("BEGIN"))
            return
        await self.session.begin()


def is_project_directory_name_conflict(error: IntegrityError) -> bool:
    original = error.orig
    diagnostic = getattr(original, "diag", None)
    if getattr(diagnostic, "constraint_name", None) == _DIRECTORY_NAME_CONSTRAINT:
        return True
    return _SQLITE_DIRECTORY_NAME_CONFLICT in str(original).casefold()


def _path_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _cleanup_owned_root(reservation: ManagedProjectReservation) -> None:
    try:
        root_stat = reservation.root.lstat()
    except FileNotFoundError:
        return
    if (
        root_stat.st_dev != reservation.root_device
        or root_stat.st_ino != reservation.root_inode
        or not stat.S_ISDIR(root_stat.st_mode)
    ):
        return
    shutil.rmtree(reservation.root)
