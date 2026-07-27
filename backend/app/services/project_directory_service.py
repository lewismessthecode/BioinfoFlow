from __future__ import annotations

import os
import re
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import inspect as sqlalchemy_inspect
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
_POSTGRES_UNIQUE_VIOLATION = "23505"
_DIRECTORY_NAME_IN_MESSAGE = re.compile(
    rf"(?<![A-Za-z0-9_]){re.escape(_DIRECTORY_NAME_CONSTRAINT)}(?![A-Za-z0-9_])"
)
_HAS_SECURE_DIRECTORY_FDS = (
    hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and os.open in os.supports_dir_fd
    and os.mkdir in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.unlink in os.supports_dir_fd
    and os.rmdir in os.supports_dir_fd
    and os.rename in os.supports_dir_fd
)
_QUARANTINE_PREFIX = ".bioinfoflow-project-cleanup-"
_QUARANTINE_ATTEMPTS = 16


@dataclass(slots=True)
class ManagedProjectReservation:
    project: Project
    root: Path
    root_device: int
    root_inode: int
    root_fd: int | None
    parent_fd: int | None


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
            root_fd, parent_fd, root_stat = opened_root
            reservation = ManagedProjectReservation(
                project=project,
                root=root,
                root_device=root_stat.st_dev,
                root_inode=root_stat.st_ino,
                root_fd=root_fd,
                parent_fd=parent_fd,
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

        _close_reservation_fds(reservation)
        await self.session.refresh(reservation.project)
        return reservation.project

    async def discard(self, reservation: ManagedProjectReservation) -> None:
        try:
            project_state = sqlalchemy_inspect(reservation.project)
            if project_state.persistent:
                await self.repo.delete_pending(reservation.project)
            elif project_state.pending:
                self.session.expunge(reservation.project)
                await self.session.flush()
        except Exception:
            await self.session.rollback()
            raise
        finally:
            _cleanup_owned_root(reservation)

    async def _ensure_outer_transaction(self) -> None:
        bind = self.session.get_bind()
        if bind.dialect.name == "sqlite":
            connection = await self.session.connection()
            raw_connection = connection.sync_connection.connection
            driver_connection = getattr(raw_connection, "driver_connection", None)
            driver_in_transaction = getattr(
                driver_connection,
                "in_transaction",
                None,
            )
            if driver_in_transaction is False:
                await self.session.execute(text("BEGIN IMMEDIATE"))
            return
        if self.session.in_transaction():
            return
        await self.session.begin()


def is_project_directory_name_conflict(error: IntegrityError) -> bool:
    for original in _exception_chain(error.orig):
        diagnostic = getattr(original, "diag", None)
        constraint_name = getattr(
            diagnostic,
            "constraint_name",
            None,
        ) or getattr(original, "constraint_name", None)
        if constraint_name is not None:
            if constraint_name == _DIRECTORY_NAME_CONSTRAINT:
                return True
            continue
        message = str(original)
        if _SQLITE_DIRECTORY_NAME_CONFLICT in message.casefold():
            return True
        sqlstate = getattr(original, "sqlstate", None) or getattr(
            original,
            "pgcode",
            None,
        )
        if str(
            sqlstate or ""
        ) == _POSTGRES_UNIQUE_VIOLATION and _DIRECTORY_NAME_IN_MESSAGE.search(message):
            return True
    return False


def _exception_chain(error: BaseException):
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        yield current
        cause = current.__cause__
        context = current.__context__
        if context is not None:
            pending.append(context)
        if cause is not None:
            pending.append(cause)


def _path_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _open_owned_root(path: Path) -> tuple[int, int, os.stat_result] | None:
    if not _secure_directory_fds_supported():
        raise ValidationError(
            "Secure project directory reservations are not supported on this platform"
        )

    flags = _directory_open_flags()
    try:
        parent_fd = os.open(path.parent, flags)
    except FileNotFoundError:
        return None

    root_fd: int | None = None
    keep_open = False
    try:
        try:
            root_fd = os.open(path.name, flags, dir_fd=parent_fd)
        except FileNotFoundError:
            return None
        except OSError:
            if not _entry_is_directory(parent_fd, path.name):
                return None
            raise

        root_stat = os.fstat(root_fd)
        if not stat.S_ISDIR(root_stat.st_mode):
            return None
        if not _entry_matches_identity(
            parent_fd,
            path.name,
            root_stat.st_dev,
            root_stat.st_ino,
        ):
            return None
        keep_open = True
        return root_fd, parent_fd, root_stat
    finally:
        if not keep_open:
            if root_fd is not None:
                os.close(root_fd)
            os.close(parent_fd)


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
    parent_fd = reservation.parent_fd
    if root_fd is None or parent_fd is None:
        _close_reservation_fds(reservation)
        return
    reservation.root_fd = None
    reservation.parent_fd = None
    try:
        quarantine_name = _move_root_to_quarantine(reservation, parent_fd)
        if quarantine_name is None:
            return
        if not _entry_matches_reservation(
            parent_fd,
            quarantine_name,
            reservation,
        ):
            _restore_quarantined_entry(
                parent_fd,
                quarantine_name,
                reservation.root.name,
            )
            return
        try:
            _remove_directory_contents(root_fd)
        except OSError:
            _restore_quarantined_entry(
                parent_fd,
                quarantine_name,
                reservation.root.name,
            )
            return
        if not _entry_matches_reservation(
            parent_fd,
            quarantine_name,
            reservation,
        ):
            _restore_quarantined_entry(
                parent_fd,
                quarantine_name,
                reservation.root.name,
            )
            return
        try:
            os.rmdir(quarantine_name, dir_fd=parent_fd)
        except OSError:
            try:
                _restore_quarantined_entry(
                    parent_fd,
                    quarantine_name,
                    reservation.root.name,
                )
            except OSError:
                pass
    finally:
        os.close(root_fd)
        os.close(parent_fd)


def _move_root_to_quarantine(
    reservation: ManagedProjectReservation,
    parent_fd: int,
) -> str | None:
    for _ in range(_QUARANTINE_ATTEMPTS):
        quarantine_name = f"{_QUARANTINE_PREFIX}{secrets.token_hex(16)}"
        if _entry_exists_at(parent_fd, quarantine_name):
            continue
        try:
            os.rename(
                reservation.root.name,
                quarantine_name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
        except FileNotFoundError:
            return None
        except OSError:
            return None
        return quarantine_name
    return None


def _restore_quarantined_entry(
    parent_fd: int,
    quarantine_name: str,
    root_name: str,
) -> None:
    if _entry_exists_at(parent_fd, root_name):
        return
    try:
        os.rename(
            quarantine_name,
            root_name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
    except OSError:
        pass


def _remove_directory_contents(directory_fd: int) -> None:
    for name in os.listdir(directory_fd):
        try:
            entry_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        if stat.S_ISDIR(entry_stat.st_mode):
            child_fd = os.open(
                name,
                _directory_open_flags(),
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


def _close_reservation_fds(reservation: ManagedProjectReservation) -> None:
    root_fd = reservation.root_fd
    parent_fd = reservation.parent_fd
    reservation.root_fd = None
    reservation.parent_fd = None
    if root_fd is not None:
        os.close(root_fd)
    if parent_fd is not None:
        os.close(parent_fd)


def _reservation_path_matches(reservation: ManagedProjectReservation) -> bool:
    parent_fd = reservation.parent_fd
    if parent_fd is None:
        return False
    return _entry_matches_identity(
        parent_fd,
        reservation.root.name,
        reservation.root_device,
        reservation.root_inode,
    )


def _entry_matches_reservation(
    parent_fd: int,
    name: str,
    reservation: ManagedProjectReservation,
) -> bool:
    return _entry_matches_identity(
        parent_fd,
        name,
        reservation.root_device,
        reservation.root_inode,
    )


def _entry_matches_identity(
    parent_fd: int,
    name: str,
    device: int,
    inode: int,
) -> bool:
    try:
        entry_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        return False
    return (
        entry_stat.st_dev == device
        and entry_stat.st_ino == inode
        and stat.S_ISDIR(entry_stat.st_mode)
    )


def _entry_is_directory(parent_fd: int, name: str) -> bool:
    try:
        entry_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISDIR(entry_stat.st_mode)


def _entry_exists_at(parent_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _directory_open_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _secure_directory_fds_supported() -> bool:
    return _HAS_SECURE_DIRECTORY_FDS
