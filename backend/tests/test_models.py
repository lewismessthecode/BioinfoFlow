from __future__ import annotations

from app.models import (
    AgentAction,
    AgentArtifact,
    AgentEvent,
    AgentMemory,
    AgentSession,
    AgentTurn,
    DockerImage,
    Project,
    Run,
    RunStatus,
    Workflow,
    WorkflowEngine,
    WorkflowSource,
)


def test_model_imports():
    assert Project.__tablename__ == "projects"
    assert Workflow.__tablename__ == "workflows"
    assert Run.__tablename__ == "runs"
    assert DockerImage.__tablename__ == "docker_images"
    assert AgentSession.__tablename__ == "agent_sessions"
    assert AgentTurn.__tablename__ == "agent_turns"
    assert AgentEvent.__tablename__ == "agent_events"
    assert AgentAction.__tablename__ == "agent_actions"
    assert AgentArtifact.__tablename__ == "agent_artifacts"
    assert AgentMemory.__tablename__ == "agent_memories"


def test_run_status_includes_pending():
    assert RunStatus.PENDING.value == "pending"
    assert RunStatus.COMPLETED.value == "completed"


def test_workflow_enums():
    assert WorkflowSource.NFCORE.value == "nf-core"
    assert WorkflowEngine.NEXTFLOW.value == "nextflow"
