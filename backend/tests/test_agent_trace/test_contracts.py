from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.services.agent_trace.contracts import (
    AGENT_TRACE_PROTOCOL,
    AGENT_TRACE_PROTOCOL_VERSION,
    AgentTraceTimeline,
)


def _timeline_payload() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "session": {
            "id": "session-1",
            "title": "RNA-seq QC",
            "status": "active",
            "model": {
                "provider": "openai",
                "model": "gpt-5",
                "display_name": "GPT-5",
            },
            "created_at": now,
            "updated_at": now,
        },
        "turns": [
            {
                "id": "turn:run-1",
                "run_id": "run-1",
                "index": 1,
                "status": "completed",
                "model": None,
                "started_at": now,
                "completed_at": now,
            }
        ],
        "context_flow": [
            {
                "id": "context:trace-1",
                "turn_id": "turn:run-1",
                "model_trace_id": "trace-1",
                "sequence": 2,
                "through_sequence": 1,
                "compacted": False,
                "input_tokens": 120,
                "output_tokens": 20,
                "cached_input_tokens": None,
                "reasoning_tokens": 4,
                "total_tokens": 144,
                "max_context_tokens": 128000,
                "composition": [
                    {
                        "category": "system",
                        "characters": 420,
                        "tokens": None,
                    }
                ],
                "created_at": now,
            }
        ],
        "events": [
            {
                "id": "system:session-1",
                "turn_id": None,
                "category": "system",
                "title": "System",
                "summary": "You are BioinfoFlow.",
                "status": "completed",
                "sequence": 1,
                "has_detail": True,
                "created_at": now,
            }
        ],
    }


def test_trace_timeline_has_a_versioned_harness_independent_contract() -> None:
    timeline = AgentTraceTimeline.model_validate(_timeline_payload())

    dumped = timeline.model_dump(mode="json")

    assert dumped["protocol"] == AGENT_TRACE_PROTOCOL
    assert dumped["protocol_version"] == AGENT_TRACE_PROTOCOL_VERSION
    assert dumped["context_flow"][0]["cached_input_tokens"] is None
    assert dumped["context_flow"][0]["output_tokens"] == 20
    assert dumped["context_flow"][0]["reasoning_tokens"] == 4
    assert dumped["context_flow"][0]["total_tokens"] == 144
    assert dumped["events"][0]["category"] == "system"


def test_trace_timeline_rejects_unknown_event_categories() -> None:
    payload = _timeline_payload()
    payload["events"][0]["category"] = "span"

    with pytest.raises(ValidationError):
        AgentTraceTimeline.model_validate(payload)
