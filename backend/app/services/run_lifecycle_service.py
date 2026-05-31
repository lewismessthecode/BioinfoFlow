"""Run lifecycle operations extracted from RunService.

Contains create_run, cancel_run, resume_run, retry_run, cleanup_run,
get_logs, append_run_log, and all supporting preflight / validation
helpers.

All callers should import RunService from run_service.py — never import
this module directly.
"""

from __future__ import annotations

import asyncio
import glob
import re
from collections import deque
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.registry import get_adapter
from app.models.run import Run, RunStatus
from app.models.run_config import RunConfigHelper
from app.models.workflow import WorkflowSource
from app.path_layout import (
    ensure_run_layout,
    project_home,
    run_audit_root,
    workflow_entrypoint_path,
)
from app.repositories.project_repo import ProjectRepository
from app.repositories.project_workflow_binding_repo import (
    ProjectWorkflowBindingRepository,
)
from app.repositories.run_repo import RunRepository
from app.repositories.workflow_repo import WorkflowRepository
from app.runtime.events import publish_run_status
from app.scheduler.cleanup import WorkDirCleaner
from app.services.authorization_service import AuthorizationService
from app.services.audit_service import AuditService
from app.services.run_archive import RunArchiveService
from app.services.run_dispatch import (
    RunDispatcher,
    get_run_dispatcher,
    get_run_scheduler,
)
from app.services.run_helpers import (
    binary_exists as _h_binary_exists,
    build_resolved_runspec,
    config_helper,
    copy_config,
    generate_run_id,
    has_glob,
    is_external_reference,
    is_path_like_key,
    iter_string_values,
    normalize_status_value,
    now as utc_now,
    resolve_resume_token,
    safe_workspace,
    sync_run_config_aliases,
)
from app.services.run_profile_service import RunProfileService
from app.utils.exceptions import PermissionDeniedError
from app.utils.project_access import can_access_run_project


class RunLifecycleService:
    """Handles run creation, cancellation, resume, retry, cleanup and logs."""

    def __init__(
        self,
        session: AsyncSession,
        dispatcher: RunDispatcher | None = None,
    ):
        self.session = session
        self.repo = RunRepository(session)
        self.project_repo = ProjectRepository(session)
        self.workflow_repo = WorkflowRepository(session)
        self.binding_repo = ProjectWorkflowBindingRepository(session)
        self.profile_service = RunProfileService()
        self.authorization = AuthorizationService(session)
        self._dispatcher = dispatcher or get_run_dispatcher()
        self._archive = RunArchiveService(self.project_repo)

    # ── cancel ────────────────────────────────────────────────────────────

    async def cancel_run(
        self,
        run_id: str,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> Run:
        run = await self._require_run(run_id)
        await self._require_run_access(run, user_id, workspace_id=workspace_id)
        if run.status not in {
            RunStatus.RUNNING.value,
            RunStatus.QUEUED.value,
            RunStatus.PENDING.value,
        }:
            raise ValueError("run is not cancellable")

        scheduler = get_run_scheduler()
        if scheduler is not None:
            cancelled = await scheduler.cancel(run_id)
            if cancelled:
                await self.session.refresh(run)
                return run
            await self.session.refresh(run)
            if run.status in {RunStatus.PENDING.value, RunStatus.QUEUED.value}:
                return await self._mark_run_cancelled(run)
            raise ValueError("run could not be cancelled")

        if run.status == RunStatus.RUNNING.value:
            pid = self._config_helper(run.config).pid
            workflow = (
                await self.workflow_repo.get(run.workflow_id)
                if run.workflow_id
                else None
            )
            engine = (
                getattr(workflow.engine, "value", workflow.engine) if workflow else None
            )
            cancelled = False
            if engine:
                cancelled = await get_adapter(str(engine)).cancel(
                    pid=pid,
                    run_name=run.nextflow_run_name,
                )
            if not cancelled:
                raise ValueError("run could not be cancelled")

        return await self._mark_run_cancelled(run)

    # ── resume ────────────────────────────────────────────────────────────

    async def resume_run(
        self,
        run_id: str,
        config_overrides: dict | None = None,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> Run:
        original = await self._require_run(run_id)
        await self._require_run_access(original, user_id, workspace_id=workspace_id)
        if original.status != RunStatus.FAILED.value:
            raise ValueError("run is not in failed status")

        workflow = None
        if original.workflow_id:
            await self._require_workflow_enabled(
                project_id=str(original.project_id),
                workflow_id=str(original.workflow_id),
            )
            workflow = await self.workflow_repo.get(original.workflow_id)

        engine = (
            getattr(workflow.engine, "value", workflow.engine) if workflow else None
        )
        if not engine:
            raise ValueError("workflow engine not found")

        adapter = get_adapter(str(engine))
        resume_token = adapter.get_resume_token(
            {
                **self._copy_config(original.config),
                "nextflow_run_name": original.nextflow_run_name,
            }
        ) or self._resolve_resume_token(original)
        if adapter.supports_native_resume:
            if not resume_token:
                raise ValueError(
                    "run cannot be resumed: missing valid nextflow resume token"
                )
            resume_payload = {
                "resume": True,
                "resume_from": resume_token,
                "resume_type": "native",
            }
        elif adapter.supports_best_effort_resume:
            if not resume_token:
                raise ValueError(
                    "run cannot be resumed: missing valid best-effort resume work dir"
                )
            resume_payload = {
                "resume": True,
                "resume_work_dir": resume_token,
                "resume_type": "best_effort",
            }
        else:
            raise ValueError("resume is not supported for this workflow")

        config = self._copy_config(original.config)
        cfg_helper = self._config_helper(config)
        merged_overrides = {
            **cfg_helper.config_overrides,
            **(config_overrides or {}),
        }
        config = self._sync_run_config_aliases(
            config,
            params=cfg_helper.params,
            inputs=cfg_helper.inputs,
            config_overrides=merged_overrides,
            resolved_runspec=cfg_helper.resolved_runspec,
        )

        new_config = {**config, **resume_payload}

        run = await self.repo.create(
            run_id=self._generate_run_id(),
            project_id=original.project_id,
            workflow_id=original.workflow_id,
            status=RunStatus.PENDING.value,
            config=new_config,
            samples_count=original.samples_count,
            tasks_total=0,
            tasks_completed=0,
        )
        project = await self.project_repo.get(original.project_id)
        if not project:
            raise FileNotFoundError("project not found")
        ensure_run_layout(project, run.run_id, engine=str(engine))
        await self._persist_run_archive(
            run=run, workspace_path=project_home(project), engine=str(engine)
        )

        return await self._finalize_new_run(
            run,
            action="run.resumed",
            message="Run resumed",
            details={
                "source_run_id": original.run_id,
                "resume_type": new_config.get("resume_type"),
            },
        )

    # ── retry ─────────────────────────────────────────────────────────────

    async def retry_run(
        self,
        run_id: str,
        *,
        params: dict | None = None,
        inputs: dict | None = None,
        config_overrides: dict | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> Run:
        original = await self._require_run(run_id)
        await self._require_run_access(original, user_id, workspace_id=workspace_id)
        if original.status != RunStatus.FAILED.value:
            raise ValueError("run is not in failed status")

        config = self._config_helper(original.config)
        if original.workflow_id:
            await self._require_workflow_enabled(
                project_id=str(original.project_id),
                workflow_id=str(original.workflow_id),
            )

        project = await self.project_repo.get(original.project_id)
        if not project:
            raise FileNotFoundError("project not found")

        workflow = (
            await self.workflow_repo.get(original.workflow_id)
            if original.workflow_id
            else None
        )
        workspace_path = project_home(project)

        resolved_runspec = config.resolved_runspec
        default_params = resolved_runspec.get("params") or config.params
        default_inputs = resolved_runspec.get("inputs") or config.inputs

        next_params = params if params is not None else default_params
        next_inputs = inputs if inputs is not None else default_inputs
        if workflow:
            await self._preflight_run(
                workflow=workflow,
                workspace_path=workspace_path,
                params=next_params,
                inputs=next_inputs,
            )

        next_resolved_runspec = self._build_resolved_runspec(
            workspace_path=workspace_path,
            params=next_params,
            inputs=next_inputs,
        )

        run = await self.repo.create(
            run_id=self._generate_run_id(),
            project_id=original.project_id,
            workflow_id=original.workflow_id,
            status=RunStatus.PENDING.value,
            config=RunConfigHelper.build_v1(
                params=next_params,
                inputs=next_inputs,
                config_overrides=config_overrides or config.config_overrides,
                resolved_runspec=next_resolved_runspec,
                retry_policy=config.retry_policy,
                timeout_seconds=config.timeout_seconds,
            ),
            samples_count=original.samples_count,
            tasks_total=0,
            tasks_completed=0,
        )
        engine_value = (
            str(getattr(workflow.engine, "value", workflow.engine))
            if workflow
            else "nextflow"
        )
        ensure_run_layout(project, run.run_id, engine=engine_value)
        await self._persist_run_archive(
            run=run,
            workspace_path=workspace_path,
            engine=engine_value,
        )

        return await self._finalize_new_run(
            run,
            action="run.retried",
            message="Run retried",
            details={"source_run_id": original.run_id},
        )

    # ── cleanup ───────────────────────────────────────────────────────────

    async def cleanup_run(
        self,
        run_id: str,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
        user_role: str | None = None,
    ) -> dict:
        run = await self._require_run(run_id)
        await self._require_run_access(run, user_id, workspace_id=workspace_id)
        await self.authorization.require_destructive_business_access(
            workspace_id=workspace_id,
            user_id=user_id,
            user_role=user_role,
        )
        project = await self.project_repo.get(run.project_id)
        if not project:
            raise FileNotFoundError("project not found")
        workflow = (
            await self.workflow_repo.get(run.workflow_id) if run.workflow_id else None
        )
        engine = (
            getattr(workflow.engine, "value", workflow.engine)
            if workflow
            else "nextflow"
        )
        workspace_path = project_home(project)
        cleaner = WorkDirCleaner()
        result = await cleaner.manual_cleanup(
            run.run_id,
            workspace_path=workspace_path,
            engine=str(engine),
            runtime=RunConfigHelper(run.config).runtime,
        )
        await self._audit().log(
            action="run.cleanup",
            resource_type="run",
            resource_id=run.run_id,
            project_id=str(run.project_id),
            actor="api",
            details=result,
        )
        return result

    # ── logs ──────────────────────────────────────────────────────────────

    async def get_logs(
        self,
        run_id: str,
        *,
        tail: int = 100,
        task: str | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict:
        run = await self._require_run(run_id)
        await self._require_run_access(run, user_id, workspace_id=workspace_id)
        log_path = run.config.get("log_path")
        if not log_path:
            log_path = f"runs/{run.run_id}/audit/run.log"

        project = await self.project_repo.get(run.project_id)
        if not project:
            raise FileNotFoundError("project not found")

        root = project_home(project)
        target = self._safe_workspace(root, log_path)
        config = RunConfigHelper(run.config)
        workspace = getattr(run, "workspace", None)
        if not workspace:
            resolved_workspace = config.resolved_runspec.get("workspace")
            if isinstance(resolved_workspace, str) and resolved_workspace.strip():
                workspace = resolved_workspace.strip()
        if (not target.exists() or not target.is_file()) and workspace not in (
            None,
            ".",
            "",
        ):
            workspace_path = Path(str(workspace))
            if workspace_path.is_absolute():
                workspace_root = workspace_path
            else:
                workspace_root = self._safe_workspace(root, str(workspace))
            target = self._safe_workspace(workspace_root, log_path)
        if not target.exists() or not target.is_file():
            if run.status in {
                RunStatus.COMPLETED.value,
                RunStatus.FAILED.value,
                RunStatus.CANCELLED.value,
            }:
                raise FileNotFoundError(f"run logs not found: {run_id}")
            return {"logs": []}

        if tail == 0:

            def _read_all_lines() -> list[dict]:
                result = []
                with target.open("r", encoding="utf-8", errors="ignore") as handle:
                    for line in handle:
                        result.append({"message": line.strip(), "task": task})
                return result

            logs = await asyncio.to_thread(_read_all_lines)
            return {"logs": logs}

        def _read_tail_lines() -> list[dict]:
            buf: deque[str] = deque(maxlen=tail)
            with target.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    buf.append(line)
            return [{"message": line.strip(), "task": task} for line in buf]

        logs = await asyncio.to_thread(_read_tail_lines)

        return {"logs": logs}

    async def _log_path(self, run: Run) -> Path | None:
        project = await self.project_repo.get(run.project_id)
        if not project:
            return None
        root = project_home(project)
        log_dir = run_audit_root(project, run.run_id)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "run.log"
        await self.repo.update(
            run, config={**run.config, "log_path": str(log_path.relative_to(root))}
        )
        return log_path

    async def append_run_log(self, run: Run, message: str) -> None:
        log_path = await self._log_path(run)
        if not log_path:
            return
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")

    # ── CRUD / query ──────────────────────────────────────────────────────

    async def list_runs(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        project_id: str | None = None,
        workflow_id: str | None = None,
        status: list[str] | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ):
        runs, pagination = await self.repo.list(
            limit=limit,
            cursor=cursor,
            project_id=project_id,
            workflow_id=workflow_id,
            status=status,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        normalized = [await self._normalize_run_status(run) for run in runs]
        return normalized, pagination

    async def get_run(
        self,
        run_id: str,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ):
        run = await self.repo.get_by_run_id(run_id)
        if not run:
            return None
        await self._require_run_access(run, user_id, workspace_id=workspace_id)
        return await self._normalize_run_status(run)

    async def get_run_audit(
        self,
        run_id: str,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[dict]:
        run = await self._require_run(run_id)
        await self._require_run_access(run, user_id, workspace_id=workspace_id)
        entries = await self._audit().list_for_resource("run", run.run_id)
        return [
            {
                "id": str(entry.id),
                "action": entry.action,
                "resource_type": entry.resource_type,
                "resource_id": entry.resource_id,
                "project_id": str(entry.project_id) if entry.project_id else None,
                "actor": entry.actor,
                "details": entry.details,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in entries
        ]

    async def delete_run(
        self,
        run_id: str,
        *,
        delete_outputs: bool = False,
        user_id: str | None = None,
        workspace_id: str | None = None,
        user_role: str | None = None,
    ) -> None:
        run = await self._require_run(run_id)
        await self._require_run_access(run, user_id, workspace_id=workspace_id)
        await self.authorization.require_destructive_business_access(
            workspace_id=workspace_id,
            user_id=user_id,
            user_role=user_role,
        )
        if delete_outputs:
            await self._archive.delete_outputs(run)
        await self.repo.delete_scheduler_tasks(run.run_id)
        await self.repo.delete(run)

    # ── outputs ───────────────────────────────────────────────────────────

    async def list_outputs(
        self,
        run_id: str,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict:
        run = await self._require_run(run_id)
        await self._require_run_access(run, user_id, workspace_id=workspace_id)
        return await self._archive.list_outputs(run)

    async def build_output_archive(
        self,
        run_id: str,
        *,
        file_path: str | None = None,
        archive_format: str = "tar.gz",
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> tuple[bytes, str]:
        run = await self._require_run(run_id)
        await self._require_run_access(run, user_id, workspace_id=workspace_id)
        return await self._archive.build_output_archive(
            run, file_path=file_path, archive_format=archive_format
        )

    # ── preflight ─────────────────────────────────────────────────────────

    async def _preflight_run(
        self,
        *,
        workflow,
        workspace_path: Path,
        params: dict,
        inputs: dict,
    ) -> None:
        engine = str(getattr(workflow.engine, "value", workflow.engine))
        self._require_engine_binary(engine)
        self._require_workflow_source(workflow)
        self._validate_path_like_values(
            workspace_path=workspace_path, payload=params, label="param"
        )
        self._validate_path_like_values(
            workspace_path=workspace_path, payload=inputs, label="input"
        )

    def _require_engine_binary(self, engine: str) -> None:
        binary: str | None = None
        try:
            binary = get_adapter(engine).binary
        except ValueError:
            binary = None
        if binary and not self._binary_exists(binary):
            raise ValueError(f"{engine} binary not found ({binary})")

    def _binary_exists(self, binary: str) -> bool:
        return _h_binary_exists(binary)

    def _require_workflow_source(self, workflow) -> None:
        source = str(getattr(workflow.source, "value", workflow.source))
        if source != WorkflowSource.LOCAL.value or not getattr(
            workflow, "entrypoint_relpath", None
        ):
            return
        path = self._resolve_workflow_source(workflow)
        if not path.exists() or not path.is_file():
            raise ValueError("workflow source not found")

    def _resolve_workflow_source(self, workflow) -> Path:
        return workflow_entrypoint_path(workflow)

    def _validate_path_like_values(
        self, *, workspace_path: Path, payload: dict, label: str
    ) -> None:
        for key, value in iter_string_values(payload):
            if not is_path_like_key(key):
                continue
            candidate = value.strip()
            if not candidate or is_external_reference(candidate):
                continue

            candidate_path = Path(candidate)
            if candidate_path.is_absolute():
                if not candidate_path.exists():
                    raise ValueError(f"{label} path not found: {key}")
                continue

            if has_glob(candidate):
                patterns = _expand_glob_braces(candidate)
                has_match = any(
                    glob.glob(pattern, root_dir=str(workspace_path), recursive=True)
                    for pattern in patterns
                )
                if not has_match:
                    raise ValueError(f"{label} glob has no matches: {key}")
                continue

            try:
                target = safe_workspace(workspace_path, candidate)
            except PermissionError as exc:
                raise ValueError(f"{label} path escapes workspace: {key}") from exc
            if not target.exists():
                raise ValueError(f"{label} path not found: {key}")

    # ── private helpers ───────────────────────────────────────────────────

    async def _require_workflow_enabled(
        self, *, project_id: str, workflow_id: str
    ) -> None:
        enabled = await self.binding_repo.is_enabled(
            project_id=project_id, workflow_id=workflow_id
        )
        if not enabled:
            from app.services.run_service import WorkflowNotEnabledError

            raise WorkflowNotEnabledError("workflow not enabled for project")

    async def _persist_run_archive(
        self, *, run: Run, workspace_path: Path, engine: str
    ) -> None:
        await self._archive.persist_run_archive(
            run=run, workspace_path=workspace_path, engine=engine
        )

    async def _require_run_access(
        self,
        run: Run,
        user_id: str | None,
        *,
        workspace_id: str | None = None,
    ) -> None:
        """Verify the caller owns the project that hosts this run.

        When *user_id* is None the call is internal (scheduler, hooks,
        background cleanup) and ownership is skipped. Any API-initiated
        call passes the authenticated user's id and must match the
        run's parent project owner.
        """
        project = await self.project_repo.get(run.project_id)
        if not project:
            raise FileNotFoundError(f"Run {run.run_id} not found")
        if not can_access_run_project(
            project,
            user_id=user_id,
            workspace_id=workspace_id,
        ):
            raise PermissionDeniedError("You do not have access to this run.")

    async def _normalize_run_status(self, run: Run) -> Run:
        current = getattr(run.status, "value", run.status)
        normalized = normalize_status_value(current)
        if normalized != current:
            run = await self.repo.update(run, status=normalized)
        return run

    async def _require_run(self, run_id: str) -> Run:
        run = await self.repo.get_by_run_id(run_id)
        if not run:
            raise FileNotFoundError("run not found")
        return await self._normalize_run_status(run)

    def _build_resolved_runspec(
        self, *, workspace_path: Path, params: dict, inputs: dict
    ) -> dict:
        return build_resolved_runspec(
            workspace_path=workspace_path, params=params, inputs=inputs
        )

    def _resolve_resume_token(self, run: Run) -> str | None:
        return resolve_resume_token(run)

    async def _mark_run_cancelled(self, run: Run) -> Run:
        run = await self.repo.update(
            run,
            status=RunStatus.CANCELLED.value,
            completed_at=self._now(),
        )
        await self._audit().log(
            action="run.cancelled",
            resource_type="run",
            resource_id=run.run_id,
            project_id=str(run.project_id),
            actor="api",
            details={"status": RunStatus.CANCELLED.value},
        )
        await publish_run_status(run, message="Run cancelled")
        return run

    def _generate_run_id(self) -> str:
        return generate_run_id()

    def _safe_workspace(self, root: Path, relative_path: str) -> Path:
        return safe_workspace(root, relative_path)

    def _now(self) -> datetime:
        return utc_now()

    def _config_helper(self, config: dict | None) -> RunConfigHelper:
        return config_helper(config)

    def _copy_config(self, config: dict | None) -> dict:
        return copy_config(config)

    def _audit(self) -> AuditService:
        return AuditService(self.session)

    async def _finalize_new_run(
        self,
        run: Run,
        *,
        action: str,
        message: str,
        details: dict | None = None,
        priority: str = "normal",
    ) -> Run:
        """Queue a newly created run: update status, audit, publish, dispatch."""
        run = await self.repo.update(run, status=RunStatus.QUEUED.value)
        await self._audit().log(
            action=action,
            resource_type="run",
            resource_id=run.run_id,
            project_id=str(run.project_id),
            actor="api",
            details=details or {},
        )
        await publish_run_status(run, message=message)
        self._dispatcher.dispatch(run.run_id, priority=priority)
        return run

    def _sync_run_config_aliases(
        self,
        config: dict,
        *,
        params: dict | None = None,
        inputs: dict | None = None,
        config_overrides: dict | None = None,
        resolved_runspec: dict | None = None,
    ) -> dict:
        return sync_run_config_aliases(
            config,
            params=params,
            inputs=inputs,
            config_overrides=config_overrides,
            resolved_runspec=resolved_runspec,
        )


def _expand_glob_braces(pattern: str) -> list[str]:
    match = re.search(r"\{([^{}]+)\}", pattern)
    if not match:
        return [pattern]
    options = [part.strip() for part in match.group(1).split(",") if part.strip()]
    if not options:
        return [pattern]
    prefix = pattern[: match.start()]
    suffix = pattern[match.end() :]
    expanded: list[str] = []
    for option in options:
        expanded.extend(_expand_glob_braces(f"{prefix}{option}{suffix}"))
    return expanded
