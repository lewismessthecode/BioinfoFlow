from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_work_dir_cleaner_keeps_success_artifacts_by_default(tmp_path):
    from app.scheduler.cleanup import WorkDirCleaner

    workspace = tmp_path / "workspace"
    run_home = workspace / "runs" / "run_123"
    archive_dir = run_home / "audit"
    wdl_dir = run_home / "engine" / "wdl" / "work"
    archive_dir.mkdir(parents=True)
    wdl_dir.mkdir(parents=True)
    (archive_dir / "run.manifest.json").write_text("{}", encoding="utf-8")
    (wdl_dir / "outputs.txt").write_text("done", encoding="utf-8")

    cleaner = WorkDirCleaner()
    result = await cleaner.cleanup_run(
        "run_123",
        workspace_path=workspace,
        status="completed",
        engine="wdl",
        runtime={"wdl_work_dir": str(Path("runs/run_123/engine/wdl/work"))},
    )

    assert run_home.exists() is True
    assert result["deleted"] == []


@pytest.mark.asyncio
async def test_work_dir_cleaner_keeps_failed_artifacts_by_default(tmp_path):
    from app.scheduler.cleanup import WorkDirCleaner

    workspace = tmp_path / "workspace"
    archive_dir = workspace / "runs" / "run_456"
    archive_dir.mkdir(parents=True)

    cleaner = WorkDirCleaner()
    result = await cleaner.cleanup_run(
        "run_456",
        workspace_path=workspace,
        status="failed",
        engine="nextflow",
        runtime={},
    )

    assert archive_dir.exists() is True
    assert result["deleted"] == []


@pytest.mark.asyncio
async def test_work_dir_cleaner_manual_cleanup_forces_deletion(tmp_path):
    from app.scheduler.cleanup import WorkDirCleaner

    workspace = tmp_path / "workspace"
    archive_dir = workspace / "runs" / "run_manual"
    archive_dir.mkdir(parents=True)

    cleaner = WorkDirCleaner()
    result = await cleaner.manual_cleanup(
        "run_manual",
        workspace_path=workspace,
        engine="nextflow",
        runtime={},
    )

    assert archive_dir.exists() is False
    assert result["deleted"] == [str(archive_dir)]
