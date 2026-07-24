from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GpuDeviceRef:
    index: int
    uuid: str


@dataclass(frozen=True)
class GpuPolicy:
    mode: str
    state: str
    selected_uuids: tuple[str, ...]
    error: str | None = None


def resolve_gpu_policy(
    mode: str,
    selectors: str,
    devices: tuple[GpuDeviceRef, ...],
) -> GpuPolicy:
    normalized_mode = mode.strip().lower()
    if normalized_mode == "disabled":
        return GpuPolicy("disabled", "disabled", ())
    if normalized_mode == "auto":
        return GpuPolicy("auto", "ready", tuple(device.uuid for device in devices))
    if normalized_mode != "manual":
        return GpuPolicy(normalized_mode, "policy_invalid", (), "Unknown GPU mode")

    tokens = tuple(token.strip() for token in selectors.split(",") if token.strip())
    by_uuid = {device.uuid: device.uuid for device in devices}
    by_index = {str(device.index): device.uuid for device in devices}
    resolved = tuple(
        by_uuid.get(token) or by_index.get(token) or "" for token in tokens
    )
    if (
        not tokens
        or "all" in tokens
        or "" in resolved
        or len(set(resolved)) != len(resolved)
    ):
        return GpuPolicy("manual", "policy_invalid", (), "Invalid GPU selection")
    return GpuPolicy("manual", "ready", resolved)
