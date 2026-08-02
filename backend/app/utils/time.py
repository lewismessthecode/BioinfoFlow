from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def duration_seconds(
    started_at: datetime | None, completed_at: datetime | None
) -> int | None:
    if not started_at or not completed_at:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    return int((completed_at - started_at).total_seconds())
