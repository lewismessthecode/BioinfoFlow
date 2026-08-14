from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest
from sqlalchemy import event

from app.models.agent_harness import AgentHarnessAttachment
from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.services.agent_harness.context_search import AgentContextSearch
from app.services.agent_harness.context_search import _search_local_paths
from app.services.agent_harness.contracts import OpenSessionRequest


def test_local_context_search_stops_at_the_entry_budget(monkeypatch, tmp_path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    entry_limit = 5_000
    for index in range(entry_limit + 1):
        (root / f"irrelevant-{index:04d}.txt").touch()

    original_scandir = os.scandir
    scanned_entries = 0

    class BoundedScandir:
        def __init__(self, stream) -> None:
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def __iter__(self):
            return self

        def __next__(self):
            nonlocal scanned_entries
            entry = next(self.stream)
            scanned_entries += 1
            if scanned_entries > entry_limit:
                raise RuntimeError("local context search exceeded its entry budget")
            return entry

    def bounded_scandir(path):
        return BoundedScandir(original_scandir(path))

    monkeypatch.setattr(os, "scandir", bounded_scandir)
    monkeypatch.setattr(
        glob._StringGlobber,
        "scandir",
        staticmethod(bounded_scandir),
    )

    assert _search_local_paths(root, "needle") == []


def test_local_context_search_stops_at_the_directory_budget(
    monkeypatch, tmp_path
) -> None:
    root = tmp_path / "project"
    directory_limit = 1_000
    for index in range(directory_limit):
        (root / f"empty-{index:04d}").mkdir(parents=True)

    original_scandir = os.scandir
    scanned_directories = 0

    def bounded_scandir(path):
        nonlocal scanned_directories
        scanned_directories += 1
        if scanned_directories > directory_limit:
            raise RuntimeError("local context search exceeded its directory budget")
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", bounded_scandir)

    assert _search_local_paths(root, "needle") == []


def test_local_context_search_stops_at_the_depth_budget(tmp_path) -> None:
    root = tmp_path / "project"
    deepest = root
    maximum_depth = 32
    for depth in range(maximum_depth + 1):
        deepest /= f"level-{depth:02d}"
    deepest.mkdir(parents=True)
    (deepest / "needle.txt").touch()

    assert _search_local_paths(root, "needle") == []


def test_local_context_search_does_not_follow_a_directory_swapped_to_a_symlink(
    monkeypatch, tmp_path
) -> None:
    root = tmp_path / "project"
    inside = root / "inside"
    inside.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "needle-secret.txt").touch()

    original_scandir = os.scandir
    swapped = False

    class SwappingEntry:
        def __init__(self, entry) -> None:
            self.entry = entry
            self.name = entry.name

        def is_symlink(self):
            return self.entry.is_symlink()

        def is_dir(self, *, follow_symlinks=True):
            nonlocal swapped
            result = self.entry.is_dir(follow_symlinks=follow_symlinks)
            if self.name == "inside" and not swapped:
                inside.rmdir()
                inside.symlink_to(outside, target_is_directory=True)
                swapped = True
            return result

    class SwappingScandir:
        def __init__(self, stream) -> None:
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def __iter__(self):
            return self

        def __next__(self):
            return SwappingEntry(next(self.stream))

    def swapping_scandir(path):
        stream = original_scandir(path)
        scanned_path = None
        if isinstance(path, int):
            for descriptor_root in ("/proc/self/fd", "/dev/fd"):
                try:
                    scanned_path = Path(os.readlink(f"{descriptor_root}/{path}"))
                    break
                except OSError:
                    continue
        else:
            scanned_path = Path(path)
        if scanned_path == root:
            return SwappingScandir(stream)
        return stream

    monkeypatch.setattr(os, "scandir", swapping_scandir)

    assert _search_local_paths(root, "needle") == []


def test_local_context_search_keeps_deterministic_path_order(tmp_path) -> None:
    root = tmp_path / "project"
    nested = root / "alpha"
    nested.mkdir(parents=True)
    (nested / "zeta.txt").touch()
    (root / "beta.txt").touch()
    (root / "aardvark.txt").touch()

    assert [
        path.relative_to(root).as_posix() for path in _search_local_paths(root, "")
    ] == [
        "aardvark.txt",
        "alpha",
        "alpha/zeta.txt",
        "beta.txt",
    ]


@pytest.mark.asyncio
async def test_attachment_context_search_applies_the_result_limit_in_sql(
    harness_db,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id="30000000-0000-0000-0000-000000000001",
            permission_mode="ask_dangerous",
            prompt_snapshot={"content": "test"},
        )
    )
    harness_db.add_all(
        AgentHarnessAttachment(
            session_id=str(session.id),
            workspace_id=str(session.workspace_id),
            user_id=session.user_id,
            kind="file",
            source="upload",
            filename=f"match-{index:03d}.txt",
            storage_path=f"{session.id}/attachment-{index:03d}",
            mime_type="text/plain",
            size_bytes=1,
            status="ready",
        )
        for index in range(75)
    )
    await harness_db.commit()

    statements: list[str] = []
    sync_engine = harness_db.get_bind()

    def capture_statement(
        _connection, _cursor, statement, _parameters, _context, _many
    ):
        if "FROM agent_attachments" in statement:
            statements.append(statement)

    event.listen(sync_engine, "before_cursor_execute", capture_statement)
    try:
        result = await AgentContextSearch(harness_db).search(
            workspace_id=str(session.workspace_id),
            user_id=session.user_id,
            query="match",
            scope="file",
            session_id=str(session.id),
        )
    finally:
        event.remove(sync_engine, "before_cursor_execute", capture_statement)

    assert len(result.results) == 50
    assert statements
    assert " LIMIT " in statements[-1].upper()
