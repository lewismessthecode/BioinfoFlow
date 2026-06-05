from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import RunStatus
from app.repositories.run_repo import RunRepository
from app.services.run_service import RunService
from app.utils.exceptions import NotFoundError


class RunDiagnosisService:
    def __init__(self, session: AsyncSession):
        self.run_repo = RunRepository(session)
        self.run_service = RunService(session)

    async def diagnose(
        self,
        *,
        run_id: str,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict:
        run = await self.run_repo.get_by_run_id(run_id)
        if run is None:
            raise NotFoundError(f"Run not found: {run_id}")

        evidence: list[dict] = []
        if run.error_message:
            evidence.append({"source": "run.error_message", "text": run.error_message})
        if run.error_json:
            evidence.append({"source": "run.error_json", "data": run.error_json})
        try:
            logs = await self.run_service.get_logs(
                run_id,
                tail=200,
                user_id=user_id,
                workspace_id=workspace_id,
            )
        except FileNotFoundError:
            logs = {"logs": []}
        for entry in logs.get("logs", []):
            message = entry.get("message")
            if message:
                evidence.append({"source": "run.log", "text": message})

        category, suggestion = _classify(evidence)
        return {
            "run_id": run.run_id,
            "status": _value(run.status),
            "failed": _value(run.status) == RunStatus.FAILED.value,
            "error_category": category,
            "root_cause": suggestion["root_cause"],
            "fix_suggestion": suggestion["fix"],
            "failed_task": run.current_task,
            "evidence": evidence[:20],
        }


def _classify(evidence: list[dict]) -> tuple[str, dict]:
    text = " ".join(str(item.get("text") or item.get("data") or "") for item in evidence).lower()
    if any(term in text for term in ("out of memory", "oom", "killed")):
        return (
            "resource_oom",
            {
                "root_cause": "The run likely exceeded memory limits.",
                "fix": "Increase memory for the failed task or reduce batch size.",
            },
        )
    if any(term in text for term in ("no space left", "disk quota", "enospc")):
        return (
            "disk_full",
            {
                "root_cause": "The run likely ran out of disk space.",
                "fix": "Free disk space or move the run to a larger workspace.",
            },
        )
    if any(term in text for term in ("permission denied", "operation not permitted")):
        return (
            "permission_error",
            {
                "root_cause": "The run hit a filesystem or container permission issue.",
                "fix": "Check input/output ownership and mount permissions.",
            },
        )
    if any(term in text for term in ("pull access denied", "manifest unknown", "imagepull")):
        return (
            "image_error",
            {
                "root_cause": "The configured container image is unavailable.",
                "fix": "Verify image registry, tag, credentials, and platform compatibility.",
            },
        )
    if any(term in text for term in ("not found", "no such file", "missing")):
        return (
            "missing_file",
            {
                "root_cause": "The run references a missing file or path.",
                "fix": "Check sample sheet paths, reference files, and workflow parameters.",
            },
        )
    return (
        "unknown",
        {
            "root_cause": "No known failure pattern was detected from current evidence.",
            "fix": "Inspect task logs, trace files, scheduler events, and workflow parameters.",
        },
    )


def _value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
