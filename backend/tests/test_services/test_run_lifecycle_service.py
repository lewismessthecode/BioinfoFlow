from __future__ import annotations

from pathlib import Path

import pytest

from app.models.project import Project
from app.models.run import Run, RunStatus
from app.services import run_lifecycle_service
from app.services.run_lifecycle_service import RunLifecycleService
from tests.support.path_contract import create_project


class _NullDispatcher:
    def dispatch(self, run_id: str, *, priority: str = "normal") -> None:
        del run_id, priority


class _AuditRecorder:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def log(self, **payload) -> None:
        self.calls.append(payload)


async def _create_run(
    db_session,
    *,
    workspace: Path,
    run_id: str,
    config: dict | None = None,
    status: RunStatus = RunStatus.RUNNING,
) -> tuple[Project, Run]:
    workspace.mkdir(parents=True, exist_ok=True)
    project = await create_project(
        db_session,
        name=f"Project {run_id}",
        storage_mode="external",
        external_root_path=str(workspace),
    )
    run = Run(
        run_id=run_id,
        project_id=str(project.id),
        workflow_id=None,
        status=status.value,
        config=config or {},
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return project, run


@pytest.mark.asyncio
async def test_cleanup_run_passes_runtime_to_cleaner_and_audits_result(
    db_session, monkeypatch, tmp_path
):
    _, run = await _create_run(
        db_session,
        workspace=tmp_path / "workspace",
        run_id="run_cleanup_service",
        config={"runtime": {"engine": "nextflow", "session_id": "sess-1"}},
    )
    service = RunLifecycleService(db_session, dispatcher=_NullDispatcher())
    calls: list[dict] = []
    audit = _AuditRecorder()

    class _FakeCleaner:
        async def manual_cleanup(
            self,
            run_id: str,
            *,
            workspace_path: Path,
            engine: str,
            runtime: dict,
        ) -> dict:
            calls.append(
                {
                    "run_id": run_id,
                    "workspace_path": workspace_path,
                    "engine": engine,
                    "runtime": runtime,
                }
            )
            return {"deleted": ["work", "results"]}

    monkeypatch.setattr(run_lifecycle_service, "WorkDirCleaner", lambda: _FakeCleaner())
    monkeypatch.setattr(RunLifecycleService, "_audit", lambda self: audit)

    result = await service.cleanup_run(run.run_id)

    assert result == {"deleted": ["work", "results"]}
    assert calls == [
        {
            "run_id": run.run_id,
            "workspace_path": tmp_path / "workspace",
            "engine": "nextflow",
            "runtime": {"engine": "nextflow", "session_id": "sess-1"},
        }
    ]
    assert audit.calls == [
        {
            "action": "run.cleanup",
            "resource_type": "run",
            "resource_id": run.run_id,
            "project_id": str(run.project_id),
            "actor": "api",
            "details": {"deleted": ["work", "results"]},
        }
    ]


@pytest.mark.asyncio
async def test_get_logs_falls_back_to_resolved_workspace_when_default_path_is_missing(
    db_session, tmp_path
):
    workspace_root = tmp_path / "workspace"
    _, run = await _create_run(
        db_session,
        workspace=workspace_root,
        run_id="run_logs_service",
        config={
            "log_path": "logs/run.log",
            "resolved_runspec": {"workspace": "analysis"},
        },
    )
    service = RunLifecycleService(db_session, dispatcher=_NullDispatcher())
    analysis_root = workspace_root / "analysis"
    analysis_root.mkdir(parents=True, exist_ok=True)
    (analysis_root / "logs").mkdir(parents=True, exist_ok=True)
    (analysis_root / "logs" / "run.log").write_text(
        "line-1\nline-2\nline-3\n",
        encoding="utf-8",
    )

    payload = await service.get_logs(run.run_id, tail=2, task="ALIGN")

    assert payload == {
        "logs": [
            {"message": "line-2", "task": "ALIGN"},
            {"message": "line-3", "task": "ALIGN"},
        ]
    }


@pytest.mark.asyncio
async def test_get_logs_returns_empty_list_before_log_file_exists(db_session, tmp_path):
    workspace_root = tmp_path / "workspace"
    _, run = await _create_run(
        db_session,
        workspace=workspace_root,
        run_id="run_logs_pending_service",
        config={},
        status=RunStatus.PENDING,
    )
    service = RunLifecycleService(db_session, dispatcher=_NullDispatcher())

    payload = await service.get_logs(run.run_id, tail=200)

    assert payload == {"logs": []}


@pytest.mark.asyncio
async def test_append_run_log_persists_relative_log_path_and_appends_messages(
    db_session, tmp_path
):
    workspace_root = tmp_path / "workspace"
    _, run = await _create_run(
        db_session,
        workspace=workspace_root,
        run_id="run_append_log_service",
        config={},
    )
    service = RunLifecycleService(db_session, dispatcher=_NullDispatcher())

    await service.append_run_log(run, "first line")
    await service.append_run_log(run, "second line")

    refreshed = await service.repo.get_by_run_id(run.run_id)
    assert refreshed is not None
    assert refreshed.config["log_path"] == f"runs/{run.run_id}/audit/run.log"
    log_path = workspace_root / refreshed.config["log_path"]
    assert log_path.read_text(encoding="utf-8") == "first line\nsecond line\n"
