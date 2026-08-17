from __future__ import annotations

import os
from pathlib import Path
import shlex
from types import SimpleNamespace

import pytest

from app.services.agent_harness.command_risk import CommandRiskAssessment
from app.services.agent_harness.sandbox.capability_paths import (
    require_safe_workspace_root,
    sensitive_capability_paths,
)
from app.services.agent_harness.sandbox.process_sandbox import (
    SandboxRunner,
    SandboxUnavailableError,
)
from app.services.agent_harness.tools.executor import ToolExecutor
from app.services.agent_harness.tools.specs import ToolCall
from app.services.agent_harness.workspace_runtime import LocalWorkspaceBackend


async def _run_with_available_host_sandbox(
    backend: LocalWorkspaceBackend,
    **kwargs,
) -> dict[str, object]:
    try:
        return await backend.run_command(**kwargs)
    except SandboxUnavailableError as exc:
        if "cannot protect privileged endpoint" not in str(exc):
            raise
        pytest.skip(f"host sandbox cannot mask capability paths: {exc}")


@pytest.mark.asyncio
async def test_real_deepseek_read_only_mode_denies_workspace_write(
    tmp_path: Path,
) -> None:
    backend = LocalWorkspaceBackend(
        working_directory=tmp_path,
        read_roots=(Path("/"),),
        write_roots=(tmp_path,),
        sandbox_runner=SandboxRunner(enabled=True),
    )

    result = await _run_with_available_host_sandbox(
        backend,
        command="touch denied.txt",
        cwd=None,
        timeout_seconds=10,
        output_limit=4096,
        cancellation=None,
        environment={},
        sandbox_mode="read-only",
    )

    assert result["exit_code"] != 0
    assert not (tmp_path / "denied.txt").exists()
    assert result["sandbox"]["mode"] == "read-only"
    assert result["sandbox"]["enforcement"] == "full"
    assert result["sandbox"]["denied"] is True


@pytest.mark.asyncio
async def test_real_deepseek_workspace_write_allows_workspace_only(
    tmp_path: Path,
) -> None:
    outside = Path.home() / f".{tmp_path.name}-outside.txt"
    outside.unlink(missing_ok=True)
    backend = LocalWorkspaceBackend(
        working_directory=tmp_path,
        read_roots=(Path("/"),),
        write_roots=(tmp_path,),
        sandbox_runner=SandboxRunner(enabled=True),
    )

    allowed = await _run_with_available_host_sandbox(
        backend,
        command="printf ok > allowed.txt",
        cwd=None,
        timeout_seconds=10,
        output_limit=4096,
        cancellation=None,
        environment={},
        sandbox_mode="workspace-write",
    )
    denied = await _run_with_available_host_sandbox(
        backend,
        command=f"printf no > {outside}",
        cwd=None,
        timeout_seconds=10,
        output_limit=4096,
        cancellation=None,
        environment={},
        sandbox_mode="workspace-write",
    )

    assert allowed["exit_code"] == 0
    assert (tmp_path / "allowed.txt").read_text(encoding="utf-8") == "ok"
    assert denied["exit_code"] != 0
    assert not outside.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["read-only", "workspace-write"])
async def test_real_deepseek_confined_modes_allow_external_reads(
    tmp_path: Path,
    mode: str,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-{mode}-readable.txt"
    outside.write_text("host-readable", encoding="utf-8")
    backend = LocalWorkspaceBackend(
        working_directory=tmp_path,
        read_roots=(Path("/"),),
        write_roots=(tmp_path,),
        sandbox_runner=SandboxRunner(enabled=True),
    )

    result = await _run_with_available_host_sandbox(
        backend,
        command=f"cat {shlex.quote(str(outside))}",
        cwd=None,
        timeout_seconds=10,
        output_limit=4096,
        cancellation=None,
        environment={},
        sandbox_mode=mode,
    )

    assert result["exit_code"] == 0
    assert result["stdout"] == "host-readable"


@pytest.mark.asyncio
async def test_local_direct_read_allows_host_readable_external_file(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-readable.txt"
    outside.write_text("host-readable", encoding="utf-8")
    backend = LocalWorkspaceBackend(
        working_directory=tmp_path,
        read_roots=(Path("/"),),
        write_roots=(tmp_path,),
        sandbox_runner=SimpleNamespace(enabled=True),
    )

    path, data = await backend.read_bytes(str(outside))

    assert path == str(outside.resolve())
    assert data == b"host-readable"
    with pytest.raises(Exception, match="outside allowed roots"):
        backend.resolve_write_path(
            str(outside),
            must_exist=True,
            create_parents=False,
        )


@pytest.mark.asyncio
async def test_local_direct_read_blocks_control_plane_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    workspace = home / "projects" / "demo"
    state = home / "state"
    workspace.mkdir(parents=True)
    state.mkdir(parents=True)
    secret = state / "better-auth.db"
    secret.write_text("session-token", encoding="utf-8")
    monkeypatch.setattr(
        "app.services.agent_harness.sandbox.filesystem_policy.settings.bioinfoflow_home",
        str(home),
    )
    backend = LocalWorkspaceBackend(
        working_directory=workspace,
        read_roots=(Path("/"),),
        write_roots=(workspace,),
        sandbox_runner=SimpleNamespace(enabled=True),
    )

    with pytest.raises(Exception, match="protected"):
        await backend.read_bytes(str(secret))


@pytest.mark.asyncio
async def test_local_direct_read_blocks_process_capabilities(tmp_path: Path) -> None:
    if not Path("/proc/self/environ").exists():
        pytest.skip("procfs is not available on this platform")
    backend = LocalWorkspaceBackend(
        working_directory=tmp_path,
        read_roots=(Path("/"),),
        write_roots=(tmp_path,),
        sandbox_runner=SimpleNamespace(enabled=True),
    )

    with pytest.raises(Exception, match="protected"):
        await backend.read_bytes("/proc/self/environ")


@pytest.mark.asyncio
async def test_local_direct_read_blocks_configured_external_auth_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_db = tmp_path.parent / f"{tmp_path.name}-better-auth.db"
    auth_db.write_text("session-token", encoding="utf-8")
    monkeypatch.setattr(
        "app.services.agent_harness.sandbox.capability_paths.settings.better_auth_db_path",
        str(auth_db),
    )
    backend = LocalWorkspaceBackend(
        working_directory=tmp_path,
        read_roots=(Path("/"),),
        write_roots=(tmp_path,),
        sandbox_runner=SimpleNamespace(enabled=True),
    )

    with pytest.raises(Exception, match="protected"):
        await backend.read_bytes(str(auth_db))


def test_local_workspace_rejects_root_containing_control_plane_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "bioinfoflow-home"
    home.mkdir(exist_ok=True)
    (home / "state").mkdir()
    monkeypatch.setattr(
        "app.services.agent_harness.sandbox.capability_paths.settings.bioinfoflow_home",
        str(home),
    )

    with pytest.raises(RuntimeError, match="overlaps a protected capability"):
        require_safe_workspace_root(home)


def test_sensitive_capability_paths_collapse_and_expand_credential_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ssh_socket = tmp_path / "ssh-agent.sock"
    kube_a = tmp_path / "kube-a"
    kube_b = tmp_path / "kube-b"
    monkeypatch.setenv("SSH_AUTH_SOCK", str(ssh_socket))
    monkeypatch.setenv("KUBECONFIG", os.pathsep.join((str(kube_a), str(kube_b))))

    paths = sensitive_capability_paths()

    assert ssh_socket.resolve(strict=False) in paths
    assert kube_a.resolve(strict=False) in paths
    assert kube_b.resolve(strict=False) in paths


class _EscalationBackend:
    supports_sandbox_escalation = True

    def __init__(self, root: Path) -> None:
        self.root = root
        self.modes: list[str] = []

    def assess_command(self, command, cwd=None):
        if command == "pwd":
            return CommandRiskAssessment(
                level="observe",
                reasons=[command],
                effects=["read"],
                confidence="high",
                target={"kind": "local"},
                boundary={"working_directory": str(self.root)},
            )
        hard_blocked = command != "touch approved.txt"
        return CommandRiskAssessment(
            level="act_high",
            reasons=[command],
            effects=["write"],
            confidence="high",
            target={"kind": "local"},
            boundary={"working_directory": str(self.root)},
            hard_blocked=hard_blocked,
        )

    async def command_cwd_binding(self, cwd):
        return {"kind": "local", "path": str(self.root), "dev": 1, "ino": 2}

    async def run_command(self, **kwargs):
        self.modes.append(kwargs["sandbox_mode"])
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    def canonical_path(self, raw_path):
        return (self.root / raw_path).resolve()


@pytest.mark.asyncio
async def test_escalation_is_structured_forced_confirmation_and_one_shot(
    tmp_path: Path,
) -> None:
    backend = _EscalationBackend(tmp_path)
    executor = ToolExecutor(
        backend,
        permission_mode="full_access",
        workspace_access="read_only",
    )
    call = ToolCall(
        "call-1",
        "bash",
        {
            "command": "touch /outside",
            "sandbox_permissions": "require_escalated",
            "justification": "write the explicitly approved external target",
        },
    )

    pending = await executor.execute(call)

    assert pending.status == "interaction_required"
    assert pending.interaction is not None
    assert pending.interaction.summary == "Run command"
    assert pending.interaction.risk is not None
    assert pending.interaction.risk["sandbox_mode"] == "danger-full-access"
    assert pending.interaction.risk["reason_codes"] == ["sandbox_escalation"]
    assert (
        pending.interaction.risk["justification"]
        == "write the explicitly approved external target"
    )
    changed_command = await executor.execute(
        ToolCall(
            call.call_id,
            call.name,
            {**call.arguments, "command": "touch  /outside"},
        ),
        interaction_response={
            "request_id": pending.interaction.request_id,
            "approved": True,
            "assessment_fingerprint": pending.interaction.risk[
                "assessment_fingerprint"
            ],
        },
    )
    assert changed_command.status == "blocked"
    assert "assessment changed" in str(changed_command.error)
    changed = await executor.execute(
        ToolCall(
            call.call_id,
            call.name,
            {**call.arguments, "justification": "a different reason"},
        ),
        interaction_response={
            "request_id": pending.interaction.request_id,
            "approved": True,
            "assessment_fingerprint": pending.interaction.risk[
                "assessment_fingerprint"
            ],
        },
    )
    assert changed.status == "blocked"
    assert "assessment changed" in str(changed.error)

    approved = await executor.execute(
        call,
        interaction_response={
            "request_id": pending.interaction.request_id,
            "approved": True,
            "assessment_fingerprint": pending.interaction.risk[
                "assessment_fingerprint"
            ],
        },
    )

    assert approved.status == "completed"
    assert backend.modes == ["danger-full-access"]

    default_call = ToolCall("call-2", "bash", {"command": "pwd"})
    default_result = await executor.execute(default_call)
    assert default_result.status == "completed"
    assert backend.modes == ["danger-full-access", "read-only"]


@pytest.mark.asyncio
async def test_approval_fingerprint_binds_effective_sandbox_mode(
    tmp_path: Path,
) -> None:
    executor = ToolExecutor(
        _EscalationBackend(tmp_path),
        permission_mode="ask_changes",
        workspace_access="read_write",
    )
    call = ToolCall("call-mode", "bash", {"command": "touch approved.txt"})
    pending = await executor.execute(call)

    assert pending.status == "interaction_required"
    assert pending.interaction is not None
    assert pending.interaction.risk is not None
    assert pending.interaction.risk["sandbox_mode"] == "workspace-write"

    executor.workspace_access = "read_only"
    assert not executor.approval_assessment_matches(
        call,
        {"risk": pending.interaction.risk},
    )


@pytest.mark.asyncio
async def test_escalation_requires_justification_and_is_rejected_remotely(
    tmp_path: Path,
) -> None:
    local = _EscalationBackend(tmp_path)
    missing = await ToolExecutor(local).execute(
        ToolCall(
            "missing",
            "bash",
            {
                "command": "true",
                "sandbox_permissions": "require_escalated",
            },
        )
    )
    assert missing.status == "failed"
    assert "justification is required" in str(missing.error)

    local.supports_sandbox_escalation = False
    remote = await ToolExecutor(local).execute(
        ToolCall(
            "remote",
            "bash",
            {
                "command": "true",
                "sandbox_permissions": "require_escalated",
                "justification": "requested remote bypass",
            },
        )
    )
    assert remote.status == "blocked"
    assert "not supported" in str(remote.error)


@pytest.mark.asyncio
async def test_runner_failure_is_classified_before_ordinary_command_failure(
    tmp_path: Path,
) -> None:
    class FailedRunner:
        enabled = True

        def build(self, **_kwargs):
            return SimpleNamespace(
                argv=["bash", "-c", "printf 'runner: fatal' >&2; exit 125"],
                mode="workspace-write",
                adapter="fake",
                enforcement="full",
                denial_signatures=("permission denied",),
                runner_failure_rules=(
                    {
                        "allowed_exit_codes": (125,),
                        "fatal_signatures": ("runner: ",),
                    },
                ),
            )

    backend = LocalWorkspaceBackend(
        working_directory=tmp_path,
        read_roots=(Path("/"),),
        write_roots=(tmp_path,),
        sandbox_runner=FailedRunner(),
    )

    with pytest.raises(RuntimeError, match="runner failed"):
        await backend.run_command(
            command="true",
            cwd=None,
            timeout_seconds=10,
            output_limit=4096,
            cancellation=None,
            environment={},
        )
