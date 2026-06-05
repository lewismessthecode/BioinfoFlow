from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image import ImageStatus
from app.repositories.image_repo import ImageRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.workflow_repo import WorkflowRepository


@dataclass(frozen=True)
class PreflightFinding:
    code: str
    severity: str
    message: str
    evidence: dict

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "evidence": self.evidence,
        }


class RunPreflightService:
    def __init__(self, session: AsyncSession):
        self.project_repo = ProjectRepository(session)
        self.workflow_repo = WorkflowRepository(session)
        self.image_repo = ImageRepository(session)

    async def check(
        self,
        *,
        project_id: str,
        workflow_id: str,
        params: dict | None = None,
        image_id: str | None = None,
    ) -> dict:
        findings: list[PreflightFinding] = []
        params = params or {}
        project = await self.project_repo.get(project_id)
        if project is None:
            findings.append(
                PreflightFinding(
                    code="PROJECT_NOT_FOUND",
                    severity="error",
                    message="Project does not exist.",
                    evidence={"project_id": project_id},
                )
            )

        workflow = await self.workflow_repo.get(workflow_id)
        if workflow is None:
            findings.append(
                PreflightFinding(
                    code="WORKFLOW_NOT_FOUND",
                    severity="error",
                    message="Workflow does not exist.",
                    evidence={"workflow_id": workflow_id},
                )
            )
        else:
            required = _required_fields(workflow.form_spec or {})
            missing = [field for field in required if field not in params or params[field] in (None, "")]
            if missing:
                findings.append(
                    PreflightFinding(
                        code="MISSING_REQUIRED_PARAMS",
                        severity="error",
                        message="Required workflow parameters are missing.",
                        evidence={"missing": missing},
                    )
                )

        if image_id:
            image = await self.image_repo.get(image_id)
            if image is None:
                findings.append(
                    PreflightFinding(
                        code="IMAGE_NOT_FOUND",
                        severity="error",
                        message="Selected image does not exist.",
                        evidence={"image_id": image_id},
                    )
                )
            elif _value(image.status) == ImageStatus.FAILED.value:
                findings.append(
                    PreflightFinding(
                        code="IMAGE_FAILED",
                        severity="error",
                        message="Selected image is marked failed.",
                        evidence={"image_id": image_id, "status": _value(image.status)},
                    )
                )
            elif _value(image.status) != ImageStatus.LOCAL.value:
                findings.append(
                    PreflightFinding(
                        code="IMAGE_NOT_LOCAL",
                        severity="warning",
                        message="Selected image is not available locally yet.",
                        evidence={"image_id": image_id, "status": _value(image.status)},
                    )
                )

        serialized = [finding.as_dict() for finding in findings]
        passed = not any(finding["severity"] == "error" for finding in serialized)
        return {
            "passed": passed,
            "findings": serialized,
            "summary": "preflight passed" if passed else "preflight failed",
        }


def _required_fields(form_spec: dict) -> list[str]:
    fields = form_spec.get("fields")
    if not isinstance(fields, list):
        return []
    required: list[str] = []
    for field in fields:
        if not isinstance(field, dict) or not field.get("required"):
            continue
        name = field.get("name") or field.get("id")
        if name:
            required.append(str(name))
    return required


def _value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
