from __future__ import annotations

from typing import Any

from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.bioinformatics import (
    ImageCardService,
    RunDiagnosisService,
    RunPreflightService,
    WorkflowCardService,
)
from app.services.bioinformatics.results import ResultInterpretationService


class BuildWorkflowCardTool:
    spec = AgentToolSpec(
        name="bio.workflow_card",
        description="Generate a structured workflow card from a registered workflow.",
        input_schema={
            "type": "object",
            "properties": {"workflow_id": {"type": "string"}},
            "required": ["workflow_id"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level="read",
        read_scope=["workflows"],
        audit="Build workflow card.",
        artifact_policy={"type": "workflow_card"},
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        return await WorkflowCardService(context.db).build_card(str(input["workflow_id"]))


class BuildImageCardTool:
    spec = AgentToolSpec(
        name="bio.image_card",
        description="Generate a structured image card from registered image metadata.",
        input_schema={
            "type": "object",
            "properties": {"image_id": {"type": "string"}},
            "required": ["image_id"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level="read",
        read_scope=["images"],
        audit="Build image card.",
        artifact_policy={"type": "image_card"},
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        return await ImageCardService(context.db).build_card(str(input["image_id"]))


class RunPreflightTool:
    spec = AgentToolSpec(
        name="bio.run_preflight",
        description="Run deterministic checks before submitting a workflow run.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "workflow_id": {"type": "string"},
                "params": {"type": "object"},
                "image_id": {"type": "string"},
            },
            "required": ["project_id", "workflow_id"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level="read",
        read_scope=["projects", "workflows", "images"],
        audit="Run preflight checks.",
        artifact_policy={"type": "preflight_report"},
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        return await RunPreflightService(context.db).check(
            project_id=str(input["project_id"]),
            workflow_id=str(input["workflow_id"]),
            params=input.get("params") or {},
            image_id=input.get("image_id"),
        )


class DiagnoseRunTool:
    spec = AgentToolSpec(
        name="bio.run_diagnosis",
        description="Diagnose a failed or suspicious workflow run from current evidence.",
        input_schema={
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level="read",
        read_scope=["runs", "logs"],
        audit="Diagnose workflow run.",
        artifact_policy={"type": "diagnosis"},
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        return await RunDiagnosisService(context.db).diagnose(
            run_id=str(input["run_id"]),
            user_id=context.user_id,
            workspace_id=context.workspace_id,
        )


class InterpretResultsTool:
    spec = AgentToolSpec(
        name="bio.result_interpretation",
        description="Summarize structured result metrics for a target role.",
        input_schema={
            "type": "object",
            "properties": {
                "metrics": {"type": "object"},
                "role": {"type": "string"},
            },
            "required": ["metrics"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level="read",
        read_scope=["results"],
        audit="Interpret structured result metrics.",
        artifact_policy={"type": "result_summary"},
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del context
        return ResultInterpretationService().summarize(
            metrics=input["metrics"],
            role=input.get("role") or "bioinformatician",
        )
