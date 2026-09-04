from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.services.agent_harness.presentation_mutation_service import (
    AgentPresentationMutationService,
)


class CapturingRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def commit_waiting_interaction(self, session_id: str, **values: Any):
        self.calls.append(("waiting", {"session_id": session_id, **values}))
        return None, None, None

    async def commit_interaction_response(self, session_id: str, **values: Any):
        self.calls.append(("response", {"session_id": session_id, **values}))
        return None

    async def begin_approved_tool_execution(self, session_id: str, **values: Any):
        self.calls.append(("approved", {"session_id": session_id, **values}))
        self.projected = values["progress_projector"](
            {
                "call_id": "bash-1",
                "group_id": "assistant-1",
                "execution_mode": "serial",
                "name": "bash",
                "display_name": "Bash",
                "category": "command",
                "summary": "Run command: OPENAI_API_KEY=sk-private-value",
                "arguments": {"command": "OPENAI_API_KEY=sk-private-value pwd"},
                "status": "interaction_required",
                "revision": 1,
            },
            datetime(2026, 9, 4, tzinfo=timezone.utc),
        )
        return None, None

    async def update_tool_progress(self, run_id: str, **values: Any):
        self.calls.append(("progress", {"run_id": run_id, **values}))
        return values["progress_projector"](
            {
                "call_id": "bash-1",
                "group_id": "assistant-1",
                "execution_mode": "serial",
                "name": "bash",
                "display_name": "Bash",
                "category": "command",
                "summary": "Run command: OPENAI_API_KEY=sk-private-value",
                "arguments": {"command": "OPENAI_API_KEY=sk-private-value pwd"},
                "status": "running",
                "revision": 1,
            },
            datetime(2026, 9, 4, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_mutation_service_projects_interaction_payloads_before_persistence() -> (
    None
):
    repository = CapturingRepository()
    service = AgentPresentationMutationService(repository)  # type: ignore[arg-type]

    await service.commit_waiting_interaction(
        "session-1",
        run_id="run-1",
        request_payload={
            "interaction_id": "approval-1",
            "request": {
                "kind": "confirmation",
                "call_id": "bash-1",
                "tool_name": "bash",
                "summary": "Run OPENAI_API_KEY=sk-private-value",
                "risk": {"level": "high", "affected_resources": ["/private/a"]},
                "target": {"environment_id": "local", "display_name": "Local"},
            },
        },
        checkpoint={"phase": "interaction"},
        tool_progress=[],
    )

    _, values = repository.calls[0]
    request = values["request_payload"]
    assert request == {
        "interaction_id": "approval-1",
        "request": {
            "type": "approval",
            "call_id": "bash-1",
            "tool_name": "bash",
            "summary": "Run OPENAI_API_KEY=sk-private-value",
            "input_preview": None,
            "allowed_responses": ["approve", "reject"],
            "target": {
                "environment_id": "local",
                "display_name": "Local",
                "kind": "local",
            },
            "risk": {
                "level": "high",
                "effects": [],
                "reasons": [],
                "reason_codes": [],
                "justification": None,
                "affected_resources": ["/private/a"],
            },
        },
    }


@pytest.mark.asyncio
async def test_mutation_service_redacts_progress_before_the_repository_writes_it() -> (
    None
):
    repository = CapturingRepository()
    service = AgentPresentationMutationService(repository)  # type: ignore[arg-type]

    progress = await service.update_tool_progress(
        "run-1",
        call_id="bash-1",
        name="bash",
        status="completed",
        output_summary="OPENAI_API_KEY=sk-private-value completed",
    )

    assert progress.arguments == {}
    assert "sk-private-value" not in str(progress.model_dump(mode="json"))
    assert progress.status == "completed"
    assert repository.calls[0][1]["progress_projector"]


@pytest.mark.asyncio
async def test_mutation_service_projects_response_and_started_progress_together() -> (
    None
):
    repository = CapturingRepository()
    service = AgentPresentationMutationService(repository)  # type: ignore[arg-type]

    await service.begin_approved_tool_execution(
        "session-1",
        run_id="run-1",
        interaction_id="approval-1",
        response={"type": "approval", "approved": True, "private": "omit"},
        call={"call_id": "bash-1", "name": "bash"},
        replay_policy="never",
    )

    _, values = repository.calls[0]
    assert values["response"] == {"type": "approval", "approved": True}
    assert repository.projected["arguments"] == {}
    assert "sk-private-value" not in str(repository.projected)
