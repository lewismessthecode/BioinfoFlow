from __future__ import annotations

import pytest

from app.services.gpu_policy import GpuDeviceRef, resolve_gpu_policy


DEVICES = (
    GpuDeviceRef(index=0, uuid="GPU-a"),
    GpuDeviceRef(index=1, uuid="GPU-b"),
)


def test_auto_selects_every_discovered_uuid() -> None:
    policy = resolve_gpu_policy("auto", "all", DEVICES)

    assert policy.state == "ready"
    assert policy.selected_uuids == ("GPU-a", "GPU-b")


def test_manual_resolves_indices_to_stable_uuids() -> None:
    policy = resolve_gpu_policy("manual", "1", DEVICES)

    assert policy.selected_uuids == ("GPU-b",)


@pytest.mark.parametrize("selectors", ["GPU-missing", "GPU-a,GPU-a", "all"])
def test_invalid_manual_policy_fails_closed(selectors: str) -> None:
    policy = resolve_gpu_policy("manual", selectors, DEVICES)

    assert policy.state == "policy_invalid"
    assert policy.selected_uuids == ()


def test_disabled_skips_selection() -> None:
    policy = resolve_gpu_policy("disabled", "all", DEVICES)

    assert policy.state == "disabled"
    assert policy.selected_uuids == ()
