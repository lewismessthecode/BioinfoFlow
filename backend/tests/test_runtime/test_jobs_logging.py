from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.engine.backend import EngineEvent, EngineEventType
from app.models.run import RunStatus
from app.runtime.jobs import _handle_engine_event


@pytest.fixture(autouse=True)
def _mock_flag_modified():
    with patch("app.runtime.jobs.flag_modified"):
        yield


@pytest.mark.asyncio
async def test_handle_engine_event_persists_structured_engine_messages_to_run_log():
    session = AsyncMock()
    run_service = SimpleNamespace(append_run_log=AsyncMock())
    run = SimpleNamespace(
        run_id="run-log-1",
        project_id="project-1",
        nextflow_run_name=None,
        current_task=None,
        tasks_completed=0,
        tasks_total=0,
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        duration_seconds=None,
        status=RunStatus.RUNNING.value,
        config={"dag": {"nodes": [], "edges": []}, "runtime": {}},
    )

    with (
        patch("app.runtime.jobs.publish_run_status", new=AsyncMock()),
        patch("app.runtime.jobs.publish_run_dag", new=AsyncMock()),
        patch("app.runtime.jobs._update_dag_task_status", new=AsyncMock()),
        patch("app.runtime.jobs._finalize_dag_statuses", new=AsyncMock()),
    ):
        await _handle_engine_event(
            session,
            run,
            run_service,
            EngineEvent(
                EngineEventType.STARTED,
                {
                    "run_name": "mighty-curie",
                    "message": "Launching `demo/main.nf` [mighty_curie] - revision: xyz",
                },
            ),
        )
        await _handle_engine_event(
            session,
            run,
            run_service,
            EngineEvent(
                EngineEventType.TASK_UPDATE,
                {
                    "name": "WRITE_HELLO",
                    "status": "completed",
                    "raw": "[12/abcd] process > WRITE_HELLO [100%]",
                    "message": "[12/abcd] process > WRITE_HELLO [100%]",
                },
            ),
        )
        await _handle_engine_event(
            session,
            run,
            run_service,
            EngineEvent(
                EngineEventType.COMPLETED,
                {"success": True, "message": "Execution complete -- goodbye"},
            ),
        )

    assert run_service.append_run_log.await_args_list == [
        ((run, "Launching `demo/main.nf` [mighty_curie] - revision: xyz"),),
        ((run, "[12/abcd] process > WRITE_HELLO [100%]"),),
        ((run, "Execution complete -- goodbye"),),
    ]
