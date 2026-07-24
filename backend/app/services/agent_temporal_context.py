from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


TEMPORAL_CONTEXT_METADATA_KEY = "_temporal_context"
_TIME_ZONE_RE = re.compile(r"^[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*$")
_UTC_TIME_ZONE = "Etc/UTC"


def resolve_temporal_context(
    *,
    turn_metadata: dict[str, Any] | None,
    previous_context: dict[str, str] | None,
    session_metadata: dict[str, Any] | None,
    now: datetime,
) -> dict[str, str]:
    time_zone_name = _resolved_time_zone(
        turn_metadata,
        previous_context,
        session_metadata,
    )
    utc_now = _as_utc(now)
    return {
        "current_date": utc_now.astimezone(ZoneInfo(time_zone_name)).date().isoformat(),
        "timezone": time_zone_name,
    }


def latest_temporal_context(messages: list[Any]) -> dict[str, str] | None:
    for message in reversed(messages):
        if getattr(message, "status", "committed") != "committed":
            continue
        context = temporal_context_from_message_metadata(
            getattr(message, "message_metadata", None)
        )
        if context is not None:
            return context
    return None


def temporal_context_from_message_metadata(
    metadata: dict[str, Any] | None,
) -> dict[str, str] | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(TEMPORAL_CONTEXT_METADATA_KEY)
    if not isinstance(value, dict):
        return None
    current_date = value.get("current_date")
    time_zone_name = value.get("timezone")
    if not isinstance(current_date, str) or not isinstance(time_zone_name, str):
        return None
    try:
        if date.fromisoformat(current_date).isoformat() != current_date:
            return None
    except ValueError:
        return None
    if _valid_time_zone(time_zone_name) is None:
        return None
    return {"current_date": current_date, "timezone": time_zone_name}


def message_metadata_with_temporal_context(
    metadata: dict[str, Any] | None,
    temporal_context: dict[str, str] | None,
) -> dict[str, Any]:
    merged = dict(metadata or {})
    if temporal_context is not None:
        merged[TEMPORAL_CONTEXT_METADATA_KEY] = dict(temporal_context)
    return merged


def render_temporal_context(temporal_context: dict[str, str]) -> str:
    return (
        "<environment_context>\n"
        f"  <current_date>{temporal_context['current_date']}</current_date>\n"
        f"  <timezone>{temporal_context['timezone']}</timezone>\n"
        "</environment_context>"
    )


def _resolved_time_zone(
    turn_metadata: dict[str, Any] | None,
    previous_context: dict[str, str] | None,
    session_metadata: dict[str, Any] | None,
) -> str:
    candidates: list[Any] = []
    if isinstance(turn_metadata, dict):
        candidates.append(turn_metadata.get("client_timezone"))
    if isinstance(previous_context, dict):
        candidates.append(previous_context.get("timezone"))
    if isinstance(session_metadata, dict):
        candidates.append(session_metadata.get("client_timezone"))
    for candidate in candidates:
        if validated := _valid_time_zone(candidate):
            return validated
    return _UTC_TIME_ZONE


def _valid_time_zone(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 100
        or not _TIME_ZONE_RE.fullmatch(normalized)
    ):
        return None
    try:
        ZoneInfo(normalized)
    except (ValueError, ZoneInfoNotFoundError):
        return None
    return normalized


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
