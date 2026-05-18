from __future__ import annotations

import secrets

from app.models.batch import BatchStatus
from app.models.run import RunStatus
from app.repositories.batch_repo import BatchRepository, BatchRunRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.run_repo import RunRepository
from app.schemas.run import RunCreate
from app.services.run_compiler import CompileError, RunCompiler, WorkflowNotEnabledError
from app.services.run_service import RunService
from app.utils.project_access import can_access_project

_BATCH_SUBMISSION_ERRORS = {
    "COMPILE_ERROR": "Run input validation failed.",
    "WORKFLOW_NOT_ENABLED": "Workflow is not enabled for this project.",
    "PROJECT_FILE_NOT_FOUND": "Required project file was not found.",
    "PROJECT_FILE_FORBIDDEN": "Required project file is not accessible.",
    "INVALID_RUN_REQUEST": "Run request is invalid.",
}


class BatchService:
    TERMINAL_BATCH_STATUSES = {
        BatchStatus.COMPLETED.value,
        BatchStatus.PARTIAL.value,
        BatchStatus.FAILED.value,
        BatchStatus.CANCELLED.value,
    }

    def __init__(
        self,
        session,
        *,
        compiler: RunCompiler | None = None,
        run_service: RunService | None = None,
    ) -> None:
        self.session = session
        self.repo = BatchRepository(session)
        self.batch_run_repo = BatchRunRepository(session)
        self.project_repo = ProjectRepository(session)
        self.run_repo = RunRepository(session)
        self._compiler = compiler or RunCompiler(session)
        self._run_service = run_service or RunService(session)

    async def create_batch(
        self,
        *,
        project_id: str,
        runs: list[RunCreate],
        description: str | None = None,
        priority: str = "normal",
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict:
        project = await self.project_repo.get(project_id)
        if project is None or not can_access_project(
            project,
            user_id=user_id,
            workspace_id=workspace_id,
        ):
            raise FileNotFoundError("project not found")

        batch = await self.repo.create(
            batch_id=self._generate_batch_id(),
            project_id=project_id,
            status=BatchStatus.PENDING.value,
            total_runs=len(runs),
            completed_runs=0,
            failed_runs=0,
            description=description,
        )
        queued = 0
        failed = 0
        run_results: list[dict] = []

        for run_payload in runs:
            try:
                run = await self._compiler.create_run(
                    run_payload,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    priority=priority,
                )
                await self.batch_run_repo.create(batch_id=batch.id, run_id=run.id)
                queued += 1
                run_results.append({"run_id": run.run_id, "status": run.status})
            except CompileError:
                failed += 1
                run_results.append(
                    _failed_submission_result(
                        "COMPILE_ERROR",
                        RunStatus.FAILED.value,
                    )
                )
            except WorkflowNotEnabledError:
                failed += 1
                run_results.append(
                    _failed_submission_result(
                        "WORKFLOW_NOT_ENABLED",
                        RunStatus.FAILED.value,
                    )
                )
            except FileNotFoundError:
                failed += 1
                run_results.append(
                    _failed_submission_result(
                        "PROJECT_FILE_NOT_FOUND",
                        RunStatus.FAILED.value,
                    )
                )
            except PermissionError:
                failed += 1
                run_results.append(
                    _failed_submission_result(
                        "PROJECT_FILE_FORBIDDEN",
                        RunStatus.FAILED.value,
                    )
                )
            except ValueError:
                failed += 1
                run_results.append(
                    _failed_submission_result(
                        "INVALID_RUN_REQUEST",
                        RunStatus.FAILED.value,
                    )
                )

        batch_summary = await self.update_batch_status(batch.batch_id)
        return {
            "batch_id": batch.batch_id,
            "total": len(runs),
            "queued": queued,
            "failed": failed,
            "status": batch_summary["status"],
            "runs": run_results,
        }

    async def get_batch(
        self,
        batch_id: str,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict | None:
        batch = await self.repo.get_by_batch_id(batch_id)
        if batch is None:
            return None
        await self._require_batch_access(
            batch.project_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        return await self._sync_and_serialize(batch)

    async def cancel_batch(
        self,
        batch_id: str,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict:
        batch = await self.repo.get_by_batch_id(batch_id)
        if batch is None:
            raise FileNotFoundError("batch not found")
        await self._require_batch_access(
            batch.project_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )

        batch_runs = await self.repo.list_batch_runs(batch.id)
        cancelled_runs = 0
        for link in batch_runs:
            run = await self.run_repo.get(link.run_id)
            if run is None:
                continue
            if run.status not in {
                RunStatus.QUEUED.value,
                RunStatus.RUNNING.value,
            }:
                continue
            await self._run_service.cancel_run(run.run_id)
            cancelled_runs += 1

        summary = await self.update_batch_status(batch_id)
        summary["cancelled_runs"] = cancelled_runs
        return summary

    async def update_batch_status(self, batch_id: str) -> dict:
        batch = await self.repo.get_by_batch_id(batch_id)
        if batch is None:
            raise FileNotFoundError("batch not found")
        return await self._sync_and_serialize(batch)

    async def find_batch_for_run(self, run_id: str):
        return await self.repo.get_for_run(run_id)

    async def _sync_and_serialize(self, batch) -> dict:
        linked_runs = await self._linked_runs(batch.id)
        submission_failures = max(batch.total_runs - len(linked_runs), 0)
        completed = sum(
            1 for run in linked_runs if run.status == RunStatus.COMPLETED.value
        )
        failed = (
            sum(1 for run in linked_runs if run.status == RunStatus.FAILED.value)
            + submission_failures
        )
        cancelled = sum(
            1 for run in linked_runs if run.status == RunStatus.CANCELLED.value
        )
        active = sum(
            1
            for run in linked_runs
            if run.status
            in {
                RunStatus.PENDING.value,
                RunStatus.QUEUED.value,
                RunStatus.RUNNING.value,
            }
        )
        status = self._derive_status(
            total=batch.total_runs,
            completed=completed,
            failed=failed,
            cancelled=cancelled,
            active=active,
        )
        batch = await self.repo.update(
            batch,
            status=status,
            completed_runs=completed,
            failed_runs=failed,
        )
        return {
            "batch_id": batch.batch_id,
            "project_id": str(batch.project_id),
            "status": batch.status,
            "total_runs": batch.total_runs,
            "completed_runs": batch.completed_runs,
            "failed_runs": batch.failed_runs,
            "description": batch.description,
            "runs": [
                {
                    "run_id": run.run_id,
                    "status": run.status,
                }
                for run in linked_runs
            ],
        }

    async def _linked_runs(self, batch_id: str) -> list:
        links = await self.repo.list_batch_runs(batch_id)
        runs = []
        for link in links:
            run = await self.run_repo.get(link.run_id)
            if run is not None:
                runs.append(run)
        return runs

    def _derive_status(
        self,
        *,
        total: int,
        completed: int,
        failed: int,
        cancelled: int,
        active: int,
    ) -> str:
        if total <= 0:
            return BatchStatus.PENDING.value
        if active > 0:
            return BatchStatus.RUNNING.value
        if cancelled == total and completed == 0 and failed == 0:
            return BatchStatus.CANCELLED.value
        if completed == total:
            return BatchStatus.COMPLETED.value
        if failed == total:
            return BatchStatus.FAILED.value
        if completed + failed + cancelled == total:
            return BatchStatus.PARTIAL.value
        return BatchStatus.RUNNING.value

    def _generate_batch_id(self) -> str:
        return f"batch_{secrets.token_hex(6)}"

    async def _require_batch_access(
        self,
        project_id: str,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> None:
        project = await self.project_repo.get(project_id)
        if project is None or not can_access_project(
            project,
            user_id=user_id,
            workspace_id=workspace_id,
        ):
            raise FileNotFoundError("project not found")


def _failed_submission_result(code: str, status: str) -> dict[str, str]:
    return {
        "status": status,
        "error": _BATCH_SUBMISSION_ERRORS[code],
        "error_code": code,
    }
