from __future__ import annotations

from pathlib import Path

import pytest

from app.services.agent_core.sandbox.process_sandbox import (
    BubblewrapAdapter,
    SandboxRunner,
    SandboxUnavailableError,
)


class _FakeAdapter:
    def __init__(self, *, name: str, available: bool):
        self.name = name
        self._available = available

    def available(self) -> bool:
        return self._available

    def build_argv(self, spec) -> list[str]:
        return ["fake-sandbox", spec.command]


def test_disabled_runner_runs_plain_bash(tmp_path):
    runner = SandboxRunner(enabled=False, adapters=[_FakeAdapter(name="fake", available=True)])
    result = runner.build(
        command="echo hi", cwd=tmp_path, read_roots=[tmp_path], write_roots=[tmp_path]
    )
    assert result.sandboxed is False
    assert result.argv == ["bash", "-lc", "echo hi"]


def test_enabled_runner_uses_available_adapter(tmp_path):
    runner = SandboxRunner(enabled=True, adapters=[_FakeAdapter(name="fake", available=True)])
    result = runner.build(
        command="echo hi", cwd=tmp_path, read_roots=[tmp_path], write_roots=[tmp_path]
    )
    assert result.sandboxed is True
    assert result.adapter == "fake"
    assert result.argv == ["fake-sandbox", "echo hi"]


def test_fail_closed_raises_when_no_adapter_available(tmp_path):
    runner = SandboxRunner(
        enabled=True, fail_closed=True, adapters=[_FakeAdapter(name="fake", available=False)]
    )
    with pytest.raises(SandboxUnavailableError):
        runner.build(command="echo hi", cwd=tmp_path, read_roots=[], write_roots=[])


def test_fail_open_falls_back_to_bash_when_no_adapter(tmp_path):
    runner = SandboxRunner(
        enabled=True, fail_closed=False, adapters=[_FakeAdapter(name="fake", available=False)]
    )
    result = runner.build(command="echo hi", cwd=tmp_path, read_roots=[], write_roots=[])
    assert result.sandboxed is False
    assert result.argv == ["bash", "-lc", "echo hi"]


def test_disable_requested_requires_allow_unsandboxed(tmp_path):
    runner = SandboxRunner(enabled=True, allow_unsandboxed=False, adapters=[_FakeAdapter(name="fake", available=True)])
    with pytest.raises(SandboxUnavailableError):
        runner.build(
            command="echo hi",
            cwd=tmp_path,
            read_roots=[tmp_path],
            write_roots=[tmp_path],
            disable_requested=True,
        )

    permissive = SandboxRunner(
        enabled=True, allow_unsandboxed=True, adapters=[_FakeAdapter(name="fake", available=True)]
    )
    result = permissive.build(
        command="echo hi",
        cwd=tmp_path,
        read_roots=[tmp_path],
        write_roots=[tmp_path],
        disable_requested=True,
    )
    assert result.sandboxed is False
    assert result.argv == ["bash", "-lc", "echo hi"]


def test_bubblewrap_argv_confines_to_roots_and_disables_network(tmp_path):
    read_root = tmp_path / "repo"
    write_root = tmp_path / "data"
    read_root.mkdir()
    write_root.mkdir()
    spec_argv = BubblewrapAdapter().build_argv(
        _spec(command="cat /etc/passwd", cwd=write_root, read_roots=[read_root], write_roots=[write_root])
    )
    assert spec_argv[0] == "bwrap"
    assert "--unshare-net" in spec_argv
    assert "--die-with-parent" in spec_argv
    # read root bound read-only, write root bound read-write
    assert "--ro-bind" in spec_argv
    assert spec_argv[-3:] == ["bash", "-lc", "cat /etc/passwd"]
    # chdir targets the working directory
    chdir_index = spec_argv.index("--chdir")
    assert spec_argv[chdir_index + 1] == str(write_root)
    # write root appears with a rw --bind
    bind_pairs = [
        (spec_argv[i + 1], spec_argv[i + 2])
        for i, token in enumerate(spec_argv)
        if token == "--bind"
    ]
    assert (str(write_root), str(write_root)) in bind_pairs


def _spec(*, command: str, cwd: Path, read_roots, write_roots):
    from app.services.agent_core.sandbox.process_sandbox import SandboxSpec

    return SandboxSpec(
        command=command,
        cwd=cwd,
        read_roots=read_roots,
        write_roots=write_roots,
        allow_network=False,
    )
