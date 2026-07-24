from __future__ import annotations

import asyncio

import pytest

from app.services.gpu_service import GpuInfo, GpuService
from app.services.gpu_probe import GpuProbeError, ProbedGpu


class FakeProcess:
    def __init__(
        self, *, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0
    ):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, self._stderr


class FakeGpuProbe:
    def __init__(self, devices: list[ProbedGpu]):
        self.devices = devices
        self.inventory_calls = 0

    async def inventory(self) -> list[ProbedGpu]:
        self.inventory_calls += 1
        return self.devices


class BlockingGpuProbe(FakeGpuProbe):
    def __init__(self, devices: list[ProbedGpu]):
        super().__init__(devices)
        self.release = asyncio.Event()

    async def inventory(self) -> list[ProbedGpu]:
        self.inventory_calls += 1
        await self.release.wait()
        return self.devices


class FlakyGpuProbe(FakeGpuProbe):
    async def inventory(self) -> list[ProbedGpu]:
        self.inventory_calls += 1
        if self.inventory_calls > 1:
            raise GpuProbeError("temporary probe failure")
        return self.devices


@pytest.mark.asyncio
async def test_get_status_applies_manual_uuid_selection_to_docker_inventory() -> None:
    probe = FakeGpuProbe(
        [
            ProbedGpu("GPU-a", 0, "NVIDIA H20", 97871, 96000, "550.54", "9.0"),
            ProbedGpu("GPU-b", 1, "NVIDIA H20", 97871, 95000, "550.54", "9.0"),
        ]
    )
    service = GpuService(
        probe=probe,
        mode="manual",
        selectors="GPU-b",
        cache_seconds=30,
    )

    status = await service.get_status()

    assert status.state == "ready"
    assert status.detected_count == 2
    assert status.selected_count == 1
    assert status.selected_gpu_uuids == ("GPU-b",)
    assert [gpu.selected for gpu in status.gpus] == [False, True]
    assert status.usable_for_gpu_workflows is True
    assert probe.inventory_calls == 1


@pytest.mark.asyncio
async def test_concurrent_status_calls_share_one_probe() -> None:
    probe = BlockingGpuProbe(
        [ProbedGpu("GPU-a", 0, "NVIDIA H20", 97871, 96000, "550.54", "9.0")]
    )
    service = GpuService(probe=probe, mode="auto", selectors="all", cache_seconds=30)

    first_task = asyncio.create_task(service.get_status())
    second_task = asyncio.create_task(service.get_status())
    await asyncio.sleep(0)
    probe.release.set()
    first, second = await asyncio.gather(first_task, second_task)

    assert first == second
    assert probe.inventory_calls == 1


@pytest.mark.asyncio
async def test_manual_index_is_exposed_as_uuid_after_inventory_resolution() -> None:
    probe = FakeGpuProbe(
        [ProbedGpu("GPU-b", 1, "NVIDIA H20", 97871, 95000, "550.54", "9.0")]
    )
    service = GpuService(probe=probe, mode="manual", selectors="1", cache_seconds=30)

    await service.get_status()

    assert service.selected_visible_devices() == "GPU-b"


@pytest.mark.asyncio
async def test_auto_mode_exposes_devices_only_after_successful_docker_inventory() -> (
    None
):
    probe = FakeGpuProbe(
        [ProbedGpu("GPU-a", 0, "NVIDIA H20", 97871, 96000, "550.54", "9.0")]
    )
    service = GpuService(probe=probe, mode="auto", selectors="all", cache_seconds=30)

    assert service.selected_visible_devices() is None

    await service.get_status()

    assert service.selected_visible_devices() == "all"


@pytest.mark.asyncio
async def test_recent_successful_inventory_is_returned_as_stale_on_refresh_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = 0.0
    monkeypatch.setattr("app.services.gpu_service.time.monotonic", lambda: clock)
    probe = FlakyGpuProbe(
        [ProbedGpu("GPU-a", 0, "NVIDIA H20", 97871, 96000, "550.54", "9.0")]
    )
    service = GpuService(probe=probe, mode="auto", selectors="all", cache_seconds=10)

    fresh = await service.get_status()
    clock = 11.0
    stale = await service.get_status()

    assert fresh.stale is False
    assert stale.stale is True
    assert stale.selected_gpu_uuids == ("GPU-a",)
    assert stale.error == "temporary probe failure"

    clock = 21.0
    failed = await service.get_status()

    assert failed.state == "probe_failed"
    assert service.selected_visible_devices() is None


@pytest.mark.asyncio
async def test_get_status_returns_apple_silicon_when_nvidia_is_missing() -> None:
    service = GpuService()
    service._nvidia_smi = None

    async def fake_detect_apple_silicon() -> GpuInfo:
        return GpuInfo(
            index=0,
            name="Apple M3 Max",
            memory_total_mb=49152,
            memory_free_mb=0,
            driver_version="N/A",
            cuda_version=None,
            compute_capability=None,
            gpu_type="Apple Silicon",
        )

    service._detect_apple_silicon = fake_detect_apple_silicon  # type: ignore[method-assign]

    status = await service.get_status()

    assert status.available is True
    assert status.detected is True
    assert status.nvidia_smi_found is False
    assert status.docker_nvidia_runtime is False
    assert status.runtime_visible_to_backend is True
    assert status.usable_for_gpu_workflows is False
    assert status.parabricks_compatible is False
    assert len(status.gpus) == 1
    assert status.gpus[0].gpu_type == "Apple Silicon"
    assert "Apple Silicon GPU detected automatically" in status.recommendation


@pytest.mark.asyncio
async def test_get_status_reports_nvidia_runtime_when_nvidia_smi_is_missing() -> None:
    service = GpuService()
    service._nvidia_smi = None

    async def fake_detect_apple_silicon() -> None:
        return None

    async def fake_check_docker_nvidia() -> bool:
        return True

    service._detect_apple_silicon = fake_detect_apple_silicon  # type: ignore[method-assign]
    service._check_docker_nvidia = fake_check_docker_nvidia  # type: ignore[method-assign]

    status = await service.get_status()

    assert status.available is False
    assert status.detected is False
    assert status.nvidia_smi_found is False
    assert status.docker_nvidia_runtime is True
    assert status.runtime_visible_to_backend is False
    assert status.usable_for_gpu_workflows is False
    assert status.gpus == []
    assert "NVIDIA container runtime is configured" in status.recommendation
    assert "GPU passthrough" in status.recommendation


@pytest.mark.asyncio
async def test_get_status_marks_parabricks_ready_when_gpu_and_runtime_are_available() -> (
    None
):
    service = GpuService()
    service._nvidia_smi = "nvidia-smi"

    async def fake_detect_gpus() -> list[GpuInfo]:
        return [
            GpuInfo(
                index=0,
                name="NVIDIA RTX 6000 Ada",
                memory_total_mb=49152,
                memory_free_mb=32768,
                driver_version="550.54",
                cuda_version="12.4",
                compute_capability="8.9",
            )
        ]

    async def fake_check_docker_nvidia() -> bool:
        return True

    service._detect_gpus = fake_detect_gpus  # type: ignore[method-assign]
    service._check_docker_nvidia = fake_check_docker_nvidia  # type: ignore[method-assign]

    status = await service.get_status()

    assert status.available is True
    assert status.detected is True
    assert status.nvidia_smi_found is True
    assert status.docker_nvidia_runtime is True
    assert status.runtime_visible_to_backend is True
    assert status.usable_for_gpu_workflows is True
    assert status.parabricks_compatible is True
    assert status.error is None
    assert "Ready for Parabricks WGS" in status.recommendation


@pytest.mark.asyncio
async def test_get_gpu_metrics_parses_na_fields_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = GpuService()
    service._nvidia_smi = "nvidia-smi"

    async def fake_create_subprocess_exec(*args, **kwargs):
        del args, kwargs
        return FakeProcess(
            stdout=(
                b"0, 75, [N/A], 4096, 24576, [N/A], 120.5\n"
                b"1, [N/A], 33, [N/A], 16384, 61, [N/A]\n"
            ),
            returncode=0,
        )

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    metrics = await service.get_gpu_metrics()

    assert metrics == [
        {
            "index": 0,
            "gpu_utilization_pct": 75,
            "memory_utilization_pct": None,
            "memory_used_mb": 4096,
            "memory_total_mb": 24576,
            "temperature_c": None,
            "power_draw_w": 120.5,
        },
        {
            "index": 1,
            "gpu_utilization_pct": None,
            "memory_utilization_pct": 33,
            "memory_used_mb": None,
            "memory_total_mb": 16384,
            "temperature_c": 61,
            "power_draw_w": None,
        },
    ]
