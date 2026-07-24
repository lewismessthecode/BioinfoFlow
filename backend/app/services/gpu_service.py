"""
GPU Detection Service

Detects NVIDIA GPUs and Apple Silicon, and checks compatibility for Parabricks WGS analysis.
"""

from __future__ import annotations

import asyncio
import os
import platform
import re
import shutil
import time
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.docker_service import DockerService
from app.services.gpu_policy import GpuDeviceRef, resolve_gpu_policy
from app.services.gpu_probe import (
    DockerGpuProbe,
    GpuDockerUnavailable,
    GpuProbeError,
    GpuToolkitUnavailable,
    ProbedGpu,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GpuInfo:
    """Information about a detected GPU."""

    index: int
    name: str
    memory_total_mb: int
    memory_free_mb: int
    driver_version: str
    cuda_version: str | None
    compute_capability: str | None
    gpu_type: str = "NVIDIA"  # "NVIDIA" or "Apple Silicon"
    uuid: str = ""
    selected: bool = False


@dataclass
class GpuStatus:
    """Overall GPU status for the system."""

    available: bool
    detected: bool
    nvidia_smi_found: bool
    docker_nvidia_runtime: bool
    runtime_visible_to_backend: bool
    usable_for_gpu_workflows: bool
    gpus: list[GpuInfo]
    parabricks_compatible: bool
    recommendation: str
    error: str | None = None
    mode: str = "auto"
    state: str = "ready"
    container_toolkit_available: bool = False
    selected_gpu_uuids: tuple[str, ...] = ()
    stale: bool = False

    @property
    def detected_count(self) -> int:
        return len(self.gpus)

    @property
    def selected_count(self) -> int:
        return len(self.selected_gpu_uuids)


# Minimum VRAM required for Parabricks low-memory mode (16GB)
PARABRICKS_MIN_VRAM_MB = 16000
NVIDIA_SMI_PATHS = (
    "/usr/bin/nvidia-smi",
    "/usr/local/bin/nvidia-smi",
    "/usr/local/nvidia/bin/nvidia-smi",
    "/usr/local/cuda/bin/nvidia-smi",
)


def _find_nvidia_smi() -> str | None:
    if path := shutil.which("nvidia-smi"):
        return path
    for path in NVIDIA_SMI_PATHS:
        if Path(path).exists():
            return path
    return None


class GpuService:
    """Service for detecting and checking GPU capabilities."""

    def __init__(
        self,
        *,
        probe: Any | None = None,
        mode: str | None = None,
        selectors: str | None = None,
        cache_seconds: float | None = None,
    ) -> None:
        self._nvidia_smi = _find_nvidia_smi()
        self._mode = mode or settings.bioinfoflow_gpu_mode
        self._selectors = selectors or settings.bioinfoflow_gpu_devices
        self._cache_seconds = (
            cache_seconds
            if cache_seconds is not None
            else settings.gpu_inventory_cache_seconds
        )
        self._status_lock = asyncio.Lock()
        self._cached_status: GpuStatus | None = None
        self._cached_at = 0.0
        if probe is not None:
            self._probe = probe
        elif platform.system() == "Linux" and Path("/.dockerenv").exists():
            self._probe = DockerGpuProbe(
                client=DockerService().client,
                hostname=os.getenv("HOSTNAME"),
                timeout=settings.gpu_probe_timeout_seconds,
            )
        else:
            self._probe = None

    async def get_status(self) -> GpuStatus:
        """Get comprehensive GPU status for the system."""
        if self._mode.strip().lower() == "disabled":
            return GpuStatus(
                available=False,
                detected=False,
                nvidia_smi_found=False,
                docker_nvidia_runtime=False,
                runtime_visible_to_backend=False,
                usable_for_gpu_workflows=False,
                gpus=[],
                parabricks_compatible=False,
                recommendation="GPU discovery is disabled. Set BIOINFOFLOW_GPU_MODE=auto or manual and recreate the backend to enable it.",
                mode="disabled",
                state="disabled",
            )
        if self._probe is not None:
            return await self._get_cached_probed_status()
        if not self._nvidia_smi:
            docker_nvidia = await self._check_docker_nvidia()
            # Check for Apple Silicon on macOS
            apple_gpu = await self._detect_apple_silicon()
            if apple_gpu:
                return GpuStatus(
                    available=True,
                    detected=True,
                    nvidia_smi_found=False,
                    docker_nvidia_runtime=docker_nvidia,
                    runtime_visible_to_backend=True,
                    usable_for_gpu_workflows=False,
                    gpus=[apple_gpu],
                    parabricks_compatible=False,
                    recommendation="Apple Silicon GPU detected automatically. CPU workflows remain available, but NVIDIA-only workflows such as Parabricks still require an NVIDIA GPU runtime.",
                    error=None,
                )

            if docker_nvidia:
                return GpuStatus(
                    available=False,
                    detected=False,
                    nvidia_smi_found=False,
                    docker_nvidia_runtime=True,
                    runtime_visible_to_backend=False,
                    usable_for_gpu_workflows=False,
                    gpus=[],
                    parabricks_compatible=False,
                    recommendation="NVIDIA container runtime is configured, but nvidia-smi is not available to the backend process. Check container GPU passthrough, PATH, and driver visibility.",
                    error="nvidia-smi not found",
                )

            return GpuStatus(
                available=False,
                detected=False,
                nvidia_smi_found=False,
                docker_nvidia_runtime=False,
                runtime_visible_to_backend=False,
                usable_for_gpu_workflows=False,
                gpus=[],
                parabricks_compatible=False,
                recommendation="No GPU runtime is visible to the backend. CPU workflows can still run, and GPU acceleration will be detected automatically once the host and container runtime expose it.",
                error="nvidia-smi not found",
            )

        try:
            gpus = await self._detect_gpus()
            docker_nvidia = await self._check_docker_nvidia()

            if not gpus:
                return GpuStatus(
                    available=False,
                    detected=False,
                    nvidia_smi_found=True,
                    docker_nvidia_runtime=docker_nvidia,
                    runtime_visible_to_backend=False,
                    usable_for_gpu_workflows=False,
                    gpus=[],
                    parabricks_compatible=False,
                    recommendation="No NVIDIA GPU detected. A GPU with 16GB+ VRAM is required.",
                    error="No GPUs found",
                )

            # Check if any GPU has enough VRAM for Parabricks
            compatible_gpus = [
                g for g in gpus if g.memory_total_mb >= PARABRICKS_MIN_VRAM_MB
            ]
            parabricks_compatible = len(compatible_gpus) > 0 and docker_nvidia

            if parabricks_compatible:
                recommendation = f"Ready for Parabricks WGS! {compatible_gpus[0].name} with {compatible_gpus[0].memory_total_mb // 1024}GB VRAM detected."
            elif compatible_gpus and not docker_nvidia:
                recommendation = "NVIDIA GPU detected, but container GPU passthrough is not enabled. Configure the Docker NVIDIA runtime so Bioinfoflow jobs can use the host GPU."
            else:
                max_vram = max(g.memory_total_mb for g in gpus) if gpus else 0
                recommendation = f"NVIDIA GPU detected with {max_vram // 1024}GB VRAM. GPU-aware workflows can be routed here automatically once the required runtime is available."

            return GpuStatus(
                available=True,
                detected=True,
                nvidia_smi_found=True,
                docker_nvidia_runtime=docker_nvidia,
                runtime_visible_to_backend=True,
                usable_for_gpu_workflows=docker_nvidia,
                gpus=gpus,
                parabricks_compatible=parabricks_compatible,
                recommendation=recommendation,
            )

        except Exception as e:
            logger.error("gpu.detection_failed", error=str(e))
            return GpuStatus(
                available=False,
                detected=False,
                nvidia_smi_found=True,
                docker_nvidia_runtime=False,
                runtime_visible_to_backend=False,
                usable_for_gpu_workflows=False,
                gpus=[],
                parabricks_compatible=False,
                recommendation="GPU detection failed. Check NVIDIA drivers.",
                error=str(e),
            )

    async def _get_cached_probed_status(self) -> GpuStatus:
        now = time.monotonic()
        if (
            self._cached_status is not None
            and now - self._cached_at < self._cache_seconds
        ):
            return self._cached_status
        async with self._status_lock:
            now = time.monotonic()
            if (
                self._cached_status is not None
                and now - self._cached_at < self._cache_seconds
            ):
                return self._cached_status
            refreshed = await self._get_probed_status()
            if refreshed.state in {"ready", "no_gpus", "policy_invalid"}:
                self._cached_status = refreshed
                self._cached_at = now
                return refreshed
            if (
                self._cached_status is not None
                and self._cached_status.state == "ready"
                and now - self._cached_at < self._cache_seconds * 2
            ):
                return replace(
                    self._cached_status,
                    stale=True,
                    error=refreshed.error,
                    recommendation=refreshed.recommendation,
                )
            return refreshed

    async def _get_probed_status(self) -> GpuStatus:
        try:
            devices: list[ProbedGpu] = await self._probe.inventory()
        except GpuDockerUnavailable as exc:
            return self._probe_failure_status("docker_unavailable", exc)
        except GpuToolkitUnavailable as exc:
            return self._probe_failure_status("toolkit_unavailable", exc)
        except GpuProbeError as exc:
            return self._probe_failure_status("probe_failed", exc)

        references = tuple(
            GpuDeviceRef(index=device.index, uuid=device.uuid) for device in devices
        )
        policy = resolve_gpu_policy(self._mode, self._selectors, references)
        selected = set(policy.selected_uuids)
        gpus = [
            GpuInfo(
                index=device.index,
                name=device.name,
                memory_total_mb=device.memory_total_mb,
                memory_free_mb=device.memory_free_mb,
                driver_version=device.driver_version,
                cuda_version=None,
                compute_capability=device.compute_capability,
                uuid=device.uuid,
                selected=device.uuid in selected,
            )
            for device in devices
        ]
        state = policy.state if devices else "no_gpus"
        usable = bool(selected) and state == "ready"
        compatible = usable and any(
            gpu.selected and gpu.memory_total_mb >= PARABRICKS_MIN_VRAM_MB
            for gpu in gpus
        )
        if state == "policy_invalid":
            recommendation = (
                "BIOINFOFLOW_GPU_DEVICES does not match the detected GPU UUIDs. "
                "Update .env and recreate the backend."
            )
        elif not devices:
            recommendation = (
                "Docker returned no NVIDIA GPUs. CPU workflows remain available."
            )
        elif self._mode == "manual":
            recommendation = f"Manual GPU policy selected {len(selected)} of {len(gpus)} detected GPUs."
        else:
            recommendation = (
                f"Automatic GPU discovery selected all {len(gpus)} detected GPUs."
            )
        return GpuStatus(
            available=bool(gpus),
            detected=bool(gpus),
            nvidia_smi_found=bool(gpus),
            docker_nvidia_runtime=bool(gpus),
            runtime_visible_to_backend=bool(gpus),
            usable_for_gpu_workflows=usable,
            gpus=gpus,
            parabricks_compatible=compatible,
            recommendation=recommendation,
            error=policy.error,
            mode=policy.mode,
            state=state,
            container_toolkit_available=bool(gpus),
            selected_gpu_uuids=policy.selected_uuids,
        )

    def _probe_failure_status(self, state: str, error: Exception) -> GpuStatus:
        recommendations = {
            "docker_unavailable": "Docker is unavailable to the backend. Check the Docker socket and recreate the backend.",
            "toolkit_unavailable": "Docker could not allocate an NVIDIA GPU. Install or configure NVIDIA Container Toolkit, then recreate the backend.",
            "probe_failed": "The NVIDIA GPU probe failed. Check the backend logs and host driver health.",
        }
        return GpuStatus(
            available=False,
            detected=False,
            nvidia_smi_found=False,
            docker_nvidia_runtime=False,
            runtime_visible_to_backend=False,
            usable_for_gpu_workflows=False,
            gpus=[],
            parabricks_compatible=False,
            recommendation=recommendations[state],
            error=str(error),
            mode=self._mode,
            state=state,
        )

    def selected_visible_devices(self) -> str | None:
        mode = self._mode.strip().lower()
        if mode == "disabled":
            return None
        if self._probe is not None:
            if (
                self._cached_status is None
                or self._cached_status.state != "ready"
                or time.monotonic() - self._cached_at >= self._cache_seconds * 2
            ):
                return None
            if mode == "manual":
                return ",".join(self._cached_status.selected_gpu_uuids) or None
            if mode == "auto" and self._cached_status.selected_gpu_uuids:
                return "all"
            return None
        if mode == "manual":
            return None
        return "all" if self._nvidia_smi else None

    async def _detect_gpus(self) -> list[GpuInfo]:
        """Detect NVIDIA GPUs using nvidia-smi."""
        if not self._nvidia_smi:
            return []

        try:
            # Query GPU info in CSV format
            process = await asyncio.create_subprocess_exec(
                self._nvidia_smi,
                "--query-gpu=index,name,memory.total,memory.free,driver_version,compute_cap",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.warning("nvidia-smi.query_failed", stderr=stderr.decode()[:200])
                return []

            gpus = []
            for line in stdout.decode().strip().split("\n"):
                if not line.strip():
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 5:
                    gpus.append(
                        GpuInfo(
                            index=int(parts[0]),
                            name=parts[1],
                            memory_total_mb=int(float(parts[2])),
                            memory_free_mb=int(float(parts[3])),
                            driver_version=parts[4],
                            compute_capability=parts[5] if len(parts) > 5 else None,
                            cuda_version=await self._get_cuda_version(),
                            gpu_type="NVIDIA",
                        )
                    )
            return gpus

        except Exception as e:
            logger.error("gpu.nvidia_smi_failed", error=str(e))
            return []

    async def _get_cuda_version(self) -> str | None:
        """Get CUDA version from nvidia-smi."""
        if not self._nvidia_smi:
            return None

        try:
            process = await asyncio.create_subprocess_exec(
                self._nvidia_smi,
                "--query-gpu=driver_version",
                "--format=csv,noheader",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

            # Try to get CUDA version from nvidia-smi header
            process2 = await asyncio.create_subprocess_exec(
                self._nvidia_smi,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout2, _ = await process2.communicate()
            output = stdout2.decode()

            # Parse CUDA Version from output like "CUDA Version: 12.1"
            match = re.search(r"CUDA Version:\s*([\d.]+)", output)
            if match:
                return match.group(1)
            return None

        except Exception:
            return None

    async def _check_docker_nvidia(self) -> bool:
        """Check if Docker NVIDIA runtime is available."""
        docker_bin = shutil.which("docker")
        if not docker_bin:
            return False

        try:
            # Check if nvidia runtime is configured
            process = await asyncio.create_subprocess_exec(
                docker_bin,
                "info",
                "--format",
                "{{json .Runtimes}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

            if process.returncode != 0:
                return False

            # Check if nvidia runtime exists
            output = stdout.decode().lower()
            return "nvidia" in output

        except Exception:
            return False

    async def _detect_apple_silicon(self) -> GpuInfo | None:
        """Detect Apple Silicon GPU on macOS."""
        # Only check on macOS
        if platform.system() != "Darwin":
            return None

        try:
            # Use system_profiler to get chip information
            process = await asyncio.create_subprocess_exec(
                "system_profiler",
                "SPHardwareDataType",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.warning(
                    "system_profiler.query_failed", stderr=stderr.decode()[:200]
                )
                return None

            output = stdout.decode()

            # Parse chip name (e.g., "Apple M1 Max", "Apple M2 Pro")
            chip_match = re.search(r"Chip:\s*(.+)", output)
            if not chip_match:
                return None

            chip_name = chip_match.group(1).strip()

            # Only return if it's an Apple Silicon chip
            if not chip_name.startswith("Apple M"):
                return None

            # Parse total memory (unified memory)
            memory_match = re.search(r"Memory:\s*([\d.]+)\s*GB", output)
            memory_gb = 0
            if memory_match:
                memory_gb = int(float(memory_match.group(1)))

            logger.debug("apple_silicon.detected", chip=chip_name, memory_gb=memory_gb)

            return GpuInfo(
                index=0,
                name=chip_name,
                memory_total_mb=memory_gb * 1024,  # Convert GB to MB
                memory_free_mb=0,  # Not available for Apple Silicon
                driver_version="N/A",
                cuda_version=None,
                compute_capability=None,
                gpu_type="Apple Silicon",
            )

        except Exception as e:
            logger.error("apple_silicon.detection_failed", error=str(e))
            return None

    async def get_gpu_metrics(self) -> list[dict[str, Any]]:
        """Get real-time GPU metrics for monitoring."""
        if not self._nvidia_smi:
            return []

        try:
            process = await asyncio.create_subprocess_exec(
                self._nvidia_smi,
                "--query-gpu=index,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

            if process.returncode != 0:
                return []

            metrics = []
            for line in stdout.decode().strip().split("\n"):
                if not line.strip():
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 6:
                    metrics.append(
                        {
                            "index": int(parts[0]),
                            "gpu_utilization_pct": int(float(parts[1]))
                            if parts[1] != "[N/A]"
                            else None,
                            "memory_utilization_pct": int(float(parts[2]))
                            if parts[2] != "[N/A]"
                            else None,
                            "memory_used_mb": int(float(parts[3]))
                            if parts[3] != "[N/A]"
                            else None,
                            "memory_total_mb": int(float(parts[4]))
                            if parts[4] != "[N/A]"
                            else None,
                            "temperature_c": int(float(parts[5]))
                            if parts[5] != "[N/A]"
                            else None,
                            "power_draw_w": float(parts[6])
                            if len(parts) > 6 and parts[6] != "[N/A]"
                            else None,
                        }
                    )
            return metrics

        except Exception as e:
            logger.error("gpu.metrics_failed", error=str(e))
            return []


# Singleton instance
_gpu_service: GpuService | None = None


def get_gpu_service() -> GpuService:
    """Get the GPU service singleton."""
    global _gpu_service
    if _gpu_service is None:
        _gpu_service = GpuService()
    return _gpu_service
