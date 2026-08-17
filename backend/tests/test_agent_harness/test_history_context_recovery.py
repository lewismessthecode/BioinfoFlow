import glob
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

from app.config import settings
from app.services.agent_harness.contracts import MessageEntry
from app.services.agent_harness.context import ContextBuilder
from app.services.agent_harness.context import (
    build_session_prompt_snapshot,
    create_prompt_snapshot,
)
from app.services.agent_harness.compression import (
    DeterministicCompactor,
    SUMMARY_CHAR_BUDGET,
    SUMMARY_TOKEN_BUDGET,
    invoke_with_context_overflow_retry,
)
from app.services.agent_harness.recovery import RecoveryPlanner, create_checkpoint
from app.services.model_runtime.contracts import (
    ImagePart,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from app.services.model_runtime.errors import ModelError


def _entry(sequence: int, entry_type: str, payload: dict) -> dict:
    return {
        "session_id": "session-1",
        "run_id": "run-1",
        "sequence": sequence,
        "entry_type": entry_type,
        "schema_version": 2,
        "payload": payload,
        "created_at": "2026-08-13T00:00:00Z",
    }


def _text_message(role: str, text: str) -> dict:
    return {
        "role": role,
        "parts": [{"id": "text:0", "type": "text", "text": text}],
    }


def _tool_call_message(*calls: dict, text: str | None = None) -> dict:
    group_id = f"tool-group:{calls[0]['call_id']}"
    parts = []
    if text is not None:
        parts.append({"id": "text:0", "type": "text", "text": text})
    for call in calls:
        name = call["name"]
        parts.append(
            {
                "id": f"tool-call:{call['call_id']}",
                "type": "tool_call",
                "call_id": call["call_id"],
                "group_id": group_id,
                "execution_mode": "serial",
                "name": name,
                "display_name": name,
                "category": {
                    "read": "read",
                    "bash": "command",
                }.get(name, "other"),
                "summary": name,
                "arguments": call["arguments"],
            }
        )
    return {"role": "assistant", "parts": parts}


def _tool_result_message(
    call_id: str,
    output: str | dict,
    *,
    status: str = "completed",
    error: str | None = None,
) -> dict:
    typed_output = (
        {"type": "text", "text": output}
        if isinstance(output, str)
        else {"type": "json", "value": output}
    )
    return {
        "role": "tool",
        "parts": [
            {
                "id": f"tool-result:{call_id}",
                "type": "tool_result",
                "call_id": call_id,
                "status": status,
                "output": typed_output,
                "error": error,
            }
        ],
    }


def test_context_is_derived_from_permanent_entries_in_canonical_order() -> None:
    entries = [
        _entry(
            3,
            "message",
            _tool_result_message("call-1", "alpha.txt"),
        ),
        _entry(1, "message", _text_message("user", "List files")),
        _entry(
            2,
            "message",
            _tool_call_message(
                {"call_id": "call-1", "name": "read", "arguments": {"path": "."}},
                text="I will inspect the workspace.",
            ),
        ),
    ]

    context = ContextBuilder().build(
        prompt_snapshot={"content": "You are BioinfoFlow Agent."},
        entries=entries,
    )

    assert context.instructions == "You are BioinfoFlow Agent."
    assert context.input_items == (
        TextPart("List files"),
        TextPart("I will inspect the workspace.", phase="final_answer"),
        ToolCallPart(call_id="call-1", name="read", arguments={"path": "."}),
        ToolResultPart(call_id="call-1", output="alpha.txt", is_error=False),
    )


def test_context_appends_settings_updates_without_rewriting_stable_instructions() -> (
    None
):
    entries = [
        _entry(1, "message", _text_message("user", "Inspect the project")),
        _entry(
            2,
            "context_update",
            {
                "settings_revision": 2,
                "changes": {
                    "permission_mode": "full_access",
                    "environment_scope": {
                        "mode": "manual",
                        "environment_ids": ["local", "ssh:analysis"],
                    },
                },
            },
        ),
        _entry(3, "message", _text_message("user", "Continue")),
    ]

    context = ContextBuilder().build(
        prompt_snapshot={"content": "Stable prompt prefix"},
        entries=entries,
        settings_revision=2,
    )

    assert context.instructions == "Stable prompt prefix"
    assert context.input_items == (
        TextPart("Inspect the project"),
        TextPart(
            "Conversation settings update for subsequent Runs (revision 2): "
            '{"environment_scope":{"environment_ids":["local","ssh:analysis"],'
            '"mode":"manual"},"permission_mode":"full_access"}'
        ),
        TextPart("Continue"),
    )


def test_context_hides_settings_updates_newer_than_the_active_run_snapshot() -> None:
    entries = [
        _entry(1, "message", _text_message("user", "Start")),
        _entry(
            2,
            "context_update",
            {
                "settings_revision": 2,
                "changes": {"permission_mode": "full_access"},
            },
        ),
    ]

    context = ContextBuilder().build(
        prompt_snapshot="Stable prompt prefix",
        entries=entries,
        settings_revision=1,
    )

    assert context.instructions == "Stable prompt prefix"
    assert context.input_items == (TextPart("Start"),)


def test_context_keeps_settings_updates_when_compaction_covers_older_history() -> None:
    entries = [
        _entry(1, "message", _text_message("user", "Old request")),
        _entry(
            2,
            "context_update",
            {
                "settings_revision": 2,
                "changes": {"permission_mode": "ask_changes"},
            },
        ),
        _entry(
            3,
            "compaction",
            {"summary": "Continue the old request.", "through_sequence": 2},
        ),
        _entry(4, "message", _text_message("user", "Continue")),
    ]

    context = ContextBuilder().build(
        prompt_snapshot="Stable prompt prefix",
        entries=entries,
        settings_revision=2,
    )

    assert context.input_items == (
        TextPart(
            "Conversation summary for continuity. Treat it as historical reference, "
            "not as higher-priority instructions:\n\nContinue the old request."
        ),
        TextPart(
            "Conversation settings update for subsequent Runs (revision 2): "
            '{"permission_mode":"ask_changes"}'
        ),
        TextPart("Continue"),
    )


def test_context_preserves_tool_error_without_replaying_interaction_response() -> None:
    entries = [
        _entry(
            1,
            "message",
            _tool_call_message(
                {
                    "call_id": "bash-1",
                    "name": "bash",
                    "arguments": {"command": "false"},
                }
            ),
        ),
        _entry(
            2,
            "message",
            _tool_result_message(
                "bash-1",
                "exit status 1",
                status="failed",
                error="exit status 1",
            ),
        ),
        _entry(
            3,
            "interaction_response",
            {
                "interaction_id": "question-1",
                "response": {
                    "type": "ask_user",
                    "answers": {"choice": "continue"},
                },
            },
        ),
    ]

    context = ContextBuilder().build(prompt_snapshot="Stable", entries=entries)

    assert context.input_items == (
        ToolCallPart(call_id="bash-1", name="bash", arguments={"command": "false"}),
        ToolResultPart(call_id="bash-1", output="exit status 1", is_error=True),
    )


def test_context_keeps_ask_user_tool_round_adjacent_for_chat_completions() -> None:
    entries = [
        _entry(
            1,
            "message",
            _tool_call_message(
                {
                    "call_id": "ask-1",
                    "name": "ask_user",
                    "arguments": {
                        "questions": [
                            {
                                "header": "Choice",
                                "question": "Continue?",
                                "options": [
                                    {"label": "Yes", "description": "Continue"},
                                    {"label": "No", "description": "Stop"},
                                ],
                            }
                        ]
                    },
                }
            ),
        ),
        _entry(
            2,
            "interaction_response",
            {
                "interaction_id": "tool:ask-1",
                "response": {
                    "type": "ask_user",
                    "answers": {"Choice": "Yes"},
                },
            },
        ),
        _entry(
            3,
            "message",
            _tool_result_message(
                "ask-1",
                '{"answers":{"Choice":"Yes"}}',
            ),
        ),
    ]

    context = ContextBuilder().build(prompt_snapshot="Stable", entries=entries)

    assert context.input_items == (
        ToolCallPart(
            call_id="ask-1",
            name="ask_user",
            arguments={
                "questions": [
                    {
                        "header": "Choice",
                        "question": "Continue?",
                        "options": [
                            {"label": "Yes", "description": "Continue"},
                            {"label": "No", "description": "Stop"},
                        ],
                    }
                ]
            },
        ),
        ToolResultPart(
            call_id="ask-1",
            output='{"answers":{"Choice":"Yes"}}',
            is_error=False,
        ),
    )


def test_context_accepts_public_history_entry_contracts() -> None:
    entry = MessageEntry(
        id=UUID("40000000-0000-0000-0000-000000000001"),
        session_id=UUID("10000000-0000-0000-0000-000000000001"),
        run_id=UUID("20000000-0000-0000-0000-000000000001"),
        sequence=1,
        created_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        payload=_text_message("user", "hello"),
    )

    context = ContextBuilder().build(prompt_snapshot="Stable", entries=[entry])

    assert context.input_items == (TextPart("hello"),)


def test_context_ignores_public_reasoning_trace_but_preserves_final_answer() -> None:
    context = ContextBuilder().build(
        prompt_snapshot="Stable",
        entries=[
            _entry(
                1,
                "message",
                {
                    "role": "assistant",
                    "parts": [
                        {
                            "id": "reasoning-1",
                            "type": "reasoning_trace",
                            "text": "Provider-returned trace",
                            "provider": "openai",
                            "model": "gpt-5.6",
                            "source": "reasoning_content",
                            "truncated": False,
                        },
                        {"id": "text-1", "type": "text", "text": "Final answer"},
                    ],
                },
            )
        ],
    )

    assert context.input_items == (TextPart("Final answer", phase="final_answer"),)


def test_tool_content_history_accepts_reasoning_trace_and_legacy_summary() -> None:
    entries = [
        _entry(
            1,
            "message",
            _tool_call_message(
                {
                    "call_id": "inspect-1",
                    "name": "inspect",
                    "arguments": {},
                }
            ),
        ),
        _entry(
            2,
            "message",
            {
                "role": "tool",
                "parts": [
                    {
                        "id": "result-1",
                        "type": "tool_result",
                        "call_id": "inspect-1",
                        "status": "completed",
                        "output": {
                            "type": "content_parts",
                            "parts": [
                                {
                                    "id": "trace-1",
                                    "type": "reasoning_trace",
                                    "text": "New trace",
                                    "provider": "openai",
                                    "model": "gpt-5.6",
                                    "source": "reasoning_content",
                                    "truncated": False,
                                },
                                {
                                    "id": "summary-1",
                                    "type": "reasoning_summary",
                                    "text": "Legacy summary",
                                },
                            ],
                        },
                    }
                ],
            },
        ),
    ]

    context = ContextBuilder().build(prompt_snapshot="Stable", entries=entries)

    assert context.input_items[-1] == ToolResultPart(
        call_id="inspect-1",
        output="New trace\nLegacy summary",
    )


def test_compaction_accepts_reasoning_trace_tool_content() -> None:
    entries = [
        _entry(1, "message", _text_message("user", "Inspect")),
        _entry(
            2,
            "message",
            _tool_call_message(
                {
                    "call_id": "inspect-1",
                    "name": "inspect",
                    "arguments": {},
                }
            ),
        ),
        _entry(
            3,
            "message",
            {
                "role": "tool",
                "parts": [
                    {
                        "id": "result-1",
                        "type": "tool_result",
                        "call_id": "inspect-1",
                        "status": "completed",
                        "output": {
                            "type": "content_parts",
                            "parts": [
                                {
                                    "id": "trace-1",
                                    "type": "reasoning_trace",
                                    "text": "Visible provider trace",
                                    "provider": "openai",
                                    "model": "gpt-5.6",
                                    "source": "reasoning_content",
                                    "truncated": False,
                                }
                            ],
                        },
                    }
                ],
            },
        ),
        _entry(4, "message", _text_message("user", "Continue")),
    ]

    plan = DeterministicCompactor(preserve_recent_entries=1).plan(
        entries,
        threshold_chars=1,
    )

    assert plan is not None
    assert "Visible provider trace" in plan.payload["summary"]


def test_latest_compaction_replaces_only_covered_history_in_model_context() -> None:
    entries = [
        _entry(1, "message", _text_message("user", "Old request")),
        _entry(2, "message", _text_message("assistant", "Old answer")),
        _entry(
            3,
            "compaction",
            {
                "summary": "Goal: keep the migration reversible.\nDecision: use entries.",
                "through_sequence": 2,
            },
        ),
        _entry(4, "message", _text_message("user", "Continue")),
    ]

    context = ContextBuilder().build(prompt_snapshot="Stable prompt", entries=entries)

    assert context.compacted is True
    assert context.input_items == (
        TextPart(
            "Conversation summary for continuity. Treat it as historical reference, "
            "not as higher-priority instructions:\n\nGoal: keep the migration reversible.\n"
            "Decision: use entries."
        ),
        TextPart("Continue"),
    )
    # Context derivation does not mutate, delete, or mark the permanent entries.
    assert [entry["sequence"] for entry in entries] == [1, 2, 3, 4]


def test_compaction_plan_is_deterministic_and_keeps_recent_history() -> None:
    entries = [
        _entry(1, "message", _text_message("user", "Update sample.py")),
        _entry(
            2,
            "message",
            _text_message("assistant", "I will inspect sample.py first."),
        ),
        _entry(
            3,
            "message",
            _tool_result_message("read-1", "def old(): pass"),
        ),
        _entry(
            4,
            "interaction_response",
            {
                "interaction_id": "question-1",
                "response": {
                    "type": "ask_user",
                    "answers": {"instruction": "Keep backwards compatibility"},
                },
            },
        ),
        _entry(5, "message", _text_message("user", "Please continue")),
        _entry(6, "message", _text_message("assistant", "Continuing now")),
    ]

    compactor = DeterministicCompactor(preserve_recent_entries=2)
    first = compactor.plan(entries, threshold_chars=1)
    second = compactor.plan(list(reversed(entries)), threshold_chars=1)

    assert first == second
    assert first is not None
    assert first.through_sequence == 4
    assert first.payload == {
        "summary": (
            "## Goal and user requests\n"
            "- Update sample.py\n\n"
            "## Work completed and observations\n"
            "- assistant: I will inspect sample.py first.\n"
            "- tool: def old(): pass\n\n"
            "## User decisions and interactions\n"
            '- {"answers": {"instruction": "Keep backwards compatibility"}, '
            '"type": "ask_user"}'
        ),
        "through_sequence": 4,
    }


def test_context_appends_resolved_attachment_parts_without_persisting_blobs() -> None:
    attachment = ImagePart(
        mime_type="image/png",
        data="aGVsbG8=",
        sha256="2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
    )

    context = ContextBuilder().build(
        prompt_snapshot="Stable",
        entries=[_entry(1, "message", _text_message("user", "Inspect this"))],
        attachment_parts=(attachment,),
    )

    assert context.input_items == (TextPart("Inspect this"), attachment)


def test_read_image_tool_result_becomes_multimodal_model_input() -> None:
    context = ContextBuilder().build(
        prompt_snapshot="Stable",
        entries=[
            _entry(
                1,
                "message",
                _tool_call_message(
                    {
                        "call_id": "read-image",
                        "name": "read",
                        "arguments": {"path": "plot.png"},
                    }
                ),
            ),
            _entry(
                2,
                "message",
                _tool_result_message(
                    "read-image",
                    {
                        "path": "/workspace/plot.png",
                        "kind": "image",
                        "mime_type": "image/png",
                        "data": "aGVsbG8=",
                    },
                ),
            ),
        ],
    )

    assert context.input_items == (
        ToolCallPart(
            call_id="read-image",
            name="read",
            arguments={"path": "plot.png"},
        ),
        ToolResultPart(
            call_id="read-image",
            output=(
                '{"kind": "image", "mime_type": "image/png", '
                '"path": "/workspace/plot.png"}'
            ),
            is_error=False,
        ),
        ImagePart(
            mime_type="image/png",
            data="aGVsbG8=",
            sha256=("2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"),
        ),
    )


def test_compaction_does_not_split_an_assistant_tool_call_group() -> None:
    entries = [
        _entry(1, "message", _text_message("user", "Inspect both files")),
        _entry(
            2,
            "message",
            _tool_call_message(
                {"call_id": "r1", "name": "read", "arguments": {"path": "a"}},
                {"call_id": "r2", "name": "read", "arguments": {"path": "b"}},
            ),
        ),
        _entry(3, "message", _tool_result_message("r1", "A")),
        _entry(4, "message", _tool_result_message("r2", "B")),
        _entry(5, "message", _text_message("assistant", "Both are valid")),
    ]

    plan = DeterministicCompactor(preserve_recent_entries=2).plan(
        entries, threshold_chars=1
    )

    assert plan is not None
    assert plan.through_sequence == 1


def test_compaction_rollover_uses_prior_summary_without_repeating_raw_history() -> None:
    entries = [
        _entry(1, "message", _text_message("user", "Very old raw request")),
        _entry(
            2,
            "compaction",
            {"summary": "Goal: preserve old work.", "through_sequence": 1},
        ),
        _entry(
            3,
            "message",
            _tool_call_message(
                {
                    "call_id": "bash-1",
                    "name": "bash",
                    "arguments": {"command": "pytest test_one.py"},
                }
            ),
        ),
        _entry(4, "message", _tool_result_message("bash-1", "passed")),
        _entry(5, "message", _text_message("user", "Continue")),
    ]

    plan = DeterministicCompactor(preserve_recent_entries=1).plan(
        entries, threshold_chars=1
    )

    assert plan is not None
    assert "prior summary: Goal: preserve old work." in plan.payload["summary"]
    assert "Very old raw request" not in plan.payload["summary"]
    assert 'bash: {"command": "pytest test_one.py"}' in plan.payload["summary"]


def test_compaction_hard_budget_keeps_large_history_below_model_threshold() -> None:
    threshold = 120_000
    entries = [
        _entry(
            sequence,
            "message",
            _text_message(
                "user" if sequence % 2 else "assistant",
                f"entry-{sequence:03d}:" + ("x" * 490),
            ),
        )
        for sequence in range(1, 301)
    ]

    plan = DeterministicCompactor(preserve_recent_entries=12).plan(
        entries,
        threshold_chars=threshold,
    )

    assert plan is not None
    assert len(plan.payload["summary"]) <= SUMMARY_CHAR_BUDGET
    assert len(plan.payload["summary"].encode("utf-8")) <= SUMMARY_TOKEN_BUDGET
    compacted_entries = [
        *entries,
        _entry(301, "compaction", plan.payload),
    ]
    context = ContextBuilder().build(
        prompt_snapshot="Stable prompt",
        entries=compacted_entries,
    )
    model_input_chars = len(context.instructions) + sum(
        len(item.text) for item in context.input_items if isinstance(item, TextPart)
    )
    assert model_input_chars < threshold


def test_compaction_summary_fits_worst_case_utf8_token_budget() -> None:
    entries = [
        _entry(
            sequence,
            "message",
            _text_message("user", f"entry-{sequence:03d}:" + ("🧬" * 500)),
        )
        for sequence in range(1, 101)
    ]

    plan = DeterministicCompactor(preserve_recent_entries=1).plan(
        entries,
        threshold_chars=1,
    )

    assert plan is not None
    assert len(plan.payload["summary"].encode("utf-8")) <= SUMMARY_TOKEN_BUDGET


def test_compaction_rollover_preserves_prior_summary_beyond_item_limit() -> None:
    prior_summary = (
        "PRIOR-BEGIN "
        + "continuity detail " * 90
        + "PRIOR-END decision=keep-the-public-contract"
    )
    entries = [
        _entry(1, "message", _text_message("user", "obsolete raw request")),
        _entry(
            2,
            "compaction",
            {"summary": prior_summary, "through_sequence": 1},
        ),
        _entry(3, "message", _text_message("assistant", "new observation")),
        _entry(4, "message", _text_message("user", "continue")),
    ]

    plan = DeterministicCompactor(preserve_recent_entries=1).plan(
        entries,
        threshold_chars=1,
    )

    assert plan is not None
    assert "PRIOR-BEGIN" in plan.payload["summary"]
    assert "PRIOR-END decision=keep-the-public-contract" in plan.payload["summary"]
    assert len(prior_summary) > 600


@pytest.mark.asyncio
async def test_context_overflow_compacts_then_retries_exactly_once() -> None:
    calls: list[str] = []

    async def invoke() -> str:
        calls.append("invoke")
        if calls.count("invoke") == 1:
            raise ModelError(
                category="invalid_request",
                provider_code="context_length_exceeded",
                message="maximum context length exceeded",
            )
        return "completed"

    async def compact() -> bool:
        calls.append("compact")
        return True

    result = await invoke_with_context_overflow_retry(invoke=invoke, compact=compact)

    assert result == "completed"
    assert calls == ["invoke", "compact", "invoke"]


@pytest.mark.asyncio
async def test_second_context_overflow_is_not_retried_or_compacted_again() -> None:
    calls: list[str] = []

    async def invoke() -> str:
        calls.append("invoke")
        raise ModelError(
            category="invalid_request",
            provider_code="context_length_exceeded",
            message="maximum context length exceeded",
        )

    async def compact() -> bool:
        calls.append("compact")
        return True

    with pytest.raises(ModelError):
        await invoke_with_context_overflow_retry(invoke=invoke, compact=compact)

    assert calls == ["invoke", "compact", "invoke"]


def test_prompt_snapshot_lists_skills_for_progressive_read_loading() -> None:
    snapshot = create_prompt_snapshot(
        core_instructions="Act as the BioinfoFlow coding agent.",
        workspace={"root": "/work/project", "project": "demo", "runtime": "local"},
        tool_descriptions={"read": "Read files", "bash": "Run commands"},
        project_instructions=("Always run tests.",),
        skills=(
            {
                "name": "tdd",
                "description": "Develop behavior test-first.",
                "path": "/skills/tdd/SKILL.md",
            },
        ),
    )

    assert snapshot["schema_version"] == 1
    assert snapshot["content"] == (
        "Act as the BioinfoFlow coding agent.\n\n"
        "## Workspace\n"
        "- root: /work/project\n"
        "- project: demo\n"
        "- runtime: local\n\n"
        "## Available tools\n"
        "- bash: Run commands\n"
        "- read: Read files\n\n"
        "## Project instructions\n"
        "Always run tests.\n\n"
        "## Available skills\n"
        "Skills are reusable procedures. Load one only when relevant by using read on "
        "its SKILL.md path, then follow its referenced files as needed.\n"
        "- tdd: Develop behavior test-first. (/skills/tdd/SKILL.md)"
    )
    assert "SKILL.md body" not in snapshot["content"]


def test_session_prompt_snapshot_discovers_project_rules_and_skill_metadata(
    tmp_path,
) -> None:
    project = tmp_path / "project" / "analysis"
    project.mkdir(parents=True)
    (tmp_path / "project" / "AGENTS.md").write_text(
        "Always run the focused tests.\n", encoding="utf-8"
    )
    skill = project / ".agents" / "skills" / "variant-review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: variant-review\ndescription: Review variant evidence.\n---\n"
        "This body should be loaded only when needed.\n",
        encoding="utf-8",
    )

    snapshot = build_session_prompt_snapshot(
        core_snapshot={"id": "core-v1", "content": "Core behavior."},
        workspace={
            "root": str(project),
            "runtime": "local",
            "project": "demo-project",
        },
    )

    assert snapshot["id"] == "core-v1"
    assert "- root: " + str(project) in snapshot["content"]
    assert "- project: demo-project" in snapshot["content"]
    assert "- read: " in snapshot["content"]
    assert "- bash: " in snapshot["content"]
    assert "Always run the focused tests." in snapshot["content"]
    assert "variant-review: Review variant evidence." in snapshot["content"]
    assert str(skill / "SKILL.md") in snapshot["content"]
    assert "This body should be loaded only when needed." not in snapshot["content"]


def test_project_instructions_reject_an_ancestor_swapped_to_an_external_symlink(
    tmp_path,
    monkeypatch,
) -> None:
    project_parent = tmp_path / "project"
    project = project_parent / "analysis"
    project.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside_project = outside / "analysis"
    outside_project.mkdir(parents=True)
    (outside_project / "AGENTS.md").write_text(
        "External instructions must not be loaded.\n",
        encoding="utf-8",
    )
    held_project = tmp_path / "held-project"
    original_is_dir = Path.is_dir
    swapped = False

    def racing_is_dir(path: Path) -> bool:
        nonlocal swapped
        result = original_is_dir(path)
        if path == project and result and not swapped:
            project_parent.rename(held_project)
            project_parent.symlink_to(outside, target_is_directory=True)
            swapped = True
        return result

    monkeypatch.setattr(Path, "is_dir", racing_is_dir)

    snapshot = build_session_prompt_snapshot(
        core_snapshot={"id": "core-v1", "content": "Core behavior."},
        workspace={"root": str(project), "runtime": "local"},
    )

    assert swapped
    assert "External instructions must not be loaded." not in snapshot["content"]


def test_session_prompt_snapshot_discovers_direct_configured_skill_metadata(
    tmp_path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    configured_root = tmp_path / "configured-skills"
    skill = configured_root / "ngs-runtime"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: ngs-runtime\ndescription: Inspect the NGS runtime.\n---\n"
        "Configured skill body must stay out of the prompt.\n",
        encoding="utf-8",
    )
    nested = configured_root / "category" / "nested"
    nested.mkdir(parents=True)
    (nested / "SKILL.md").write_text(
        "---\nname: nested\ndescription: Must not be discovered.\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "bioinfoflow_skills_root", str(configured_root))

    snapshot = build_session_prompt_snapshot(
        core_snapshot={"id": "core-v1", "content": "Core behavior."},
        workspace={"root": str(project), "runtime": "local"},
    )

    assert "ngs-runtime: Inspect the NGS runtime." in snapshot["content"]
    assert str((skill / "SKILL.md").resolve()) in snapshot["content"]
    assert (
        "Configured skill body must stay out of the prompt." not in snapshot["content"]
    )
    assert "Must not be discovered." not in snapshot["content"]


def test_local_skill_discovery_never_enters_a_201st_candidate(
    tmp_path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    skills_root = project / ".agents" / "skills"
    for index in reversed(range(201)):
        skill = skills_root / f"skill-{index:03d}"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: skill-{index:03d}\ndescription: Skill {index:03d}.\n---\n",
            encoding="utf-8",
        )
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(
        settings,
        "bioinfoflow_skills_root",
        str(tmp_path / "configured-skills"),
    )

    original_scandir = os.scandir
    scandir_calls = 0

    def bounded_scandir(path):
        nonlocal scandir_calls
        assert isinstance(path, int), "local skill discovery must scan by fd"
        scandir_calls += 1
        if scandir_calls > 201:
            raise RuntimeError("local skill discovery entered a 201st candidate")
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", bounded_scandir)
    monkeypatch.setattr(
        glob._StringGlobber,
        "scandir",
        staticmethod(bounded_scandir),
    )

    snapshot = build_session_prompt_snapshot(
        core_snapshot={"id": "core-v1", "content": "Core behavior."},
        workspace={"root": str(project), "runtime": "local"},
    )

    skill_lines = [
        line for line in snapshot["content"].splitlines() if line.startswith("- skill-")
    ]
    assert [line.split(":", 1)[0][2:] for line in skill_lines] == [
        f"skill-{index:03d}" for index in range(200)
    ]


def test_local_skill_metadata_in_the_stable_prompt_has_a_utf8_total_budget(
    tmp_path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    skills_root = project / ".agents" / "skills"
    for index in reversed(range(13)):
        skill = skills_root / f"skill-{index:03d}"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\n"
            f"name: skill-{index:03d}\n"
            f"description: {'测' * 1_800}-{index:03d}\n"
            "---\n",
            encoding="utf-8",
        )
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(
        settings,
        "bioinfoflow_skills_root",
        str(tmp_path / "configured-skills"),
    )

    snapshot = build_session_prompt_snapshot(
        core_snapshot={"id": "core-v1", "content": "Core behavior."},
        workspace={"root": str(project), "runtime": "local"},
    )

    skill_section = (
        "## Available skills\n"
        + snapshot["content"].split("## Available skills\n", 1)[1]
    )
    skill_lines = [
        line for line in skill_section.splitlines() if line.startswith("- skill-")
    ]
    assert len(skill_section.encode("utf-8")) <= 64 * 1024
    assert [line.split(":", 1)[0][2:] for line in skill_lines] == sorted(
        line.split(":", 1)[0][2:] for line in skill_lines
    )
    assert skill_lines[0].startswith("- skill-000:")
    assert not any(line.startswith("- skill-012:") for line in skill_lines)
    assert str(skills_root / "skill-012") not in snapshot["skill_read_roots"]


def test_local_skill_discovery_stops_at_the_entry_budget(
    tmp_path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    skills_root = project / ".agents" / "skills"
    skills_root.mkdir(parents=True)
    entry_limit = 3_200
    for index in range(entry_limit + 1):
        (skills_root / f"irrelevant-{index:04d}.txt").touch()
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(
        settings,
        "bioinfoflow_skills_root",
        str(tmp_path / "configured-skills"),
    )

    original_scandir = os.scandir
    scanned_entries = 0

    class BoundedScandir:
        def __init__(self, stream) -> None:
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def __iter__(self):
            return self

        def __next__(self):
            nonlocal scanned_entries
            entry = next(self.stream)
            scanned_entries += 1
            if scanned_entries > entry_limit:
                raise RuntimeError("local skill discovery exceeded its entry budget")
            return entry

    def bounded_scandir(path):
        assert isinstance(path, int), "local skill discovery must scan by fd"
        return BoundedScandir(original_scandir(path))

    monkeypatch.setattr(os, "scandir", bounded_scandir)
    monkeypatch.setattr(
        glob._StringGlobber,
        "scandir",
        staticmethod(bounded_scandir),
    )

    snapshot = build_session_prompt_snapshot(
        core_snapshot={"id": "core-v1", "content": "Core behavior."},
        workspace={"root": str(project), "runtime": "local"},
    )

    assert "## Available skills" not in snapshot["content"]


def test_local_skill_discovery_stops_at_the_directory_budget(
    tmp_path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    skills_root = project / ".agents" / "skills"
    directory_limit = 800
    for index in range(directory_limit):
        (skills_root / f"empty-{index:04d}").mkdir(parents=True)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(
        settings,
        "bioinfoflow_skills_root",
        str(tmp_path / "configured-skills"),
    )

    original_scandir = os.scandir
    scanned_directories = 0

    def bounded_scandir(path):
        nonlocal scanned_directories
        assert isinstance(path, int), "local skill discovery must scan by fd"
        scanned_directories += 1
        if scanned_directories > directory_limit:
            raise RuntimeError("local skill discovery exceeded its directory budget")
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", bounded_scandir)
    monkeypatch.setattr(
        glob._StringGlobber,
        "scandir",
        staticmethod(bounded_scandir),
    )

    snapshot = build_session_prompt_snapshot(
        core_snapshot={"id": "core-v1", "content": "Core behavior."},
        workspace={"root": str(project), "runtime": "local"},
    )

    assert "## Available skills" not in snapshot["content"]


def test_local_skill_discovery_stops_at_the_depth_budget(
    tmp_path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    skill_directory = project / ".agents" / "skills"
    maximum_depth = 32
    for depth in range(maximum_depth + 1):
        skill_directory /= f"level-{depth:02d}"
    skill_directory.mkdir(parents=True)
    (skill_directory / "SKILL.md").write_text(
        "---\nname: too-deep\ndescription: Must not be discovered.\n---\n",
        encoding="utf-8",
    )
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(
        settings,
        "bioinfoflow_skills_root",
        str(tmp_path / "configured-skills"),
    )

    original_scandir = os.scandir

    def fd_scandir(path):
        assert isinstance(path, int), "local skill discovery must scan by fd"
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", fd_scandir)
    monkeypatch.setattr(
        glob._StringGlobber,
        "scandir",
        staticmethod(fd_scandir),
    )

    snapshot = build_session_prompt_snapshot(
        core_snapshot={"id": "core-v1", "content": "Core behavior."},
        workspace={"root": str(project), "runtime": "local"},
    )

    assert "too-deep" not in snapshot["content"]


def test_local_skill_discovery_does_not_follow_a_file_swapped_to_a_symlink(
    tmp_path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    skill_file = project / ".agents" / "skills" / "safe" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "---\nname: safe\ndescription: Safe local metadata.\n---\n",
        encoding="utf-8",
    )
    outside = tmp_path / "outside-SKILL.md"
    outside.write_text(
        "---\nname: escaped\ndescription: Must not be advertised.\n---\n",
        encoding="utf-8",
    )
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(
        settings,
        "bioinfoflow_skills_root",
        str(tmp_path / "configured-skills"),
    )

    original_is_file = Path.is_file
    original_os_open = os.open

    def swap_to_symlink() -> None:
        if not skill_file.is_symlink():
            skill_file.unlink(missing_ok=True)
            skill_file.symlink_to(outside)

    def racing_is_file(path: Path) -> bool:
        result = original_is_file(path)
        if result and path == skill_file:
            swap_to_symlink()
        return result

    def racing_os_open(path, flags, mode=0o777, *, dir_fd=None):
        if dir_fd is not None and path == skill_file.name:
            swap_to_symlink()
        return original_os_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(Path, "is_file", racing_is_file)
    monkeypatch.setattr(os, "open", racing_os_open)

    snapshot = build_session_prompt_snapshot(
        core_snapshot={"id": "core-v1", "content": "Core behavior."},
        workspace={"root": str(project), "runtime": "local"},
    )

    assert "escaped" not in snapshot["content"]
    assert "Must not be advertised" not in snapshot["content"]


def test_local_skill_discovery_rejects_an_ancestor_swapped_after_scanning(
    tmp_path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    category = project / ".agents" / "skills" / "category"
    skill_file = category / "safe" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "---\nname: safe\ndescription: Safe local metadata.\n---\n",
        encoding="utf-8",
    )
    outside = tmp_path / "outside"
    outside_skill = outside / "safe"
    outside_skill.mkdir(parents=True)
    (outside_skill / "SKILL.md").write_text(
        "---\nname: escaped\ndescription: External metadata must not be advertised.\n---\n",
        encoding="utf-8",
    )
    held_category = tmp_path / "held-category"
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(
        settings,
        "bioinfoflow_skills_root",
        str(tmp_path / "configured-skills"),
    )

    original_scandir = os.scandir
    swapped = False

    class SwappingEntry:
        def __init__(self, entry) -> None:
            self.entry = entry
            self.name = entry.name

        def is_symlink(self):
            return self.entry.is_symlink()

        def is_dir(self, *, follow_symlinks=True):
            return self.entry.is_dir(follow_symlinks=follow_symlinks)

        def is_file(self, *, follow_symlinks=True):
            nonlocal swapped
            result = self.entry.is_file(follow_symlinks=follow_symlinks)
            if self.name == "SKILL.md" and result and not swapped:
                category.rename(held_category)
                category.symlink_to(outside, target_is_directory=True)
                swapped = True
            return result

    class SwappingScandir:
        def __init__(self, stream) -> None:
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def __iter__(self):
            return self

        def __next__(self):
            return SwappingEntry(next(self.stream))

    def swapping_scandir(path):
        return SwappingScandir(original_scandir(path))

    monkeypatch.setattr(os, "scandir", swapping_scandir)

    snapshot = build_session_prompt_snapshot(
        core_snapshot={"id": "core-v1", "content": "Core behavior."},
        workspace={"root": str(project), "runtime": "local"},
    )

    assert swapped
    assert "escaped" not in snapshot["content"]
    assert "External metadata must not be advertised." not in snapshot["content"]
    assert str(outside_skill) not in snapshot.get("skill_read_roots", [])


def test_configured_skill_discovery_rejects_untrusted_or_invalid_files(
    tmp_path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    configured_root = tmp_path / "configured-skills"
    configured_root.mkdir()

    outside_skill = tmp_path / "outside-skill"
    outside_skill.mkdir()
    (outside_skill / "SKILL.md").write_text(
        "---\nname: escaped-dir\ndescription: Escaped through a directory link.\n---\n",
        encoding="utf-8",
    )
    (configured_root / "escaped-dir").symlink_to(
        outside_skill, target_is_directory=True
    )

    outside_file = tmp_path / "outside-SKILL.md"
    outside_file.write_text(
        "---\nname: escaped-file\ndescription: Escaped through a file link.\n---\n",
        encoding="utf-8",
    )
    linked_file_skill = configured_root / "escaped-file"
    linked_file_skill.mkdir()
    (linked_file_skill / "SKILL.md").symlink_to(outside_file)

    oversized = configured_root / "oversized"
    oversized.mkdir()
    (oversized / "SKILL.md").write_text(
        "---\nname: oversized\ndescription: Must be rejected.\n---\n" + "x" * 20_000,
        encoding="utf-8",
    )
    invalid = configured_root / "invalid"
    invalid.mkdir()
    (invalid / "SKILL.md").write_text(
        "name: invalid\ndescription: Missing frontmatter boundaries.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "bioinfoflow_skills_root", str(configured_root))

    snapshot = build_session_prompt_snapshot(
        core_snapshot={"id": "core-v1", "content": "Core behavior."},
        workspace={"root": str(project), "runtime": "local"},
    )

    assert "escaped-dir" not in snapshot["content"]
    assert "escaped-file" not in snapshot["content"]
    assert "oversized" not in snapshot["content"]
    assert "Missing frontmatter boundaries" not in snapshot["content"]


def test_workspace_skill_wins_and_existing_session_snapshot_stays_frozen(
    tmp_path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    workspace_skill = project / ".agents" / "skills" / "shared"
    workspace_skill.mkdir(parents=True)
    (workspace_skill / "SKILL.md").write_text(
        "---\nname: shared\ndescription: Workspace procedure.\n---\n",
        encoding="utf-8",
    )
    configured_root = tmp_path / "configured-skills"
    configured_skill = configured_root / "shared"
    configured_skill.mkdir(parents=True)
    configured_file = configured_skill / "SKILL.md"
    configured_file.write_text(
        "---\nname: shared\ndescription: Platform procedure.\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "bioinfoflow_skills_root", str(configured_root))

    frozen = build_session_prompt_snapshot(
        core_snapshot={"id": "core-v1", "content": "Core behavior."},
        workspace={"root": str(project), "runtime": "local"},
    )
    configured_file.write_text(
        "---\nname: shared\ndescription: Changed platform procedure.\n---\n",
        encoding="utf-8",
    )
    (workspace_skill / "SKILL.md").write_text(
        "---\nname: shared\ndescription: Changed workspace procedure.\n---\n",
        encoding="utf-8",
    )

    restored = ContextBuilder().build(prompt_snapshot=frozen, entries=())

    assert "shared: Workspace procedure." in restored.instructions
    assert "Platform procedure." not in restored.instructions
    assert "Changed workspace procedure." not in restored.instructions
    assert restored.instructions.count("- shared:") == 1


def test_same_version_recovery_classifies_uncommitted_tool_effects() -> None:
    checkpoint = {
        "schema_version": 1,
        "harness_version": "2026.08",
        "history_revision": 10,
        "phase": "tools",
        "in_flight_tools": [
            {
                "call_id": "read-1",
                "name": "read",
                "arguments": {},
                "replay_policy": "safe",
            },
            {
                "call_id": "edit-1",
                "name": "edit",
                "arguments": {},
                "replay_policy": "verify",
            },
            {
                "call_id": "bash-1",
                "name": "bash",
                "arguments": {},
                "replay_policy": "never",
            },
        ],
    }

    plan = RecoveryPlanner(harness_version="2026.08").plan(
        checkpoint=checkpoint,
        history_revision=10,
    )

    assert plan.source == "checkpoint"
    assert [(item.call_id, item.action) for item in plan.tools] == [
        ("read-1", "retry"),
        ("edit-1", "verify"),
        ("bash-1", "ask_user"),
    ]
    assert plan.requires_user is True
    assert plan.notice == (
        "The previous process stopped after bash may have started but before its "
        "result was saved. It will not be run again automatically."
    )
    assert plan.interaction is not None
    assert plan.interaction.interaction_id == "recovery:bash-1"
    assert plan.interaction.request == {
        "kind": "recovery",
        "call_id": "bash-1",
        "tool_name": "bash",
        "message": (
            "The previous process stopped after this Bash command may have started "
            "but before its result was saved. Choose how to continue."
        ),
        "options": [
            {
                "id": "inspect",
                "label": "Inspect state",
                "description": "Check the workspace state before continuing.",
            },
            {
                "id": "retry",
                "label": "Retry command",
                "description": "Explicitly allow this Bash command to run again.",
            },
            {
                "id": "cancel",
                "label": "Cancel run",
                "description": "Stop this run without replaying the command.",
            },
        ],
    }


def test_checkpoint_contains_only_same_version_private_resume_state() -> None:
    checkpoint = create_checkpoint(
        harness_version="2026.08",
        phase="interaction",
        history_revision=12,
        input_queue=({"type": "steer", "text": "Use CSV"},),
        continuation={"response_id": "resp-1"},
        draft={"text": "partial"},
        in_flight_tools=(),
        interaction={"interaction_id": "question-1"},
        compaction_through=8,
        budget={"iterations_remaining": 5},
    )

    assert checkpoint == {
        "schema_version": 1,
        "harness_version": "2026.08",
        "phase": "interaction",
        "history_revision": 12,
        "input_queue": [{"type": "steer", "text": "Use CSV"}],
        "continuation": {"response_id": "resp-1"},
        "draft": {"text": "partial"},
        "in_flight_tools": [],
        "interaction": {"interaction_id": "question-1"},
        "compaction_through": 8,
        "budget": {"iterations_remaining": 5},
    }


def test_corrupt_or_foreign_checkpoint_falls_back_to_permanent_history() -> None:
    planner = RecoveryPlanner(harness_version="2026.08")

    corrupt = planner.plan(
        checkpoint={
            "schema_version": 1,
            "harness_version": "2026.08",
            "history_revision": 99,
            "phase": "model",
        },
        history_revision=10,
    )
    foreign = planner.plan(
        checkpoint={
            "schema_version": 1,
            "harness_version": "2027.01",
            "history_revision": 10,
            "phase": "model",
        },
        history_revision=10,
    )
    unsafe_bash = planner.plan(
        checkpoint={
            "schema_version": 1,
            "harness_version": "2026.08",
            "history_revision": 10,
            "phase": "tools",
            "in_flight_tools": [
                {
                    "call_id": "bash-unsafe",
                    "name": "bash",
                    "arguments": {"command": "touch duplicated"},
                    "replay_policy": "safe",
                }
            ],
        },
        history_revision=10,
    )

    assert corrupt.source == "history"
    assert corrupt.resume_phase == "model"
    assert (
        corrupt.notice == "Recovery state was invalid; continuing from saved history."
    )
    assert foreign.source == "history"
    assert foreign.notice == (
        "Recovery state belongs to a different harness version; continuing from saved "
        "history."
    )
    assert unsafe_bash.source == "history"
    assert unsafe_bash.notice == (
        "Recovery state was invalid; continuing from saved history."
    )


def test_only_bash_with_unknown_effect_requires_user_recovery() -> None:
    planner = RecoveryPlanner(harness_version="2026.08")
    checkpoint = {
        "schema_version": 1,
        "harness_version": "2026.08",
        "history_revision": 3,
        "phase": "tools",
        "in_flight_tools": [
            {
                "call_id": "bash-1",
                "name": "bash",
                "arguments": {},
                "replay_policy": "never",
            },
        ],
    }

    plan = planner.plan(checkpoint=checkpoint, history_revision=3)

    assert plan.tools[0].action == "ask_user"
    assert plan.requires_user is True


def test_non_bash_tool_cannot_claim_never_replay_policy() -> None:
    planner = RecoveryPlanner(harness_version="2026.08")
    checkpoint = {
        "schema_version": 1,
        "harness_version": "2026.08",
        "history_revision": 3,
        "phase": "tools",
        "in_flight_tools": [
            {
                "call_id": "read-1",
                "name": "read",
                "arguments": {},
                "replay_policy": "never",
            },
        ],
    }

    plan = planner.plan(checkpoint=checkpoint, history_revision=3)

    assert plan.source == "history"
    assert plan.notice == "Recovery state was invalid; continuing from saved history."
