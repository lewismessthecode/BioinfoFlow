"""Tests for slot-based admission control (replaced old resource estimation tests)."""

from __future__ import annotations

from app.scheduler.slots import SlotTracker


def test_slot_tracker_initial_state():
    tracker = SlotTracker(total=8)
    assert tracker.total == 8
    assert tracker.used == 0
    assert tracker.available == 8


def test_slot_tracker_acquire_and_release():
    tracker = SlotTracker(total=4)
    tracker.acquire(2)
    assert tracker.used == 2
    assert tracker.available == 2

    tracker.release(2)
    assert tracker.used == 0
    assert tracker.available == 4


def test_slot_tracker_can_admit():
    tracker = SlotTracker(total=4)
    assert tracker.can_admit(4) is True
    assert tracker.can_admit(5) is False

    tracker.acquire(3)
    assert tracker.can_admit(1) is True
    assert tracker.can_admit(2) is False


def test_slot_tracker_release_clamps_to_zero():
    tracker = SlotTracker(total=4)
    tracker.release(10)
    assert tracker.used == 0


def test_slot_tracker_sync_from_db():
    tracker = SlotTracker(total=8)
    tracker.sync_from_db(5)
    assert tracker.used == 5
    assert tracker.available == 3
