from __future__ import annotations

import asyncio

import pytest

from app.services.gpu_service import GpuInfo, GpuService


class FakeProcess:
    def __init__(
        self, *, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0
    ):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, self._stderr


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
