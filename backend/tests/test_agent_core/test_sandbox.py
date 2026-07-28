from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import settings
from app.services.agent_core.sandbox.process_sandbox import (
    BubblewrapAdapter,
    SandboxRunner,
    SandboxUnavailableError,
    SeatbeltAdapter,
)
from app.services.agent_core.sandbox import FilesystemPolicy
from app.utils.exceptions import PermissionDeniedError


class _FakeAdapter:
    def __init__(self, *, name: str, available: bool):
        self.name = name
        self._available = available

    def available(self) -> bool:
        return self._available

    def build_argv(self, spec) -> list[str]:
        return ["fake-sandbox", spec.command]


def test_disabled_runner_runs_plain_bash(tmp_path):
    runner = SandboxRunner(
        enabled=False, adapters=[_FakeAdapter(name="fake", available=True)]
    )
    result = runner.build(
        command="echo hi", cwd=tmp_path, read_roots=[tmp_path], write_roots=[tmp_path]
    )
    assert result.sandboxed is False
    assert result.argv == ["bash", "-lc", "echo hi"]


def test_enabled_runner_uses_available_adapter(tmp_path):
    runner = SandboxRunner(
        enabled=True, adapters=[_FakeAdapter(name="fake", available=True)]
    )
    result = runner.build(
        command="echo hi", cwd=tmp_path, read_roots=[tmp_path], write_roots=[tmp_path]
    )
    assert result.sandboxed is True
    assert result.adapter == "fake"
    assert result.argv == ["fake-sandbox", "echo hi"]


def test_fail_closed_raises_when_no_adapter_available(tmp_path):
    runner = SandboxRunner(
        enabled=True,
        fail_closed=True,
        adapters=[_FakeAdapter(name="fake", available=False)],
    )
    with pytest.raises(SandboxUnavailableError):
        runner.build(command="echo hi", cwd=tmp_path, read_roots=[], write_roots=[])


def test_fail_open_falls_back_to_bash_when_no_adapter(tmp_path):
    runner = SandboxRunner(
        enabled=True,
        fail_closed=False,
        adapters=[_FakeAdapter(name="fake", available=False)],
    )
    result = runner.build(
        command="echo hi", cwd=tmp_path, read_roots=[], write_roots=[]
    )
    assert result.sandboxed is False
    assert result.argv == ["bash", "-lc", "echo hi"]


def test_disable_requested_requires_allow_unsandboxed(tmp_path):
    runner = SandboxRunner(
        enabled=True,
        allow_unsandboxed=False,
        adapters=[_FakeAdapter(name="fake", available=True)],
    )
    with pytest.raises(SandboxUnavailableError):
        runner.build(
            command="echo hi",
            cwd=tmp_path,
            read_roots=[tmp_path],
            write_roots=[tmp_path],
            disable_requested=True,
        )

    permissive = SandboxRunner(
        enabled=True,
        allow_unsandboxed=True,
        adapters=[_FakeAdapter(name="fake", available=True)],
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
        _spec(
            command="cat /etc/passwd",
            cwd=write_root,
            read_roots=[read_root],
            write_roots=[write_root],
        )
    )
    assert spec_argv[:6] == [
        "bwrap",
        "--unshare-user",
        "--uid",
        "0",
        "--gid",
        "0",
    ]
    assert spec_argv.index("--ro-bind") >= 6
    assert "--unshare-net" in spec_argv
    assert "--die-with-parent" in spec_argv
    # read root bound read-only, write root bound read-write
    assert "--ro-bind" in spec_argv
    assert spec_argv[-3:] == ["bash", "-lc", "cat /etc/passwd"]
    ro_bind_pairs = [
        (spec_argv[i + 1], spec_argv[i + 2])
        for i, token in enumerate(spec_argv)
        if token == "--ro-bind"
    ]
    assert ("/etc", "/etc") not in ro_bind_pairs
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


def test_bubblewrap_is_unavailable_when_binary_is_missing(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_core.sandbox.process_sandbox.shutil.which",
        lambda _name: None,
    )
    run_calls = 0

    def unexpected_run(*_args, **_kwargs):
        nonlocal run_calls
        run_calls += 1
        raise AssertionError("probe must not run without the binary")

    monkeypatch.setattr(
        "app.services.agent_core.sandbox.process_sandbox.subprocess.run",
        unexpected_run,
    )

    assert BubblewrapAdapter().available() is False
    assert run_calls == 0


@pytest.mark.parametrize(
    ("returncode", "expected"),
    [(0, True), (1, False)],
)
def test_bubblewrap_availability_requires_successful_user_namespace_probe(
    monkeypatch, returncode, expected
):
    executable = f"/usr/bin/bwrap-exit-{returncode}"
    monkeypatch.setattr(
        "app.services.agent_core.sandbox.process_sandbox.shutil.which",
        lambda _name: executable,
    )
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr(
        "app.services.agent_core.sandbox.process_sandbox.subprocess.run", fake_run
    )

    assert BubblewrapAdapter().available() is expected
    assert calls == [
        (
            [
                executable,
                "--unshare-user",
                "--uid",
                "0",
                "--gid",
                "0",
                "--ro-bind",
                "/",
                "/",
                "--",
                "/bin/true",
            ],
            {
                "check": False,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "timeout": 2.0,
            },
        )
    ]


def test_bubblewrap_availability_treats_probe_timeout_as_unavailable(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_core.sandbox.process_sandbox.shutil.which",
        lambda _name: "/usr/bin/bwrap-timeout",
    )

    def timed_out(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="bwrap", timeout=2.0)

    monkeypatch.setattr(
        "app.services.agent_core.sandbox.process_sandbox.subprocess.run", timed_out
    )

    assert BubblewrapAdapter().available() is False


def test_bubblewrap_availability_probe_is_cached_across_adapters(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_core.sandbox.process_sandbox.shutil.which",
        lambda _name: "/usr/bin/bwrap-cross-adapter-cache",
    )
    calls = 0

    def fake_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        "app.services.agent_core.sandbox.process_sandbox.subprocess.run", fake_run
    )
    assert BubblewrapAdapter().available() is True
    assert BubblewrapAdapter().available() is True
    assert calls == 1


def test_bubblewrap_availability_reprobes_after_cache_ttl(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_core.sandbox.process_sandbox.shutil.which",
        lambda _name: "/usr/bin/bwrap-expiring-cache",
    )
    now = 100.0
    returncodes = iter((1, 0))
    calls = 0

    def clock():
        return now

    def fake_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(returncode=next(returncodes))

    monkeypatch.setattr(
        "app.services.agent_core.sandbox.process_sandbox.subprocess.run", fake_run
    )

    assert BubblewrapAdapter(clock=clock).available() is False
    assert BubblewrapAdapter(clock=clock).available() is False
    assert calls == 1

    now += 31.0

    assert BubblewrapAdapter(clock=clock).available() is True
    assert calls == 2


def test_bubblewrap_mounts_tmpfs_before_capability_roots_under_tmp(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    argv = BubblewrapAdapter().build_argv(
        _spec(
            command="printf ok",
            cwd=workspace,
            read_roots=[workspace],
            write_roots=[workspace],
        )
    )

    tmpfs_index = argv.index("--tmpfs")
    workspace_bind_index = next(
        index
        for index, token in enumerate(argv)
        if token == "--bind" and argv[index + 1] == str(workspace)
    )
    assert tmpfs_index < workspace_bind_index


def test_bubblewrap_masks_attachment_store_then_exposes_only_session_read_only(
    tmp_path,
):
    data_root = tmp_path / "data"
    attachment_store = data_root / "state" / "agent_core" / "attachments"
    session_root = attachment_store / "session-current"
    other_root = attachment_store / "session-other"
    session_root.mkdir(parents=True)
    other_root.mkdir()

    argv = BubblewrapAdapter().build_argv(
        _spec(
            command="cat input.txt",
            cwd=data_root,
            read_roots=[data_root, session_root],
            write_roots=[data_root],
            protected_roots=[attachment_store],
            protected_read_roots=[session_root],
        )
    )

    data_bind = argv.index("--bind", argv.index(str(data_root)) - 1)
    mask = argv.index("--tmpfs", data_bind + 1)
    stage_bind = next(
        index
        for index, token in enumerate(argv)
        if token == "--ro-bind"
        and argv[index + 1] == str(session_root)
        and argv[index + 2] != str(session_root)
    )
    stage_alias = argv[stage_bind + 2]
    session_ro_bind = next(
        index
        for index, token in enumerate(argv)
        if token == "--ro-bind"
        and argv[index + 1 : index + 3] == [stage_alias, str(session_root)]
    )
    hide_stage = next(
        index
        for index, token in enumerate(argv)
        if token == "--tmpfs" and argv[index + 1] == stage_alias
    )
    assert argv[mask + 1] == str(attachment_store)
    assert data_bind < stage_bind < mask < session_ro_bind < hide_stage
    assert str(other_root) not in argv
    assert (str(session_root), str(session_root)) not in [
        (argv[index + 1], argv[index + 2])
        for index, token in enumerate(argv)
        if token == "--ro-bind"
    ]
    assert (str(session_root), str(session_root)) not in [
        (argv[index + 1], argv[index + 2])
        for index, token in enumerate(argv)
        if token == "--bind"
    ]


def test_bubblewrap_masks_protected_files_with_dev_null(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    protected_file = workspace / "secret.db"
    protected_file.write_text("secret", encoding="utf-8")

    argv = BubblewrapAdapter().build_argv(
        _spec(
            command="true",
            cwd=workspace,
            read_roots=[workspace],
            write_roots=[workspace],
            protected_roots=[protected_file],
        )
    )

    assert ["--ro-bind", "/dev/null", str(protected_file)] == argv[
        argv.index(str(protected_file)) - 2 : argv.index(str(protected_file)) + 1
    ]
    assert not any(
        token == "--tmpfs" and argv[index + 1] == str(protected_file)
        for index, token in enumerate(argv[:-1])
    )


def test_seatbelt_denies_attachment_writes_and_other_session_reads(tmp_path):
    data_root = tmp_path / "data"
    attachment_store = data_root / "state" / "agent_core" / "attachments"
    session_root = attachment_store / "session-current"
    session_root.mkdir(parents=True)

    profile = SeatbeltAdapter()._profile(
        _spec(
            command="cat input.txt",
            cwd=data_root,
            read_roots=[data_root, session_root],
            write_roots=[data_root],
            protected_roots=[attachment_store],
            protected_read_roots=[session_root],
        )
    )

    assert f'(deny file-write* (subpath "{attachment_store}"))' in profile
    assert str(session_root) in profile
    assert "require-not" in profile


def test_filesystem_policy_allows_absolute_path_inside_allowed_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    target = root / "sample.txt"
    target.write_text("ok", encoding="utf-8")

    assert (
        FilesystemPolicy(allowed_roots=[root]).require_allowed_path(target)
        == target.resolve()
    )


def test_filesystem_policy_rejects_absolute_path_outside_allowed_root(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    target = outside / "secret.txt"
    target.write_text("secret", encoding="utf-8")

    with pytest.raises(PermissionDeniedError):
        FilesystemPolicy(allowed_roots=[root]).require_allowed_path(target)


def test_filesystem_policy_rejects_symlink_escape(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    target = outside / "secret.txt"
    target.write_text("secret", encoding="utf-8")
    link = root / "link.txt"
    link.symlink_to(target)

    with pytest.raises(PermissionDeniedError):
        FilesystemPolicy(allowed_roots=[root]).require_allowed_path(link)


def test_filesystem_policy_resolves_relative_paths_from_allowed_root(
    tmp_path, monkeypatch
):
    root = tmp_path / "root"
    root.mkdir()
    target = root / "sample.txt"
    target.write_text("ok", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert (
        FilesystemPolicy(allowed_roots=[root]).require_allowed_path("sample.txt")
        == target.resolve()
    )


def test_filesystem_policy_distinguishes_read_and_write_roots(tmp_path):
    read_root = tmp_path / "reference"
    write_root = tmp_path / "project"
    read_root.mkdir()
    write_root.mkdir()
    reference = read_root / "genome.fa"
    reference.write_text("ACGT", encoding="utf-8")

    policy = FilesystemPolicy(
        read_roots=[read_root, write_root],
        write_roots=[write_root],
        default_root=write_root,
    )

    assert policy.require_allowed_path(reference) == reference.resolve()
    with pytest.raises(PermissionDeniedError, match="outside allowed roots"):
        policy.require_parent_dir(read_root / "new.fa")


def test_filesystem_policy_denies_protected_path_before_allowed_root(tmp_path):
    allowed = tmp_path
    protected = tmp_path / "product-source"
    protected.mkdir()
    source = protected / "main.py"
    source.write_text("secret implementation", encoding="utf-8")

    policy = FilesystemPolicy(
        read_roots=[allowed],
        write_roots=[allowed],
        protected_roots=[protected],
        default_root=allowed,
    )

    with pytest.raises(PermissionDeniedError, match="protected"):
        policy.require_allowed_path(source)


def test_filesystem_policy_cannot_resolve_docker_socket_outside_ordinary_roots(
    tmp_path, monkeypatch
):
    socket = tmp_path / "docker.sock"
    socket.touch()
    monkeypatch.setattr(settings, "docker_socket", f"unix://{socket}")
    ordinary_root = tmp_path / "ordinary"
    ordinary_root.mkdir()
    policy = FilesystemPolicy(allowed_roots=[ordinary_root])

    with pytest.raises(PermissionDeniedError, match="outside allowed roots"):
        policy.require_allowed_path(socket)


def test_container_repo_root_slash_does_not_block_declared_external_root(
    tmp_path, monkeypatch
):
    external = tmp_path / "external"
    external.mkdir()
    target = external / "result.txt"
    target.write_text("ok", encoding="utf-8")
    monkeypatch.setattr(settings, "repo_root", "/")
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path / "data"))

    assert (
        FilesystemPolicy(allowed_roots=[external]).require_allowed_path(target)
        == target
    )


def test_filesystem_policy_rejects_writes_inside_protected_root(tmp_path):
    root = tmp_path / "root"
    protected = root / "attachments"
    protected.mkdir(parents=True)
    target = protected / "input.txt"
    target.write_text("keep", encoding="utf-8")
    policy = FilesystemPolicy(allowed_roots=[root], protected_roots=[protected])

    with pytest.raises(PermissionDeniedError, match="protected"):
        policy.require_allowed_path(target)
    with pytest.raises(PermissionDeniedError, match="protected"):
        policy.require_parent_dir(protected / "new.txt")


def _spec(
    *,
    command: str,
    cwd: Path,
    read_roots,
    write_roots,
    deny_read_roots=None,
    protected_roots=None,
    protected_read_roots=None,
):
    from app.services.agent_core.sandbox.process_sandbox import SandboxSpec

    return SandboxSpec(
        command=command,
        cwd=cwd,
        read_roots=read_roots,
        write_roots=write_roots,
        deny_read_roots=deny_read_roots or [],
        protected_roots=protected_roots or [],
        protected_read_roots=protected_read_roots or [],
        allow_network=False,
    )
