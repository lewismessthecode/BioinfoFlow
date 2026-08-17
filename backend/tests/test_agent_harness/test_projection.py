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
    public_tool_progress_view,
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


def test_run_projection_exposes_immutable_public_execution_config() -> None:
    run = _run(
        model_snapshot={
            "display_name": "GPT Run Snapshot",
            "target": {
                "provider_kind": "openai",
                "model_name": "gpt-run",
                "api_key": "must-not-leak",
            },
            "capabilities": {"supports_reasoning": True, "private": "hidden"},
        },
        turn_execution_config={
            "settings_revision": 7,
            "model": {
                "display_name": "GPT Run Snapshot",
                "target": {
                    "provider_kind": "openai",
                    "model_name": "gpt-run",
                    "api_key": "must-not-leak",
                },
                "capabilities": {"supports_reasoning": True},
            },
            "permission_mode": "ask_changes",
            "workspace_access": "read_only",
            "environment_scope": {
                "mode": "manual",
                "environment_ids": ["local", "ssh:gpu"],
            },
            "environment_targets": {
                "ssh:gpu": {
                    "display_name": "GPU",
                    "host": "gpu.internal",
                    "port": 22,
                    "username": "runner",
                    "credential_revision": "private-revision",
                }
            },
        },
    )

    projected = run_view(run).model_dump(mode="json")["execution_config"]

    assert projected == {
        "settings_revision": 7,
        "model": {
            "provider": "openai",
            "model": "gpt-run",
            "display_name": "GPT Run Snapshot",
            "supports_vision": False,
            "supports_reasoning": True,
            "supports_tools": False,
        },
        "permission_mode": "ask_changes",
        "workspace_access": "read_only",
        "environment_scope": {
            "mode": "manual",
            "environment_ids": ["local", "ssh:gpu"],
        },
        "environment_targets": [
            {
                "environment_id": "local",
                "display_name": "Local",
                "kind": "local",
                "host": None,
            },
            {
                "environment_id": "ssh:gpu",
                "display_name": "GPU",
                "kind": "ssh",
                "host": "gpu.internal",
            },
        ],
    }
    assert "must-not-leak" not in str(projected)
    assert "private-revision" not in str(projected)


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


def test_notice_projection_exposes_stable_code_params_and_safe_fallback() -> None:
    entry = AgentHarnessEntry(
        id=UUID("30000000-0000-0000-0000-000000000013"),
        session_id=SESSION_ID,
        run_id=RUN_ID,
        sequence=13,
        type="notice",
        schema_version=2,
        payload={
            "code": "run_timeout_exceeded",
            "message": "Agent Run exceeded its 300-second wall-clock budget.",
            "details": {"limit_seconds": 300, "private": {"token": "secret"}},
        },
        created_at=NOW,
        updated_at=NOW,
    )

    projected = entry_contract(entry).model_dump(mode="json")["payload"]

    assert projected == {
        "code": "run_timeout_exceeded",
        "message": "Agent Run exceeded its 300-second wall-clock budget.",
        "params": {"limit_seconds": 300},
        "details": None,
    }
    assert "secret" not in str(projected)


def test_entry_projection_upgrades_legacy_and_provider_reasoning_to_traces() -> None:
    entry = AgentHarnessEntry(
        id=UUID("30000000-0000-0000-0000-000000000002"),
        session_id=SESSION_ID,
        run_id=RUN_ID,
        sequence=5,
        type="message",
        schema_version=2,
        payload={
            "role": "assistant",
            "parts": [
                {
                    "id": "legacy-reasoning",
                    "type": "reasoning_summary",
                    "text": "Legacy summary",
                },
                {
                    "id": "provider-reasoning",
                    "type": "thinking",
                    "thinking": "Provider trace",
                    "provider": "deepseek",
                    "model": "deepseek-reasoner",
                    "truncated": True,
                    "started_at": NOW,
                    "completed_at": NOW,
                    "signature": "private-signature",
                },
            ],
        },
        created_at=NOW,
        updated_at=NOW,
    )

    dumped = entry_contract(entry).model_dump(mode="json")

    assert dumped["payload"]["parts"] == [
        {
            "id": "legacy-reasoning",
            "type": "reasoning_trace",
            "text": "Legacy summary",
            "provider": "unknown",
            "model": "unknown",
            "source": "reasoning_summary",
            "truncated": False,
            "started_at": None,
            "completed_at": None,
        },
        {
            "id": "provider-reasoning",
            "type": "reasoning_trace",
            "text": "Provider trace",
            "provider": "deepseek",
            "model": "deepseek-reasoner",
            "source": "thinking",
            "truncated": True,
            "started_at": "2026-08-15T00:00:00Z",
            "completed_at": "2026-08-15T00:00:00Z",
        },
    ]
    assert "private-signature" not in str(dumped)


def test_entry_projection_safely_falls_back_for_unknown_parts_and_entries() -> None:
    unknown_part_entry = AgentHarnessEntry(
        id=UUID("30000000-0000-0000-0000-000000000003"),
        session_id=SESSION_ID,
        run_id=RUN_ID,
        sequence=6,
        type="message",
        schema_version=3,
        payload={
            "role": "assistant",
            "parts": [
                {
                    "id": "future-part",
                    "type": "provider_future_part",
                    "raw": {"secret": "must-not-publish"},
                }
            ],
        },
        created_at=NOW,
        updated_at=NOW,
    )
    unknown_entry = AgentHarnessEntry(
        id=UUID("30000000-0000-0000-0000-000000000004"),
        session_id=SESSION_ID,
        run_id=RUN_ID,
        sequence=7,
        type="future_activity",
        schema_version=9,
        payload={"private": "must-not-publish"},
        created_at=NOW,
        updated_at=NOW,
    )

    part_dump = entry_contract(unknown_part_entry).model_dump(mode="json")
    entry_dump = entry_contract(unknown_entry).model_dump(mode="json")

    assert part_dump["payload"]["parts"] == [
        {
            "id": "future-part",
            "type": "unknown",
            "original_type": "provider_future_part",
            "display_text": "Unsupported conversation content",
        }
    ]
    assert entry_dump["type"] == "unknown"
    assert entry_dump["payload"] == {
        "original_type": "future_activity",
        "display_text": "Unsupported conversation activity",
    }
    assert "must-not-publish" not in str([part_dump, entry_dump])


def test_reasoning_projection_never_publishes_opaque_provider_state() -> None:
    entry = AgentHarnessEntry(
        id=UUID("30000000-0000-0000-0000-000000000005"),
        session_id=SESSION_ID,
        run_id=RUN_ID,
        sequence=8,
        type="message",
        schema_version=3,
        payload={
            "role": "assistant",
            "parts": [
                {
                    "id": "opaque-reasoning",
                    "type": "reasoning",
                    "encrypted_content": "opaque-private-state",
                    "signature": "private-signature",
                }
            ],
        },
        created_at=NOW,
        updated_at=NOW,
    )

    dumped = entry_contract(entry).model_dump(mode="json")

    assert dumped["payload"]["parts"][0]["type"] == "unknown"
    assert "opaque-private-state" not in str(dumped)
    assert "private-signature" not in str(dumped)


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
    assert dumped["summary"] == "Bash: Check provider status"
    assert [detail["kind"] for detail in dumped["public_details"]] == [
        "command",
        "working_directory",
    ]
    assert "OPENAI_API_KEY=[REDACTED]" in dumped["public_details"][0]["value"]
    assert "Authorization: Bearer [REDACTED]" in dumped["public_details"][0]["value"]
    assert "sk-private-value" not in str(dumped)
    assert "private-bearer" not in str(dumped)
    assert "/Users/private" not in str(dumped)


def test_bash_projection_hides_absolute_paths_inside_commands() -> None:
    details = public_tool_details(
        "bash",
        {
            "command": (
                "OPENAI_API_KEY=sk-private-value "
                "cat /Users/private/workspace/sample-sheet.csv"
            )
        },
    )

    assert len(details) == 1
    assert details[0].value == (
        "OPENAI_API_KEY=[REDACTED] cat …/workspace/sample-sheet.csv"
    )
    assert details[0].redacted is True
    assert "/Users/private" not in details[0].value


def test_bash_projection_redacts_quoted_headers_file_urls_and_known_secrets() -> None:
    details = public_tool_details(
        "bash",
        {
            "command": (
                "AWS_ACCESS_KEY_ID='AKIAIOSFODNN7EXAMPLE' "
                'curl -H "X-API-Key: sk-private-value" '
                "file:///Users/private/workspace/input.txt "
                "https://example.test?token=ghp_privatevalue1234567890"
            )
        },
    )

    assert len(details) == 1
    value = details[0].value
    assert "AWS_ACCESS_KEY_ID=[REDACTED]" in value
    assert "X-API-Key: [REDACTED]" in value
    assert "file://…/workspace/input.txt" in value
    assert "token=[REDACTED]" in value
    assert "AKIAIOSFODNN7EXAMPLE" not in value
    assert "sk-private-value" not in value
    assert "ghp_privatevalue" not in value
    assert "/Users/private" not in value
    assert details[0].copyable is False
    assert details[0].redacted is True


def test_public_tool_progress_rebuilds_legacy_payload_through_safe_projection() -> None:
    projected = public_tool_progress_view(
        {
            "call_id": "bash-legacy",
            "group_id": "group-1",
            "execution_mode": "serial",
            "name": "bash",
            "display_name": "Bash",
            "category": "command",
            "summary": "Run command: AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE",
            "arguments": {
                "command": "X-API-Key: sk-private-value curl file:///Users/private/a.txt"
            },
            "status": "completed",
            "revision": 8,
            "output_summary": "SENTINEL_LEGACY_SUMMARY",
            "error": None,
            "public_details": [
                {
                    "id": "command",
                    "kind": "command",
                    "value": "old persisted secret sk-private-value",
                    "format": "code",
                    "copyable": True,
                },
                {
                    "id": "output",
                    "kind": "output",
                    "value": "SENTINEL_LEGACY_DETAIL",
                    "format": "code",
                    "copyable": True,
                },
            ],
            "private_future_field": "must-not-publish",
        }
    ).model_dump(mode="json")

    assert projected["arguments"] == {}
    assert projected["summary"] == "Run command: AWS_ACCESS_KEY_ID=[REDACTED]"
    assert projected["output_summary"] is None
    assert "private_future_field" not in projected
    assert "sk-private-value" not in str(projected)
    assert "SENTINEL_LEGACY_SUMMARY" not in str(projected)
    assert "SENTINEL_LEGACY_DETAIL" not in str(projected)
    assert "/Users/private" not in str(projected)
    assert [detail["kind"] for detail in projected["public_details"]] == ["command"]


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
            "value": "bytes=23",
            "format": "text",
            "copyable": False,
            "truncated": False,
            "redacted": False,
        },
    ]


def test_unknown_tools_publish_no_details_by_default() -> None:
    assert public_tool_details("future_tool", {"secret": "must-not-render"}) == []


def test_public_output_summary_never_exposes_bash_output_or_private_file_content() -> (
    None
):
    command_summary = public_output_summary(
        {
            "stdout": (
                "SENTINEL_7ca1d8f4e962\n"
                'token=private-output\n{"api_key":"private-json-output"}\ncompleted'
            ),
            "stderr": "",
            "exit_code": 0,
            "truncated": True,
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

    assert command_summary == "exit_code=0 · truncated=true"
    assert "SENTINEL_7ca1d8f4e962" not in command_summary
    assert "private-output" not in command_summary
    assert "private-json-output" not in command_summary
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
                    "arguments": {"command": "API_TOKEN=private-call-value make test"},
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


def test_entry_projection_preserves_sanitized_success_result_summary_and_details() -> (
    None
):
    entry = AgentHarnessEntry(
        id=UUID("30000000-0000-0000-0000-000000000012"),
        session_id=SESSION_ID,
        run_id=RUN_ID,
        sequence=12,
        type="message",
        schema_version=2,
        payload={
            "role": "tool",
            "parts": [
                {
                    "id": "result-part-1",
                    "type": "tool_result",
                    "call_id": "bash-1",
                    "status": "completed",
                    "summary": "token=private-result-summary\npassed",
                    "output": {"type": "text", "text": "private raw output"},
                    "public_details": [
                        {
                            "id": "output",
                            "kind": "output",
                            "value": "X-API-Key: private-result-detail\npassed",
                            "format": "code",
                            "copyable": True,
                        }
                    ],
                }
            ],
        },
        created_at=NOW,
        updated_at=NOW,
    )

    projected = entry_contract(entry).model_dump(mode="json")["payload"]["parts"][0]

    assert projected["summary"] == "token=[REDACTED]\npassed"
    assert projected["output"] is None
    assert projected["public_details"][0]["value"] == ("X-API-Key: [REDACTED]\npassed")
    assert projected["public_details"][0]["copyable"] is False
    assert "private-result" not in str(projected)


def test_content_parts_projection_rebuilds_each_reference_and_sanitizes_paths() -> None:
    entry = AgentHarnessEntry(
        id=UUID("30000000-0000-0000-0000-000000000013"),
        session_id=SESSION_ID,
        run_id=RUN_ID,
        sequence=13,
        type="message",
        schema_version=2,
        payload={
            "role": "tool",
            "parts": [
                {
                    "id": "result-part-1",
                    "type": "tool_result",
                    "call_id": "read-1",
                    "status": "completed",
                    "output": {
                        "type": "content_parts",
                        "private_output": "must-not-publish",
                        "parts": [
                            {
                                "id": "file-1",
                                "type": "file_ref",
                                "label": "/Users/private/workspace/report.txt",
                                "path": "/Users/private/workspace/report.txt",
                                "project_id": str(SESSION_ID),
                                "private_field": "must-not-publish",
                            },
                            {
                                "id": "run-1",
                                "type": "run_ref",
                                "run_id": "run-123",
                                "label": "Run 123",
                                "private_field": "must-not-publish",
                            },
                            {
                                "id": "text-1",
                                "type": "text",
                                "text": "private raw output",
                            },
                        ],
                    },
                }
            ],
        },
        created_at=NOW,
        updated_at=NOW,
    )

    output = entry_contract(entry).model_dump(mode="json")["payload"]["parts"][0][
        "output"
    ]

    assert output == {
        "type": "content_parts",
        "parts": [
            {
                "id": "file-1",
                "type": "file_ref",
                "label": "…/workspace/report.txt",
                "project_id": str(SESSION_ID),
                "attachment_id": None,
                "path": "…/workspace/report.txt",
            },
            {
                "id": "run-1",
                "type": "run_ref",
                "run_id": "run-123",
                "label": "Run 123",
            },
        ],
    }
    assert "private" not in str(output)


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


def test_recovery_interaction_projection_exposes_localization_code_and_params() -> None:
    projected = public_interaction_request(
        {
            "kind": "recovery",
            "call_id": "bash-1",
            "tool_name": "bash",
            "message": "Backend-owned English fallback",
            "message_code": "unknown_tool_effect",
            "message_params": {"tool_name": "bash"},
            "options": [
                {"id": "inspect", "label": "Inspect state"},
                {"id": "retry", "label": "Retry operation"},
                {"id": "cancel", "label": "Cancel run"},
            ],
        }
    )

    assert projected == {
        "type": "recovery",
        "call_id": "bash-1",
        "tool_name": "bash",
        "message": "Backend-owned English fallback",
        "message_code": "unknown_tool_effect",
        "message_params": {"tool_name": "bash"},
        "options": [
            {
                "id": "inspect",
                "label": "Inspect state",
                "description": "",
                "recommended": False,
            },
            {
                "id": "retry",
                "label": "Retry operation",
                "description": "",
                "recommended": False,
            },
            {
                "id": "cancel",
                "label": "Cancel run",
                "description": "",
                "recommended": False,
            },
        ],
    }


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
            "target": {
                "environment_id": "ssh:gpu",
                "display_name": "GPU server",
                "kind": "ssh",
                "host": "gpu.example.test",
            },
                "risk": {
                    "level": "high",
                    "effects": ["delete"],
                    "reasons": ["removes output"],
                    "reason_codes": ["sandbox_escalation"],
                    "justification": "remove the obsolete output",
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
        "target": {
            "environment_id": "ssh:gpu",
            "display_name": "GPU server",
            "kind": "ssh",
            "host": "gpu.example.test",
        },
        "risk": {
            "level": "high",
            "effects": ["delete"],
            "reasons": ["removes output"],
            "reason_codes": ["sandbox_escalation"],
            "justification": "remove the obsolete output",
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
