from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.scheduler.monitor import ResourceMonitor
from app.scheduler.resources import SystemResources


class FakeGpuService:
    async def get_status(self):
        return SimpleNamespace(
            gpus=[
                SimpleNamespace(selected=False, memory_free_mb=64000),
                SimpleNamespace(selected=True, memory_free_mb=49152),
            ]
        )


@pytest.mark.asyncio
async def test_resource_monitor_uses_selected_shared_gpu_inventory(monkeypatch):
    base = SystemResources(
        cpu_count=8,
        cpu_available=6.0,
        memory_total_gb=32.0,
        memory_available_gb=20.0,
        disk_total_gb=200.0,
        disk_available_gb=150.0,
    )
    monitor = ResourceMonitor(workspace_path="/tmp", gpu_service=FakeGpuService())
    monkeypatch.setattr(monitor, "_sample_system_sync", lambda: base)

    snapshot = await monitor._sample()

    assert snapshot.gpu_count == 1
    assert snapshot.gpu_memory_gb == 48.0


def test_resource_monitor_samples_system_resources(monkeypatch):
    gib = 1024**3
    sampled_at = datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        "app.scheduler.monitor.psutil.virtual_memory",
        lambda: SimpleNamespace(total=64 * gib, available=24 * gib),
    )
    monkeypatch.setattr(
        "app.scheduler.monitor.psutil.disk_usage",
        lambda path: SimpleNamespace(total=500 * gib, free=120 * gib),
    )

    def _cpu_count_stub(logical=True):
        del logical
        return 16

    monkeypatch.setattr(
        "app.scheduler.monitor.psutil.cpu_count",
        _cpu_count_stub,
    )
    monkeypatch.setattr(
        "app.scheduler.monitor.psutil.getloadavg",
        lambda: (2.5, 2.0, 1.5),
    )
    monkeypatch.setattr(
        ResourceMonitor,
        "_detect_gpu",
        lambda self: (2, 31.5),
    )
    monkeypatch.setattr("app.scheduler.monitor._utc_now", lambda: sampled_at)

    snapshot = ResourceMonitor(workspace_path="/tmp")._sample_sync()

    assert snapshot == SystemResources(
        cpu_count=16,
        cpu_available=13.5,
        memory_total_gb=64.0,
        memory_available_gb=24.0,
        disk_total_gb=500.0,
        disk_available_gb=120.0,
        gpu_count=2,
        gpu_memory_gb=31.5,
        sampled_at=sampled_at,
    )


@pytest.mark.asyncio
async def test_resource_monitor_start_refreshes_snapshot_in_background(monkeypatch):
    first = SystemResources(
        cpu_count=8,
        cpu_available=6.0,
        memory_total_gb=32.0,
        memory_available_gb=20.0,
        disk_total_gb=200.0,
        disk_available_gb=150.0,
    )
    refreshed = SystemResources(
        cpu_count=8,
        cpu_available=4.0,
        memory_total_gb=32.0,
        memory_available_gb=18.0,
        disk_total_gb=200.0,
        disk_available_gb=140.0,
    )
    seen_refresh = asyncio.Event()
    samples = [first, refreshed]

    monitor = ResourceMonitor(sample_interval=0.01)

    async def fake_sample() -> SystemResources:
        snapshot = samples.pop(0) if samples else refreshed
        if snapshot == refreshed:
            seen_refresh.set()
        return snapshot

    monkeypatch.setattr(monitor, "_sample", fake_sample)

    await monitor.start()
    try:
        await asyncio.wait_for(seen_refresh.wait(), timeout=0.2)
        assert monitor.current() == refreshed
    finally:
        await monitor.stop()


@pytest.mark.asyncio
async def test_resource_monitor_start_tolerates_sampling_failures(monkeypatch):
    monitor = ResourceMonitor(sample_interval=0.01)
    refreshed = SystemResources(
        cpu_count=8,
        cpu_available=5.0,
        memory_total_gb=32.0,
        memory_available_gb=20.0,
        disk_total_gb=200.0,
        disk_available_gb=150.0,
    )
    calls = 0
    seen_refresh = asyncio.Event()

    async def flaky_sample() -> SystemResources:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("sampling failed")
        seen_refresh.set()
        return refreshed

    monkeypatch.setattr(monitor, "_sample", flaky_sample)

    await monitor.start()
    try:
        await asyncio.wait_for(seen_refresh.wait(), timeout=0.2)
        assert monitor.current() == refreshed
    finally:
        await monitor.stop()
