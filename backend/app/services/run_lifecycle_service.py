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
import hashlib
import json
import re
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.engine.registry import get_adapter
from app.models.run import Run, RunStatus
from app.models.run_config import RunConfigHelper
from app.models.workflow import WorkflowSource
from app.path_layout import (
    project_home,
    run_audit_root,
    run_engine_workspace,
    workflow_entrypoint_path,
)
from app.repositories.project_repo import ProjectRepository
from app.repositories.project_workflow_binding_repo import (
    ProjectWorkflowBindingRepository,
)
from app.repositories.run_repo import RunRepository
from app.repositories.workflow_repo import WorkflowRepository
from app.runtime.events import publish_run_status
from app.schemas.form_spec import FormField, FormSpec
from app.schemas.run import RunCreate, RunOptions
from app.scheduler.cleanup import WorkDirCleaner
from app.services.authorization_service import AuthorizationService
from app.services.audit_service import AuditService
from app.services.run_archive import RunArchiveService
from app.services.run_compiler import RunCompiler
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
from app.services.workflow_form_spec import effective_workflow_form_spec
from app.utils.exceptions import PermissionDeniedError
from app.utils.project_access import can_access_run_project


_PLATFORM_MANAGED_DIR_NAMES = {"outdir", "output_dir", "publish_dir", "work_dir"}


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
            project = await self.project_repo.get(original.project_id)
            if not project:
                raise FileNotFoundError("project not found")
            _validate_best_effort_resume_work_dir(
                project=project,
                run_id=original.run_id,
                token=resume_token,
            )
            resume_payload = {
                "resume": True,
                "resume_work_dir": resume_token,
                "resume_type": "best_effort",
            }
        else:
            raise ValueError("resume is not supported for this workflow")

        config = self._config_helper(original.config)
        run = await self._compile_replayed_run(
            original=original,
            workflow=workflow,
            replay_kind="resume",
            values=None,
            params=None,
            inputs=None,
            config_overrides={
                **config.config_overrides,
                **(config_overrides or {}),
            },
            extra_config=resume_payload,
            audit_action="run.resumed",
            audit_details={
                "source_run_id": original.run_id,
                "resume_type": resume_payload.get("resume_type"),
            },
            user_id=user_id,
            workspace_id=workspace_id,
        )
        return run

    # ── retry ─────────────────────────────────────────────────────────────

    async def retry_run(
        self,
        run_id: str,
        *,
        values: dict | None = None,
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

        if workflow is None:
            raise ValueError("workflow not found")

        run = await self._compile_replayed_run(
            original=original,
            workflow=workflow,
            replay_kind="retry",
            values=values,
            params=params,
            inputs=inputs,
            config_overrides={
                **config.config_overrides,
                **(config_overrides or {}),
            },
            extra_config=None,
            audit_action="run.retried",
            audit_details={"source_run_id": original.run_id},
            user_id=user_id,
            workspace_id=workspace_id,
        )
        return run

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
        if await self.repo.has_replay_children(run.run_id):
            raise ValueError(
                "cannot delete a source run while replay runs still reference it; "
                "delete replay runs first"
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
        completed_at = self._now()
        run = await self.repo.update(
            run,
            status=RunStatus.CANCELLED.value,
            completed_at=completed_at,
            duration_seconds=_duration_seconds(run.started_at, completed_at),
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

    async def _compile_replayed_run(
        self,
        *,
        original: Run,
        workflow,
        replay_kind: str,
        values: dict | None,
        params: dict | None,
        inputs: dict | None,
        config_overrides: dict,
        extra_config: dict | None,
        audit_action: str | None,
        audit_details: dict | None,
        user_id: str | None,
        workspace_id: str | None,
    ) -> Run:
        replay_values = self._replay_values(
            original=original,
            workflow=workflow,
            values=values,
            params=params,
            inputs=inputs,
        )
        options = self._replay_options(self._config_helper(original.config))
        options_payload = (
            options.model_dump(mode="json", exclude_none=True) if options else {}
        )
        replay_key = _replay_idempotency_key(
            source_run_id=original.run_id,
            replay_kind=replay_kind,
            values=replay_values,
            options=options_payload,
            config_overrides=config_overrides,
            extra_config=extra_config,
        )
        existing = await self.repo.get_replay_by_intent(
            source_run_id=original.run_id,
            replay_kind=replay_kind,
            replay_idempotency_key=replay_key,
        )
        if existing is not None:
            setattr(existing, "_reused_replay", True)
            return existing

        payload = RunCreate.model_validate(
            {
                "project_id": str(original.project_id),
                "workflow_id": str(original.workflow_id),
                "values": replay_values,
                **({"options": options_payload} if options is not None else {}),
            }
        )
        try:
            return await RunCompiler(
                self.session,
                dispatcher=self._dispatcher,
            ).create_run(
                payload,
                user_id=user_id,
                workspace_id=workspace_id,
                config_overrides=config_overrides,
                extra_config=extra_config,
                audit_action=audit_action,
                audit_details=audit_details,
                source_run_id=original.run_id,
                replay_kind=replay_kind,
                replay_idempotency_key=replay_key,
                attempt_number=int(original.attempt_number or 1) + 1,
            )
        except IntegrityError:
            await self.session.rollback()
            existing = await self.repo.get_replay_by_intent(
                source_run_id=original.run_id,
                replay_kind=replay_kind,
                replay_idempotency_key=replay_key,
            )
            if existing is not None:
                setattr(existing, "_reused_replay", True)
                return existing
            raise

    def _replay_values(
        self,
        *,
        original: Run,
        workflow,
        values: dict | None,
        params: dict | None,
        inputs: dict | None,
    ) -> dict:
        if values is not None:
            return deepcopy(values)

        config = self._config_helper(original.config)
        stored_values = config.values
        if stored_values:
            base_values = stored_values
        else:
            default_params, default_inputs = _default_engine_payloads(config)
            base_values = _values_from_engine_payloads(
                workflow=workflow,
                params=default_params,
                inputs=default_inputs,
            )

        if params is None and inputs is None:
            return base_values

        override_values = _values_from_engine_payloads(
            workflow=workflow,
            params=params or {},
            inputs=inputs or {},
        )
        return {**base_values, **override_values}

    def _replay_options(self, config: RunConfigHelper) -> RunOptions | None:
        payload = config.options
        payload.pop("resume_from_run_id", None)
        retry_policy = config.retry_policy
        if "max_retries" not in payload and isinstance(
            retry_policy.get("max_retries"), int
        ):
            payload["max_retries"] = retry_policy["max_retries"]
        timeout_seconds = config.timeout_seconds
        if "timeout_seconds" not in payload and timeout_seconds is not None:
            payload["timeout_seconds"] = timeout_seconds
        raw_config = config.to_dict()
        profile = raw_config.get("profile")
        if "profile" not in payload and isinstance(profile, str) and profile.strip():
            payload["profile"] = profile.strip()
        if not payload:
            return None
        return RunOptions.model_validate(payload)

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


def _values_from_engine_payloads(
    *,
    workflow,
    params: dict,
    inputs: dict,
) -> dict:
    spec = effective_workflow_form_spec(workflow)
    user_fields = [field for field in spec.fields if not field.platform_managed]
    if not user_fields:
        return _legacy_values_from_payloads(params=params, inputs=inputs)

    values: dict[str, Any] = {}
    for field in user_fields:
        value = _value_for_field(field, params=params, inputs=inputs, spec=spec)
        if value is not _MISSING:
            values[field.id] = deepcopy(value)
    return values


def _default_engine_payloads(config: RunConfigHelper) -> tuple[dict, dict]:
    resolved = config.resolved_runspec
    resolved_params = resolved.get("params")
    resolved_inputs = resolved.get("inputs")
    params = resolved_params if isinstance(resolved_params, dict) else {}
    inputs = resolved_inputs if isinstance(resolved_inputs, dict) else {}
    return params or config.params, inputs or config.inputs


def _legacy_values_from_payloads(*, params: dict, inputs: dict) -> dict:
    values: dict[str, Any] = {}
    for source in (inputs, params):
        for key, value in source.items():
            if _is_platform_managed_dir_key(key):
                continue
            values[str(key)] = deepcopy(value)
    return values


_MISSING = object()


def _value_for_field(
    field: FormField,
    *,
    params: dict,
    inputs: dict,
    spec: FormSpec,
) -> Any:
    for key in _field_payload_keys(field, spec):
        if key in inputs:
            return inputs[key]
        if key in params:
            return params[key]
    return _MISSING


def _field_payload_keys(field: FormField, spec: FormSpec) -> tuple[str, ...]:
    keys = [field.id]
    if field.engine_key:
        keys.append(field.engine_key)
    workflow_name = _workflow_name_from_spec(spec)
    if workflow_name and "." not in field.id:
        keys.append(f"{workflow_name}.{field.id}")

    deduped: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return tuple(deduped)


def _workflow_name_from_spec(spec: FormSpec) -> str:
    for field in spec.fields:
        if not field.engine_key or "." not in field.engine_key:
            continue
        return field.engine_key.split(".", 1)[0]
    return ""


def _is_platform_managed_dir_key(key: object) -> bool:
    text = str(key or "").strip().lower()
    if not text:
        return False
    return text.split(".")[-1] in _PLATFORM_MANAGED_DIR_NAMES


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


def _replay_idempotency_key(
    *,
    source_run_id: str,
    replay_kind: str,
    values: dict,
    options: dict,
    config_overrides: dict,
    extra_config: dict | None,
) -> str:
    payload = {
        "source_run_id": source_run_id,
        "replay_kind": replay_kind,
        "values": values,
        "options": options,
        "config_overrides": config_overrides,
        "extra_config": extra_config or {},
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolve_work_dir_token(workspace_path: Path, token: str) -> Path:
    path = Path(token)
    return path if path.is_absolute() else workspace_path / path


def _validate_best_effort_resume_work_dir(*, project, run_id: str, token: str) -> Path:
    source = _resolve_work_dir_token(project_home(project), token)
    if not source.exists() or not source.is_dir():
        raise ValueError(
            "run cannot be resumed: best-effort resume work dir is unavailable"
        )

    expected = run_engine_workspace(project, run_id, "wdl").resolve(strict=False)
    source_resolved = source.resolve()
    if source_resolved != expected:
        raise ValueError(
            "run cannot be resumed: best-effort resume work dir is outside source run work dir"
        )
    if source.is_symlink() or _contains_symlink(source):
        raise ValueError(
            "run cannot be resumed: best-effort resume work dir contains symlinks"
        )
    return source


def _contains_symlink(path: Path) -> bool:
    try:
        return any(item.is_symlink() for item in path.rglob("*"))
    except OSError:
        return True


def _duration_seconds(
    started_at: datetime | None,
    completed_at: datetime | None,
) -> int | None:
    if not started_at or not completed_at:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    return int((completed_at - started_at).total_seconds())
