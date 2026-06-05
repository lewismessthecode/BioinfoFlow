from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.workflow_repo import WorkflowRepository
from app.utils.exceptions import NotFoundError


class WorkflowCardService:
    def __init__(self, session: AsyncSession):
        self.workflow_repo = WorkflowRepository(session)

    async def build_card(self, workflow_id: str) -> dict:
        workflow = await self.workflow_repo.get(workflow_id)
        if workflow is None:
            raise NotFoundError(f"Workflow not found: {workflow_id}")
        form_spec = workflow.form_spec or {}
        schema_json = workflow.schema_json or {}
        fields = form_spec.get("fields") if isinstance(form_spec, dict) else []
        required_inputs = [
            field.get("name") or field.get("id")
            for field in fields or []
            if isinstance(field, dict) and field.get("required")
        ]
        optional_inputs = [
            field.get("name") or field.get("id")
            for field in fields or []
            if isinstance(field, dict) and not field.get("required")
        ]
        outputs = _extract_outputs(schema_json)
        return {
            "workflow_id": str(workflow.id),
            "name": workflow.name,
            "description": workflow.description,
            "engine": _value(workflow.engine),
            "source": _value(workflow.source),
            "version": workflow.version,
            "source_ref": workflow.source_ref,
            "entrypoint_relpath": workflow.entrypoint_relpath,
            "bundle_kind": workflow.bundle_kind,
            "required_inputs": [item for item in required_inputs if item],
            "optional_inputs": [item for item in optional_inputs if item],
            "outputs": outputs,
            "has_form_spec": bool(form_spec),
            "has_schema": bool(schema_json),
            "suitability": _suitability(workflow.name, workflow.description),
        }


def _extract_outputs(schema_json: dict) -> list[str]:
    outputs = schema_json.get("outputs") if isinstance(schema_json, dict) else None
    if isinstance(outputs, list):
        return [str(item.get("name") if isinstance(item, dict) else item) for item in outputs]
    if isinstance(outputs, dict):
        return [str(key) for key in outputs.keys()]
    return []


def _suitability(name: str, description: str | None) -> list[str]:
    text = f"{name} {description or ''}".lower()
    hints: list[str] = []
    if "rna" in text:
        hints.append("rna_seq")
    if "single" in text or "scrna" in text:
        hints.append("single_cell")
    if "variant" in text or "gatk" in text or "germline" in text:
        hints.append("variant_calling")
    if "qc" in text or "fastqc" in text or "multiqc" in text:
        hints.append("quality_control")
    return hints or ["general_workflow"]


def _value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
