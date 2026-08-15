from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.models.agent_harness import AgentHarnessEntry, AgentHarnessRun
from app.services.agent_harness.projection import (
    entry_contract,
    pending_interaction_entry_view,
    public_interaction_request,
    public_interaction_response,
    public_model_summary,
    public_run_error,
    run_view,
)
from app.services.agent_harness.tool_projection import (
    project_tool_view,
    public_output_summary,
    public_tool_details,
)
from app.services.agent_harness.tools.bash import BashTool
from app.services.agent_harness.tools.write import WriteTool


SESSION_ID = UUID("10000000-0000-0000-0000-000000000001")
RUN_ID = UUID("20000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


def _run(**changes: object) -> AgentHarnessRun:
    values = {
        "id": RUN_ID,
        "session_id": SESSION_ID,
        "status": "failed",
        "phase": None,
        "revision": 3,
        "started_at": NOW,
        "completed_at": NOW,
        "termination_reason": "runtime_failed",
        "error": {
            "code": "provider_specific_failure",
            "message": "credential sk-private-value was rejected",
        },
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return AgentHarnessRun(**values)


def test_run_projection_exposes_only_stable_public_error() -> None:
    run = _run()

    assert public_run_error(run) == {
        "code": "runtime_failed",
        "message": "The Agent runtime stopped unexpectedly.",
    }
    assert run_view(run).model_dump(mode="json")["error"] == {
        "code": "runtime_failed",
        "message": "The Agent runtime stopped unexpectedly.",
    }


def test_entry_projection_returns_typed_public_history() -> None:
    entry = AgentHarnessEntry(
        id=UUID("30000000-0000-0000-0000-000000000001"),
        session_id=SESSION_ID,
        run_id=RUN_ID,
        sequence=4,
        type="message",
        schema_version=2,
        payload={
            "role": "assistant",
            "parts": [{"id": "text-1", "type": "text", "text": "Finished"}],
        },
        created_at=NOW,
        updated_at=NOW,
    )

    projected = entry_contract(entry)

    assert projected.type == "message"
    assert projected.payload.parts[0].type == "text"
    assert projected.payload.parts[0].text == "Finished"


def test_tool_progress_projection_redacts_arguments_and_builds_safe_details() -> None:
    projected = project_tool_view(
        spec=BashTool.spec,
        call_id="bash-1",
        name="bash",
        arguments={
            "command": (
                "OPENAI_API_KEY=sk-private-value curl "
                "-H 'Authorization: Bearer private-bearer' https://example.test"
            ),
            "cwd": "/Users/private/workspace/project",
            "description": "Check provider status",
        },
        status="running",
        group_id="group-1",
        execution_mode="serial",
    )

    dumped = projected.model_dump(mode="json")

    assert dumped["arguments"] == {}
    assert dumped["summary"] == "Run command: Check provider status"
    assert [detail["kind"] for detail in dumped["public_details"]] == [
        "command",
        "working_directory",
    ]
    assert "OPENAI_API_KEY=[REDACTED]" in dumped["public_details"][0]["value"]
    assert "Authorization: Bearer [REDACTED]" in dumped["public_details"][0]["value"]
    assert "sk-private-value" not in str(dumped)
    assert "private-bearer" not in str(dumped)
    assert "/Users/private" not in str(dumped)


def test_write_projection_never_exposes_written_content() -> None:
    projected = project_tool_view(
        spec=WriteTool.spec,
        call_id="write-1",
        name="write",
        arguments={
            "path": "reports/result.md",
            "content": "private-written-content",
        },
        status="running",
        group_id="group-1",
        execution_mode="serial",
    ).model_dump(mode="json")

    assert projected["arguments"] == {}
    assert "private-written-content" not in str(projected)
    assert projected["public_details"] == [
        {
            "id": "path",
            "kind": "path",
            "label": None,
            "value": "reports/result.md",
            "format": "path",
            "copyable": True,
            "truncated": False,
            "redacted": False,
        },
        {
            "id": "changes",
            "kind": "changes",
            "label": None,
            "value": "23 bytes",
            "format": "text",
            "copyable": False,
            "truncated": False,
            "redacted": False,
        },
    ]


def test_unknown_tools_publish_no_details_by_default() -> None:
    assert public_tool_details("future_tool", {"secret": "must-not-render"}) == []


def test_public_output_summary_removes_secret_values_and_private_file_content() -> None:
    command_summary = public_output_summary(
        {
            "stdout": "token=private-output\ncompleted",
            "stderr": "",
            "exit_code": 0,
        },
        tool_name="bash",
    )
    read_summary = public_output_summary(
        {
            "path": "/Users/private/workspace/data.txt",
            "kind": "text",
            "text": "private-file-content",
            "start_line": 1,
            "end_line": 12,
            "truncated": False,
        },
        tool_name="read",
    )

    assert command_summary is not None
    assert "token=[REDACTED]" in command_summary
    assert "private-output" not in command_summary
    assert read_summary is not None
    assert "private-file-content" not in read_summary
    assert "/Users/private" not in read_summary


def test_entry_projection_removes_private_tool_call_and_result_payloads() -> None:
    call_entry = AgentHarnessEntry(
        id=UUID("30000000-0000-0000-0000-000000000010"),
        session_id=SESSION_ID,
        run_id=RUN_ID,
        sequence=10,
        type="message",
        schema_version=2,
        payload={
            "role": "assistant",
            "parts": [
                {
                    "id": "call-part-1",
                    "type": "tool_call",
                    "call_id": "bash-1",
                    "group_id": "group-1",
                    "execution_mode": "serial",
                    "name": "bash",
                    "display_name": "Bash",
                    "category": "command",
                    "summary": "Run command: token=private-call-summary",
                    "arguments": {
                        "command": "API_TOKEN=private-call-value make test"
                    },
                }
            ],
        },
        created_at=NOW,
        updated_at=NOW,
    )
    result_entry = AgentHarnessEntry(
        id=UUID("30000000-0000-0000-0000-000000000011"),
        session_id=SESSION_ID,
        run_id=RUN_ID,
        sequence=11,
        type="message",
        schema_version=2,
        payload={
            "role": "tool",
            "parts": [
                {
                    "id": "result-part-1",
                    "type": "tool_result",
                    "call_id": "bash-1",
                    "status": "failed",
                    "summary": "token=private-result-summary",
                    "output": {
                        "type": "text",
                        "text": "token=private-result-output",
                    },
                    "error": "API_TOKEN=private-result-error failed",
                }
            ],
        },
        created_at=NOW,
        updated_at=NOW,
    )

    projected = [
        entry_contract(call_entry).model_dump(mode="json"),
        entry_contract(result_entry).model_dump(mode="json"),
    ]

    assert "private-call-summary" not in str(projected)
    assert "private-call-value" not in str(projected)
    assert "private-result-summary" not in str(projected)
    assert "private-result-output" not in str(projected)
    assert "private-result-error" not in str(projected)
    assert projected[0]["payload"]["parts"][0]["arguments"] == {}
    assert projected[1]["payload"]["parts"][0]["output"] is None


def test_pending_interaction_projection_uses_entry_revision() -> None:
    entry = AgentHarnessEntry(
        id=UUID("30000000-0000-0000-0000-000000000002"),
        session_id=SESSION_ID,
        run_id=RUN_ID,
        sequence=5,
        type="interaction_request",
        schema_version=2,
        payload={
            "interaction_id": "approval-1",
            "request": {
                "type": "approval",
                "call_id": "bash-1",
                "tool_name": "bash",
                "summary": "Run command",
                "allowed_responses": ["reject"],
                "risk": {
                    "level": "high",
                    "effects": ["write"],
                    "reasons": ["changes files"],
                    "affected_resources": ["results.txt"],
                },
            },
        },
        created_at=NOW,
        updated_at=NOW,
    )

    projected = pending_interaction_entry_view(entry)

    assert projected.interaction_id == "approval-1"
    assert projected.run_id == RUN_ID
    assert projected.revision == 5
    assert projected.request.type == "approval"
    assert projected.request.allowed_responses == ["reject"]


def test_model_projection_exposes_only_rendering_capabilities() -> None:
    projected = public_model_summary(
        {
            "display_name": "GPT-5.6",
            "target": {
                "provider_kind": "openai",
                "model_name": "gpt-5.6",
                "api_key": "sk-private-value",
            },
            "capabilities": {
                "supports_vision": True,
                "supports_reasoning": True,
                "supports_tools": True,
                "private_transport": "responses",
            },
        }
    )

    assert projected == {
        "provider": "openai",
        "model": "gpt-5.6",
        "display_name": "GPT-5.6",
        "supports_vision": True,
        "supports_reasoning": True,
        "supports_tools": True,
    }
    assert "sk-private-value" not in str(projected)


def test_interaction_request_projection_normalizes_approval_risk() -> None:
    projected = public_interaction_request(
        {
            "kind": "confirmation",
            "call_id": "bash-1",
            "tool_name": "bash",
            "summary": "Run command",
            "input_preview": "rm output.txt",
            "allowed_responses": ["reject"],
            "risk": {
                "level": "high",
                "effects": ["delete"],
                "reasons": ["removes output"],
                "affected_resources": [{"id": "output.txt", "private": True}],
            },
            "private_policy": {"rule": "secret"},
        }
    )

    assert projected == {
        "type": "approval",
        "call_id": "bash-1",
        "tool_name": "bash",
        "summary": "Run command",
        "input_preview": "rm output.txt",
        "allowed_responses": ["reject"],
        "risk": {
            "level": "high",
            "effects": ["delete"],
            "reasons": ["removes output"],
            "affected_resources": ["output.txt"],
        },
    }


def test_interaction_response_projection_drops_private_fields() -> None:
    projected = public_interaction_response(
        {
            "type": "approval",
            "approved": True,
            "actor": "private-user-id",
            "policy_revision": 42,
        }
    )

    assert projected == {"type": "approval", "approved": True}
