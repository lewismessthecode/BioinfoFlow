"""DAG operations extracted from RunService.

Contains get_dag, repair_run_dag, repair_run_dags, create_mock_dag_variants
and all supporting helpers for DAG repair and mock variant generation.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import Run, RunStatus
from app.path_layout import project_home, run_audit_root, run_results_root
from app.repositories.project_repo import ProjectRepository
from app.repositories.run_repo import RunRepository
from app.repositories.workflow_repo import WorkflowRepository
from app.runtime.events import publish_run_dag
from app.services.dag_parser import DagParser
from app.services.run_helpers import (
    _clone_json,
    _sync_edge_animation,
    build_mock_variant_dag,
    generate_mock_run_id,
    mock_current_task,
    mock_log_content,
    mock_timestamps,
    mock_variant_run_status,
    normalize_status_value,
    safe_workspace,
)
from app.services.run_helpers import now as utc_now
from app.services.trace_parser import TraceParser
from app.utils.dag_builder import build_dag_from_schema, normalize_dag_id
from app.utils.exceptions import PermissionDeniedError
from app.utils.project_access import can_access_run_project


class RunDagService:
    """Handles DAG retrieval, repair, and mock variant generation."""

    _MOCK_VARIANTS = ("pending", "queued", "running", "failed", "success")

    def __init__(
        self,
        session: AsyncSession,
        dispatcher=None,  # noqa: ARG002 — kept for init-pattern parity
    ):
        self.session = session
        self.repo = RunRepository(session)
        self.project_repo = ProjectRepository(session)
        self.workflow_repo = WorkflowRepository(session)

    # ── public methods ───────────────────────────────────────────────────

    async def get_dag(
        self,
        run_id: str,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict:
        run = await self._require_run(run_id)
        await self._require_run_access(run, user_id, workspace_id=workspace_id)
        dag = self._config_helper(run.config).dag

        # Return stored DAG if it has nodes (the single source of truth)
        if dag.get("nodes"):
            return dag

        # Fallback: build from workflow schema
        if run.workflow_id:
            workflow = await self.workflow_repo.get(run.workflow_id)
            if workflow and workflow.schema_json:
                return build_dag_from_schema(workflow.schema_json)

        raise FileNotFoundError("dag not found")

    async def repair_run_dag(
        self,
        run_id: str,
        *,
        dry_run: bool = False,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict:
        run = await self._require_run(run_id)
        await self._require_run_access(run, user_id, workspace_id=workspace_id)
        return await self._repair_run_dag_instance(run, dry_run=dry_run)

    async def repair_run_dags(
        self,
        *,
        run_ids: list[str] | None = None,
        project_id: str | None = None,
        dry_run: bool = False,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict:
        runs = await self._select_runs_for_dag_repair(
            run_ids=run_ids,
            project_id=project_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )

        results: list[dict] = []
        for run in runs:
            try:
                results.append(
                    await self._repair_run_dag_instance(run, dry_run=dry_run)
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {
                        "run_id": run.run_id,
                        "status": getattr(run.status, "value", run.status),
                        "repaired": False,
                        "reason": str(exc),
                        "node_status_counts": {},
                    }
                )

        repaired_count = sum(1 for item in results if item["repaired"])
        return {
            "runs": results,
            "summary": {
                "total": len(results),
                "repaired": repaired_count,
                "skipped": len(results) - repaired_count,
                "dry_run": dry_run,
            },
        }

    async def create_mock_dag_variants(
        self,
        source_run_id: str,
        *,
        variants: list[str] | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict:
        source_run = await self._require_run(source_run_id)
        await self._require_run_access(
            source_run,
            user_id,
            workspace_id=workspace_id,
        )
        source_dag = await self._resolve_repairable_dag(source_run)
        if not source_dag.get("nodes"):
            raise FileNotFoundError("dag not found")

        project = await self.project_repo.get(source_run.project_id)
        if not project:
            raise FileNotFoundError("project not found")

        workspace = project_home(project)
        source_config = source_run.config if isinstance(source_run.config, dict) else {}
        source_runtime = source_config.get("runtime", {}) or {}
        mock_runtime = {
            key: value
            for key, value in source_runtime.items()
            if key not in {"trace_path", "dag_path"}
        }

        requested = variants or ["pending", "queued", "running", "failed"]
        normalized_variants = []
        for variant in requested:
            value = str(variant).strip().lower()
            if value not in self._MOCK_VARIANTS:
                raise ValueError(f"unsupported mock variant: {variant}")
            if value not in normalized_variants:
                normalized_variants.append(value)

        created: list[dict] = []
        for variant in normalized_variants:
            run_id = generate_mock_run_id(variant)
            dag = build_mock_variant_dag(source_dag, variant)
            output_dir = f"runs/{run_id}/results"
            log_path = run_audit_root(project, run_id) / "run.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                mock_log_content(variant, dag),
                encoding="utf-8",
            )

            output_root = run_results_root(project, run_id)
            output_root.mkdir(parents=True, exist_ok=True)
            (output_root / "summary.txt").write_text(
                f"Mock DAG variant: {variant}\nrun_id: {run_id}\n",
                encoding="utf-8",
            )

            now = utc_now()
            started_at, completed_at = mock_timestamps(variant, now)
            params = {
                **(source_config.get("params", {}) or {}),
                "outdir": output_dir,
            }
            status = mock_variant_run_status(variant)
            counts = _count_node_statuses(dag)
            run = await self.repo.create(
                run_id=run_id,
                project_id=source_run.project_id,
                workflow_id=source_run.workflow_id,
                status=status,
                config={
                    **source_config,
                    "runtime": mock_runtime,
                    "params": params,
                    "dag": dag,
                    "log_path": str(log_path.relative_to(workspace)),
                    "mock_variant": variant,
                    "mock_source_run_id": source_run.run_id,
                },
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=_mock_duration_seconds(started_at, completed_at),
                samples_count=source_run.samples_count,
                tasks_total=len(dag.get("nodes", [])),
                tasks_completed=counts.get("success", 0),
                current_task=mock_current_task(dag),
                error_message="Mock task failure" if variant == "failed" else None,
                nextflow_run_name=f"mock_{variant}",
            )
            created.append(
                {
                    "variant": variant,
                    "run_id": run.run_id,
                    "status": getattr(run.status, "value", run.status),
                    "node_status_counts": counts,
                }
            )

        return {
            "source_run_id": source_run.run_id,
            "runs": created,
        }

    # ── private helpers ──────────────────────────────────────────────────

    async def _require_run(self, run_id: str) -> Run:
        run = await self.repo.get_by_run_id(run_id)
        if not run:
            raise FileNotFoundError("run not found")
        return await self._normalize_run_status(run)

    async def _require_run_access(
        self,
        run: Run,
        user_id: str | None,
        *,
        workspace_id: str | None = None,
    ) -> None:
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

    def _config_helper(self, config: dict | None):
        from app.models.run_config import RunConfigHelper

        return RunConfigHelper(config if isinstance(config, dict) else {})

    async def _select_runs_for_dag_repair(
        self,
        *,
        run_ids: list[str] | None,
        project_id: str | None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[Run]:
        if run_ids:
            runs: list[Run] = []
            for run_id in run_ids:
                run = await self._require_run(run_id)
                await self._require_run_access(
                    run,
                    user_id,
                    workspace_id=workspace_id,
                )
                runs.append(run)
            return runs

        statuses = [
            RunStatus.COMPLETED.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
        ]
        runs = await self.repo.list_by_statuses(
            statuses,
            project_id=project_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        return [await self._normalize_run_status(run) for run in runs]

    async def _repair_run_dag_instance(self, run: Run, *, dry_run: bool) -> dict:
        dag_before = await self._resolve_repairable_dag(run)
        if not dag_before.get("nodes"):
            return {
                "run_id": run.run_id,
                "status": getattr(run.status, "value", run.status),
                "repaired": False,
                "reason": "dag not available",
                "node_status_counts": {},
            }

        dag_after = await self._repair_dag_statuses_for_run(run, dag_before)
        repaired = dag_after != dag_before

        if repaired and not dry_run:
            config = run.config if isinstance(run.config, dict) else {}
            repo = RunRepository(self.session)
            await repo.update_config(run, {**config, "dag": dag_after})
            await publish_run_dag(run)

        return {
            "run_id": run.run_id,
            "status": getattr(run.status, "value", run.status),
            "repaired": repaired,
            "reason": "dry-run"
            if dry_run and repaired
            else ("updated" if repaired else "no changes"),
            "node_status_counts": _count_node_statuses(dag_after),
        }

    async def _resolve_repairable_dag(self, run: Run) -> dict:
        config = run.config if isinstance(run.config, dict) else {}
        stored = config.get("dag", {"nodes": [], "edges": []})
        if stored.get("nodes"):
            return _clone_json(stored)

        project = await self.project_repo.get(run.project_id)
        if not project:
            return {"nodes": [], "edges": []}

        workspace = project_home(project)
        workflow = (
            await self.workflow_repo.get(run.workflow_id) if run.workflow_id else None
        )
        schema = workflow.schema_json if workflow and workflow.schema_json else None

        runtime = config.get("runtime", {}) or {}
        dag_rel_path = runtime.get("dag_path")
        if dag_rel_path:
            dag_path = safe_workspace(workspace, dag_rel_path)
            if dag_path.exists():
                return DagParser().parse_dot_file(dag_path, schema=schema)

        if schema:
            return build_dag_from_schema(schema)

        return {"nodes": [], "edges": []}

    async def _repair_dag_statuses_for_run(self, run: Run, dag: dict) -> dict:
        repaired = _clone_json(dag)
        config = run.config if isinstance(run.config, dict) else {}

        runtime = config.get("runtime", {}) or {}
        trace_path = await self._resolve_runtime_workspace_file(
            run,
            runtime.get("trace_path"),
        )
        if trace_path and trace_path.exists():
            statuses = TraceParser().get_process_statuses(trace_path)
            if statuses:
                repaired = _apply_status_map_to_dag(repaired, statuses)

        run_status = getattr(run.status, "value", run.status)
        if run_status == RunStatus.COMPLETED.value:
            for node in repaired.get("nodes", []):
                node_status = node.get("data", {}).get("status", "pending")
                if node_status in {"pending", "queued", "running"}:
                    node["data"]["status"] = "success"
        elif run_status in {RunStatus.FAILED.value, RunStatus.CANCELLED.value}:
            for node in repaired.get("nodes", []):
                node_status = node.get("data", {}).get("status", "pending")
                if node_status in {"queued", "running"}:
                    node["data"]["status"] = "failed"

        _sync_edge_animation(repaired)
        if run_status in {
            RunStatus.COMPLETED.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
        }:
            for edge in repaired.get("edges", []):
                edge["animated"] = False

        return repaired

    async def _resolve_runtime_workspace_file(
        self, run: Run, relative_path: str | None
    ) -> Path | None:
        if not relative_path:
            return None
        project = await self.project_repo.get(run.project_id)
        if not project:
            return None
        workspace = project_home(project)
        return safe_workspace(workspace, relative_path)


# ── module-level helpers ────────────────────────────────────────────────


def _count_node_statuses(dag: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in dag.get("nodes", []):
        status = node.get("data", {}).get("status", "pending")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _apply_status_map_to_dag(dag: dict, statuses: dict[str, str]) -> dict:
    normalized = {normalize_dag_id(name): value for name, value in statuses.items()}
    for node in dag.get("nodes", []):
        node_id = node.get("id")
        if node_id in normalized:
            node.setdefault("data", {})["status"] = normalized[node_id]
    return dag


def _mock_duration_seconds(
    started_at: datetime | None, completed_at: datetime | None
) -> int | None:
    if not started_at or not completed_at:
        return None
    return int((completed_at - started_at).total_seconds())
