from __future__ import annotations

import logging
from pathlib import Path

from WDL.runtime.backend.docker_swarm import SwarmContainer
from WDL.runtime.config import Loader

import app.engine.miniwdl_container_backend as backend_module
from app.engine.miniwdl_container_backend import BioinfoflowSwarmContainer
from app.engine.miniwdl_mounts import ContainerPathMapping


def _make_container(tmp_path: Path) -> BioinfoflowSwarmContainer:
    host_dir = tmp_path / "task"
    host_dir.mkdir()
    (host_dir / "command").write_text("echo ok\n", encoding="utf-8")
    cfg = Loader(logging.getLogger(__name__), filenames=[])
    return BioinfoflowSwarmContainer(cfg, "run-test", str(host_dir))


def test_prepare_mounts_identity_shared_and_run_mounts(tmp_path, monkeypatch):
    host_dir = tmp_path / "task"
    host_dir.mkdir()
    (host_dir / "command").write_text("echo ok\n", encoding="utf-8")
    cfg = Loader(logging.getLogger(__name__), filenames=[])

    monkeypatch.setattr(
        backend_module,
        "configured_shared_mounts",
        lambda: (
            ContainerPathMapping(
                container_root=Path("/srv/bioinfoflow/sources/deliveries"),
                host_root=Path("/srv/bioinfoflow/sources/deliveries"),
                read_only=True,
            ),
        ),
    )
    monkeypatch.setattr(
        backend_module,
        "configured_run_mounts",
        lambda _host_dir: (
            ContainerPathMapping(
                container_root=Path(
                    "/srv/bioinfoflow/projects/proj-abc/runs/run-xyz/input"
                ),
                host_root=Path("/srv/bioinfoflow/projects/proj-abc/runs/run-xyz/input"),
                read_only=True,
            ),
            ContainerPathMapping(
                container_root=Path(
                    "/srv/bioinfoflow/projects/proj-abc/runs/run-xyz/results"
                ),
                host_root=Path(
                    "/srv/bioinfoflow/projects/proj-abc/runs/run-xyz/results"
                ),
                read_only=False,
            ),
        ),
    )

    container = BioinfoflowSwarmContainer(cfg, "run-test", str(host_dir))
    mounts = container.prepare_mounts(logging.getLogger(__name__))
    targets = {mount["Target"]: mount for mount in mounts}

    assert "/srv/bioinfoflow/sources/deliveries" in targets
    assert (
        targets["/srv/bioinfoflow/sources/deliveries"]["Source"]
        == "/srv/bioinfoflow/sources/deliveries"
    )
    assert targets["/srv/bioinfoflow/sources/deliveries"]["ReadOnly"] is True

    input_target = "/srv/bioinfoflow/projects/proj-abc/runs/run-xyz/input"
    assert input_target in targets
    assert targets[input_target]["ReadOnly"] is True

    results_target = "/srv/bioinfoflow/projects/proj-abc/runs/run-xyz/results"
    assert results_target in targets
    assert targets[results_target]["ReadOnly"] is False

    # Swarm nested-mount regression guard: no mount target may be a
    # parent of any other mount target.
    paths = [Path(t) for t in targets]
    for a in paths:
        for b in paths:
            if a == b:
                continue
            assert a not in b.parents, (
                f"mount {b} is nested under {a} — Swarm will demote the child"
            )


def test_prepare_mounts_deduplicates_targets(tmp_path, monkeypatch):
    host_dir = tmp_path / "task"
    host_dir.mkdir()
    (host_dir / "command").write_text("echo ok\n", encoding="utf-8")
    cfg = Loader(logging.getLogger(__name__), filenames=[])

    shared = ContainerPathMapping(
        container_root=Path("/srv/bioinfoflow/sources/deliveries"),
        host_root=Path("/srv/bioinfoflow/sources/deliveries"),
        read_only=True,
    )
    monkeypatch.setattr(
        backend_module, "configured_shared_mounts", lambda: (shared, shared)
    )
    monkeypatch.setattr(backend_module, "configured_run_mounts", lambda _h: ())

    container = BioinfoflowSwarmContainer(cfg, "run-test", str(host_dir))
    mounts = container.prepare_mounts(logging.getLogger(__name__))
    targets = [m["Target"] for m in mounts if m["Target"] == str(shared.container_root)]
    assert len(targets) == 1


def test_misc_config_adds_nvidia_runtime_env_and_gpu_reservation(tmp_path):
    container = _make_container(tmp_path)
    container.runtime_values = {
        "gpu": True,
        "env": {
            "EXISTING": "1",
        },
    }

    resources, _user, _groups = container.misc_config(logging.getLogger(__name__))

    assert container.runtime_values["env"]["EXISTING"] == "1"
    assert container.runtime_values["env"]["NVIDIA_VISIBLE_DEVICES"] == "all"
    assert container.runtime_values["env"]["NVIDIA_DRIVER_CAPABILITIES"] == "compute,utility"
    assert resources is not None
    assert resources["Reservations"]["GenericResources"] == [
        {"DiscreteResourceSpec": {"Kind": "NVIDIA-GPU", "Value": 1}}
    ]


# ---------------------------------------------------------------------------
# host_path override: let declared outputs under the platform's rw mount
# bypass miniwdl's work-dir-only validation (see issue #214 upstream).
# ---------------------------------------------------------------------------


def _install_rw_results_mount(
    monkeypatch, container_root: Path, host_root: Path | None = None
) -> None:
    host_root = host_root or container_root
    monkeypatch.setattr(
        backend_module,
        "configured_run_mounts",
        lambda _host_dir: (
            ContainerPathMapping(
                container_root=container_root,
                host_root=host_root,
                read_only=False,
            ),
        ),
    )


def test_host_path_rw_mount_existing_file_returns_host_path(tmp_path, monkeypatch):
    results = tmp_path / "srv/bioinfoflow/projects/p/runs/r/results"
    results.mkdir(parents=True)
    output = results / "Sample.info"
    output.write_text("x", encoding="utf-8")
    _install_rw_results_mount(monkeypatch, results)

    container = _make_container(tmp_path)
    assert container.host_path(str(output)) == str(output)


def test_host_path_rw_mount_missing_file_returns_none(tmp_path, monkeypatch):
    results = tmp_path / "srv/bioinfoflow/projects/p/runs/r/results"
    results.mkdir(parents=True)
    # Do NOT create the file — simulate WDL declaring an output the task did
    # not actually produce. miniwdl treats None as "output missing".
    _install_rw_results_mount(monkeypatch, results)

    container = _make_container(tmp_path)
    assert container.host_path(str(results / "Sample.info")) is None


def test_host_path_rw_mount_directory_reference_returns_trailing_slash(
    tmp_path, monkeypatch
):
    results = tmp_path / "srv/bioinfoflow/projects/p/runs/r/results"
    nested = results / "01.Split_index"
    nested.mkdir(parents=True)
    _install_rw_results_mount(monkeypatch, results)

    container = _make_container(tmp_path)
    assert container.host_path(str(nested) + "/") == f"{nested}/"


def test_host_path_rw_mount_directory_reference_missing_returns_none(
    tmp_path, monkeypatch
):
    results = tmp_path / "srv/bioinfoflow/projects/p/runs/r/results"
    results.mkdir(parents=True)
    _install_rw_results_mount(monkeypatch, results)

    container = _make_container(tmp_path)
    # Directory ref but the dir does not exist.
    missing = results / "nonexistent"
    assert container.host_path(f"{missing}/") is None


def test_host_path_inputs_only_always_delegates(tmp_path, monkeypatch):
    # Even if the path would otherwise match our rw mount, inputs_only=True
    # must NOT trigger the override — miniwdl uses that mode to validate
    # that inputs resolve to registered input mounts, and we don't want to
    # masquerade random rw files as legitimate inputs.
    results = tmp_path / "srv/bioinfoflow/projects/p/runs/r/results"
    results.mkdir(parents=True)
    (results / "Sample.info").write_text("x", encoding="utf-8")
    _install_rw_results_mount(monkeypatch, results)

    calls: list[tuple[str, bool]] = []
    sentinel = object()

    def spy(self, container_path, inputs_only=False):
        calls.append((container_path, inputs_only))
        return sentinel

    monkeypatch.setattr(SwarmContainer, "host_path", spy)

    container = _make_container(tmp_path)
    result = container.host_path(str(results / "Sample.info"), inputs_only=True)
    assert result is sentinel
    assert calls == [(str(results / "Sample.info"), True)]


def test_host_path_path_outside_platform_mounts_delegates(tmp_path, monkeypatch):
    # A path that's NOT under any platform-declared rw mount must pass
    # through untouched. In real miniwdl the parent implementation would
    # raise OutputError; here we spy to verify delegation.
    results = tmp_path / "srv/bioinfoflow/projects/p/runs/r/results"
    results.mkdir(parents=True)
    _install_rw_results_mount(monkeypatch, results)

    calls: list[tuple[str, bool]] = []

    def spy(self, container_path, inputs_only=False):
        calls.append((container_path, inputs_only))
        return "<super>"

    monkeypatch.setattr(SwarmContainer, "host_path", spy)

    container = _make_container(tmp_path)
    foreign = "/etc/passwd"
    assert container.host_path(foreign) == "<super>"
    assert calls == [(foreign, False)]


def test_host_path_ro_mount_delegates(tmp_path, monkeypatch):
    # A path under a RO platform mount (e.g. run's input dir) is not
    # something a task should declare as an output anyway. We short-circuit
    # only rw mounts; ro paths fall through to miniwdl's standard handling.
    input_dir = tmp_path / "srv/bioinfoflow/projects/p/runs/r/input"
    results_dir = tmp_path / "srv/bioinfoflow/projects/p/runs/r/results"
    input_dir.mkdir(parents=True)
    results_dir.mkdir(parents=True)
    (input_dir / "manifest.tsv").write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        backend_module,
        "configured_run_mounts",
        lambda _host_dir: (
            ContainerPathMapping(
                container_root=input_dir,
                host_root=input_dir,
                read_only=True,
            ),
            ContainerPathMapping(
                container_root=results_dir,
                host_root=results_dir,
                read_only=False,
            ),
        ),
    )

    calls: list[tuple[str, bool]] = []

    def spy(self, container_path, inputs_only=False):
        calls.append((container_path, inputs_only))
        return "<super>"

    monkeypatch.setattr(SwarmContainer, "host_path", spy)

    container = _make_container(tmp_path)
    manifest_path = str(input_dir / "manifest.tsv")
    assert container.host_path(manifest_path) == "<super>"
    assert calls == [(manifest_path, False)]


def test_host_path_relative_path_delegates(tmp_path, monkeypatch):
    # Relative container paths (miniwdl's normal form for in-workdir outputs)
    # must skip our override entirely and go to miniwdl's standard logic.
    results = tmp_path / "srv/bioinfoflow/projects/p/runs/r/results"
    results.mkdir(parents=True)
    _install_rw_results_mount(monkeypatch, results)

    calls: list[tuple[str, bool]] = []

    def spy(self, container_path, inputs_only=False):
        calls.append((container_path, inputs_only))
        return "<super>"

    monkeypatch.setattr(SwarmContainer, "host_path", spy)

    container = _make_container(tmp_path)
    assert container.host_path("out.txt") == "<super>"
    assert calls == [("out.txt", False)]
