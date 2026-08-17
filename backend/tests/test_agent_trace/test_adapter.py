from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.models.workspace import Workspace
from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.repositories.agent_trace_repo import AgentModelTraceRepository
from app.services.agent_harness.contracts import OpenSessionRequest
from app.services.agent_trace.adapter import CompleteHarnessTraceAdapter


WORKSPACE_ID = UUID("71000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_complete_harness_adapter_builds_session_trace_from_raw_sources(
    db_session,
) -> None:
    db_session.add(
        Workspace(
            id=str(WORKSPACE_ID),
            name="Trace Adapter",
            slug="trace-adapter",
            is_default=False,
        )
    )
    await db_session.commit()
    harness = AgentHarnessRepository(db_session)
    session = await harness.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id=WORKSPACE_ID,
            title="RNA-seq QC",
            prompt_snapshot={
                "schema_version": 1,
                "content": "System prompt first line\nSystem prompt second line",
            },
            model={
                "target": {
                    "provider_kind": "openai",
                    "model_name": "gpt-5",
                }
            },
        )
    )
    run = await harness.create_run(
        str(session.id),
        turn_execution_config={
            "settings_revision": 1,
            "model": session.model_snapshot,
            "permission_mode": "ask_dangerous",
            "workspace_access": "read_write",
            "environment_scope": {"mode": "auto", "environment_ids": ["local"]},
        },
    )
    user = await harness.append_entry(
        str(session.id),
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "user",
            "parts": [
                {
                    "id": "user-text",
                    "type": "text",
                    "text": "Run FastQC first line\nKeep raw reads.",
                }
            ],
        },
    )
    traces = AgentModelTraceRepository(db_session)
    trace = await traces.start(
        session_id=str(session.id),
        run_id=str(run.id),
        iteration=1,
        attempt=1,
        context_through_sequence=user.sequence,
        provider="openai",
        model="gpt-5",
        wire_protocol="responses",
        context_snapshot={
            "compacted": False,
            "max_context_tokens": 128000,
            "composition": [
                {"category": "system", "characters": 45, "tokens": None},
                {"category": "user", "characters": 38, "tokens": None},
            ],
        },
    )
    request_prepared_at = trace.started_at + timedelta(milliseconds=10)
    first_byte_at = trace.started_at + timedelta(milliseconds=45)
    model_completed_at = trace.started_at + timedelta(milliseconds=90)
    await traces.record_request(
        str(trace.id),
        {
            "model": "gpt-5",
            "input": [{"role": "user", "content": "Run FastQC first line"}],
            "tools": [
                {
                    "type": "function",
                    "name": "bash",
                    "description": "Run a command",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                    },
                }
            ],
        },
        prepared_at=request_prepared_at,
    )
    await traces.record_first_byte(str(trace.id), occurred_at=first_byte_at)
    await traces.complete(
        str(trace.id),
        response_payload={"id": "resp-1", "output": [{"type": "tool_call"}]},
        usage={
            "input_tokens": 120,
            "output_tokens": 20,
            "total_tokens": 140,
            "cached_input_tokens": 80,
            "reasoning_tokens": None,
        },
        provider_response_id="resp-1",
        finish_reason="tool_calls",
        completed_at=model_completed_at,
    )
    assistant = await harness.append_entry(
        str(session.id),
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "assistant",
            "parts": [
                {
                    "id": "assistant-text",
                    "type": "text",
                    "text": "I will inspect the reads.\nThen summarize QC.",
                },
                {
                    "id": "tool-call:call-1",
                    "type": "tool_call",
                    "call_id": "call-1",
                    "group_id": "group-1",
                    "execution_mode": "serial",
                    "name": "bash",
                    "display_name": "Terminal",
                    "category": "command",
                    "summary": "Run FastQC",
                    "arguments": {"command": "fastqc reads.fastq.gz"},
                },
            ],
        },
    )
    started_at = datetime.now(timezone.utc)
    completed_at = started_at + timedelta(milliseconds=250)
    tool_result = await harness.append_entry(
        str(session.id),
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "tool",
            "parts": [
                {
                    "id": "tool-result:call-1",
                    "type": "tool_result",
                    "call_id": "call-1",
                    "status": "completed",
                    "output": {"type": "text", "text": "FastQC complete\nPASS"},
                    "started_at": started_at,
                    "completed_at": completed_at,
                }
            ],
        },
    )
    adapter = CompleteHarnessTraceAdapter(db_session)

    timeline = await adapter.timeline(str(session.id))

    assert [turn.id for turn in timeline.turns] == [f"turn:{run.id}"]
    assert [event.category for event in timeline.events] == [
        "system",
        "user",
        "context",
        "assistant",
        "tool",
    ]
    assert timeline.events[0].summary == "System prompt first line"
    assert timeline.events[1].summary == "Run FastQC first line"
    assert timeline.events[2].summary == "openai/gpt-5 · 120 input tokens"
    assert timeline.events[3].summary == "I will inspect the reads."
    assert timeline.events[4].summary == ('bash({"command":"fastqc reads.fastq.gz"})')
    assert timeline.context_flow[0].sequence == 3
    assert timeline.context_flow[0].through_sequence == 2
    assert timeline.context_flow[0].input_tokens == 120
    assert timeline.context_flow[0].output_tokens == 20
    assert timeline.context_flow[0].cached_input_tokens == 80
    assert timeline.context_flow[0].reasoning_tokens is None
    assert timeline.context_flow[0].total_tokens == 140
    assert timeline.context_flow[0].max_context_tokens == 128000

    model_detail = await adapter.detail(str(session.id), f"model:{trace.id}")

    assert model_detail is not None
    assert model_detail.summary == {
        "category": "context",
        "provider": "openai",
        "model": "gpt-5",
        "status": "completed",
        "wire_protocol": "responses",
        "input_tokens": 120,
        "output_tokens": 20,
        "cached_input_tokens": 80,
        "reasoning_tokens": None,
        "total_tokens": 140,
    }
    assert model_detail.timing is not None
    assert model_detail.timing.started_at == trace.started_at.replace(tzinfo=None)
    assert model_detail.timing.request_prepared_at == request_prepared_at.replace(
        tzinfo=None
    )
    assert model_detail.timing.first_byte_at == first_byte_at.replace(tzinfo=None)
    assert model_detail.timing.completed_at == model_completed_at.replace(tzinfo=None)
    assert model_detail.timing.duration_ms == 90

    call_event_id = f"entry:{assistant.id}:tool-call:call-1"
    detail = await adapter.detail(str(session.id), call_event_id)

    assert detail is not None
    assert detail.payload == {"command": "fastqc reads.fastq.gz"}
    assert detail.result == {"type": "text", "text": "FastQC complete\nPASS"}
    assert detail.schema_ == {
        "type": "object",
        "properties": {"command": {"type": "string"}},
    }
    assert detail.timing is not None
    assert detail.timing.duration_ms == 250
    assert f"entry:{tool_result.id}:tool-result:call-1" not in {
        event.id for event in timeline.events
    }


@pytest.mark.asyncio
async def test_tool_results_are_scoped_to_their_run_when_call_ids_repeat(
    db_session,
) -> None:
    db_session.add(
        Workspace(
            id=str(WORKSPACE_ID),
            name="Scoped Trace Adapter",
            slug="scoped-trace-adapter",
            is_default=False,
        )
    )
    await db_session.commit()
    harness = AgentHarnessRepository(db_session)
    session = await harness.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id=WORKSPACE_ID,
            prompt_snapshot={"schema_version": 1, "content": "System prompt."},
            model={"target": {"provider_kind": "openai", "model_name": "gpt-5"}},
        )
    )
    runs = []
    call_entries = []
    for index, (status, output) in enumerate(
        (("completed", "first result"), ("failed", "second result")), start=1
    ):
        run = await harness.create_run(
            str(session.id),
            turn_execution_config={
                "settings_revision": index,
                "model": session.model_snapshot,
                "permission_mode": "ask_dangerous",
                "workspace_access": "read_write",
                "environment_scope": {"mode": "auto", "environment_ids": ["local"]},
            },
        )
        call = await harness.append_entry(
            str(session.id),
            run_id=str(run.id),
            entry_type="message",
            payload={
                "role": "assistant",
                "parts": [
                    {
                        "id": "tool-call:shared-call",
                        "type": "tool_call",
                        "call_id": "shared-call",
                        "group_id": f"group-{index}",
                        "execution_mode": "serial",
                        "name": "bash",
                        "display_name": "Terminal",
                        "summary": f"Echo {index}",
                        "arguments": {"command": f"echo {index}"},
                    }
                ],
            },
        )
        await harness.append_entry(
            str(session.id),
            run_id=str(run.id),
            entry_type="message",
            payload={
                "role": "tool",
                "parts": [
                    {
                        "id": "tool-result:shared-call",
                        "type": "tool_result",
                        "call_id": "shared-call",
                        "status": status,
                        "output": {"type": "text", "text": output},
                    }
                ],
            },
        )
        await harness.update_run(str(run.id), status="completed")
        runs.append(run)
        call_entries.append(call)
    adapter = CompleteHarnessTraceAdapter(db_session)

    timeline = await adapter.timeline(str(session.id))
    details = [
        await adapter.detail(
            str(session.id),
            f"entry:{entry.id}:tool-call:shared-call",
        )
        for entry in call_entries
    ]

    tool_events = [event for event in timeline.events if event.category == "tool"]
    assert [event.turn_id for event in tool_events] == [
        f"turn:{runs[0].id}",
        f"turn:{runs[1].id}",
    ]
    assert [event.status for event in tool_events] == ["completed", "failed"]
    assert [detail.result for detail in details if detail is not None] == [
        {"type": "text", "text": "first result"},
        {"type": "text", "text": "second result"},
    ]
