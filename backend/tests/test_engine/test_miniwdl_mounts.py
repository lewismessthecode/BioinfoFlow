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


def test_configured_run_mounts_identity_input_and_results(monkeypatch):
    monkeypatch.setattr(
        mounts_module, "projects_root", lambda: Path("/srv/bioinfoflow/projects")
    )

    host_dir = "/srv/bioinfoflow/projects/proj-abc/runs/run-xyz/engine/wdl/work/20260417_042839_Deaf_20/call-PREPARATION"

    mounts = configured_run_mounts(host_dir)

    # Siblings under run_root — never nested, so Swarm cannot silently
    # demote the rw results mount via a ro parent.
    assert mounts == (
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


def test_configured_run_mounts_never_nests_targets(monkeypatch):
    # Regression guard for the deaf_20 "read sample list error" silent
    # failure: Docker Swarm demotes a rw child mount to ro when its
    # parent is mounted ro, so every mount we declare for a run MUST
    # be a sibling of the others.
    monkeypatch.setattr(
        mounts_module, "projects_root", lambda: Path("/srv/bioinfoflow/projects")
    )
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


def test_configured_run_mounts_returns_empty_outside_projects_root(monkeypatch):
    monkeypatch.setattr(
        mounts_module, "projects_root", lambda: Path("/srv/bioinfoflow/projects")
    )

    assert configured_run_mounts("/tmp/unrelated/task") == ()


def test_configured_run_mounts_returns_empty_for_shallow_dir(monkeypatch):
    monkeypatch.setattr(
        mounts_module, "projects_root", lambda: Path("/srv/bioinfoflow/projects")
    )

    # Missing 'runs/{run_id}' segment.
    assert configured_run_mounts("/srv/bioinfoflow/projects/proj-abc") == ()


def test_docker_mount_path_mappings_returns_empty_when_escape_hatch_off(monkeypatch):
    mounts_module._reset_mount_cache()
    monkeypatch.setattr(mounts_module.settings, "allow_path_translation", False)

    assert docker_mount_path_mappings() == ()
