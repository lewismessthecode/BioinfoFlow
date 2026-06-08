"""
GPU Detection Service

Detects NVIDIA GPUs and Apple Silicon, and checks compatibility for Parabricks WGS analysis.
"""

from __future__ import annotations

import asyncio
import platform
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

    def __init__(self) -> None:
        self._nvidia_smi = _find_nvidia_smi()

    async def get_status(self) -> GpuStatus:
        """Get comprehensive GPU status for the system."""
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
