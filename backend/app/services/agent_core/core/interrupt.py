from __future__ import annotations


def is_interrupt_requested(turn) -> bool:
    return getattr(turn, "interrupt_requested_at", None) is not None
