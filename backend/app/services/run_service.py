"""RunService facade — thin delegation layer for runs lifecycle.

The create path lives in ``RunCompiler`` and is called directly by the API
handler + agent tools. Everything else — listing, cancel/resume/retry,
DAG, outputs — is delegated from this facade.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import Run
from app.repositories.project_repo import ProjectRepository
from app.repositories.run_repo import RunRepository
from app.repositories.workflow_repo import WorkflowRepository
from app.runtime.task_runner import task_runner as runtime_task_runner
from app.services.run_archive import RunArchiveService
from app.services.run_compiler import WorkflowNotEnabledError
from app.services.run_dag_service import RunDagService
from app.services.run_dispatch import RunDispatcher, get_run_dispatcher
from app.services.run_lifecycle_service import RunLifecycleService


# Deprecated compatibility export. Production run dispatch is owned by the
# injected RunDispatcher collaborator; this alias remains importable for
# downstream callers that used the former public module surface.
task_runner = runtime_task_runner

__all__ = ["RunService", "RunLifecycleService", "WorkflowNotEnabledError", "task_runner"]


class RunService:

    def __init__(
        self,
        session: AsyncSession,
        dispatcher: RunDispatcher | None = None,
    ):
        self.session = session
        self.repo = RunRepository(session)
        self.project_repo = ProjectRepository(session)
        self.workflow_repo = WorkflowRepository(session)
        self._dispatcher = dispatcher or get_run_dispatcher()
        self._archive = RunArchiveService(self.project_repo)
        self._dag_ops = RunDagService(session, self._dispatcher)
        self._lifecycle = RunLifecycleService(session, self._dispatcher)

    # ── DAG operations ─────────────────────────────────────────────────────

    async def get_dag(self, run_id: str, **kwargs) -> dict:
        return await self._dag_ops.get_dag(run_id, **kwargs)

    async def repair_run_dag(self, run_id: str, **kwargs) -> dict:
        return await self._dag_ops.repair_run_dag(run_id, **kwargs)

    async def repair_run_dags(self, **kwargs) -> dict:
        return await self._dag_ops.repair_run_dags(**kwargs)

    async def create_mock_dag_variants(self, source_run_id: str, **kwargs) -> dict:
        return await self._dag_ops.create_mock_dag_variants(source_run_id, **kwargs)

    # ── lifecycle (cancel / resume / retry / cleanup) ──────────────────────

    async def cancel_run(self, run_id: str, **kwargs) -> Run:
        return await self._lifecycle.cancel_run(run_id, **kwargs)

    async def resume_run(self, run_id: str, config_overrides=None, **kwargs) -> Run:
        return await self._lifecycle.resume_run(run_id, config_overrides, **kwargs)

    async def retry_run(self, run_id: str, **kwargs) -> Run:
        return await self._lifecycle.retry_run(run_id, **kwargs)

    async def cleanup_run(self, run_id: str, **kwargs) -> dict:
        return await self._lifecycle.cleanup_run(run_id, **kwargs)

    async def get_logs(self, run_id: str, **kwargs) -> dict:
        return await self._lifecycle.get_logs(run_id, **kwargs)

    async def append_run_log(self, run: Run, message: str) -> None:
        return await self._lifecycle.append_run_log(run, message)

    # ── CRUD / query ───────────────────────────────────────────────────────

    async def list_runs(self, **kwargs):
        return await self._lifecycle.list_runs(**kwargs)

    async def get_run(self, run_id: str, **kwargs):
        return await self._lifecycle.get_run(run_id, **kwargs)

    async def get_run_audit(self, run_id: str, **kwargs) -> list[dict]:
        return await self._lifecycle.get_run_audit(run_id, **kwargs)

    async def delete_run(self, run_id: str, **kwargs) -> None:
        return await self._lifecycle.delete_run(run_id, **kwargs)

    # ── outputs ────────────────────────────────────────────────────────────

    async def list_outputs(self, run_id: str, **kwargs) -> dict:
        return await self._lifecycle.list_outputs(run_id, **kwargs)

    async def build_output_archive(
        self, run_id: str, **kwargs
    ) -> tuple[bytes, str]:
        return await self._lifecycle.build_output_archive(run_id, **kwargs)
