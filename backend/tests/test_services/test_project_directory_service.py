from __future__ import annotations

import asyncio
import errno
import os
import shutil
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.project import Project
from app.path_layout import projects_root
from app.repositories.project_repo import ProjectRepository
from app.services.project_directory_service import (
    MAX_CANDIDATES,
    ProjectDirectoryService,
    is_project_directory_name_conflict,
)
from app.utils.exceptions import ValidationError
from app.utils.project_directory_names import project_directory_candidate


def _project_data(name: str = "测试") -> dict[str, object]:
    return {
        "name": name,
        "description": None,
        "storage_mode": "managed",
        "external_root_path": None,
        "user_id": "dev",
    }


async def _directory_names(session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(Project.directory_name).order_by(Project.directory_name)
    )
    return [name for name in result.scalars() if name is not None]


def _assert_fd_closed(file_descriptor: int | None) -> None:
    assert file_descriptor is not None
    with pytest.raises(OSError) as caught:
        os.fstat(file_descriptor)
    assert caught.value.errno == errno.EBADF


@pytest.mark.asyncio
async def test_allocates_readable_suffixes_and_creates_layout(db_session) -> None:
    service = ProjectDirectoryService(db_session)

    projects = []
    for _ in range(3):
        reservation = await service.add_pending(_project_data())
        root_fd = reservation.root_fd
        parent_fd = reservation.parent_fd
        projects.append(await service.commit(reservation))
        assert reservation.root_fd is None
        assert reservation.parent_fd is None
        _assert_fd_closed(root_fd)
        _assert_fd_closed(parent_fd)

    assert [project.directory_name for project in projects] == [
        "ce-shi",
        "ce-shi-2",
        "ce-shi-3",
    ]
    for project in projects:
        root = projects_root() / str(project.directory_name)
        assert (root / "data").is_dir()
        assert (root / "runs").is_dir()


@pytest.mark.asyncio
async def test_skips_an_existing_regular_directory(db_session) -> None:
    occupied = projects_root() / "ce-shi"
    occupied.mkdir(parents=True)

    service = ProjectDirectoryService(db_session)
    project = await service.commit(await service.add_pending(_project_data()))

    assert project.directory_name == "ce-shi-2"
    assert occupied.is_dir()


@pytest.mark.asyncio
async def test_skips_a_dangling_symlink_without_following_it(db_session) -> None:
    root = projects_root()
    root.mkdir(parents=True)
    dangling = root / "ce-shi"
    dangling.symlink_to(root / "missing-target", target_is_directory=True)

    service = ProjectDirectoryService(db_session)
    project = await service.commit(await service.add_pending(_project_data()))

    assert project.directory_name == "ce-shi-2"
    assert dangling.is_symlink()
    assert not dangling.exists()


@pytest.mark.asyncio
async def test_skips_a_database_reservation_when_disk_entry_is_missing(
    db_session,
) -> None:
    await ProjectRepository(db_session).create(
        **_project_data(),
        directory_name="ce-shi",
    )

    service = ProjectDirectoryService(db_session)
    project = await service.commit(await service.add_pending(_project_data()))

    assert project.directory_name == "ce-shi-2"


@pytest.mark.asyncio
async def test_two_sessions_concurrently_commit_distinct_names(db_engine) -> None:
    session_maker = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async def create_project() -> str:
        async with session_maker() as session:
            service = ProjectDirectoryService(session)
            reservation = await service.add_pending(_project_data())
            project = await service.commit(reservation)
            return str(project.directory_name)

    names = await asyncio.gather(create_project(), create_project())

    async with session_maker() as session:
        assert sorted(names) == ["ce-shi", "ce-shi-2"]
        assert await _directory_names(session) == ["ce-shi", "ce-shi-2"]


class _PostgresDiag:
    def __init__(self, constraint_name: str):
        self.constraint_name = constraint_name


class _PostgresError(Exception):
    def __init__(self, constraint_name: str):
        self.diag = _PostgresDiag(constraint_name)


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        (_PostgresError("uq_projects_directory_name"), True),
        (_PostgresError("uq_projects_name"), False),
        (Exception("UNIQUE constraint failed: projects.directory_name"), True),
        (Exception("UNIQUE constraint failed: projects.name"), False),
        (Exception("database is locked"), False),
    ],
)
def test_recognizes_only_directory_name_unique_conflicts(
    original: Exception,
    expected: bool,
) -> None:
    error = IntegrityError("statement", {}, original)

    assert is_project_directory_name_conflict(error) is expected


@pytest.mark.asyncio
async def test_unrelated_integrity_error_is_reraised_unchanged(
    db_session,
    monkeypatch,
) -> None:
    service = ProjectDirectoryService(db_session)
    expected = IntegrityError(
        "statement",
        {},
        Exception("UNIQUE constraint failed: projects.name"),
    )

    async def fail_add(**data):
        del data
        raise expected

    monkeypatch.setattr(service.repo, "add", fail_add)

    with pytest.raises(IntegrityError) as caught:
        await service.add_pending(_project_data())

    assert caught.value is expected


@pytest.mark.asyncio
async def test_mkdir_race_discards_pending_row_and_uses_next_suffix(
    db_session,
    monkeypatch,
) -> None:
    original_mkdir = Path.mkdir
    lost_candidate = projects_root() / "ce-shi"
    raced = False

    def race_once(
        self: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        nonlocal raced
        if self == lost_candidate and not raced:
            raced = True
            original_mkdir(self, mode=mode, parents=parents, exist_ok=exist_ok)
            raise FileExistsError(self)
        original_mkdir(self, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", race_once)
    service = ProjectDirectoryService(db_session)

    project = await service.commit(await service.add_pending(_project_data()))

    assert raced is True
    assert project.directory_name == "ce-shi-2"
    assert await _directory_names(db_session) == ["ce-shi-2"]
    assert lost_candidate.is_dir()


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement_kind", ["symlink", "directory"])
async def test_root_replaced_after_identity_check_is_not_used_for_layout(
    db_session,
    monkeypatch,
    replacement_kind: str,
) -> None:
    original_mkdir = os.mkdir
    candidate = projects_root() / "ce-shi"
    victim = projects_root().parent / "victim"
    victim.mkdir()
    marker = victim / "keep.txt"
    marker.write_text("keep")
    replaced = False

    def replace_before_layout(
        path,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        nonlocal replaced
        is_layout_mkdir = (dir_fd is not None and path == "data") or (
            dir_fd is None and Path(path) == candidate / "data"
        )
        if is_layout_mkdir and not replaced:
            replaced = True
            shutil.rmtree(candidate)
            if replacement_kind == "symlink":
                candidate.symlink_to(victim, target_is_directory=True)
            else:
                original_mkdir(candidate)
                (candidate / "replacement.txt").write_text("keep")
        original_mkdir(path, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "mkdir", replace_before_layout)
    service = ProjectDirectoryService(db_session)

    project = await service.commit(await service.add_pending(_project_data()))

    assert project.directory_name == "ce-shi-2"
    assert replaced is True
    assert marker.read_text() == "keep"
    assert not (victim / "data").exists()
    assert not (victim / "runs").exists()
    if replacement_kind == "directory":
        assert (candidate / "replacement.txt").read_text() == "keep"
        assert not (candidate / "data").exists()
        assert not (candidate / "runs").exists()
    else:
        assert candidate.is_symlink()
    assert await _directory_names(db_session) == ["ce-shi-2"]


@pytest.mark.asyncio
async def test_layout_failure_rolls_back_and_removes_only_owned_root(
    db_session,
    monkeypatch,
) -> None:
    original_mkdir = os.mkdir

    def fail_layout(
        path,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        is_data_directory = (dir_fd is not None and path == "data") or (
            dir_fd is None and Path(path) == projects_root() / "ce-shi" / "data"
        )
        if is_data_directory:
            raise RuntimeError("layout failed")
        original_mkdir(path, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "mkdir", fail_layout)
    service = ProjectDirectoryService(db_session)

    with pytest.raises(RuntimeError, match="layout failed"):
        await service.add_pending(_project_data())

    assert db_session.in_transaction() is False
    assert await _directory_names(db_session) == []
    assert not (projects_root() / "ce-shi").exists()


@pytest.mark.asyncio
async def test_commit_failure_rolls_back_and_removes_owned_root(
    db_session,
    monkeypatch,
) -> None:
    service = ProjectDirectoryService(db_session)
    reservation = await service.add_pending(_project_data())
    root_fd = reservation.root_fd
    parent_fd = reservation.parent_fd

    async def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="commit failed"):
        await service.commit(reservation)

    assert reservation.root_fd is None
    assert reservation.parent_fd is None
    _assert_fd_closed(root_fd)
    _assert_fd_closed(parent_fd)
    assert await _directory_names(db_session) == []
    assert not reservation.root.exists()
    assert not any(
        path.name.startswith(".bioinfoflow-project-cleanup-")
        for path in projects_root().iterdir()
    )


@pytest.mark.asyncio
async def test_discard_does_not_follow_replacement_symlink(
    db_session,
) -> None:
    service = ProjectDirectoryService(db_session)
    reservation = await service.add_pending(_project_data())
    root_fd = reservation.root_fd
    parent_fd = reservation.parent_fd
    victim = projects_root().parent / "victim"
    victim.mkdir()
    marker = victim / "keep.txt"
    marker.write_text("keep")
    shutil.rmtree(reservation.root)
    reservation.root.symlink_to(victim, target_is_directory=True)

    await service.discard(reservation)

    assert reservation.root_fd is None
    assert reservation.parent_fd is None
    _assert_fd_closed(root_fd)
    _assert_fd_closed(parent_fd)
    assert reservation.root.is_symlink()
    assert marker.read_text() == "keep"
    assert await _directory_names(db_session) == []


@pytest.mark.asyncio
async def test_cleanup_does_not_recurse_into_root_replaced_after_identity_check(
    db_session,
    monkeypatch,
) -> None:
    service = ProjectDirectoryService(db_session)
    reservation = await service.add_pending(_project_data())
    root_fd = reservation.root_fd
    parent_fd = reservation.parent_fd
    victim = projects_root().parent / "victim"
    victim.mkdir()
    marker = victim / "keep.txt"
    marker.write_text("keep")
    original_lstat = Path.lstat
    original_rename = os.rename
    replaced = False

    def replace_root() -> None:
        nonlocal replaced
        if not replaced:
            replaced = True
            shutil.rmtree(reservation.root)
            reservation.root.symlink_to(victim, target_is_directory=True)

    def replace_after_identity_check(self: Path):
        result = original_lstat(self)
        if self == reservation.root:
            replace_root()
        return result

    def replace_before_quarantine(
        src,
        dst,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        if src == reservation.root.name and src_dir_fd is not None:
            replace_root()
        original_rename(
            src,
            dst,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(Path, "lstat", replace_after_identity_check)
    monkeypatch.setattr(os, "rename", replace_before_quarantine)

    await service.discard(reservation)

    assert reservation.root_fd is None
    assert reservation.parent_fd is None
    _assert_fd_closed(root_fd)
    _assert_fd_closed(parent_fd)
    assert replaced is True
    assert reservation.root.is_symlink()
    assert marker.read_text() == "keep"
    assert await _directory_names(db_session) == []


@pytest.mark.asyncio
async def test_cleanup_does_not_remove_empty_root_replaced_after_identity_check(
    db_session,
    monkeypatch,
) -> None:
    service = ProjectDirectoryService(db_session)
    reservation = await service.add_pending(_project_data())
    original_lstat = Path.lstat
    original_rename = os.rename
    replacement_fd: int | None = None

    def replace_root() -> None:
        nonlocal replacement_fd
        if replacement_fd is None:
            shutil.rmtree(reservation.root)
            reservation.root.mkdir()
            replacement_fd = os.open(
                reservation.root,
                os.O_RDONLY | os.O_DIRECTORY,
            )

    def replace_with_empty_directory_after_identity_check(self: Path):
        result = original_lstat(self)
        if self == reservation.root:
            replace_root()
        return result

    def replace_before_quarantine(
        src,
        dst,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        if src == reservation.root.name and src_dir_fd is not None:
            replace_root()
        original_rename(
            src,
            dst,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(
        Path,
        "lstat",
        replace_with_empty_directory_after_identity_check,
    )
    monkeypatch.setattr(os, "rename", replace_before_quarantine)

    await service.discard(reservation)

    assert replacement_fd is not None
    try:
        replacement_stat = os.fstat(replacement_fd)
        current_stat = original_lstat(reservation.root)
        assert (current_stat.st_dev, current_stat.st_ino) == (
            replacement_stat.st_dev,
            replacement_stat.st_ino,
        )
    finally:
        os.close(replacement_fd)
    assert await _directory_names(db_session) == []


@pytest.mark.asyncio
async def test_platform_without_secure_directory_fds_fails_closed(
    db_session,
    monkeypatch,
) -> None:
    import app.services.project_directory_service as directory_service_module

    monkeypatch.setattr(directory_service_module, "_HAS_SECURE_DIRECTORY_FDS", False)
    service = ProjectDirectoryService(db_session)

    with pytest.raises(ValidationError, match="not supported"):
        await service.add_pending(_project_data())

    assert db_session.in_transaction() is False
    assert await _directory_names(db_session) == []
    assert not (projects_root() / "ce-shi").exists()


@pytest.mark.asyncio
async def test_raises_clear_validation_error_after_max_candidates(
    db_session,
) -> None:
    root = projects_root()
    root.mkdir(parents=True)
    for ordinal in range(1, MAX_CANDIDATES + 1):
        (root / project_directory_candidate("测试", ordinal)).mkdir()

    service = ProjectDirectoryService(db_session)

    with pytest.raises(ValidationError, match="10,000"):
        await service.add_pending(_project_data())
