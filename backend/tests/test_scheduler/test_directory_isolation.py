"""Tests for Path Contract V2 run directory isolation."""

from __future__ import annotations


import pytest

from app.scheduler.cleanup import WorkDirCleaner


# ── Cleanup covers the new run-scoped layout ─────────────────────────────


@pytest.mark.asyncio
async def test_cleanup_candidate_paths_include_new_layout(tmp_path):
    """runs/<run_id>/ is the cleanup boundary."""
    workspace = tmp_path / "workspace"
    new_dir = workspace / "runs" / "run_new_123"
    new_dir.mkdir(parents=True)
    (new_dir / "results").mkdir()

    cleaner = WorkDirCleaner()
    result = await cleaner.manual_cleanup(
        "run_new_123",
        workspace_path=workspace,
        engine="nextflow",
        runtime={},
    )

    assert new_dir.exists() is False
    assert result["deleted"]


@pytest.mark.asyncio
async def test_cleanup_wdl_removes_run_home(tmp_path):
    """WDL cleanup removes the run home, including engine work dirs."""
    workspace = tmp_path / "workspace"
    run_home = workspace / "runs" / "run_wdl_789"
    new_work = run_home / "engine" / "wdl" / "work"
    new_work.mkdir(parents=True)

    cleaner = WorkDirCleaner()
    result = await cleaner.manual_cleanup(
        "run_wdl_789",
        workspace_path=workspace,
        engine="wdl",
        runtime={"wdl_work_dir": "runs/run_wdl_789/work"},
    )

    assert run_home.exists() is False
    assert new_work.exists() is False
    assert result["deleted"] == [str(run_home)]


# ── resolve_output_path follows fixed V2 results root ────────────────────


@pytest.mark.asyncio
async def test_resolve_output_path_uses_run_results_root(tmp_path, db_session):
    """Output resolution is fixed to runs/<run_id>/results."""
    from app.models.project import Project
    from app.models.run import Run, RunStatus
    from app.repositories.project_repo import ProjectRepository
    from app.services.run_archive import RunArchiveService

    workspace = tmp_path / "ws"
    workspace.mkdir()
    results = workspace / "runs" / "run_explicit_outdir" / "results"
    results.mkdir(parents=True)

    project = Project(
        name="P",
        storage_mode="external",
        external_root_path=str(workspace),
        user_id="dev",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    run = Run(
        run_id="run_explicit_outdir",
        project_id=str(project.id),
        status=RunStatus.COMPLETED.value,
        config={"request": {"params": {"outdir": "ignored-by-v2"}}},
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    service = RunArchiveService(ProjectRepository(db_session))
    path = await service.resolve_output_path(run)
    assert path == results


@pytest.mark.asyncio
async def test_resolve_output_path_uses_run_results_root_without_config_outdir(
    tmp_path, db_session
):
    """Output resolution does not depend on config outdir."""
    from app.models.project import Project
    from app.models.run import Run, RunStatus
    from app.repositories.project_repo import ProjectRepository
    from app.services.run_archive import RunArchiveService

    workspace = tmp_path / "ws"
    workspace.mkdir()
    new_results = workspace / "runs" / "run_no_outdir" / "results"
    new_results.mkdir(parents=True)

    project = Project(
        name="P",
        storage_mode="external",
        external_root_path=str(workspace),
        user_id="dev",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    run = Run(
        run_id="run_no_outdir",
        project_id=str(project.id),
        status=RunStatus.COMPLETED.value,
        config={"request": {"params": {}}},
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    service = RunArchiveService(ProjectRepository(db_session))
    path = await service.resolve_output_path(run)
    assert path == new_results
