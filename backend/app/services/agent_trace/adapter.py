from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import json
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_harness import AgentHarnessEntry, AgentHarnessRun
from app.models.agent_trace import AgentModelTrace
from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.repositories.agent_trace_repo import AgentModelTraceRepository
from app.services.agent_trace.contracts import (
    AgentTraceEventDetail,
    AgentTraceTimeline,
    ContextCompositionItem,
    ContextFlowSnapshot,
    TraceEvent,
    TraceModelSummary,
    TraceSessionSummary,
    TraceTiming,
    TraceTurn,
)


class AgentTraceAdapter(Protocol):
    async def timeline(self, session_id: str) -> AgentTraceTimeline: ...

    async def detail(
        self, session_id: str, event_id: str
    ) -> AgentTraceEventDetail | None: ...


class CompleteHarnessTraceAdapter:
    """Project Complete Harness persistence into the stable Trace Contract."""

    def __init__(self, db: AsyncSession):
        self.harness = AgentHarnessRepository(db)
        self.model_traces = AgentModelTraceRepository(db)

    async def timeline(self, session_id: str) -> AgentTraceTimeline:
        session = await self.harness.get_session(session_id)
        if session is None:
            raise LookupError(f"agent session not found: {session_id}")
        runs = await self.harness.list_runs(session_id)
        entries = await self.harness.list_entries(session_id)
        traces = await self.model_traces.list_for_session(session_id)
        turns, turn_ids = _turns(runs)
        tool_results = _tool_results(entries)
        matched_tool_result_keys = {
            (
                str(entry.run_id) if entry.run_id is not None else None,
                str(part.get("call_id") or ""),
            )
            for entry in entries
            for part in entry.payload.get("parts") or []
            if isinstance(part, dict) and part.get("type") == "tool_call"
            if (
                str(entry.run_id) if entry.run_id is not None else None,
                str(part.get("call_id") or ""),
            )
            in tool_results
        }
        candidates: list[_EventCandidate] = [
            _EventCandidate(
                occurred_at=session.created_at,
                source_order=-1,
                event=TraceEvent(
                    id=f"system:{session.id}",
                    turn_id=None,
                    category="system",
                    title="System",
                    summary=_first_line(_prompt_content(session.prompt_snapshot)),
                    status="completed",
                    sequence=1,
                    has_detail=True,
                    created_at=session.created_at,
                ),
            )
        ]
        for trace in traces:
            candidates.append(
                _EventCandidate(
                    occurred_at=trace.started_at,
                    source_order=trace.context_through_sequence * 10 + 5,
                    event=TraceEvent(
                        id=f"model:{trace.id}",
                        turn_id=turn_ids.get(str(trace.run_id)),
                        category="context",
                        title="Model request",
                        summary=_model_trace_summary(trace),
                        status=trace.status,
                        sequence=1,
                        has_detail=True,
                        created_at=trace.started_at,
                    ),
                )
            )
        for entry in entries:
            candidates.extend(
                _entry_events(
                    entry,
                    turn_ids=turn_ids,
                    tool_results=tool_results,
                    matched_tool_result_keys=matched_tool_result_keys,
                )
            )
        candidates.sort(
            key=lambda candidate: (
                candidate.source_order,
                candidate.occurred_at,
                candidate.event.id,
            )
        )
        events = [
            candidate.event.model_copy(update={"sequence": index})
            for index, candidate in enumerate(candidates, start=1)
        ]
        sequence_by_id = {event.id: event.sequence for event in events}
        entry_sequence_by_event_id = {
            candidate.event.id: candidate.entry_sequence
            for candidate in candidates
            if candidate.entry_sequence is not None
        }
        return AgentTraceTimeline(
            session=TraceSessionSummary(
                id=str(session.id),
                title=session.title,
                status=session.status,
                model=_model_summary(session.model_snapshot),
                created_at=session.created_at,
                updated_at=session.updated_at,
            ),
            turns=turns,
            context_flow=[
                _context_flow_snapshot(
                    trace,
                    turn_id=turn_ids[str(trace.run_id)],
                    sequence=sequence_by_id[f"model:{trace.id}"],
                    through_sequence=_normalized_through_sequence(
                        trace.context_through_sequence,
                        sequence_by_id=sequence_by_id,
                        entry_sequence_by_event_id=entry_sequence_by_event_id,
                    ),
                )
                for trace in traces
                if str(trace.run_id) in turn_ids
            ],
            events=events,
        )

    async def detail(
        self, session_id: str, event_id: str
    ) -> AgentTraceEventDetail | None:
        session = await self.harness.get_session(session_id)
        if session is None:
            raise LookupError(f"agent session not found: {session_id}")
        if event_id == f"system:{session_id}":
            return AgentTraceEventDetail(
                event_id=event_id,
                summary={"category": "system", "title": "System"},
                payload=session.prompt_snapshot,
            )
        if event_id.startswith("model:"):
            trace_id = event_id.removeprefix("model:")
            if not _is_uuid(trace_id):
                return None
            trace = await self.model_traces.get(trace_id, session_id=session_id)
            return _model_trace_detail(trace) if trace is not None else None
        if not event_id.startswith("entry:"):
            return None
        raw = event_id.removeprefix("entry:")
        entry_id, separator, part_id = raw.partition(":")
        if not _is_uuid(entry_id):
            return None
        entry = next(
            (
                item
                for item in await self.harness.list_entries(session_id)
                if str(item.id) == entry_id
            ),
            None,
        )
        if entry is None:
            return None
        if not separator:
            return _entry_detail(event_id, entry)
        part = next(
            (
                item
                for item in entry.payload.get("parts") or []
                if isinstance(item, dict) and str(item.get("id")) == part_id
            ),
            None,
        )
        if part is None:
            return None
        entries = await self.harness.list_entries(session_id)
        traces = await self.model_traces.list_for_session(session_id)
        return _part_detail(event_id, entry, part, entries=entries, traces=traces)


class _EventCandidate:
    def __init__(
        self,
        *,
        occurred_at: datetime,
        source_order: int,
        event: TraceEvent,
        entry_sequence: int | None = None,
    ) -> None:
        self.occurred_at = occurred_at
        self.source_order = source_order
        self.event = event
        self.entry_sequence = entry_sequence


def _turns(
    runs: list[AgentHarnessRun],
) -> tuple[list[TraceTurn], dict[str, str]]:
    turn_ids = {str(run.id): f"turn:{run.id}" for run in runs}
    return (
        [
            TraceTurn(
                id=turn_ids[str(run.id)],
                run_id=str(run.id),
                index=index,
                status=run.status,
                model=_model_summary(run.model_snapshot),
                started_at=run.started_at or run.created_at,
                completed_at=run.completed_at,
            )
            for index, run in enumerate(runs, start=1)
        ],
        turn_ids,
    )


def _entry_events(
    entry: AgentHarnessEntry,
    *,
    turn_ids: dict[str, str],
    tool_results: dict[tuple[str | None, str], dict[str, Any]],
    matched_tool_result_keys: set[tuple[str | None, str]],
) -> list[_EventCandidate]:
    turn_id = turn_ids.get(str(entry.run_id)) if entry.run_id else None
    run_scope = str(entry.run_id) if entry.run_id is not None else None
    if entry.type != "message":
        return [
            _EventCandidate(
                occurred_at=entry.created_at,
                source_order=entry.sequence * 10,
                entry_sequence=entry.sequence,
                event=TraceEvent(
                    id=f"entry:{entry.id}",
                    turn_id=turn_id,
                    category="context",
                    title=_entry_title(entry.type),
                    summary=_raw_first_line(entry.payload),
                    status="completed",
                    sequence=1,
                    has_detail=True,
                    created_at=entry.created_at,
                ),
            )
        ]
    role = str(entry.payload.get("role") or "assistant")
    candidates: list[_EventCandidate] = []
    for part_index, part in enumerate(entry.payload.get("parts") or []):
        if not isinstance(part, dict):
            continue
        part_type = str(part.get("type") or "unknown")
        tool_result_key = (run_scope, str(part.get("call_id") or ""))
        if part_type == "tool_result" and tool_result_key in matched_tool_result_keys:
            continue
        category = "tool" if part_type in {"tool_call", "tool_result"} else role
        if category not in {"user", "assistant", "tool"}:
            category = "context"
        part_id = str(part.get("id") or f"part-{part_index}")
        candidates.append(
            _EventCandidate(
                occurred_at=entry.created_at,
                source_order=entry.sequence * 10 + part_index,
                entry_sequence=entry.sequence,
                event=TraceEvent(
                    id=f"entry:{entry.id}:{part_id}",
                    turn_id=turn_id,
                    category=category,
                    title=_part_title(part_type, role=role, part=part),
                    summary=_part_first_line(part),
                    status=(
                        str((tool_results.get(tool_result_key) or part).get("status"))
                        if (tool_results.get(tool_result_key) or part).get("status")
                        is not None
                        else "completed"
                    ),
                    sequence=1,
                    has_detail=True,
                    created_at=entry.created_at,
                ),
            )
        )
    return candidates


def _context_flow_snapshot(
    trace: AgentModelTrace,
    *,
    turn_id: str,
    sequence: int,
    through_sequence: int,
) -> ContextFlowSnapshot:
    snapshot = (
        trace.context_snapshot if isinstance(trace.context_snapshot, dict) else {}
    )
    usage = trace.usage if isinstance(trace.usage, dict) else {}
    return ContextFlowSnapshot(
        id=f"context:{trace.id}",
        turn_id=turn_id,
        model_trace_id=str(trace.id),
        sequence=sequence,
        through_sequence=through_sequence,
        compacted=bool(snapshot.get("compacted", False)),
        input_tokens=_optional_int(usage.get("input_tokens")),
        output_tokens=_optional_int(usage.get("output_tokens")),
        cached_input_tokens=_optional_int(usage.get("cached_input_tokens")),
        reasoning_tokens=_optional_int(usage.get("reasoning_tokens")),
        total_tokens=_optional_int(usage.get("total_tokens")),
        max_context_tokens=_optional_int(snapshot.get("max_context_tokens")),
        composition=[
            ContextCompositionItem.model_validate(item)
            for item in snapshot.get("composition") or []
            if isinstance(item, dict)
        ],
        created_at=trace.started_at,
    )


def _normalized_through_sequence(
    context_through_sequence: int,
    *,
    sequence_by_id: Mapping[str, int],
    entry_sequence_by_event_id: Mapping[str, int],
) -> int:
    return max(
        (
            sequence_by_id[event_id]
            for event_id, entry_sequence in entry_sequence_by_event_id.items()
            if entry_sequence <= context_through_sequence
        ),
        default=0,
    )


def _model_trace_detail(trace: AgentModelTrace) -> AgentTraceEventDetail:
    usage = trace.usage if isinstance(trace.usage, Mapping) else {}
    usage_summary = {
        key: value
        for key in (
            "input_tokens",
            "output_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "total_tokens",
        )
        if (value := _optional_int(usage.get(key))) is not None
    }
    return AgentTraceEventDetail(
        event_id=f"model:{trace.id}",
        summary={
            "category": "context",
            "provider": trace.provider,
            "model": trace.model,
            "status": trace.status,
            "wire_protocol": trace.wire_protocol,
            **usage_summary,
        },
        payload=trace.request_payload,
        result=trace.response_payload,
        schema=_tool_schemas(trace.request_payload),
        timing=_timing(
            trace.started_at,
            trace.completed_at,
            request_prepared_at=trace.request_prepared_at,
            first_byte_at=trace.first_byte_at,
        ),
    )


def _entry_detail(event_id: str, entry: AgentHarnessEntry) -> AgentTraceEventDetail:
    return AgentTraceEventDetail(
        event_id=event_id,
        summary={"category": "context", "type": entry.type},
        payload=entry.payload,
        timing=_timing(entry.created_at, entry.created_at),
    )


def _part_detail(
    event_id: str,
    entry: AgentHarnessEntry,
    part: dict[str, Any],
    *,
    entries: list[AgentHarnessEntry],
    traces: list[AgentModelTrace],
) -> AgentTraceEventDetail:
    part_type = str(part.get("type") or "unknown")
    if part_type == "tool_call":
        call_id = str(part.get("call_id") or "")
        result = _tool_result(
            entries,
            run_id=str(entry.run_id) if entry.run_id is not None else None,
            call_id=call_id,
        )
        timing = (
            _timing_values(result.get("started_at"), result.get("completed_at"))
            if result is not None
            else None
        )
        return AgentTraceEventDetail(
            event_id=event_id,
            summary={
                "category": "tool",
                "name": str(part.get("name") or "unknown"),
                "call_id": call_id,
                "status": str((result or {}).get("status") or "pending"),
            },
            payload=part.get("arguments"),
            result=(result or {}).get("output"),
            schema=_tool_schema(
                traces,
                run_id=str(entry.run_id) if entry.run_id else None,
                name=str(part.get("name") or ""),
            ),
            timing=timing,
        )
    if part_type == "tool_result":
        return AgentTraceEventDetail(
            event_id=event_id,
            summary={
                "category": "tool",
                "call_id": str(part.get("call_id") or ""),
                "status": str(part.get("status") or "completed"),
            },
            result=part.get("output"),
            timing=_timing_values(part.get("started_at"), part.get("completed_at")),
        )
    role = str(entry.payload.get("role") or "assistant")
    return AgentTraceEventDetail(
        event_id=event_id,
        summary={"category": role, "type": part_type},
        payload=part,
        timing=_timing(entry.created_at, entry.created_at),
    )


def _tool_result(
    entries: list[AgentHarnessEntry], *, run_id: str | None, call_id: str
) -> dict[str, Any] | None:
    for entry in entries:
        entry_run_id = str(entry.run_id) if entry.run_id is not None else None
        if entry_run_id != run_id:
            continue
        for part in entry.payload.get("parts") or []:
            if (
                isinstance(part, dict)
                and part.get("type") == "tool_result"
                and str(part.get("call_id") or "") == call_id
            ):
                return part
    return None


def _tool_results(
    entries: list[AgentHarnessEntry],
) -> dict[tuple[str | None, str], dict[str, Any]]:
    results: dict[tuple[str | None, str], dict[str, Any]] = {}
    for entry in entries:
        run_id = str(entry.run_id) if entry.run_id is not None else None
        for part in entry.payload.get("parts") or []:
            if not isinstance(part, dict) or part.get("type") != "tool_result":
                continue
            call_id = str(part.get("call_id") or "")
            if call_id:
                results.setdefault((run_id, call_id), part)
    return results


def _tool_schema(
    traces: list[AgentModelTrace], *, run_id: str | None, name: str
) -> Any:
    for trace in reversed(traces):
        if run_id is not None and str(trace.run_id) != run_id:
            continue
        for tool in _tools(trace.request_payload):
            function = (
                tool.get("function") if isinstance(tool.get("function"), dict) else tool
            )
            if str(function.get("name") or "") == name:
                return function.get("parameters")
    return None


def _tool_schemas(payload: Any) -> list[dict[str, Any]] | None:
    tools = _tools(payload)
    return tools or None


def _tools(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("tools"), list):
        return []
    return [item for item in payload["tools"] if isinstance(item, dict)]


def _timing(
    started_at: datetime | None,
    completed_at: datetime | None,
    *,
    request_prepared_at: datetime | None = None,
    first_byte_at: datetime | None = None,
) -> TraceTiming:
    duration_ms = None
    if started_at is not None and completed_at is not None:
        duration_ms = max(0, round((completed_at - started_at).total_seconds() * 1000))
    return TraceTiming(
        started_at=started_at,
        request_prepared_at=request_prepared_at,
        first_byte_at=first_byte_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
    )


def _timing_values(started_at: Any, completed_at: Any) -> TraceTiming | None:
    start = _datetime(started_at)
    end = _datetime(completed_at)
    if start is None and end is None:
        return None
    return _timing(start, end)


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _model_summary(snapshot: Any) -> TraceModelSummary:
    target = snapshot.get("target") if isinstance(snapshot, Mapping) else {}
    if not isinstance(target, Mapping):
        target = {}
    provider = str(
        target.get("provider_kind") or snapshot.get("provider")
        if isinstance(snapshot, Mapping)
        else "unknown"
    )
    model = str(
        target.get("model_name") or snapshot.get("model")
        if isinstance(snapshot, Mapping)
        else "unknown"
    )
    return TraceModelSummary(provider=provider, model=model, display_name=model)


def _prompt_content(snapshot: Any) -> str:
    if isinstance(snapshot, str):
        return snapshot
    if isinstance(snapshot, Mapping):
        content = snapshot.get("content") or snapshot.get("system")
        return content if isinstance(content, str) else _json_text(snapshot)
    return ""


def _model_trace_summary(trace: AgentModelTrace) -> str:
    summary = f"{trace.provider}/{trace.model}"
    usage = trace.usage if isinstance(trace.usage, Mapping) else {}
    input_tokens = _optional_int(usage.get("input_tokens"))
    if input_tokens is not None:
        return f"{summary} · {input_tokens} input tokens"
    return summary


def _part_first_line(part: Mapping[str, Any]) -> str:
    part_type = part.get("type")
    if part_type in {"text", "reasoning_summary", "reasoning_trace"}:
        return _first_line(str(part.get("text") or ""))
    if part_type == "tool_call":
        name = str(part.get("name") or "tool")
        arguments = part.get("arguments")
        rendered_arguments = _json_text(arguments if arguments is not None else {})
        return _truncate(f"{name}({rendered_arguments})")
    if part_type == "tool_result":
        return _raw_first_line(part.get("output"))
    for key in ("filename", "label", "display_text"):
        if isinstance(part.get(key), str):
            return _first_line(str(part[key]))
    return _raw_first_line(part)


def _raw_first_line(value: Any) -> str:
    if isinstance(value, Mapping):
        if value.get("type") == "text" and isinstance(value.get("text"), str):
            return _first_line(value["text"])
        if value.get("type") == "json":
            return _raw_first_line(value.get("value"))
    return _first_line(value if isinstance(value, str) else _json_text(value))


def _first_line(value: str) -> str:
    return value.splitlines()[0] if value else ""


def _truncate(value: str, *, limit: int = 180) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1]}…"


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _entry_title(entry_type: str) -> str:
    return {
        "compaction": "Compaction",
        "context_update": "Context update",
        "interaction_request": "Interaction request",
        "interaction_response": "Interaction response",
        "notice": "Notice",
        "plan": "Plan",
    }.get(entry_type, "Context")


def _part_title(part_type: str, *, role: str, part: Mapping[str, Any]) -> str:
    if part_type == "tool_call":
        return str(part.get("display_name") or part.get("name") or "Tool")
    if part_type == "tool_result":
        return "Tool result"
    if part_type == "reasoning_trace":
        return "Reasoning"
    return {"user": "User", "assistant": "Assistant", "tool": "Tool"}.get(
        role, "Context"
    )


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


__all__ = ["AgentTraceAdapter", "CompleteHarnessTraceAdapter"]
