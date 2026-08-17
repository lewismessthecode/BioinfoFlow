from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import app.services.agent_harness.sandbox as sandbox
from app.config import Settings
from app.services.agent_harness.sandbox.process_sandbox import (
    SandboxRunner,
    SandboxUnavailableError,
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
    assert "BubblewrapAdapter" not in sandbox.__all__
    assert "SeatbeltAdapter" not in sandbox.__all__


def test_settings_do_not_expose_an_unsandboxed_agent_escape_hatch() -> None:
    assert "agent_sandbox_allow_unsandboxed" not in Settings.model_fields


def test_sandbox_runner_rejects_legacy_fail_open_options(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="fail_closed"):
        SandboxRunner(enabled=True, fail_closed=False)
    with pytest.raises(TypeError, match="disable_requested"):
        SandboxRunner(enabled=True).build(
            command="true",
            cwd=tmp_path,
            disable_requested=True,
        )


def test_disabled_sandbox_runner_fails_closed(tmp_path: Path) -> None:
    runner = SandboxRunner(enabled=False)

    with pytest.raises(
        SandboxUnavailableError,
        match="requires operating-system sandboxing",
    ):
        runner.build(command="true", cwd=tmp_path)


def test_unavailable_worker_fails_closed(tmp_path: Path) -> None:
    class MissingClient:
        def availability(self):
            return {
                "adapter": "deepseek-local",
                "executable": None,
                "available": False,
                "failure_category": "binary_missing",
                "failure_message": "node missing",
            }

        def confine(self, **request):
            raise SandboxUnavailableError(f"unavailable: {request['mode']}")

    runner = SandboxRunner(enabled=True, client=MissingClient())

    with pytest.raises(SandboxUnavailableError, match="unavailable"):
        runner.build(command="true", cwd=tmp_path, mode="read-only")


def test_local_backend_assesses_commands_with_its_enforced_boundary(
    tmp_path: Path,
) -> None:
    backend = LocalWorkspaceBackend(
        working_directory=tmp_path,
        read_roots=(Path("/"),),
        write_roots=(tmp_path,),
        sandbox_runner=SimpleNamespace(
            enabled=True,
            available_adapter=lambda: object(),
        ),
    )

    assessment = backend.assess_command("pwd")

    assert assessment.target["kind"] == "local"
    assert assessment.boundary == {
        "enforced": True,
        "sandbox_strength": "enforced",
        "working_directory": str(tmp_path),
    }
    assert assessment.target["network_allowed"] is True


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
