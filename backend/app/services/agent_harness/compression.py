from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

from app.services.agent_harness.history import HistoryEntry
from app.services.model_runtime.errors import ModelError


T = TypeVar("T")

SUMMARY_CHAR_BUDGET = 24_000
SUMMARY_TOKEN_BUDGET = 8_000
_SUMMARY_OMISSION = "\n\n[Earlier summary detail omitted within the hard budget.]\n\n"


@dataclass(frozen=True)
class CompactionPlan:
    through_sequence: int
    payload: dict[str, Any]


class DeterministicCompactor:
    """Build a stable continuity entry without mutating permanent history."""

    def __init__(
        self,
        *,
        preserve_recent_entries: int = 12,
        item_chars: int = 600,
        summary_char_budget: int = SUMMARY_CHAR_BUDGET,
        summary_token_budget: int = SUMMARY_TOKEN_BUDGET,
    ):
        if preserve_recent_entries < 1:
            raise ValueError("preserve_recent_entries must be positive")
        if item_chars < 1:
            raise ValueError("item_chars must be positive")
        if summary_char_budget < 1 or summary_token_budget < 1:
            raise ValueError("summary budgets must be positive")
        self.preserve_recent_entries = preserve_recent_entries
        self.item_chars = item_chars
        self.summary_char_budget = summary_char_budget
        self.summary_token_budget = summary_token_budget

    def plan(
        self,
        entries: Iterable[HistoryEntry | Mapping[str, Any]],
        *,
        threshold_chars: int,
    ) -> CompactionPlan | None:
        ordered = sorted(entries, key=_sequence)
        if len(ordered) <= self.preserve_recent_entries:
            return None
        size = len(json.dumps(ordered, default=_json_default, ensure_ascii=False))
        if size <= threshold_chars:
            return None
        candidates = ordered[: -self.preserve_recent_entries]
        candidates = _avoid_partial_tool_group(candidates, ordered[len(candidates) :])
        candidates = _drop_entries_covered_by_latest_compaction(candidates)
        if not candidates:
            return None
        summary = self._summary(candidates)
        if not summary:
            return None
        end = _sequence(candidates[-1])
        return CompactionPlan(
            through_sequence=end,
            payload={
                "summary": summary,
                "through_sequence": end,
            },
        )

    def _summary(self, entries: list[HistoryEntry | Mapping[str, Any]]) -> str:
        goals: list[str] = []
        observations: list[str] = []
        decisions: list[str] = []
        prior_summaries: list[str] = []
        for entry in entries:
            entry_type = _entry_type(entry)
            payload = _payload(entry)
            if entry_type == "message":
                role = payload.get("role")
                content = _text(payload)
                if role == "user" and content:
                    goals.append(content)
                elif role in {"assistant", "tool"} and content:
                    observations.append(f"{role}: {content}")
                if role == "assistant":
                    calls = _typed_tool_calls(payload)
                    if isinstance(calls, list):
                        for call in calls:
                            if not isinstance(call, Mapping):
                                continue
                            name = call.get("name")
                            arguments = call.get("arguments")
                            if isinstance(name, str) and isinstance(arguments, Mapping):
                                observations.append(
                                    f"{name}: "
                                    + json.dumps(
                                        dict(arguments),
                                        ensure_ascii=False,
                                        sort_keys=True,
                                        default=str,
                                    )
                                )
            elif entry_type in {"interaction_request", "interaction_response"}:
                content = _interaction_text(payload)
                if content:
                    decisions.append(content)
            elif entry_type == "compaction":
                prior = payload.get("summary")
                if isinstance(prior, str) and prior.strip():
                    prior_summaries.append(f"prior summary: {prior.strip()}")
            elif entry_type == "notice":
                content = _text(payload)
                if content:
                    observations.append(f"notice: {content}")
        sections: tuple[tuple[str, list[str], bool], ...] = (
            ("## Prior conversation summary", prior_summaries, False),
            ("## Goal and user requests", goals, True),
            ("## Work completed and observations", observations, True),
            ("## User decisions and interactions", decisions, True),
        )
        rendered = "\n\n".join(
            f"{title}\n"
            + "\n".join(
                f"- {self._truncate(item) if truncate_items else self._normalize(item)}"
                for item in items
            )
            for title, items, truncate_items in sections
            if items
        )
        return self._fit_summary_budget(rendered)

    def _truncate(self, text: str) -> str:
        compact = self._normalize(text)
        if len(compact) <= self.item_chars:
            return compact
        return compact[: self.item_chars - 1] + "…"

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.split())

    def _fit_summary_budget(self, summary: str) -> str:
        summary = _fit_middle_by_chars(summary, self.summary_char_budget)
        if len(summary.encode("utf-8")) <= self.summary_token_budget:
            return summary
        omission_bytes = len(_SUMMARY_OMISSION.encode("utf-8"))
        remaining = self.summary_token_budget - omission_bytes
        if remaining < 2:
            return summary.encode("utf-8")[: self.summary_token_budget].decode(
                "utf-8", errors="ignore"
            )
        head_bytes = remaining // 2
        tail_bytes = remaining - head_bytes
        encoded = summary.encode("utf-8")
        head = encoded[:head_bytes].decode("utf-8", errors="ignore").rstrip()
        tail = encoded[-tail_bytes:].decode("utf-8", errors="ignore").lstrip()
        return head + _SUMMARY_OMISSION + tail


def _fit_middle_by_chars(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    remaining = max_chars - len(_SUMMARY_OMISSION)
    if remaining < 2:
        return text[:max_chars]
    head = remaining // 2
    tail = remaining - head
    return text[:head].rstrip() + _SUMMARY_OMISSION + text[-tail:].lstrip()


async def invoke_with_context_overflow_retry(
    *,
    invoke: Callable[[], Awaitable[T]],
    compact: Callable[[], Awaitable[bool]],
) -> T:
    """Retry one model invocation once, and only after durable compaction."""

    try:
        return await invoke()
    except ModelError as exc:
        if not is_context_overflow(exc) or not await compact():
            raise
    return await invoke()


def is_context_overflow(exc: ModelError) -> bool:
    if exc.category != "invalid_request":
        return False
    provider_code = (exc.provider_code or "").lower()
    message = exc.message.lower()
    return provider_code in {
        "context_length_exceeded",
        "context_window_exceeded",
        "prompt_too_long",
    } or any(
        marker in message
        for marker in (
            "maximum context length",
            "context length exceeded",
            "context window exceeded",
            "prompt is too long",
            "too many tokens",
        )
    )


def _json_default(value: Any) -> Any:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return vars(value)


def _sequence(entry: HistoryEntry | Mapping[str, Any]) -> int:
    value = entry.get("sequence") if isinstance(entry, Mapping) else entry.sequence
    return int(value)


def _entry_type(entry: HistoryEntry | Mapping[str, Any]) -> str:
    if isinstance(entry, Mapping):
        value = entry.get("entry_type", entry.get("type"))
    else:
        value = entry.type
    return str(value)


def _payload(entry: HistoryEntry | Mapping[str, Any]) -> Mapping[str, Any]:
    value = entry.get("payload") if isinstance(entry, Mapping) else entry.payload
    if isinstance(value, Mapping):
        return value
    model_dump = getattr(value, "model_dump", None)
    return model_dump(mode="python") if callable(model_dump) else {}


def _text(payload: Mapping[str, Any]) -> str:
    for key in ("parts", "text", "message", "summary"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if key == "parts" and isinstance(value, list):
            text = "\n".join(
                part_text
                for part in value
                if isinstance(part, Mapping) and (part_text := _message_part_text(part))
            ).strip()
            if text:
                return text
    return ""


def _message_part_text(part: Mapping[str, Any]) -> str:
    if part.get("type") == "text" and isinstance(part.get("text"), str):
        return str(part["text"])
    if part.get("type") != "tool_result":
        return ""
    output = part.get("output")
    if not isinstance(output, Mapping):
        return str(part.get("error") or "")
    output_type = output.get("type")
    if output_type == "text" and isinstance(output.get("text"), str):
        return str(output["text"])
    if output_type == "json":
        return json.dumps(output.get("value"), ensure_ascii=False, default=str)
    if output_type == "content_parts" and isinstance(output.get("parts"), list):
        return "\n".join(
            str(item.get("text"))
            for item in output["parts"]
            if isinstance(item, Mapping)
            and item.get("type") in {"text", "reasoning_summary", "reasoning_trace"}
            and isinstance(item.get("text"), str)
        )
    return ""


def _typed_tool_calls(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    parts = payload.get("parts")
    if not isinstance(parts, list):
        return []
    return [
        item
        for item in parts
        if isinstance(item, Mapping) and item.get("type") == "tool_call"
    ]


def _interaction_text(payload: Mapping[str, Any]) -> str:
    for key in ("request", "response"):
        value = payload.get(key)
        if value is not None:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return ""


def _avoid_partial_tool_group(
    candidates: list[HistoryEntry | Mapping[str, Any]],
    recent: list[HistoryEntry | Mapping[str, Any]],
) -> list[HistoryEntry | Mapping[str, Any]]:
    pending_call_ids = {
        str(_tool_result_call_id(_payload(entry)))
        for entry in recent
        if _entry_type(entry) == "message"
        and _payload(entry).get("role") == "tool"
        and _tool_result_call_id(_payload(entry))
    }
    if not pending_call_ids:
        return candidates
    for index in range(len(candidates) - 1, -1, -1):
        entry = candidates[index]
        payload = _payload(entry)
        if _entry_type(entry) != "message" or payload.get("role") != "assistant":
            continue
        calls = _typed_tool_calls(payload)
        if not calls:
            continue
        produced = {
            str(call.get("call_id"))
            for call in calls
            if isinstance(call, Mapping) and call.get("call_id")
        }
        if produced & pending_call_ids:
            return candidates[:index]
    return candidates


def _tool_result_call_id(payload: Mapping[str, Any]) -> str | None:
    parts = payload.get("parts")
    if not isinstance(parts, list):
        return None
    for part in parts:
        if isinstance(part, Mapping) and part.get("type") == "tool_result":
            call_id = part.get("call_id")
            return str(call_id) if call_id else None
    return None


def _drop_entries_covered_by_latest_compaction(
    entries: list[HistoryEntry | Mapping[str, Any]],
) -> list[HistoryEntry | Mapping[str, Any]]:
    for entry in reversed(entries):
        if _entry_type(entry) != "compaction":
            continue
        through_sequence = _payload(entry).get("through_sequence")
        if isinstance(through_sequence, int) and not isinstance(through_sequence, bool):
            return [item for item in entries if _sequence(item) > through_sequence]
    return entries
