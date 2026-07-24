from __future__ import annotations

import io
import tarfile

import pytest
from requests.exceptions import ReadTimeout

from app.services.gpu_probe import (
    DockerGpuProbe,
    GpuProbeOutputError,
    GpuProbeTimeout,
    ProbedGpu,
    parse_inventory_csv,
)


H20_CSV = "GPU-123, 0, NVIDIA H20, 97871, 96000, 550.54, 9.0\n"


def test_parse_inventory_csv_preserves_uuid_and_h20_fields() -> None:
    devices = parse_inventory_csv(H20_CSV)

    assert devices == [
        ProbedGpu(
            uuid="GPU-123",
            index=0,
            name="NVIDIA H20",
            memory_total_mb=97871,
            memory_free_mb=96000,
            driver_version="550.54",
            compute_capability="9.0",
        )
    ]


def test_parse_inventory_csv_rejects_malformed_rows() -> None:
    with pytest.raises(GpuProbeOutputError, match="expected 7 columns"):
        parse_inventory_csv("GPU-123, 0, NVIDIA H20\n")


class FakeImage:
    id = "sha256:backend-image"


class FakeCurrentContainer:
    image = FakeImage()


class FakeProbeContainer:
    def __init__(
        self, *, status_code: int = 0, wait_error: Exception | None = None
    ) -> None:
        self.status_code = status_code
        self.wait_error = wait_error
        self.removed_forcefully = False

    def wait(self, timeout: float):
        assert timeout == 3
        if self.wait_error:
            raise self.wait_error
        return {"StatusCode": self.status_code}

    def get_archive(self, path: str):
        content = H20_CSV.encode() if path.endswith("inventory.csv") else b"probe failed"
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            info = tarfile.TarInfo(name=path.rsplit("/", 1)[-1])
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        return [buffer.getvalue()], {"size": len(content)}

    def remove(self, *, force: bool):
        self.removed_forcefully = force


class FakeContainers:
    def __init__(self) -> None:
        self.probe = FakeProbeContainer()
        self.run_kwargs = None

    def get(self, hostname: str):
        assert hostname == "backend-container"
        return FakeCurrentContainer()

    def run(self, **kwargs):
        self.run_kwargs = kwargs
        return self.probe


class FakeDockerClient:
    def __init__(self) -> None:
        self.containers = FakeContainers()


@pytest.mark.asyncio
async def test_docker_probe_runs_same_image_and_always_removes_container() -> None:
    client = FakeDockerClient()
    probe = DockerGpuProbe(client=client, hostname="backend-container", timeout=3)

    devices = await probe.inventory()

    assert devices[0].name == "NVIDIA H20"
    assert client.containers.run_kwargs["image"] == "sha256:backend-image"
    assert client.containers.run_kwargs["entrypoint"] == ["/bin/sh", "-c"]
    assert "nvidia-smi" in client.containers.run_kwargs["command"][0]
    assert client.containers.run_kwargs["log_config"]["Type"] == "none"
    request = client.containers.run_kwargs["device_requests"][0]
    assert request["Count"] == -1
    assert request["Capabilities"] == [["gpu"]]
    assert client.containers.probe.removed_forcefully is True


@pytest.mark.asyncio
async def test_docker_probe_removes_container_after_timeout() -> None:
    client = FakeDockerClient()
    client.containers.probe = FakeProbeContainer(wait_error=ReadTimeout("timed out"))
    probe = DockerGpuProbe(client=client, hostname="backend-container", timeout=3)

    with pytest.raises(GpuProbeTimeout, match="timed out"):
        await probe.inventory()

    assert client.containers.probe.removed_forcefully is True
