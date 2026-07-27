from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.path_layout import projects_root
from app.repositories.project_repo import ProjectRepository
from app.utils.exceptions import ValidationError
from app.utils.project_directory_names import (
    normalize_project_directory_name,
    project_directory_candidate,
)


MAX_CANDIDATES = 10_000
_DIRECTORY_NAME_CONSTRAINT = "uq_projects_directory_name"
_SQLITE_DIRECTORY_NAME_CONFLICT = "unique constraint failed: projects.directory_name"
_HAS_SECURE_DIRECTORY_FDS = (
    hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and os.open in os.supports_dir_fd
    and os.mkdir in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.unlink in os.supports_dir_fd
    and os.rmdir in os.supports_dir_fd
)


@dataclass(slots=True)
class ManagedProjectReservation:
    project: Project
    root: Path
    root_device: int
    root_inode: int
    root_fd: int | None


class ProjectDirectoryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ProjectRepository(session)

    async def add_pending(self, data: dict[str, Any]) -> ManagedProjectReservation:
        if not _secure_directory_fds_supported():
            raise ValidationError(
                "Secure project directory reservations are not supported on this platform"
            )
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
                opened_root = _open_owned_root(root)
            except OSError:
                await self.repo.delete_pending(project)
                raise
            if opened_root is None:
                await self.repo.delete_pending(project)
                continue
            root_fd, root_stat = opened_root
            reservation = ManagedProjectReservation(
                project=project,
                root=root,
                root_device=root_stat.st_dev,
                root_inode=root_stat.st_ino,
                root_fd=root_fd,
            )
            try:
                layout_created = _create_project_layout(reservation)
            except Exception:
                try:
                    await self.session.rollback()
                finally:
                    _cleanup_owned_root(reservation)
                raise
            if not layout_created:
                try:
                    await self.repo.delete_pending(project)
                finally:
                    _cleanup_owned_root(reservation)
                continue
            return reservation

        raise ValidationError(
            "Unable to allocate a project directory after checking 10,000 candidates"
        )

    async def commit(self, reservation: ManagedProjectReservation) -> Project:
        try:
            await self.session.commit()
        except Exception:
            try:
                await self.session.rollback()
            finally:
                _cleanup_owned_root(reservation)
            raise

        _close_reservation_fd(reservation)
        await self.session.refresh(reservation.project)
        return reservation.project

    async def discard(self, reservation: ManagedProjectReservation) -> None:
        try:
            await self.repo.delete_pending(reservation.project)
        except Exception:
            await self.session.rollback()
            raise
        finally:
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


def _open_owned_root(path: Path) -> tuple[int, os.stat_result] | None:
    if not _secure_directory_fds_supported():
        raise ValidationError(
            "Secure project directory reservations are not supported on this platform"
        )

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        root_fd = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError:
        if not _path_is_directory(path):
            return None
        raise

    keep_open = False
    try:
        root_stat = os.fstat(root_fd)
        if not stat.S_ISDIR(root_stat.st_mode):
            return None
        if not _path_matches_identity(path, root_stat.st_dev, root_stat.st_ino):
            return None
        keep_open = True
        return root_fd, root_stat
    finally:
        if not keep_open:
            os.close(root_fd)


def _create_project_layout(reservation: ManagedProjectReservation) -> bool:
    root_fd = reservation.root_fd
    if root_fd is None:
        return False
    if not _reservation_path_matches(reservation):
        return False

    try:
        os.mkdir("data", dir_fd=root_fd)
        os.mkdir("runs", dir_fd=root_fd)
    except OSError:
        if not _reservation_path_matches(reservation):
            return False
        raise
    return _reservation_path_matches(reservation)


def _cleanup_owned_root(reservation: ManagedProjectReservation) -> None:
    root_fd = reservation.root_fd
    if root_fd is None:
        return
    reservation.root_fd = None
    contents_removed = False
    try:
        try:
            _remove_directory_contents(root_fd)
            contents_removed = True
        except OSError:
            pass
        if contents_removed and _reservation_path_matches(reservation):
            try:
                os.rmdir(reservation.root)
            except OSError:
                pass
    finally:
        os.close(root_fd)


def _remove_directory_contents(directory_fd: int) -> None:
    for name in os.listdir(directory_fd):
        try:
            entry_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        if stat.S_ISDIR(entry_stat.st_mode):
            child_fd = os.open(
                name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            try:
                child_stat = os.fstat(child_fd)
                if (
                    child_stat.st_dev != entry_stat.st_dev
                    or child_stat.st_ino != entry_stat.st_ino
                ):
                    continue
                _remove_directory_contents(child_fd)
            finally:
                os.close(child_fd)
            try:
                os.rmdir(name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            continue
        try:
            os.unlink(name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def _close_reservation_fd(reservation: ManagedProjectReservation) -> None:
    root_fd = reservation.root_fd
    if root_fd is None:
        return
    reservation.root_fd = None
    os.close(root_fd)


def _reservation_path_matches(reservation: ManagedProjectReservation) -> bool:
    return _path_matches_identity(
        reservation.root,
        reservation.root_device,
        reservation.root_inode,
    )


def _path_matches_identity(path: Path, device: int, inode: int) -> bool:
    try:
        path_stat = path.lstat()
    except OSError:
        return False
    return (
        path_stat.st_dev == device
        and path_stat.st_ino == inode
        and stat.S_ISDIR(path_stat.st_mode)
    )


def _path_is_directory(path: Path) -> bool:
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False


def _secure_directory_fds_supported() -> bool:
    return _HAS_SECURE_DIRECTORY_FDS
