"""Slot-based admission control for the run scheduler.

SlotTracker is an in-memory cache — NOT the source of truth.
On restart, ``used`` is rebuilt from the DB via ``sync_from_db()``.
"""

from __future__ import annotations


class SlotTracker:
    """Tracks slot usage for weight-based admission control."""

    def __init__(self, total: int) -> None:
        self._total = max(1, total)
        self._used = 0

    @property
    def total(self) -> int:
        return self._total

    @property
    def used(self) -> int:
        return self._used

    @property
    def available(self) -> int:
        return max(0, self._total - self._used)

    def can_admit(self, weight: int) -> bool:
        return self._used + weight <= self._total

    def try_acquire(self, weight: int) -> bool:
        """Atomically reserve ``weight`` slots if they fit.

        Used by workers to close the check-then-acquire race: two
        workers could each pass a stale ``available`` snapshot through
        the queue claim lock and then both call ``acquire`` against
        the same view, over-subscribing the pool. Because this method
        runs synchronously on the asyncio thread, the admission check
        and bump happen without an interleaving ``await``.
        """
        if not self.can_admit(weight):
            return False
        self._used += weight
        return True

    def acquire(self, weight: int) -> None:
        self._used += weight

    def release(self, weight: int) -> None:
        self._used = max(0, self._used - weight)

    def sync_from_db(self, used: int) -> None:
        """Rebuild used count from DB (called on recovery)."""
        self._used = max(0, used)
