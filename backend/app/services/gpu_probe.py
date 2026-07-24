from __future__ import annotations

import asyncio
import io
import os
import tarfile
from dataclasses import dataclass

import docker
from docker.errors import APIError, DockerException
from requests.exceptions import ReadTimeout


class GpuProbeError(RuntimeError):
    pass


class GpuProbeOutputError(GpuProbeError):
    pass


class GpuProbeTimeout(GpuProbeError):
    pass


class GpuDockerUnavailable(GpuProbeError):
    pass


class GpuToolkitUnavailable(GpuProbeError):
    pass


@dataclass(frozen=True)
class ProbedGpu:
    uuid: str
    index: int
    name: str
    memory_total_mb: int
    memory_free_mb: int
    driver_version: str
    compute_capability: str | None


def parse_inventory_csv(output: str) -> list[ProbedGpu]:
    devices: list[ProbedGpu] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 7:
            raise GpuProbeOutputError(
                f"expected 7 columns from nvidia-smi, received {len(parts)}"
            )
        try:
            devices.append(
                ProbedGpu(
                    uuid=parts[0],
                    index=int(parts[1]),
                    name=parts[2],
                    memory_total_mb=int(float(parts[3])),
                    memory_free_mb=int(float(parts[4])),
                    driver_version=parts[5],
                    compute_capability=None if parts[6] == "[N/A]" else parts[6],
                )
            )
        except ValueError as exc:
            raise GpuProbeOutputError("invalid numeric field from nvidia-smi") from exc
    return devices


class DockerGpuProbe:
    def __init__(
        self,
        *,
        client: docker.DockerClient,
        hostname: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._client = client
        self._hostname = hostname or os.getenv("HOSTNAME", "")
        self._timeout = timeout

    async def inventory(self) -> list[ProbedGpu]:
        return await asyncio.to_thread(self._inventory_sync)

    def _inventory_sync(self) -> list[ProbedGpu]:
        if not self._hostname:
            raise GpuProbeError("backend container identity is unavailable")
        try:
            current = self._client.containers.get(self._hostname)
        except DockerException as exc:
            raise GpuDockerUnavailable(_diagnostic(exc)) from exc
        request = docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])
        inventory_path = "/tmp/bioinfoflow-gpu-inventory.csv"
        stderr_path = "/tmp/bioinfoflow-gpu-probe.stderr"
        command = (
            "nvidia-smi "
            "--query-gpu=uuid,index,name,memory.total,memory.free,driver_version,compute_cap "
            "--format=csv,noheader,nounits "
            f"> {inventory_path} 2> {stderr_path}"
        )
        try:
            container = self._client.containers.run(
                image=current.image.id,
                command=[command],
                entrypoint=["/bin/sh", "-c"],
                detach=True,
                network_disabled=True,
                device_requests=[request],
                environment={
                    "NVIDIA_VISIBLE_DEVICES": "all",
                    "NVIDIA_DRIVER_CAPABILITIES": "compute,utility",
                },
                labels={"bioinfoflow.gpu-probe": "true"},
                log_config=docker.types.LogConfig(type="none"),
            )
        except APIError as exc:
            diagnostic = _diagnostic(exc)
            if any(
                token in diagnostic.lower()
                for token in ("gpu", "nvidia", "device driver")
            ):
                raise GpuToolkitUnavailable(diagnostic) from exc
            raise GpuProbeError(diagnostic) from exc
        except DockerException as exc:
            raise GpuDockerUnavailable(_diagnostic(exc)) from exc
        try:
            try:
                result = container.wait(timeout=self._timeout)
            except ReadTimeout as exc:
                raise GpuProbeTimeout(_diagnostic(exc)) from exc
            stdout = _read_container_file(container, inventory_path)
            if int(result.get("StatusCode", 1)) != 0:
                stderr = _read_container_file(container, stderr_path)
                raise GpuProbeError(
                    " ".join(stderr.split())[:400] or "GPU probe failed"
                )
            return parse_inventory_csv(stdout)
        finally:
            container.remove(force=True)


def _diagnostic(error: BaseException) -> str:
    return " ".join(str(error).split())[:400] or error.__class__.__name__


def _read_container_file(container, path: str) -> str:
    chunks, _stat = container.get_archive(path)
    archive_bytes = b"".join(chunks)
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        member = archive.next()
        if member is None:
            return ""
        extracted = archive.extractfile(member)
        if extracted is None:
            return ""
        return extracted.read().decode("utf-8", "replace")
