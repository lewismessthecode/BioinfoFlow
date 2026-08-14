from __future__ import annotations

import platform
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.services.agent_harness.sandbox as sandbox
from app.config import Settings
from app.services.agent_harness.sandbox.process_sandbox import (
    BubblewrapAdapter,
    SandboxAvailability,
    SandboxRunner,
    SandboxSpec,
    SeatbeltAdapter,
    _executable_runtime_root,
)
from app.services.agent_harness.workspace_runtime import (
    LocalWorkspaceBackend,
    RemoteWorkspaceBackend,
)
from app.services.remote_execution import RemoteConnectionConfig


def test_sandbox_package_exposes_only_the_active_confinement_boundary() -> None:
    assert "LocalFilesystemBoundary" not in sandbox.__all__
    assert "LocalFilesystemBoundaryResolver" not in sandbox.__all__
    assert "local_boundary_from_tool_context" not in sandbox.__all__


def test_settings_do_not_expose_an_unsandboxed_agent_escape_hatch() -> None:
    assert "agent_sandbox_allow_unsandboxed" not in Settings.model_fields


def test_sandbox_runner_rejects_legacy_unsandboxed_constructor_option() -> None:
    with pytest.raises(TypeError, match="allow_unsandboxed"):
        SandboxRunner(
            enabled=True,
            allow_unsandboxed=True,
        )


def test_sandbox_runner_rejects_per_execution_disable_requests(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="disable_requested"):
        SandboxRunner(enabled=True).build(
            command="true",
            cwd=tmp_path,
            read_roots=[tmp_path],
            write_roots=[tmp_path],
            disable_requested=True,
        )


def test_disabled_sandbox_runner_fails_closed(tmp_path: Path) -> None:
    class _AvailableAdapter:
        name = "capture"

        def availability(self):
            return SandboxAvailability("capture", "/capture", True)

        def available(self):
            return True

        def supports_docker_socket(self, root):
            del root
            return False

        def build_argv(self, spec):
            return ["capture", spec.command]

    runner = SandboxRunner(enabled=False, adapters=[_AvailableAdapter()])

    with pytest.raises(RuntimeError, match="requires operating-system sandboxing"):
        runner.build(
            command="true",
            cwd=tmp_path,
            read_roots=[tmp_path],
            write_roots=[tmp_path],
        )


def test_sandbox_runner_rejects_legacy_fail_open_constructor_option() -> None:
    with pytest.raises(TypeError, match="fail_closed"):
        SandboxRunner(enabled=True, fail_closed=False)


def test_unavailable_sandbox_fails_closed(tmp_path: Path) -> None:
    class _UnavailableAdapter:
        name = "missing"

        def availability(self):
            return SandboxAvailability(
                adapter="missing",
                executable=None,
                available=False,
                failure_category="binary_missing",
                failure_message="missing executable",
            )

        def available(self):
            return False

        def supports_docker_socket(self, root):
            del root
            return False

        def build_argv(self, spec):
            raise AssertionError(f"unavailable adapter used for {spec.command}")

    runner = SandboxRunner(
        enabled=True,
        adapters=[_UnavailableAdapter()],
    )

    with pytest.raises(RuntimeError, match="agent sandbox unavailable"):
        runner.build(
            command="true",
            cwd=tmp_path,
            read_roots=[tmp_path],
            write_roots=[tmp_path],
        )


def test_local_backend_assesses_commands_with_its_enforced_boundary(
    tmp_path: Path,
) -> None:
    backend = LocalWorkspaceBackend(
        working_directory=tmp_path,
        read_roots=(tmp_path,),
        write_roots=(tmp_path,),
        sandbox_runner=SimpleNamespace(
            enabled=True,
            allow_network=False,
            available_adapter=lambda: object(),
        ),
    )

    assessment = backend.assess_command("pwd")

    assert assessment.target["kind"] == "local"
    assert assessment.target["network_allowed"] is False
    assert assessment.boundary == {
        "enforced": True,
        "sandbox_strength": "enforced",
        "working_directory": str(tmp_path),
    }
    assert "sandbox_bypass_requested" not in assessment.boundary


def test_remote_backend_assesses_commands_against_its_fixed_connection() -> None:
    backend = RemoteWorkspaceBackend(
        connection=RemoteConnectionConfig(
            id="connection-1",
            name="analysis-host",
            host="compute.example.org",
            username="agent",
        ),
        executor=object(),
        working_directory="/workspace",
        read_roots=("/workspace",),
        write_roots=("/workspace",),
        allow_network=False,
    )

    assessment = backend.assess_command("pwd")

    assert assessment.target == {
        "kind": "remote_ssh",
        "trust_domain": "compute.example.org",
        "identity": "agent",
        "connection_id": "connection-1",
        "network_allowed": False,
        "privileged": False,
    }
    assert assessment.boundary == {
        "enforced": True,
        "sandbox_strength": "enforced",
        "working_directory": "/workspace",
    }


def test_seatbelt_profile_allows_only_workspace_and_runtime_reads(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    profile = SeatbeltAdapter()._profile(
        SandboxSpec(
            command="cat input.txt",
            cwd=workspace,
            read_roots=[workspace],
            write_roots=[workspace],
        )
    )

    assert "(allow file-read*)" not in profile
    assert f'(subpath "{workspace}")' in profile
    assert "(deny file-read-data\n" in profile
    assert '(require-not (literal "/"))' in profile
    assert f'(require-not (subpath "{workspace}"))' in profile
    assert f'(subpath "{Path.home()}")' not in profile
    assert f'(require-not (subpath "{Path.home() / ".ssh"}"))' not in profile


@pytest.mark.skipif(
    platform.system() != "Darwin" or shutil.which("sandbox-exec") is None,
    reason="real Seatbelt verification requires macOS sandbox-exec",
)
def test_real_seatbelt_denies_workspace_external_secret(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    allowed = workspace / "allowed.txt"
    allowed.write_text("allowed", encoding="utf-8")
    secret = tmp_path / "outside-secret.txt"
    secret.write_text("secret", encoding="utf-8")
    adapter = SeatbeltAdapter()
    spec = SandboxSpec(
        command="",
        cwd=workspace,
        read_roots=[workspace],
        write_roots=[workspace],
    )

    allowed_run = subprocess.run(
        adapter.build_argv(
            SandboxSpec(**{**spec.__dict__, "command": f"/bin/cat {allowed}"})
        ),
        check=False,
        capture_output=True,
        text=True,
    )
    denied_run = subprocess.run(
        adapter.build_argv(
            SandboxSpec(**{**spec.__dict__, "command": f"/bin/cat {secret}"})
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert allowed_run.returncode == 0
    assert allowed_run.stdout == "allowed"
    assert denied_run.returncode != 0
    assert "secret" not in denied_run.stdout


@pytest.mark.skipif(
    platform.system() != "Darwin" or shutil.which("sandbox-exec") is None,
    reason="real Seatbelt verification requires macOS sandbox-exec",
)
def test_real_seatbelt_masks_platform_data_inside_a_broad_workspace(
    tmp_path: Path,
) -> None:
    external_root = tmp_path / "home"
    repo_root = external_root / "BioinfoFlow"
    state = repo_root / "data" / "state"
    skill_root = repo_root / "data" / "skills" / "ngs"
    source = repo_root / "backend" / "app" / "secret.py"
    attachment = state / "attachments" / "secret.txt"
    skill = skill_root / "SKILL.md"
    for path, content in (
        (source, "source-secret"),
        (attachment, "attachment-secret"),
        (skill, "allowed-skill"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    command = "; ".join(
        (
            f"/bin/cat {shlex.quote(str(source))} 2>/dev/null || true",
            f"/bin/echo changed > {shlex.quote(str(attachment))} 2>/dev/null || true",
            f"/bin/cat {shlex.quote(str(skill))}",
        )
    )
    run = subprocess.run(
        SeatbeltAdapter().build_argv(
            SandboxSpec(
                command=command,
                cwd=external_root,
                read_roots=[external_root, skill_root],
                write_roots=[external_root],
                protected_roots=[repo_root, state],
                protected_read_roots=[skill_root],
            )
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert run.returncode == 0
    assert run.stdout == "allowed-skill"
    assert attachment.read_text(encoding="utf-8") == "attachment-secret"


@pytest.mark.skipif(
    platform.system() != "Darwin" or shutil.which("sandbox-exec") is None,
    reason="real Seatbelt verification requires macOS sandbox-exec",
)
def test_real_seatbelt_denies_secret_outside_enumerated_scopes(tmp_path: Path) -> None:
    outside_root = Path("/private/var/tmp")
    if not outside_root.is_dir():
        pytest.skip("/private/var/tmp is unavailable")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="bioinfoflow-seatbelt-secret-",
        dir=outside_root,
        delete=False,
    ) as handle:
        handle.write("outside-scope-secret")
        secret = Path(handle.name)
    try:
        run = subprocess.run(
            SeatbeltAdapter().build_argv(
                SandboxSpec(
                    command=f"/bin/cat {secret}",
                    cwd=workspace,
                    read_roots=[workspace],
                    write_roots=[workspace],
                )
            ),
            check=False,
            capture_output=True,
            text=True,
        )
        assert run.returncode != 0
        assert "outside-scope-secret" not in run.stdout
    finally:
        secret.unlink(missing_ok=True)


@pytest.mark.skipif(
    platform.system() != "Darwin" or shutil.which("sandbox-exec") is None,
    reason="real Seatbelt verification requires macOS sandbox-exec",
)
def test_real_seatbelt_denies_home_ssh_reads(tmp_path: Path) -> None:
    ssh_root = Path.home() / ".ssh"
    candidate = next((path for path in ssh_root.glob("*") if path.is_file()), None)
    if candidate is None:
        pytest.skip("no existing ~/.ssh file is available for a non-mutating test")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run = subprocess.run(
        SeatbeltAdapter().build_argv(
            SandboxSpec(
                command=f"/bin/cat {candidate}",
                cwd=workspace,
                read_roots=[workspace],
                write_roots=[workspace],
            )
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert run.returncode != 0
    assert candidate.read_text(encoding="utf-8", errors="replace") not in run.stdout


def test_bubblewrap_structure_binds_runtime_read_only_and_denies_network(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    runtime = tmp_path / "runtime"
    workspace.mkdir()
    runtime.mkdir()
    argv = BubblewrapAdapter().build_argv(
        SandboxSpec(
            command="bif --version",
            cwd=workspace,
            read_roots=[workspace, runtime],
            write_roots=[workspace],
        )
    )

    runtime_index = argv.index(str(runtime))
    assert argv[runtime_index - 1] == "--ro-bind"
    assert "--unshare-net" in argv
    write_index = argv.index("--bind")
    assert argv[write_index : write_index + 3] == [
        "--bind",
        str(workspace),
        str(workspace),
    ]
    assert argv[-5:] == [
        "bash",
        "--noprofile",
        "--norc",
        "-c",
        "bif --version",
    ]


def test_bubblewrap_masks_a_broad_platform_root_and_restores_narrow_reads(
    tmp_path: Path,
) -> None:
    external_root = tmp_path / "home"
    repo_root = external_root / "BioinfoFlow"
    state = repo_root / "data" / "state"
    skill_root = repo_root / "data" / "skills" / "ngs"
    for path in (state, skill_root):
        path.mkdir(parents=True)

    argv = BubblewrapAdapter().build_argv(
        SandboxSpec(
            command="true",
            cwd=external_root,
            read_roots=[external_root, skill_root],
            write_roots=[external_root],
            protected_roots=[repo_root, state],
            protected_read_roots=[skill_root],
        )
    )

    repo_hide = _argv_sequence_index(argv, ["--tmpfs", str(repo_root)])
    state_hide = _argv_sequence_index(argv, ["--tmpfs", str(state)])
    skill_restore = _argv_sequence_index(
        argv,
        [
            "--ro-bind",
            "/.bioinfoflow-protected-read-0",
            str(skill_root),
        ],
    )
    assert repo_hide < state_hide < skill_restore
    assert ["--bind", str(external_root), str(external_root)] == argv[
        argv.index("--bind") : argv.index("--bind") + 3
    ]
    assert (
        _argv_sequence_index(
            argv,
            ["--dir", str(skill_root)],
        )
        < skill_restore
    )


def test_seatbelt_masks_platform_roots_but_preserves_nested_reads(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "BioinfoFlow"
    project_root = repo_root / "data" / "projects" / "project-1"
    state = repo_root / "data" / "state"
    for path in (project_root, state):
        path.mkdir(parents=True)

    profile = SeatbeltAdapter()._profile(
        SandboxSpec(
            command="true",
            cwd=project_root,
            read_roots=[project_root],
            write_roots=[project_root],
            protected_roots=[repo_root, state],
            protected_read_roots=[project_root],
        )
    )

    assert f'(deny file-write* (subpath "{state}"))' in profile
    assert f'(deny file-read* (subpath "{state}"))' in profile
    assert f'(require-not (subpath "{project_root}"))' in profile
    assert f'(subpath "{repo_root}")' in profile


def test_bubblewrap_binds_the_inherited_cwd_fd_over_the_approved_path(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    argv = BubblewrapAdapter().build_argv(
        SandboxSpec(
            command="pwd",
            cwd=workspace,
            cwd_fd=17,
            read_roots=[workspace],
            write_roots=[workspace],
        )
    )

    fd_bind = argv.index("/proc/self/fd/17")
    sync_fd = argv.index("--sync-fd")
    assert argv[sync_fd + 1] == "17"
    assert argv[fd_bind - 1 : fd_bind + 2] == [
        "--bind",
        "/proc/self/fd/17",
        str(workspace),
    ]
    chdir = argv.index("--chdir")
    assert argv[chdir + 1] == str(workspace)
    assert sync_fd < fd_bind < chdir


def test_bubblewrap_keeps_a_read_only_approved_cwd_fd_read_only(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    output = tmp_path / "output"
    workspace.mkdir()
    output.mkdir()

    argv = BubblewrapAdapter().build_argv(
        SandboxSpec(
            command="pwd",
            cwd=workspace,
            cwd_fd=17,
            read_roots=[workspace],
            write_roots=[output],
        )
    )

    fd_bind = argv.index("/proc/self/fd/17")
    assert argv[fd_bind - 1 : fd_bind + 2] == [
        "--ro-bind",
        "/proc/self/fd/17",
        str(workspace),
    ]


@pytest.mark.asyncio
async def test_only_scoped_bif_enables_network_for_its_sandbox_process(
    tmp_path: Path,
) -> None:
    captured = []
    trusted_bin = tmp_path.parent / f"{tmp_path.name}-trusted-bin"
    trusted_bin.mkdir()
    trusted_bif = trusted_bin / "bif"
    trusted_bif.write_text("#!/bin/sh\n", encoding="utf-8")
    trusted_bif.chmod(0o755)

    class _Adapter:
        name = "capture"

        def availability(self):
            return SandboxAvailability("capture", "/capture", True)

        def supports_docker_socket(self, root):
            del root
            return False

        def build_argv(self, spec):
            captured.append(spec)
            return ["bash", "-lc", "true"]

    backend = LocalWorkspaceBackend(
        working_directory=tmp_path,
        read_roots=(tmp_path,),
        write_roots=(tmp_path,),
        sandbox_runner=SandboxRunner(
            enabled=True,
            allow_network=False,
            adapters=[_Adapter()],
        ),
        base_environment={"PATH": f"{trusted_bin}:/usr/bin:/bin"},
    )

    await backend.run_command(
        command="bif system health",
        cwd=None,
        timeout_seconds=5,
        output_limit=100,
        cancellation=None,
        environment={
            "BIOFLOW_API_URL": "http://127.0.0.1:8000/api/v1",
            "BIOFLOW_AGENT_TOKEN": "short-lived",
        },
    )
    await backend.run_command(
        command="curl https://example.org",
        cwd=None,
        timeout_seconds=5,
        output_limit=100,
        cancellation=None,
        environment={},
    )

    assert captured[0].allow_network is True
    assert captured[1].allow_network is False


@pytest.mark.asyncio
async def test_global_network_setting_remains_enabled_for_non_bif_commands(
    tmp_path: Path,
) -> None:
    captured = []

    class _Adapter:
        name = "capture"

        def availability(self):
            return SandboxAvailability("capture", "/capture", True)

        def supports_docker_socket(self, root):
            del root
            return False

        def build_argv(self, spec):
            captured.append(spec)
            return ["bash", "-lc", "true"]

    backend = LocalWorkspaceBackend(
        working_directory=tmp_path,
        read_roots=(tmp_path,),
        write_roots=(tmp_path,),
        sandbox_runner=SandboxRunner(
            enabled=True,
            allow_network=True,
            adapters=[_Adapter()],
        ),
        base_environment={"PATH": "/usr/bin:/bin"},
    )

    await backend.run_command(
        command="curl https://example.org",
        cwd=None,
        timeout_seconds=5,
        output_limit=100,
        cancellation=None,
        environment={},
    )

    assert captured[0].allow_network is True


def test_home_bin_runtime_never_expands_to_the_whole_home() -> None:
    home = Path.home().resolve()
    executable = home / "bin" / "bif"

    assert _executable_runtime_root(executable) == executable.parent
    assert _executable_runtime_root(executable) != home


def _argv_sequence_index(argv: list[str], sequence: list[str]) -> int:
    for index in range(len(argv) - len(sequence) + 1):
        if argv[index : index + len(sequence)] == sequence:
            return index
    raise AssertionError(f"argv does not contain sequence: {sequence!r}")
