from __future__ import annotations

import asyncio
import csv
import json
import threading
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from app.config import settings
from app.models.run_config import RunConfigHelper
from app.repositories.project_repo import ProjectRepository
from app.repositories.run_repo import RunRepository
from app.schemas.run import RunCreate
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.repositories.workflow_repo import WorkflowRepository
from app.services.project_workflow_service import ProjectWorkflowService
from app.services.run_archive import RunArchiveService
from app.services.run_compiler import (
    CompileError,
    RunCompiler,
    WorkflowNotEnabledError,
)
from app.services.run_profile_service import RunProfileService
from app.services.run_service import RunService
from app.services.hermes_service.home import ensure_hermes_home_environment
from app.utils.logging import get_logger

logger = get_logger(__name__)

ensure_hermes_home_environment(state_db_path=settings.agent_hermes_state_db)

try:  # pragma: no cover - exercised when Hermes SDK is installed
    from tools.registry import registry as hermes_registry
except Exception as exc:  # pragma: no cover - graceful fallback in dev/test
    logger.warning(
        "hermes.sdk.import_failed", module="tools.registry", error=str(exc)
    )
    hermes_registry = None

try:  # pragma: no cover - exercised when Hermes SDK is installed
    from toolsets import TOOLSETS as HERMES_TOOLSETS
    from toolsets import create_custom_toolset
except Exception as exc:  # pragma: no cover - graceful fallback in dev/test
    logger.warning("hermes.sdk.import_failed", module="toolsets", error=str(exc))
    HERMES_TOOLSETS = None
    create_custom_toolset = None


ToolApprovalCallback = Callable[..., str]

DEFAULT_HERMES_TOOLSET_ALIASES: dict[str, tuple[str, ...]] = {
    "file": ("file", "files", "filesystem"),
    "terminal": ("terminal", "shell", "bash"),
    "search": ("search", "web", "browser"),
    "clarify": ("clarify",),
}
TEXT_PREVIEW_SUFFIXES = {
    ".txt",
    ".log",
    ".md",
    ".csv",
    ".tsv",
    ".json",
    ".yaml",
    ".yml",
    ".html",
    ".xml",
}


@dataclass(frozen=True)
class HermesToolRuntimeContext:
    session_factory: async_sessionmaker
    project_id: str
    user_id: str | None
    workspace_root: str | None
    workspace_id: str | None = None
    approval_callback: ToolApprovalCallback | None = None


_tool_context: ContextVar[HermesToolRuntimeContext | None] = ContextVar(
    "bioinfoflow_hermes_tool_context",
    default=None,
)
_toolset_registered = False
_tool_loop: asyncio.AbstractEventLoop | None = None
_tool_loop_lock = threading.Lock()
_worker_thread_local = threading.local()


def _run_async(awaitable):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        context = copy_context()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(context.run, asyncio.run, awaitable)
            return future.result(timeout=300)

    if threading.current_thread() is not threading.main_thread():
        worker_loop = getattr(_worker_thread_local, "loop", None)
        if worker_loop is None or worker_loop.is_closed():
            worker_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(worker_loop)
            _worker_thread_local.loop = worker_loop
        return worker_loop.run_until_complete(awaitable)

    global _tool_loop
    with _tool_loop_lock:
        if _tool_loop is None or _tool_loop.is_closed():
            _tool_loop = asyncio.new_event_loop()
        tool_loop = _tool_loop

    return tool_loop.run_until_complete(awaitable)


def _json_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True)


def _coerce_tool_kwargs(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    runtime_only_keys = {
        "task_id",
        "tool_call_id",
        "session_id",
        "user_task",
        "enabled_tools",
        "skip_pre_tool_call_hook",
    }
    payload: dict[str, Any] = {}

    if len(args) == 1 and isinstance(args[0], dict):
        payload.update(args[0])
    elif len(args) == 1 and isinstance(args[0], str):
        try:
            parsed = json.loads(args[0])
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            payload.update(parsed)

    payload.update(
        {
            key: value
            for key, value in kwargs.items()
            if key not in runtime_only_keys
        }
    )
    return payload


def _require_tool_context() -> HermesToolRuntimeContext:
    context = _tool_context.get()
    if context is None:
        raise RuntimeError("Hermes tool context is not bound")
    return context


@contextmanager
def bind_tool_context(context: HermesToolRuntimeContext) -> Iterator[None]:
    token = _tool_context.set(context)
    try:
        yield
    finally:
        _tool_context.reset(token)


def _register_tool(name: str, schema: dict[str, Any], handler: Callable[..., Any]) -> None:
    if hermes_registry is None:
        return

    for call in (
        lambda: hermes_registry.register(
            name=name,
            toolset="bioinfoflow",
            schema=schema,
            handler=handler,
            description=str(schema.get("description") or ""),
        ),
        lambda: hermes_registry.register(name, "bioinfoflow", schema, handler),
    ):
        try:
            call()
            return
        except TypeError:
            continue

    logger.warning("hermes.tool_registration.unsupported", tool_name=name)


def _serialize_workflow_summary(workflow) -> dict[str, Any]:
    return {
        "id": str(workflow.id),
        "name": workflow.name,
        "version": workflow.version,
        "source": str(getattr(workflow.source, "value", workflow.source)),
        "engine": str(getattr(workflow.engine, "value", workflow.engine)),
        "description": workflow.description,
    }


def _serialize_run_summary(run) -> dict[str, Any]:
    config = RunConfigHelper(getattr(run, "config", None))
    workspace = getattr(run, "workspace", None)
    if not workspace:
        resolved_workspace = config.resolved_runspec.get("workspace")
        if isinstance(resolved_workspace, str) and resolved_workspace.strip():
            workspace = resolved_workspace
    return {
        "run_id": run.run_id,
        "status": str(getattr(run.status, "value", run.status)),
        "workspace": workspace,
        "current_task": run.current_task,
        "tasks_completed": run.tasks_completed,
        "tasks_total": run.tasks_total,
        "samples_count": run.samples_count,
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat() if getattr(run, "started_at", None) else None,
        "completed_at": run.completed_at.isoformat() if getattr(run, "completed_at", None) else None,
    }


def _resolve_tool_path(path_value: str) -> Path:
    context = _require_tool_context()
    if not context.workspace_root:
        raise FileNotFoundError("workspace root is not available in this Hermes session")

    root = Path(context.workspace_root).expanduser().resolve()
    return _resolve_path_within(root, path_value)


def _resolve_path_within(root: Path, path_value: str) -> Path:
    candidate = Path(path_value).expanduser()
    target = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if not target.is_relative_to(root):
        raise PermissionError("path escapes workspace root")
    return target


def _resolve_tool_workspace(workspace: str) -> Path:
    return _resolve_tool_path(workspace or ".")


def _workflow_search_rank(workflow, search: str) -> tuple[Any, ...]:
    query = search.strip().lower()
    name = str(getattr(workflow, "name", "") or "").lower()
    description = str(getattr(workflow, "description", "") or "").lower()
    name_contains = query in name
    description_contains = query in description
    name_position = name.find(query) if name_contains else 10_000
    description_position = description.find(query) if description_contains else 10_000

    return (
        0 if name == query else 1,
        0 if name.startswith(query) else 1,
        0 if name_contains else 1,
        name_position,
        0 if description_contains else 1,
        description_position,
        len(name),
        name,
    )


def _load_samplesheet_preview(
    *,
    workspace_path: Path,
    samplesheet_path: str,
    limit: int = 500,
) -> list[dict[str, str]]:
    try:
        target = _resolve_path_within(workspace_path.resolve(), samplesheet_path)
    except (FileNotFoundError, PermissionError):
        return []

    if not target.exists() or not target.is_file():
        return []

    rows: list[dict[str, str]] = []
    with target.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw_row in reader:
            if not raw_row:
                continue
            sample_id = (
                raw_row.get("sample_id")
                or raw_row.get("sample")
                or raw_row.get("sampleid")
                or ""
            ).strip()
            row: dict[str, str] = {}
            if sample_id:
                row["sample_id"] = sample_id

            for source_key, target_key in (
                ("fastq_1", "fastq_1"),
                ("fastq_2", "fastq_2"),
                ("file_1", "file_1"),
                ("file_2", "file_2"),
                ("bam", "bam"),
            ):
                value = (raw_row.get(source_key) or "").strip()
                if value:
                    row[target_key] = value

            if row:
                rows.append(row)
            if len(rows) >= limit:
                break

    return rows


def _supplement_preview_payload(
    *,
    workspace: str,
    resolved_params: dict[str, Any],
    detected_inputs: dict[str, Any],
    sample_rows: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    workspace_path = _resolve_tool_workspace(workspace)
    profile_service = RunProfileService()
    resolved = dict(resolved_params)
    detected = dict(detected_inputs)
    rows = list(sample_rows)

    samplesheet = resolved.get("samplesheet")
    if not isinstance(samplesheet, str) or not samplesheet.strip():
        candidate = profile_service._detect_samplesheet(workspace_path)
        if candidate:
            resolved["samplesheet"] = candidate
            detected.setdefault("samplesheet", candidate)
            samplesheet = candidate
    elif isinstance(samplesheet, str):
        detected.setdefault("samplesheet", samplesheet)

    reference = resolved.get("reference")
    if not isinstance(reference, str) or not reference.strip():
        candidate = profile_service._detect_reference(workspace_path)
        if candidate:
            resolved["reference"] = candidate
            detected.setdefault("reference", candidate)

    if not rows and isinstance(samplesheet, str) and samplesheet.strip():
        rows = _load_samplesheet_preview(
            workspace_path=workspace_path,
            samplesheet_path=samplesheet,
        )

    return resolved, detected, rows


def _ensure_custom_toolset(tool_names: list[str]) -> None:
    if HERMES_TOOLSETS is None:
        return

    if "bioinfoflow" in HERMES_TOOLSETS:
        return

    if create_custom_toolset is not None:
        for call in (
            lambda: create_custom_toolset(
                "bioinfoflow",
                "Bioinfoflow workflow and run tools",
                tool_names,
            ),
            lambda: create_custom_toolset(
                name="bioinfoflow",
                description="Bioinfoflow workflow and run tools",
                tools=tool_names,
            ),
        ):
            try:
                call()
                return
            except TypeError:
                continue

    HERMES_TOOLSETS["bioinfoflow"] = {
        "description": "Bioinfoflow workflow and run tools",
        "tools": tool_names,
        "includes": [],
    }


def get_enabled_toolsets() -> list[str]:
    if not HERMES_TOOLSETS:
        return ["file", "terminal", "search", "clarify", "bioinfoflow"]

    resolved: list[str] = []
    available = set(HERMES_TOOLSETS.keys())
    for aliases in DEFAULT_HERMES_TOOLSET_ALIASES.values():
        match = next((alias for alias in aliases if alias in available), None)
        if match:
            resolved.append(match)
    registered_toolsets = (
        set(hermes_registry.get_registered_toolset_names())
        if hermes_registry is not None
        else set()
    )
    if "bioinfoflow" in available or "bioinfoflow" in registered_toolsets:
        resolved.append("bioinfoflow")
    return resolved


async def _list_workflows(*, search: str | None, limit: int) -> dict[str, Any]:
    context = _require_tool_context()
    async with context.session_factory() as session:
        repo = WorkflowRepository(session)
        capped_limit = max(1, min(limit, 20))
        workflows, pagination = await repo.list(
            limit=20 if search else capped_limit,
            search=search,
        )
        if search:
            workflows = sorted(
                workflows,
                key=lambda workflow: _workflow_search_rank(workflow, search),
            )[:capped_limit]
        results = [
            {
                "id": str(workflow.id),
                "name": workflow.name,
                "version": workflow.version,
                "source": str(getattr(workflow.source, "value", workflow.source)),
                "engine": str(getattr(workflow.engine, "value", workflow.engine)),
                "description": workflow.description,
            }
            for workflow in workflows
        ]
        return {
            "summary": f"Found {len(results)} workflows",
            "results": results,
            "total_count": pagination.total_count,
        }


def workflow_catalog(*args, **kwargs) -> str:
    payload = _coerce_tool_kwargs(args, kwargs)
    return _json_result(
        _run_async(
            _list_workflows(
                search=payload.get("search"),
                limit=int(payload.get("limit", 10)),
            )
        )
    )


async def _get_workflow_schema(
    *,
    workflow_id: str | None,
    workflow_name: str | None,
    version: str | None,
) -> dict[str, Any]:
    context = _require_tool_context()
    async with context.session_factory() as session:
        repo = WorkflowRepository(session)
        workflow = None
        if workflow_id:
            workflow = await repo.get(workflow_id)
        elif workflow_name and version:
            workflow = await repo.get_by_unique(
                source="local",
                name=workflow_name,
                version=version,
            )
        else:
            workflows, _ = await repo.list(limit=1, search=workflow_name)
            workflow = workflows[0] if workflows else None

        if workflow is None:
            return {"summary": "Workflow not found", "found": False}

        return {
            "summary": f"Loaded schema for {workflow.name} {workflow.version}",
            "found": True,
            "workflow": {
                "id": str(workflow.id),
                "name": workflow.name,
                "version": workflow.version,
                "source": str(getattr(workflow.source, "value", workflow.source)),
                "engine": str(getattr(workflow.engine, "value", workflow.engine)),
                "description": workflow.description,
                "schema": workflow.schema_json,
                "form_spec": workflow.form_spec,
            },
        }


def workflow_schema(*args, **kwargs) -> str:
    payload = _coerce_tool_kwargs(args, kwargs)
    return _json_result(
        _run_async(
            _get_workflow_schema(
                workflow_id=payload.get("workflow_id"),
                workflow_name=payload.get("workflow_name"),
                version=payload.get("version"),
            )
        )
    )


async def _project_enable_workflow(*, workflow_id: str) -> dict[str, Any]:
    context = _require_tool_context()
    async with context.session_factory() as session:
        workflow = await WorkflowRepository(session).get(workflow_id)
        if workflow is None:
            return {
                "summary": "Workflow not found",
                "enabled": False,
                "workflow_id": workflow_id,
            }

        await ProjectWorkflowService(session).bind_workflow(
            project_id=context.project_id,
            workflow_id=workflow_id,
        )
        return {
            "summary": f"Enabled {workflow.name} {workflow.version} for this project",
            "enabled": True,
            "project_id": context.project_id,
            "workflow": _serialize_workflow_summary(workflow),
        }


def project_enable_workflow(*args, **kwargs) -> str:
    payload = _coerce_tool_kwargs(args, kwargs)
    return _json_result(
        _run_async(
            _project_enable_workflow(
                workflow_id=str(payload.get("workflow_id") or ""),
            )
        )
    )


async def _preview_run_profile(*, workflow_id: str, workspace: str = ".") -> dict[str, Any]:
    context = _require_tool_context()
    async with context.session_factory() as session:
        workflow_repo = WorkflowRepository(session)
        workflow = await workflow_repo.get(workflow_id)
        if workflow is None:
            return {
                "summary": "Workflow not found",
                "found": False,
                "workflow_id": workflow_id,
            }

        return {
            "summary": f"Loaded form spec for {workflow.name}",
            "found": True,
            "ready": True,
            "workflow": _serialize_workflow_summary(workflow),
            "workspace": workspace,
            "form_spec": workflow.form_spec or {"fields": []},
            "resolved_params": {},
            "detected_inputs": {},
            "sample_rows": [],
        }


def preview_run_profile(*args, **kwargs) -> str:
    payload = _coerce_tool_kwargs(args, kwargs)
    return _json_result(
        _run_async(
            _preview_run_profile(
                workflow_id=str(payload.get("workflow_id") or ""),
                workspace=str(payload.get("workspace") or "."),
            )
        )
    )


async def _submit_run(
    *,
    workflow_id: str,
    values: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
    priority: str = "normal",
) -> dict[str, Any]:
    context = _require_tool_context()
    tool_input = {
        "workflow_id": workflow_id,
        "values": values or {},
        "options": options or {},
        "priority": priority,
    }

    if context.approval_callback is not None:
        decision = context.approval_callback(
            tool_name="submit_run",
            tool_input=tool_input,
            risk="act_high",
            description="Submit a workflow run in the current project",
        )
        if decision not in {"once", "session", "always"}:
            return {
                "summary": "Workflow submission was denied",
                "approved": False,
                "status": "cancelled",
            }

    async with context.session_factory() as session:
        try:
            payload = RunCreate.model_validate(
                {
                    "project_id": context.project_id,
                    "workflow_id": workflow_id,
                    "values": values or {},
                    "options": options,
                }
            )
            run = await RunCompiler(session).create_run(
                payload,
                user_id=context.user_id,
                workspace_id=context.workspace_id,
                priority=priority,
            )
        except FileNotFoundError as exc:
            return {
                "summary": f"Workflow submission failed: {exc}",
                "approved": True,
                "submitted": False,
                "status": "error",
                "workflow_id": workflow_id,
                "error": {
                    "code": "NOT_FOUND",
                    "message": str(exc),
                    "hint": "Check that the project and workflow still exist.",
                },
            }
        except WorkflowNotEnabledError as exc:
            return {
                "summary": "Workflow submission failed: workflow not enabled for project",
                "approved": True,
                "submitted": False,
                "status": "error",
                "workflow_id": workflow_id,
                "error": {
                    "code": "WORKFLOW_NOT_ENABLED_FOR_PROJECT",
                    "message": str(exc),
                    "hint": "Enable the workflow for this project before submitting.",
                },
            }
        except CompileError as exc:
            return {
                "summary": f"Workflow submission failed: {exc}",
                "approved": True,
                "submitted": False,
                "status": "error",
                "workflow_id": workflow_id,
                "error": {
                    "code": exc.code,
                    "message": str(exc),
                    "hint": exc.hint,
                },
            }
        except ValueError as exc:
            return {
                "summary": f"Workflow submission failed: {exc}",
                "approved": True,
                "submitted": False,
                "status": "error",
                "workflow_id": workflow_id,
                "error": {
                    "code": "INVALID_PAYLOAD",
                    "message": str(exc),
                    "hint": "Submit values/options that match the workflow form spec.",
                },
            }

        return {
            "summary": f"Run submitted: {run.run_id}",
            "approved": True,
            "submitted": True,
            "run_id": run.run_id,
            "status": run.status,
            "workflow_id": workflow_id,
        }


def submit_run(*args, **kwargs) -> str:
    payload = _coerce_tool_kwargs(args, kwargs)
    return _json_result(
        _run_async(
            _submit_run(
                workflow_id=str(payload.get("workflow_id") or ""),
                values=payload.get("values"),
                options=payload.get("options"),
                priority=str(payload.get("priority") or "normal"),
            )
        )
    )


async def _run_status(run_id: str) -> dict[str, Any]:
    context = _require_tool_context()
    async with context.session_factory() as session:
        service = RunService(session)
        run = await service.get_run(run_id, user_id=context.user_id)
        if run is None:
            return {"summary": "Run not found", "found": False, "run_id": run_id}
        return {
            "summary": f"Run {run.run_id} is {run.status}",
            "found": True,
            "run": {
                "run_id": run.run_id,
                "status": run.status,
                "current_task": run.current_task,
                "tasks_completed": run.tasks_completed,
                "tasks_total": run.tasks_total,
                "error_message": run.error_message,
            },
        }


def run_status(*args, **kwargs) -> str:
    payload = _coerce_tool_kwargs(args, kwargs)
    return _json_result(_run_async(_run_status(str(payload.get("run_id") or ""))))


async def _run_logs(run_id: str, tail: int = 50) -> dict[str, Any]:
    context = _require_tool_context()
    async with context.session_factory() as session:
        service = RunService(session)
        logs = await service.get_logs(run_id, user_id=context.user_id)
        entries = list((logs or {}).get("logs") or [])[-max(1, min(tail, 200)) :]
        return {
            "summary": f"Fetched {len(entries)} log entries",
            "run_id": run_id,
            "logs": entries,
        }


def run_logs(*args, **kwargs) -> str:
    payload = _coerce_tool_kwargs(args, kwargs)
    return _json_result(
        _run_async(
            _run_logs(
                str(payload.get("run_id") or ""),
                tail=int(payload.get("tail", 50)),
            )
        )
    )


async def _list_artifacts(run_id: str) -> dict[str, Any]:
    context = _require_tool_context()
    async with context.session_factory() as session:
        service = RunService(session)
        outputs = await service.list_outputs(run_id, user_id=context.user_id)
        files = list((outputs or {}).get("files") or [])
        return {
            "summary": f"Found {len(files)} output artifacts",
            "run_id": run_id,
            "files": files,
        }


def list_artifacts(*args, **kwargs) -> str:
    payload = _coerce_tool_kwargs(args, kwargs)
    return _json_result(_run_async(_list_artifacts(str(payload.get("run_id") or ""))))


async def _collect_run_results_context(
    *,
    run_id: str,
    tail: int,
    artifact_limit: int,
) -> dict[str, Any]:
    context = _require_tool_context()
    async with context.session_factory() as session:
        service = RunService(session)
        run = await service.get_run(run_id, user_id=context.user_id)
        if run is None:
            return {"summary": "Run not found", "found": False, "run_id": run_id}

        run_repo = RunRepository(session)
        raw_run = await run_repo.get_by_run_id(run_id)
        archive = RunArchiveService(ProjectRepository(session))

        logs: list[dict[str, Any]] = []
        log_error = None
        try:
            log_payload = await service.get_logs(
                run_id,
                tail=max(0, min(tail, 200)),
                user_id=context.user_id,
            )
            logs = list((log_payload or {}).get("logs") or [])
        except FileNotFoundError:
            log_error = "log file not found"

        files: list[dict[str, Any]] = []
        artifacts_error = None
        try:
            artifacts = await service.list_outputs(run_id, user_id=context.user_id)
            files = list((artifacts or {}).get("files") or [])
        except FileNotFoundError:
            artifacts_error = "output path not found"

        limited_files = files[: max(1, min(artifact_limit, 100))]
        output_path = None
        if raw_run is not None:
            resolved_output = await archive.resolve_output_path(raw_run)
            output_path = str(resolved_output) if resolved_output is not None else None

        config = RunConfigHelper(getattr(run, "config", None))
        artifact_count = len(files)
        summary = (
            f"Run {run.run_id} is {getattr(run.status, 'value', run.status)} "
            f"with {artifact_count} artifact(s)"
        )
        return {
            "summary": summary,
            "found": True,
            "run": run,
            "raw_run": raw_run,
            "output_path": output_path,
            "resolved_runspec": config.resolved_runspec,
            "logs": logs,
            "log_error": log_error,
            "artifact_count": artifact_count,
            "files": limited_files,
            "artifacts_error": artifacts_error,
        }


def _artifact_preview_sort_key(file_entry: dict[str, Any]) -> tuple[int, int, str]:
    name = str(file_entry.get("name") or "").lower()
    path = str(file_entry.get("path") or "").lower()
    priority = 10
    if "summary" in name:
        priority = 0
    elif "report" in name:
        priority = 1
    elif "result" in name:
        priority = 2
    elif path.endswith(".md"):
        priority = 3
    elif path.endswith(".tsv") or path.endswith(".csv") or path.endswith(".json"):
        priority = 4
    return (priority, len(path), path)


def _preview_artifact_excerpt(path: Path, *, preview_chars: int) -> tuple[str, bool] | None:
    if path.suffix.lower() not in TEXT_PREVIEW_SUFFIXES:
        return None
    if not path.exists() or not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return None
    if not text:
        return ("", False)
    truncated = len(text) > preview_chars
    excerpt = text[:preview_chars].rstrip()
    if truncated:
        excerpt = f"{excerpt}..."
    return (excerpt, truncated)


def _summarize_log_tail(logs: list[dict[str, Any]]) -> str:
    messages = [
        str(entry.get("message") or "").strip()
        for entry in logs
        if isinstance(entry, dict) and str(entry.get("message") or "").strip()
    ]
    if not messages:
        return "No recent log lines were available."
    if len(messages) == 1:
        return f"Latest log line: {messages[0]}"
    return f"Recent logs end with: {messages[-1]}"


def _build_result_explanation(
    *,
    run,
    output_path: str | None,
    logs: list[dict[str, Any]],
    artifact_previews: list[dict[str, Any]],
) -> dict[str, Any]:
    status = str(getattr(run.status, "value", run.status))
    if status == "completed":
        status_summary = f"Run {run.run_id} completed successfully."
    elif status in {"error", "failed"}:
        status_summary = f"Run {run.run_id} finished with {status} status."
    else:
        status_summary = f"Run {run.run_id} is currently {status}."

    if artifact_previews:
        names = ", ".join(preview["name"] for preview in artifact_previews[:3])
        artifact_summary = f"Key result files include {names}."
    elif output_path:
        artifact_summary = f"Outputs are expected under {output_path}, but no previewable text artifacts were found."
    else:
        artifact_summary = "No output artifacts were available yet."

    next_steps: list[str] = []
    if output_path:
        next_steps.append(f"Review outputs in {output_path}")
    if artifact_previews:
        next_steps.append(f"Inspect {artifact_previews[0]['path']} for the most relevant summary")
    elif status not in {"completed", "error", "failed"}:
        next_steps.append(f"Check run_status again until run {run.run_id} finishes")

    return {
        "status_summary": status_summary,
        "log_summary": _summarize_log_tail(logs),
        "artifact_summary": artifact_summary,
        "next_steps": next_steps,
    }


async def _run_results_overview(
    *,
    run_id: str,
    tail: int = 20,
    artifact_limit: int = 20,
) -> dict[str, Any]:
    collected = await _collect_run_results_context(
        run_id=run_id,
        tail=tail,
        artifact_limit=artifact_limit,
    )
    if not collected.get("found"):
        return collected

    run = collected["run"]
    files = list(collected.get("files") or [])
    artifact_count = int(collected.get("artifact_count") or 0)
    return {
        "summary": str(collected.get("summary") or ""),
        "found": True,
        "run": _serialize_run_summary(run),
        "output_path": collected.get("output_path"),
        "resolved_runspec": collected.get("resolved_runspec") or {},
        "logs": list(collected.get("logs") or []),
        "log_error": collected.get("log_error"),
        "artifacts": {
            "count": artifact_count,
            "files": files,
            "truncated": len(files) < artifact_count,
            "error": collected.get("artifacts_error"),
        },
    }


def run_results_overview(*args, **kwargs) -> str:
    payload = _coerce_tool_kwargs(args, kwargs)
    return _json_result(
        _run_async(
            _run_results_overview(
                run_id=str(payload.get("run_id") or ""),
                tail=int(payload.get("tail", 20)),
                artifact_limit=int(payload.get("artifact_limit", 20)),
            )
        )
    )


async def _explain_run_results(
    *,
    run_id: str,
    tail: int = 20,
    artifact_limit: int = 5,
    preview_chars: int = 600,
) -> dict[str, Any]:
    collected = await _collect_run_results_context(
        run_id=run_id,
        tail=tail,
        artifact_limit=artifact_limit,
    )
    if not collected.get("found"):
        return collected

    run = collected["run"]
    files = sorted(
        list(collected.get("files") or []),
        key=_artifact_preview_sort_key,
    )[: max(1, min(artifact_limit, 10))]

    artifact_previews: list[dict[str, Any]] = []
    for file_entry in files:
        if str(file_entry.get("type") or "") != "file":
            continue
        file_path = str(file_entry.get("path") or "")
        if not file_path:
            continue
        try:
            target = _resolve_tool_path(file_path)
        except (FileNotFoundError, PermissionError):
            continue
        preview = _preview_artifact_excerpt(
            target,
            preview_chars=max(120, min(preview_chars, 4000)),
        )
        if preview is None:
            continue
        excerpt, truncated = preview
        artifact_previews.append(
            {
                "name": str(file_entry.get("name") or target.name),
                "path": file_path,
                "excerpt": excerpt,
                "truncated": truncated,
                "size_bytes": file_entry.get("size_bytes"),
            }
        )

    explanation = _build_result_explanation(
        run=run,
        output_path=collected.get("output_path"),
        logs=list(collected.get("logs") or []),
        artifact_previews=artifact_previews,
    )
    summary = " ".join(
        part.strip()
        for part in [
            explanation.get("status_summary"),
            explanation.get("artifact_summary"),
        ]
        if isinstance(part, str) and part.strip()
    )
    return {
        "summary": summary or f"Prepared a plain-language explanation for run {run.run_id}",
        "found": True,
        "run": _serialize_run_summary(run),
        "output_path": collected.get("output_path"),
        "resolved_runspec": collected.get("resolved_runspec") or {},
        "logs": list(collected.get("logs") or []),
        "artifact_previews": artifact_previews,
        "explanation": explanation,
    }


def explain_run_results(*args, **kwargs) -> str:
    payload = _coerce_tool_kwargs(args, kwargs)
    return _json_result(
        _run_async(
            _explain_run_results(
                run_id=str(payload.get("run_id") or ""),
                tail=int(payload.get("tail", 20)),
                artifact_limit=int(payload.get("artifact_limit", 5)),
                preview_chars=int(payload.get("preview_chars", 600)),
            )
        )
    )


def ensure_bioinfoflow_toolset_registered() -> None:
    global _toolset_registered
    if _toolset_registered:
        return

    tool_specs = [
        (
            "workflow_catalog",
            {
                "description": "List and search workflows available in Bioinfoflow",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "search": {"type": "string"},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "additionalProperties": False,
                },
            },
            workflow_catalog,
        ),
        (
            "workflow_schema",
            {
                "description": "Inspect a workflow schema and form spec",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string"},
                        "workflow_name": {"type": "string"},
                        "version": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            workflow_schema,
        ),
        (
            "project_enable_workflow",
            {
                "description": "Enable a workflow for the active project so it can be previewed and run",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string"},
                    },
                    "required": ["workflow_id"],
                    "additionalProperties": False,
                },
            },
            project_enable_workflow,
        ),
        (
            "preview_run_profile",
            {
                "description": "Preview the workflow form spec for a workflow in a workspace",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string"},
                        "workspace": {"type": "string", "default": "."},
                    },
                    "required": ["workflow_id"],
                    "additionalProperties": False,
                },
            },
            preview_run_profile,
        ),
        (
            "submit_run",
            {
                "description": "Submit a new workflow run for the current Bioinfoflow project",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string"},
                        "values": {"type": "object"},
                        "options": {"type": "object"},
                        "priority": {"type": "string", "default": "normal"},
                    },
                    "required": ["workflow_id"],
                    "additionalProperties": False,
                },
            },
            submit_run,
        ),
        (
            "run_status",
            {
                "description": "Get status for a Bioinfoflow run",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                    },
                    "required": ["run_id"],
                    "additionalProperties": False,
                },
            },
            run_status,
        ),
        (
            "run_logs",
            {
                "description": "Fetch recent log lines for a Bioinfoflow run",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "tail": {"type": "integer", "default": 50},
                    },
                    "required": ["run_id"],
                    "additionalProperties": False,
                },
            },
            run_logs,
        ),
        (
            "list_artifacts",
            {
                "description": "List output artifacts for a Bioinfoflow run",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                    },
                    "required": ["run_id"],
                    "additionalProperties": False,
                },
            },
            list_artifacts,
        ),
        (
            "run_results_overview",
            {
                "description": "Summarize a run's current status, recent logs, and output artifacts",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "tail": {"type": "integer", "default": 20},
                        "artifact_limit": {"type": "integer", "default": 20},
                    },
                    "required": ["run_id"],
                    "additionalProperties": False,
                },
            },
            run_results_overview,
        ),
        (
            "explain_run_results",
            {
                "description": "Read previewable output artifacts and prepare a plain-language explanation of a run's outcome",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "tail": {"type": "integer", "default": 20},
                        "artifact_limit": {"type": "integer", "default": 5},
                        "preview_chars": {"type": "integer", "default": 600},
                    },
                    "required": ["run_id"],
                    "additionalProperties": False,
                },
            },
            explain_run_results,
        ),
    ]

    for name, schema, handler in tool_specs:
        _register_tool(name, schema, handler)
    _ensure_custom_toolset([name for name, _, _ in tool_specs])
    _toolset_registered = True
