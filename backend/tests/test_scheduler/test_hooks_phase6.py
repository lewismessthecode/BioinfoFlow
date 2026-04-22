from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.scheduler.hooks import RunCompletionHooks


class _Cleaner:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def cleanup_run(self, run_id: str, **kwargs):
        self.calls.append({"run_id": run_id, **kwargs})
        return {"deleted": [f"/tmp/{run_id}"]}


class _Audit:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def log(self, **kwargs):
        self.calls.append(kwargs)


class _Notifications:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def notify(self, project_id: str, trigger: str, payload: dict):
        self.calls.append(
            {"project_id": project_id, "trigger": trigger, "payload": payload}
        )


class _Batches:
    def __init__(self, *, batch_status: str | None) -> None:
        self.batch_status = batch_status
        self.find_calls: list[str] = []
        self.update_calls: list[str] = []

    async def find_batch_for_run(self, run_id: str):
        self.find_calls.append(run_id)
        if self.batch_status is None:
            return None
        return SimpleNamespace(batch_id="batch_123")

    async def update_batch_status(self, batch_id: str):
        self.update_calls.append(batch_id)
        return await self.get_batch(batch_id)

    async def get_batch(self, batch_id: str):
        return {
            "batch_id": batch_id,
            "project_id": "project-1",
            "status": self.batch_status,
        }


@pytest.mark.asyncio
async def test_run_completion_hooks_send_run_and_batch_notifications(db_session):
    cleaner = _Cleaner()
    audit = _Audit()
    notifications = _Notifications()
    batches = _Batches(batch_status="completed")
    run = SimpleNamespace(
        run_id="run_hooks_phase6",
        project_id="project-1",
        config={"runtime": {}, "params": {"outdir": "results"}},
    )

    hooks = RunCompletionHooks(
        db_session,
        cleaner=cleaner,
        audit_service=audit,
        notification_service=notifications,
        batch_service=batches,
    )
    await hooks.on_run_terminal(
        run,
        status="completed",
        workspace_path="/srv/bioinfoflow/projects/project-1",
        engine="nextflow",
    )

    assert cleaner.calls[0]["run_id"] == "run_hooks_phase6"
    assert audit.calls[0]["action"] == "run.completed"
    assert batches.find_calls == ["run_hooks_phase6"]
    assert batches.update_calls == ["batch_123"]
    assert notifications.calls == [
        {
            "project_id": "project-1",
            "trigger": "on_complete",
            "payload": {"run_id": "run_hooks_phase6", "status": "completed"},
        },
        {
            "project_id": "project-1",
            "trigger": "on_batch_complete",
            "payload": {
                "batch_id": "batch_123",
                "project_id": "project-1",
                "status": "completed",
            },
        },
    ]


@pytest.mark.asyncio
async def test_run_completion_hooks_skip_batch_complete_when_batch_not_terminal(
    db_session,
):
    notifications = _Notifications()
    batches = _Batches(batch_status="running")
    run = SimpleNamespace(
        run_id="run_hooks_phase6_running",
        project_id="project-1",
        config={"runtime": {}, "params": {"outdir": "results"}},
    )

    hooks = RunCompletionHooks(
        db_session,
        cleaner=_Cleaner(),
        audit_service=_Audit(),
        notification_service=notifications,
        batch_service=batches,
    )
    await hooks.on_run_terminal(
        run,
        status="failed",
        workspace_path="/srv/bioinfoflow/projects/project-1",
        engine="nextflow",
    )

    assert notifications.calls == [
        {
            "project_id": "project-1",
            "trigger": "on_failure",
            "payload": {"run_id": "run_hooks_phase6_running", "status": "failed"},
        }
    ]
