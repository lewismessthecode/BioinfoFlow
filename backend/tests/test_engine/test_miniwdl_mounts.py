from __future__ import annotations

from pathlib import Path

import app.engine.miniwdl_mounts as mounts_module
from app.engine.miniwdl_mounts import (
    ContainerPathMapping,
    configured_run_mounts,
    configured_shared_mounts,
    docker_mount_path_mappings,
)


def test_configured_shared_mounts_returns_identity_mappings(monkeypatch):
    monkeypatch.setattr(
        mounts_module,
        "deliveries_root",
        lambda: Path("/srv/bioinfoflow/sources/deliveries"),
    )
    monkeypatch.setattr(
        mounts_module,
        "reference_root",
        lambda: Path("/srv/bioinfoflow/sources/reference"),
    )
    monkeypatch.setattr(
        mounts_module,
        "database_root",
        lambda: Path("/srv/bioinfoflow/sources/database"),
    )

    mounts = configured_shared_mounts()

    assert mounts == (
        ContainerPathMapping(
            container_root=Path("/srv/bioinfoflow/sources/deliveries"),
            host_root=Path("/srv/bioinfoflow/sources/deliveries"),
            read_only=True,
        ),
        ContainerPathMapping(
            container_root=Path("/srv/bioinfoflow/sources/reference"),
            host_root=Path("/srv/bioinfoflow/sources/reference"),
            read_only=True,
        ),
        ContainerPathMapping(
            container_root=Path("/srv/bioinfoflow/sources/database"),
            host_root=Path("/srv/bioinfoflow/sources/database"),
            read_only=True,
        ),
    )


def test_configured_run_mounts_identity_data_input_and_results():
    host_dir = "/srv/bioinfoflow/projects/proj-abc/runs/run-xyz/engine/wdl/work/20260417_042839_Deaf_20/call-PREPARATION"

    mounts = configured_run_mounts(host_dir)

    # Siblings under run_root — never nested, so Swarm cannot silently
    # demote the rw results mount via a ro parent.
    assert mounts == (
        ContainerPathMapping(
            container_root=Path("/srv/bioinfoflow/projects/proj-abc/data"),
            host_root=Path("/srv/bioinfoflow/projects/proj-abc/data"),
            read_only=True,
        ),
        ContainerPathMapping(
            container_root=Path(
                "/srv/bioinfoflow/projects/proj-abc/runs/run-xyz/input"
            ),
            host_root=Path("/srv/bioinfoflow/projects/proj-abc/runs/run-xyz/input"),
            read_only=True,
        ),
        ContainerPathMapping(
            container_root=Path(
                "/srv/bioinfoflow/projects/proj-abc/runs/run-xyz/results"
            ),
            host_root=Path("/srv/bioinfoflow/projects/proj-abc/runs/run-xyz/results"),
            read_only=False,
        ),
    )


def test_configured_run_mounts_supports_external_project_layout():
    host_dir = (
        "/lab/project-a/runs/run-ext/engine/wdl/work/20260417_042839_Demo/call-TASK"
    )

    mounts = configured_run_mounts(host_dir)

    assert mounts == (
        ContainerPathMapping(
            container_root=Path("/lab/project-a/data"),
            host_root=Path("/lab/project-a/data"),
            read_only=True,
        ),
        ContainerPathMapping(
            container_root=Path("/lab/project-a/runs/run-ext/input"),
            host_root=Path("/lab/project-a/runs/run-ext/input"),
            read_only=True,
        ),
        ContainerPathMapping(
            container_root=Path("/lab/project-a/runs/run-ext/results"),
            host_root=Path("/lab/project-a/runs/run-ext/results"),
            read_only=False,
        ),
    )


def test_configured_run_mounts_uses_rightmost_runs_segment():
    host_dir = (
        "/lab/project-a/runs/archive-copy/engine/wdl/work/imported/runs/run-real/"
        "engine/wdl/work/20260417_042839_Demo/call-TASK"
    )

    mounts = configured_run_mounts(host_dir)

    assert mounts[0] == ContainerPathMapping(
        container_root=Path(
            "/lab/project-a/runs/archive-copy/engine/wdl/work/imported/data"
        ),
        host_root=Path(
            "/lab/project-a/runs/archive-copy/engine/wdl/work/imported/data"
        ),
        read_only=True,
    )
    assert mounts[1] == ContainerPathMapping(
        container_root=Path(
            "/lab/project-a/runs/archive-copy/engine/wdl/work/imported/"
            "runs/run-real/input"
        ),
        host_root=Path(
            "/lab/project-a/runs/archive-copy/engine/wdl/work/imported/"
            "runs/run-real/input"
        ),
        read_only=True,
    )
    assert mounts[2] == ContainerPathMapping(
        container_root=Path(
            "/lab/project-a/runs/archive-copy/engine/wdl/work/imported/"
            "runs/run-real/results"
        ),
        host_root=Path(
            "/lab/project-a/runs/archive-copy/engine/wdl/work/imported/"
            "runs/run-real/results"
        ),
        read_only=False,
    )


def test_configured_run_mounts_never_nests_targets():
    # Regression guard for the deaf_20 "read sample list error" silent
    # failure: Docker Swarm demotes a rw child mount to ro when its
    # parent is mounted ro, so every mount we declare for a run MUST
    # be a sibling of the others.
    host_dir = (
        "/srv/bioinfoflow/projects/proj-abc/runs/run-xyz/"
        "engine/wdl/work/20260417_042839_Deaf_20/call-PREPARATION"
    )

    mounts = configured_run_mounts(host_dir)

    targets = [m.container_root for m in mounts]
    for i, a in enumerate(targets):
        for j, b in enumerate(targets):
            if i == j:
                continue
            assert a not in b.parents, (
                f"mount target {b} is nested under {a} — Swarm will "
                "silently make {b} read-only"
            )


def test_configured_run_mounts_returns_empty_outside_projects_root():
    assert configured_run_mounts("/tmp/unrelated/task") == ()


def test_configured_run_mounts_returns_empty_for_shallow_dir():
    # Missing 'runs/{run_id}' segment.
    assert configured_run_mounts("/srv/bioinfoflow/projects/proj-abc") == ()


def test_docker_mount_path_mappings_returns_empty_when_escape_hatch_off(monkeypatch):
    mounts_module._reset_mount_cache()
    monkeypatch.setattr(mounts_module.settings, "allow_path_translation", False)

    assert docker_mount_path_mappings() == ()
