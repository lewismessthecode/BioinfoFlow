from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import app.database as app_database
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.run import Run, RunStatus
from app.models.run_config import RunConfigHelper
from app.engine.backend import EngineEvent, EngineEventType
from app.path_layout import workflow_entrypoint_path
from app.runtime.events import publish_run_dag, publish_run_log, publish_run_status
from app.services.dag_parser import DagParser
from app.services.container_registry_service import ContainerRegistryService
from app.services.trace_parser import TraceParser
from app.utils.dag_builder import (
    build_dag_from_schema,
    clean_process_label,
    create_runtime_node,
    infer_runtime_edge,
    normalize_dag_id,
)
from app.utils.dag_matcher import DagMatcher
from app.utils.logging import get_logger


logger = get_logger(__name__)

# Compatibility alias for tests that patch runtime_jobs.async_session_maker.
async_session_maker = app_database.async_session_maker

if TYPE_CHECKING:
    from app.services.run_service import RunService


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _duration_seconds(
    started_at: datetime | None, completed_at: datetime | None
) -> int | None:
    if not started_at or not completed_at:
        return None
    # Normalize both to UTC-aware datetimes to avoid offset-naive vs offset-aware errors
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    return int((completed_at - started_at).total_seconds())


async def recover_stale_runs(
    *, session: AsyncSession | None = None, stale_after_minutes: int = 30
) -> int:
    if session is not None:
        return await _recover_stale_runs_in_session(
            session=session,
            stale_after_minutes=stale_after_minutes,
        )

    from app.scheduler.config import SchedulerConfig
    from app.scheduler.scheduler import RunScheduler

    scheduler = RunScheduler(
        config=SchedulerConfig(stale_timeout_minutes=stale_after_minutes),
    )
    return await scheduler.recover()


async def _recover_stale_runs_in_session(
    *, session: AsyncSession, stale_after_minutes: int
) -> int:
    cutoff = _now() - timedelta(minutes=stale_after_minutes)
    stmt = select(Run).where(
        Run.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value])
    )
    try:
        result = await session.execute(stmt)
    except OperationalError as exc:
        if "no such table: runs" not in str(exc).lower():
            raise
        logger.info("run.recovery.skipped_missing_runs_table")
        return 0
    candidates = result.scalars().all()

    recovered = 0
    now = _now()
    for run in candidates:
        stale_anchor = run.started_at or run.created_at
        if stale_anchor is None:
            continue
        if stale_anchor.tzinfo is None:
            stale_anchor = stale_anchor.replace(tzinfo=timezone.utc)
        if stale_anchor > cutoff:
            continue

        run.status = RunStatus.FAILED.value
        run.error_message = "Run recovery: marked stale after service restart"
        run.completed_at = now
        run.duration_seconds = _duration_seconds(run.started_at, run.completed_at)
        recovered += 1

    if recovered:
        await session.commit()
        logger.warning(
            "run.recovery.completed",
            recovered=recovered,
            stale_after_minutes=stale_after_minutes,
        )
    return recovered


async def execute_run(run_id: str) -> None:
    from app.scheduler.config import SchedulerConfig
    from app.scheduler.scheduler import RunScheduler

    scheduler = RunScheduler(config=SchedulerConfig())
    await scheduler.execute_run(run_id)


async def _handle_run_event(
    session,
    run,
    run_service: RunService,
    event: EngineEvent,
    workspace_path: str | None = None,
    *,
    finalize_error: bool = True,
) -> None:
    event_type = event.type
    if event_type == EngineEventType.STARTED:
        await _append_structured_event_log(run_service, run, event)
        run.nextflow_run_name = event.data.get("run_name") or run.nextflow_run_name
        await session.commit()
        await publish_run_status(run)
        return

    if event_type == EngineEventType.PROCESS_INFO:
        runtime = {}
        if isinstance(run.config, dict):
            runtime = dict(run.config.get("runtime", {}) or {})
        pid = event.pid
        if pid:
            runtime["pid"] = pid
        engine = event.data.get("engine")
        if engine:
            runtime["engine"] = engine
        if isinstance(run.config, dict):
            run.config = {**run.config, "runtime": runtime}
        else:
            run.config = {"runtime": runtime}
        await session.commit()
        return

    if event_type == EngineEventType.TASK_UPDATE:
        await _append_structured_event_log(run_service, run, event)
        run.current_task = event.task_name or run.current_task
        status = event.task_status
        if status == "completed":
            run.tasks_completed = (run.tasks_completed or 0) + 1
        tasks_total = event.data.get("tasks_total")
        if isinstance(tasks_total, int):
            run.tasks_total = tasks_total

        # Update DAG task status
        await _update_dag_task_status(
            session, run, event.task_name, status, workspace_path
        )
        await session.commit()
        await publish_run_status(run)
        await publish_run_dag(run)
        return

    if event_type == EngineEventType.LOG:
        message = event.message
        if message:
            await run_service.append_run_log(run, message)
            await _apply_runtime_patch(session, run, event.data.get("config_patch"))
            await publish_run_log(
                project_id=str(run.project_id),
                run_id=run.run_id,
                message=message,
                level=event.data.get("level", "info"),
                task=event.data.get("task"),
            )
        return

    if event_type == EngineEventType.ERROR:
        await _apply_runtime_patch(session, run, event.data.get("config_patch"))
        message = event.message or "Run failed"
        exit_code = event.exit_code
        formatted_message = (
            f"{message} (exit {exit_code})" if exit_code is not None else message
        )
        run.error_message = formatted_message
        await run_service.append_run_log(run, f"ERROR: {message}")
        await publish_run_log(
            project_id=str(run.project_id),
            run_id=run.run_id,
            message=message,
            level="error",
            task=event.data.get("task"),
        )
        if not finalize_error:
            await session.commit()
            logger.error(
                "run.execute.error",
                run_id=run.run_id,
                exit_code=exit_code,
                message=message,
            )
            return
        run.status = RunStatus.FAILED.value
        run.completed_at = _now()
        run.duration_seconds = _duration_seconds(run.started_at, run.completed_at)
        await session.commit()
        await publish_run_status(run, message="Run failed")
        logger.error(
            "run.execute.failed",
            run_id=run.run_id,
            exit_code=exit_code,
            message=message,
        )
        return

    if event_type == EngineEventType.COMPLETED:
        await _append_structured_event_log(run_service, run, event)
        run.status = RunStatus.COMPLETED.value
        run.completed_at = _now()
        run.duration_seconds = _duration_seconds(run.started_at, run.completed_at)
        await _finalize_dag_statuses(run, workspace_path=workspace_path)
        await session.commit()
        await publish_run_status(run, message="Run completed")
        await publish_run_dag(run)


async def _append_structured_event_log(
    run_service: RunService,
    run,
    event: EngineEvent,
) -> None:
    raw_message = event.message
    if not raw_message:
        candidate = event.data.get("raw")
        if isinstance(candidate, str) and candidate.strip():
            raw_message = candidate
    if raw_message:
        await run_service.append_run_log(run, raw_message)


async def _handle_engine_event(
    session,
    run,
    run_service: RunService,
    event: EngineEvent,
    workspace_path: str | None = None,
    *,
    finalize_error: bool = True,
) -> None:
    await _handle_run_event(
        session=session,
        run=run,
        run_service=run_service,
        event=event,
        workspace_path=workspace_path,
        finalize_error=finalize_error,
    )


async def _update_dag_task_status(
    session,
    run,
    task_name: str | None,
    status: str | None,
    workspace_path: str | None = None,
) -> None:
    """Update a single DAG node status from a task event.

    Uses clean_process_label to strip workflow prefixes and sample suffixes,
    then normalize_dag_id for stable node ID matching. No DOT re-parsing or
    trace file reading — those are unreliable mid-run and caused status clobbering.
    """
    if not task_name:
        return

    dag = (
        run.config.get("dag", {"nodes": [], "edges": []})
        if isinstance(run.config, dict)
        else {"nodes": [], "edges": []}
    )
    process_label = clean_process_label(task_name)
    frontend_status = TraceParser().map_status(status) if status else "pending"
    matched_id = DagMatcher(dag.get("nodes", [])).match(task_name)

    matched = False
    for node in dag.get("nodes", []):
        if node.get("id") == matched_id:
            node["data"]["status"] = frontend_status
            matched = True
            break

    if not matched:
        target_id = normalize_dag_id(process_label)
        logger.debug(
            "dag.task_status.no_match",
            task_name=task_name,
            cleaned=process_label,
            target_id=target_id,
            available_ids=[n.get("id") for n in dag["nodes"]],
        )
        runtime_node = create_runtime_node(task_name, frontend_status, dag)
        dag.setdefault("nodes", []).append(runtime_node)

    dag = DagParser.update_edge_animations(dag)

    if not matched:
        infer_runtime_edge(dag, runtime_node["id"])

    if isinstance(run.config, dict):
        run.config = {**run.config, "dag": dag}
    else:
        run.config = {"dag": dag}
    flag_modified(run, "config")


async def _finalize_dag_statuses(
    run,
    *,
    workspace_path: str | None = None,
) -> None:
    """Apply terminal statuses to the DAG on run completion.

    Uses trace file when available, then sweeps remaining nodes based on
    the run's outcome so no node stays stuck as "pending" or "running".
    """
    dag = (
        run.config.get("dag", {"nodes": [], "edges": []})
        if isinstance(run.config, dict)
        else {"nodes": [], "edges": []}
    )
    if not dag.get("nodes"):
        return

    # Apply trace-based statuses if available
    trace_path = _resolve_runtime_path(workspace_path, run, "trace_path")
    if trace_path and trace_path.exists():
        statuses = TraceParser().get_process_statuses(trace_path)
        if statuses:
            dag = _apply_process_statuses(dag, statuses)

    # Fallback sweep based on run outcome
    run_succeeded = run.status == RunStatus.COMPLETED.value
    for node in dag.get("nodes", []):
        node_status = node.get("data", {}).get("status", "pending")
        if run_succeeded and node_status in {"pending", "running"}:
            node["data"]["status"] = "success"
        elif not run_succeeded and node_status == "running":
            node["data"]["status"] = "failed"

    # Stop all edge animations on completion
    for edge in dag.get("edges", []):
        edge["animated"] = False

    if isinstance(run.config, dict):
        run.config = {**run.config, "dag": dag}
    else:
        run.config = {"dag": dag}
    flag_modified(run, "config")


async def initialize_run_dag(session, run, workflow, workspace_path: str) -> None:
    """Initialize DAG for a run from workflow file.

    Args:
        session: Database session
        run: Run model instance
        workflow: Workflow model instance
        workspace_path: Path to workspace directory
    """
    dag_parser = DagParser()
    dot_path = _resolve_runtime_path(workspace_path, run, "dag_path")
    schema = workflow.schema_json if getattr(workflow, "schema_json", None) else None

    if dot_path and dot_path.exists():
        dag = dag_parser.parse_dot_file(dot_path, schema=schema)
    elif schema:
        dag = build_dag_from_schema(schema)
    else:
        dag = dag_parser.create_empty_dag()

    # Save DAG to run config
    if isinstance(run.config, dict):
        run.config = {**run.config, "dag": dag}
    else:
        run.config = {"dag": dag}
    flag_modified(run, "config")
    await session.commit()
    await publish_run_dag(run)


def _resolve_runtime_path(workspace_path: str | None, run, key: str) -> Path | None:
    if not workspace_path or not isinstance(run.config, dict):
        return None
    runtime = run.config.get("runtime", {}) or {}
    rel_path = runtime.get(key)
    if not rel_path:
        return None
    return Path(workspace_path) / rel_path


def _build_engine_config(
    *,
    run,
    workflow,
    workspace_path: Path,
    dag_path: Path,
    trace_path: Path,
) -> dict:
    config = RunConfigHelper(
        run.config if isinstance(run.config, dict) else {}
    ).to_dict()
    runtime = dict(config.get("runtime", {}) or {})
    work_dir = runtime.get("work_dir")
    work_dir_value = (
        str((workspace_path / work_dir).resolve())
        if isinstance(work_dir, str) and work_dir.strip()
        else ""
    )
    workflow_path = _optional_runtime_path(runtime.get("resolved_workflow_path"))
    if not workflow_path and str(getattr(workflow.source, "value", workflow.source)) == "local":
        workflow_path = str(workflow_entrypoint_path(workflow))
    elif not workflow_path and getattr(workflow, "source_ref", None):
        workflow_path = str(workflow.source_ref)
    config.update(
        {
            "run_id": run.run_id,
            "engine": getattr(workflow.engine, "value", workflow.engine),
            "pipeline": workflow_path or workflow.name,
            "workflow_path": workflow_path,
            "profile": config.get("profile"),
            "resume": bool(config.get("resume")),
            "resume_from": config.get("resume_from"),
            "options": dict(config.get("options", {}) or {}),
            "dag_path": str(dag_path.relative_to(workspace_path)),
            "trace_path": str(trace_path.relative_to(workspace_path)),
            "work_dir": work_dir_value or config.get("work_dir"),
            "outdir": (
                RunConfigHelper(config).params.get("outdir")
                or RunConfigHelper(config).params.get("output_dir")
                or "results"
            ),
        }
    )
    return config


async def attach_required_image_auth(session: AsyncSession, config: dict) -> dict:
    runtime = dict(config.get("runtime", {}) or {})
    required_images = runtime.get("required_images")
    if not isinstance(required_images, list):
        return config

    registry_service = ContainerRegistryService(session)
    cache: dict[str, dict[str, str] | None] = {}
    resolved_images: list[Any] = []
    changed = False
    for image in required_images:
        if not isinstance(image, dict):
            resolved_images.append(image)
            continue
        registry_id = image.get("registry_id")
        if not isinstance(registry_id, str) or not registry_id.strip():
            resolved_images.append(image)
            continue
        if registry_id not in cache:
            material = await registry_service.resolve_auth_material(registry_id)
            auth_config: dict[str, str] = {}
            if material.username:
                auth_config["username"] = material.username
            if material.password:
                auth_config["password"] = material.password
            cache[registry_id] = auth_config or None
        auth_config = cache[registry_id]
        if auth_config is None:
            resolved_images.append(image)
            continue
        resolved_images.append({**image, "auth_config": auth_config})
        changed = True

    if not changed:
        return config
    runtime["required_images"] = resolved_images
    return {**config, "runtime": runtime}


def _optional_runtime_path(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    return text


async def _apply_runtime_patch(session, run, patch: dict | None) -> None:
    if not isinstance(patch, dict) or not patch:
        return
    config = dict(run.config) if isinstance(run.config, dict) else {}
    runtime_patch = patch.get("runtime")
    if isinstance(runtime_patch, dict):
        runtime = dict(config.get("runtime", {}) or {})
        runtime.update(runtime_patch)
        config["runtime"] = runtime
        patch = {key: value for key, value in patch.items() if key != "runtime"}
    config.update(patch)
    run.config = config
    flag_modified(run, "config")
    await session.commit()


def _apply_process_statuses(
    dag: dict[str, Any], statuses: dict[str, str]
) -> dict[str, Any]:
    node_ids = {node.get("id") for node in dag.get("nodes", [])}
    normalized_map = {
        normalize_dag_id(name): status for name, status in statuses.items()
    }
    for node in dag.get("nodes", []):
        node_id = node.get("id")
        if node_id is not None and node_id in normalized_map:
            node["data"]["status"] = normalized_map[node_id]
    unmatched = set(normalized_map) - node_ids
    for norm_id in unmatched:
        logger.debug(
            "dag.apply_statuses.unmatched",
            normalized=norm_id,
            available_ids=list(node_ids),
        )
    return dag
