from __future__ import annotations

import asyncio
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from app.services.agent_harness.sandbox.container_executor import (
    DockerSandboxExecutor,
)


class _FakeContainer:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.removed = False
        self.killed = False

    def wait(self):
        return {"StatusCode": 0}

    def logs(self, *, stdout, stderr):
        if stdout:
            assert stderr is False
            return json.dumps(self.response).encode() + b"\n"
        assert stderr is True
        return b""

    def kill(self):
        self.killed = True

    def remove(self, *, force):
        assert force is True
        self.removed = True


@pytest.mark.asyncio
async def test_container_executor_never_mounts_the_docker_socket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    workspace = home / "projects" / "demo"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(
        "app.services.agent_harness.sandbox.container_executor.settings.bioinfoflow_home",
        str(home),
    )
    response = {
        "version": 1,
        "status": "completed",
        "exit_code": 0,
        "signal": None,
        "stdout": "ready",
        "stderr": "",
        "output_limit_exceeded": False,
        "timed_out": False,
        "sandbox": {
            "mode": "workspace-write",
            "adapter": "landlock-run",
            "enforcement": "full",
            "denial_signatures": ["permission denied"],
            "runner_failure_rules": [],
        },
    }
    container = _FakeContainer(response)
    captured: dict = {}

    class Containers:
        def run(self, image, **options):
            captured.update(image=image, **options)
            return container

    client = SimpleNamespace(containers=Containers())
    executor = DockerSandboxExecutor(image="bioinfoflow-backend:test", client=client)

    result = await executor.execute(
        argv=["/bin/bash", "-c", "printf ready"],
        cwd=workspace,
        workspace_root=workspace,
        environment={"PATH": "/usr/bin:/bin"},
        mode="workspace-write",
        timeout_seconds=10,
        capture_limit=4096,
        cancellation=None,
        cwd_inode=workspace.stat().st_ino,
        workspace_inode=workspace.stat().st_ino,
    )

    assert result.stdout == "ready"
    assert captured["image"] == "bioinfoflow-backend:test"
    assert captured["read_only"] is True
    assert captured["cap_drop"] == ["ALL"]
    assert captured["security_opt"] == ["no-new-privileges:true"]
    assert all("docker.sock" not in source for source in captured["volumes"])
    assert str(home) not in captured["volumes"]
    assert captured["volumes"][str(home / "projects")]["mode"] == "ro"
    assert captured["volumes"][str(workspace)]["mode"] == "rw"
    assert captured["environment"] == {}
    assert container.removed is True


@pytest.mark.asyncio
async def test_container_executor_rejects_non_identity_mounted_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    workspace = home / "projects" / "demo"
    workspace.mkdir(parents=True)
    outside_cwd = tmp_path / "image-path"
    outside_cwd.mkdir()
    monkeypatch.setattr(
        "app.services.agent_harness.sandbox.container_executor.settings.bioinfoflow_home",
        str(home),
    )

    class Containers:
        def run(self, _image, **_options):
            raise AssertionError("container must not start")

    executor = DockerSandboxExecutor(
        image="bioinfoflow-backend:test",
        client=SimpleNamespace(containers=Containers()),
    )

    with pytest.raises(RuntimeError, match="identity-mounted"):
        await executor.execute(
            argv=["/bin/true"],
            cwd=outside_cwd,
            workspace_root=workspace,
            environment={},
            mode="read-only",
            timeout_seconds=10,
            capture_limit=4096,
            cancellation=None,
            cwd_inode=outside_cwd.stat().st_ino,
            workspace_inode=workspace.stat().st_ino,
        )


@pytest.mark.asyncio
async def test_container_executor_rejects_workspace_containing_control_plane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(
        "app.services.agent_harness.sandbox.container_executor.settings.bioinfoflow_home",
        str(home),
    )

    class Containers:
        def run(self, _image, **_options):
            raise AssertionError("container must not start")

    executor = DockerSandboxExecutor(
        image="bioinfoflow-backend:test",
        client=SimpleNamespace(containers=Containers()),
    )

    with pytest.raises(RuntimeError, match="overlaps a protected capability"):
        await executor.execute(
            argv=["/bin/true"],
            cwd=home,
            workspace_root=home,
            environment={},
            mode="workspace-write",
            timeout_seconds=10,
            capture_limit=4096,
            cancellation=None,
            cwd_inode=home.stat().st_ino,
            workspace_inode=home.stat().st_ino,
        )


@pytest.mark.asyncio
async def test_container_executor_rejects_broad_custom_skills_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    workspace = home / "projects" / "demo"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(
        "app.services.agent_harness.sandbox.container_executor.settings.bioinfoflow_home",
        str(home),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.sandbox.container_executor.settings.bioinfoflow_skills_root",
        "/",
    )
    executor = DockerSandboxExecutor(
        image="bioinfoflow-backend:test",
        client=SimpleNamespace(),
    )

    with pytest.raises(RuntimeError, match="protected capability path"):
        await executor.execute(
            argv=["/bin/true"],
            cwd=workspace,
            workspace_root=workspace,
            environment={},
            mode="read-only",
            timeout_seconds=10,
            capture_limit=4096,
            cancellation=None,
            cwd_inode=workspace.stat().st_ino,
            workspace_inode=workspace.stat().st_ino,
        )


@pytest.mark.asyncio
async def test_container_executor_cleans_up_when_cancelled_during_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    workspace = home / "projects" / "demo"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(
        "app.services.agent_harness.sandbox.container_executor.settings.bioinfoflow_home",
        str(home),
    )
    response = {
        "version": 1,
        "status": "completed",
        "exit_code": 0,
        "signal": None,
        "stdout": "",
        "stderr": "",
        "output_limit_exceeded": False,
        "timed_out": False,
        "sandbox": {
            "mode": "workspace-write",
            "adapter": "landlock-run",
            "enforcement": "full",
            "denial_signatures": ["permission denied"],
            "runner_failure_rules": [],
        },
    }
    container = _FakeContainer(response)
    start_entered = threading.Event()
    release_start = threading.Event()
    captured_request: list[Path] = []

    class Containers:
        def run(self, _image, **options):
            captured_request.append(
                Path(
                    next(
                        source
                        for source, mount in options["volumes"].items()
                        if mount["bind"]
                        == "/run/bioinfoflow-sandbox/request.json"
                    )
                )
            )
            start_entered.set()
            assert release_start.wait(timeout=5)
            return container

    executor = DockerSandboxExecutor(
        image="bioinfoflow-backend:test",
        client=SimpleNamespace(containers=Containers()),
    )
    task = asyncio.create_task(
        executor.execute(
            argv=["/bin/true"],
            cwd=workspace,
            workspace_root=workspace,
            environment={},
            mode="workspace-write",
            timeout_seconds=10,
            capture_limit=4096,
            cancellation=None,
            cwd_inode=workspace.stat().st_ino,
            workspace_inode=workspace.stat().st_ino,
        )
    )
    assert await asyncio.to_thread(start_entered.wait, 5)

    task.cancel()
    release_start.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert container.killed is True
    assert container.removed is True
    assert len(captured_request) == 1
    assert not captured_request[0].exists()


def test_container_executor_pins_the_running_backend_image_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.agent_harness.sandbox.container_executor._running_in_container",
        lambda: True,
    )
    monkeypatch.setenv("HOSTNAME", "backend-container")
    image = SimpleNamespace(id="sha256:matching")
    client = SimpleNamespace(
        containers=SimpleNamespace(
            get=lambda name: SimpleNamespace(image=image) if name else None
        ),
        images=SimpleNamespace(get=lambda _reference: image),
    )
    executor = DockerSandboxExecutor(image="bioinfoflow-backend:latest", client=client)

    assert executor._execution_image() == "sha256:matching"

    client.images = SimpleNamespace(
        get=lambda _reference: SimpleNamespace(id="sha256:different")
    )
    with pytest.raises(RuntimeError, match="does not match"):
        executor._execution_image()


@pytest.mark.asyncio
async def test_danger_full_access_gets_only_an_ephemeral_writable_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    workspace = home / "projects" / "demo"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(
        "app.services.agent_harness.sandbox.container_executor.settings.bioinfoflow_home",
        str(home),
    )
    response = {
        "version": 1,
        "status": "completed",
        "exit_code": 0,
        "signal": None,
        "stdout": "",
        "stderr": "",
        "output_limit_exceeded": False,
        "timed_out": False,
        "sandbox": {
            "mode": "danger-full-access",
            "adapter": "danger-full-access",
            "enforcement": None,
            "denial_signatures": [],
            "runner_failure_rules": [],
        },
    }
    container = _FakeContainer(response)
    captured: dict = {}

    class Containers:
        def run(self, image, **options):
            captured.update(image=image, **options)
            return container

    executor = DockerSandboxExecutor(
        image="bioinfoflow-backend:test",
        client=SimpleNamespace(containers=Containers()),
    )

    await executor.execute(
        argv=["/bin/true"],
        cwd=workspace,
        workspace_root=workspace,
        environment={},
        mode="danger-full-access",
        timeout_seconds=10,
        capture_limit=4096,
        cancellation=None,
        cwd_inode=workspace.stat().st_ino,
        workspace_inode=workspace.stat().st_ino,
    )

    assert captured["read_only"] is False
    assert captured["cap_drop"] == ["ALL"]
    assert all("docker.sock" not in source for source in captured["volumes"])


@pytest.mark.asyncio
async def test_container_executor_rejects_partial_success_responses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    workspace = home / "projects" / "demo"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(
        "app.services.agent_harness.sandbox.container_executor.settings.bioinfoflow_home",
        str(home),
    )
    container = _FakeContainer(
        {
            "version": 1,
            "status": "completed",
            "stdout": "",
            "stderr": "",
            "sandbox": {},
        }
    )

    class Containers:
        def run(self, _image, **_options):
            return container

    executor = DockerSandboxExecutor(
        image="bioinfoflow-backend:test",
        client=SimpleNamespace(containers=Containers()),
    )

    with pytest.raises(RuntimeError, match="schema is invalid"):
        await executor.execute(
            argv=["/bin/true"],
            cwd=workspace,
            workspace_root=workspace,
            environment={},
            mode="workspace-write",
            timeout_seconds=10,
            capture_limit=4096,
            cancellation=None,
            cwd_inode=workspace.stat().st_ino,
            workspace_inode=workspace.stat().st_ino,
        )
    assert container.removed is True


@pytest.mark.asyncio
async def test_container_executor_rejects_nonzero_container_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    workspace = home / "projects" / "demo"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(
        "app.services.agent_harness.sandbox.container_executor.settings.bioinfoflow_home",
        str(home),
    )
    response = {
        "version": 1,
        "status": "completed",
        "exit_code": 0,
        "signal": None,
        "stdout": "misleading success",
        "stderr": "",
        "output_limit_exceeded": False,
        "timed_out": False,
        "sandbox": {
            "mode": "workspace-write",
            "adapter": "landlock-run",
            "enforcement": "full",
            "denial_signatures": ["permission denied"],
            "runner_failure_rules": [],
        },
    }

    class FailedContainer(_FakeContainer):
        def wait(self):
            return {"StatusCode": 17}

    container = FailedContainer(response)

    class Containers:
        def run(self, _image, **_options):
            return container

    executor = DockerSandboxExecutor(
        image="bioinfoflow-backend:test",
        client=SimpleNamespace(containers=Containers()),
    )

    with pytest.raises(RuntimeError, match="exited with status 17"):
        await executor.execute(
            argv=["/bin/true"],
            cwd=workspace,
            workspace_root=workspace,
            environment={},
            mode="workspace-write",
            timeout_seconds=10,
            capture_limit=4096,
            cancellation=None,
            cwd_inode=workspace.stat().st_ino,
            workspace_inode=workspace.stat().st_ino,
        )
    assert container.removed is True
