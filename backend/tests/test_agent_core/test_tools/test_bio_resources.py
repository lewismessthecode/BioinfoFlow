from __future__ import annotations

import pytest

from app.models.image import DockerImage, ImageStatus
from app.models.project import Project
from app.models.run import Run, RunStatus
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.models.workspace import Workspace
from app.services.agent_core import AgentCoreService
from app.services.agent_core.tools import (
    AgentToolContext,
    AgentToolDispatcher,
    build_default_tool_registry,
)
from app.workspace import DEFAULT_WORKSPACE_ID


async def _bio_context(db_session) -> tuple[AgentToolDispatcher, AgentToolContext, dict]:
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    project = Project(
        name="Bio Project",
        description="Bioinformatics tools",
        user_id="dev",
        created_by_user_id="dev",
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    workflow = Workflow(
        name="germline-wgs",
        description="GATK germline variant calling workflow",
        source=WorkflowSource.LOCAL.value,
        engine=WorkflowEngine.NEXTFLOW.value,
        source_ref="local",
        version="1.0.0",
        schema_json={"outputs": [{"name": "vcf"}]},
        form_spec={
            "fields": [
                {"name": "fastq_1", "required": True},
                {"name": "fastq_2", "required": True},
                {"name": "known_sites", "required": False},
            ]
        },
    )
    image = DockerImage(
        name="broadinstitute/gatk",
        tag="latest",
        full_name="broadinstitute/gatk:latest",
        registry="docker.io",
        status=ImageStatus.LOCAL.value,
        entrypoint=["gatk"],
        env=["GATK_VERSION=4.5.0"],
    )
    db_session.add_all([workspace, project, workflow, image])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)
    await db_session.refresh(image)

    run = Run(
        run_id="run-bio-1",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.FAILED.value,
        config={},
        current_task="HaplotypeCaller",
        error_message="Task was killed: out of memory",
        samples_count=1,
    )
    db_session.add(run)
    await db_session.commit()

    core = AgentCoreService(db_session)
    session = await core.create_session(
        project_id=str(project.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        title="Bio tools",
    )
    turn = await core.create_turn(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Check bio resources.",
    )
    context = AgentToolContext(
        db=db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        session_id=str(session.id),
        turn_id=str(turn.id),
    )
    return (
        AgentToolDispatcher(db_session, build_default_tool_registry()),
        context,
        {"project": project, "workflow": workflow, "image": image, "run": run},
    )


@pytest.mark.asyncio
async def test_workflow_card_tool_generates_structured_card(db_session):
    dispatcher, context, resources = await _bio_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="bio.workflow_card",
        input={"workflow_id": str(resources["workflow"].id)},
        context=context,
    )

    assert result.status == "completed"
    assert result.result["required_inputs"] == ["fastq_1", "fastq_2"]
    assert "variant_calling" in result.result["suitability"]
    assert result.result["outputs"] == ["vcf"]


@pytest.mark.asyncio
async def test_image_card_tool_generates_software_and_risk_hints(db_session):
    dispatcher, context, resources = await _bio_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="bio.image_card",
        input={"image_id": str(resources["image"].id)},
        context=context,
    )

    assert result.status == "completed"
    assert result.result["validation_state"] == "available"
    assert result.result["risk_level"] == "low"
    assert result.result["software_hints"][0]["name"] == "gatk"


@pytest.mark.asyncio
async def test_run_preflight_tool_reports_missing_required_params(db_session):
    dispatcher, context, resources = await _bio_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="bio.run_preflight",
        input={
            "project_id": str(resources["project"].id),
            "workflow_id": str(resources["workflow"].id),
            "params": {"fastq_1": "sample_R1.fastq.gz"},
            "image_id": str(resources["image"].id),
        },
        context=context,
    )

    assert result.status == "completed"
    assert result.result["passed"] is False
    assert result.result["findings"][0]["code"] == "MISSING_REQUIRED_PARAMS"
    assert result.result["findings"][0]["evidence"]["missing"] == ["fastq_2"]


@pytest.mark.asyncio
async def test_run_diagnosis_tool_classifies_oom_failure(db_session):
    dispatcher, context, _resources = await _bio_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="bio.run_diagnosis",
        input={"run_id": "run-bio-1"},
        context=context,
    )

    assert result.status == "completed"
    assert result.result["error_category"] == "resource_oom"
    assert result.result["failed_task"] == "HaplotypeCaller"


@pytest.mark.asyncio
async def test_result_interpretation_tool_produces_role_specific_summary(db_session):
    dispatcher, context, _resources = await _bio_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="bio.result_interpretation",
        input={
            "role": "project_manager",
            "metrics": {"mapping_rate": 0.65, "duplication_rate": 0.2},
        },
        context=context,
    )

    assert result.status == "completed"
    assert result.result["ready_for_review"] is False
    assert "1 blocking issue" in result.result["summary"]
