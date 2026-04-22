from __future__ import annotations

from app.models import (
    DockerImage,
    Message,
    MessageRole,
    MessageType,
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
    assert Message.__tablename__ == "messages"


def test_run_status_includes_pending():
    assert RunStatus.PENDING.value == "pending"
    assert RunStatus.COMPLETED.value == "completed"


def test_workflow_enums():
    assert WorkflowSource.NFCORE.value == "nf-core"
    assert WorkflowEngine.NEXTFLOW.value == "nextflow"


def test_message_enums():
    assert MessageRole.USER.value == "user"
    assert MessageType.TEXT.value == "text"


def test_thinking_content_message_type():
    """THINKING_CONTENT enum member exists and maps to correct value."""
    assert MessageType.THINKING_CONTENT.value == "thinking_content"
    # Confirm it round-trips from string
    assert MessageType("thinking_content") is MessageType.THINKING_CONTENT


def test_thinking_content_in_event_map():
    """THINKING_CONTENT maps to agent.thinking_content SSE event."""
    from app.services.agent.agent_service import EVENT_MAP

    assert EVENT_MAP["thinking_content"] == "agent.thinking_content"
