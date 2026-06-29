from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.engine.backend import EngineEvent, EngineEventType
from app.models.run import RunStatus
from app.runtime.jobs import (
    _build_engine_config,
    _handle_engine_event,
    attach_required_image_auth,
)


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


def test_build_engine_config_prefers_resolved_workflow_path(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    original = tmp_path / "workflow.wdl"
    resolved = workspace / "runs" / "run-1" / "engine" / "workflow.resolved.wdl"
    resolved.parent.mkdir(parents=True)
    original.write_text("version 1.0\nworkflow original {}\n", encoding="utf-8")
    resolved.write_text("version 1.0\nworkflow resolved {}\n", encoding="utf-8")

    run = SimpleNamespace(
        run_id="run-1",
        config={
            "runtime": {
                "work_dir": "runs/run-1/engine/wdl/work",
                "resolved_workflow_path": str(resolved),
            }
        },
    )
    workflow = SimpleNamespace(
        source="local",
        entrypoint_relpath="workflow.wdl",
        source_ref="local",
        name="wf",
        engine="wdl",
    )

    with patch("app.runtime.jobs.workflow_entrypoint_path", return_value=original):
        config = _build_engine_config(
            run=run,
            workflow=workflow,
            workspace_path=workspace,
            dag_path=workspace / "runs" / "run-1" / "audit" / "dag.dot",
            trace_path=workspace / "runs" / "run-1" / "audit" / "trace.tsv",
        )

    assert config["workflow_path"] == str(resolved)
    assert config["pipeline"] == str(resolved)


@pytest.mark.asyncio
async def test_attach_required_image_auth_uses_registry_id_without_persisting_secret(
    db_session,
):
    from app.services.container_registry_service import ContainerRegistryService

    registry = await ContainerRegistryService(db_session).create_registry(
        {
            "name": "Harbor Bio",
            "endpoint": "https://harbor.example.test",
            "namespace": "bio",
            "credential_source": "stored",
            "username": "robot-user",
            "password": "top-secret-value",
            "updated_by": "user-1",
        }
    )
    config = {
        "runtime": {
            "required_images": [
                {
                    "full_name": "harbor.example.test/bio/bwa:0.7.17",
                    "name": "bio/bwa",
                    "tag": "0.7.17",
                    "registry": "harbor.example.test",
                    "registry_id": str(registry.id),
                }
            ]
        }
    }

    resolved = await attach_required_image_auth(db_session, config)

    assert resolved["runtime"]["required_images"] == [
        {
            "full_name": "harbor.example.test/bio/bwa:0.7.17",
            "name": "bio/bwa",
            "tag": "0.7.17",
            "registry": "harbor.example.test",
            "registry_id": str(registry.id),
            "auth_config": {
                "username": "robot-user",
                "password": "top-secret-value",
            },
        }
    ]
    assert "top-secret-value" not in str(config)
