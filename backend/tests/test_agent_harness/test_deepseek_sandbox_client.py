from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.services.agent_harness.sandbox.process_sandbox import (
    DeepSeekSandboxClient,
    SandboxRunner,
    SandboxUnavailableError,
)


_ECHO_WORKER = r"""
import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    response = {
        "version": 1,
        "id": request["id"],
        "ok": True,
        "result": {
            "argv": ["sandbox-runner", "--", *request["argv"]],
            "adapter": "fake",
            "enforcement": "full",
            "denial_signatures": ["denied"],
            "runner_failure_rules": [{"fatal_signatures": ["runner failed"]}],
        },
    }
    print(json.dumps(response), flush=True)
"""


def _client(script: str = _ECHO_WORKER) -> DeepSeekSandboxClient:
    return DeepSeekSandboxClient(
        worker_command=(sys.executable, "-u", "-c", script),
        request_timeout_seconds=2,
    )


def test_deepseek_client_returns_structured_confinement(tmp_path: Path) -> None:
    client = _client()
    try:
        result = client.confine(
            argv=["/bin/bash", "-c", "pwd"],
            mode="workspace-write",
            workspace_root=tmp_path,
            protected_endpoints=[Path("/var/run/docker.sock")],
        )
    finally:
        client.close()

    assert result.argv == ["sandbox-runner", "--", "/bin/bash", "-c", "pwd"]
    assert result.adapter == "fake"
    assert result.enforcement == "full"
    assert result.denial_signatures == ("denied",)
    assert result.runner_failure_rules == (
        {"fatal_signatures": ("runner failed",)},
    )


def test_deepseek_client_rejects_mismatched_response_id(tmp_path: Path) -> None:
    script = _ECHO_WORKER.replace('request["id"]', '"wrong-id"')
    client = _client(script)
    try:
        with pytest.raises(SandboxUnavailableError, match="response id"):
            client.confine(
                argv=["true"],
                mode="read-only",
                workspace_root=tmp_path,
                protected_endpoints=[],
            )
    finally:
        client.close()


@pytest.mark.parametrize(
    "script",
    [
        _ECHO_WORKER.replace(
            '"ok": True,',
            '"ok": True, "unexpected": True,',
        ),
        _ECHO_WORKER.replace(
            '"runner_failure_rules": [{"fatal_signatures": ["runner failed"]}],',
            '"runner_failure_rules": [{"fatal_signatures": ["runner failed"]}], "unexpected": True,',
        ),
    ],
)
def test_deepseek_client_rejects_unknown_protocol_fields(
    tmp_path: Path,
    script: str,
) -> None:
    client = _client(script)
    try:
        with pytest.raises(SandboxUnavailableError, match="schema is invalid"):
            client.confine(
                argv=["true"],
                mode="read-only",
                workspace_root=tmp_path,
                protected_endpoints=[],
            )
    finally:
        client.close()


def test_deepseek_client_fails_closed_on_worker_eof(tmp_path: Path) -> None:
    client = _client("raise SystemExit(17)")
    try:
        with pytest.raises(SandboxUnavailableError, match="worker exited"):
            client.confine(
                argv=["true"],
                mode="read-only",
                workspace_root=tmp_path,
                protected_endpoints=[],
            )
    finally:
        client.close()


def test_deepseek_client_fails_closed_on_worker_timeout(tmp_path: Path) -> None:
    client = DeepSeekSandboxClient(
        worker_command=(
            sys.executable,
            "-u",
            "-c",
            "import sys, time; sys.stdin.readline(); time.sleep(60)",
        ),
        request_timeout_seconds=0.05,
    )
    try:
        with pytest.raises(SandboxUnavailableError, match="response timed out"):
            client.confine(
                argv=["true"],
                mode="read-only",
                workspace_root=tmp_path,
                protected_endpoints=[],
            )
    finally:
        client.close()


def test_sandbox_runner_maps_mode_without_parsing_command(tmp_path: Path) -> None:
    class CaptureClient:
        def __init__(self) -> None:
            self.request: dict[str, object] | None = None

        def availability(self):
            return {
                "adapter": "deepseek-local",
                "executable": "node",
                "available": True,
            }

        def confine(self, **request):
            self.request = request
            return type(
                "Result",
                (),
                {
                    "argv": ["confined", *request["argv"]],
                    "adapter": "fake",
                    "enforcement": "full",
                    "denial_signatures": (),
                    "runner_failure_rules": (),
                },
            )()

    client = CaptureClient()
    runner = SandboxRunner(enabled=True, client=client)

    result = runner.build(
        command="printf ready",
        cwd=tmp_path,
        mode="read-only",
    )

    assert client.request is not None
    assert client.request["mode"] == "read-only"
    assert client.request["workspace_root"] == tmp_path.resolve()
    assert client.request["argv"] == [
        "/bin/bash",
        "--noprofile",
        "--norc",
        "-c",
        "printf ready",
    ]
    assert result.mode == "read-only"
    assert result.argv[0] == "confined"


def test_default_sandbox_runners_share_one_persistent_worker_client() -> None:
    first = SandboxRunner(enabled=True)
    second = SandboxRunner(enabled=True)

    assert first.client is second.client


def test_worker_error_is_not_treated_as_unconfined_execution(tmp_path: Path) -> None:
    script = r"""
import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    print(json.dumps({
        "version": 1,
        "id": request["id"],
        "ok": False,
        "error": {"code": "SANDBOX_UNAVAILABLE", "message": "no provider"},
    }), flush=True)
"""
    client = _client(script)
    try:
        with pytest.raises(SandboxUnavailableError, match="no provider"):
            client.confine(
                argv=["true"],
                mode="workspace-write",
                workspace_root=tmp_path,
                protected_endpoints=[],
            )
    finally:
        client.close()


def test_protocol_request_contains_only_versioned_structured_fields(
    tmp_path: Path,
) -> None:
    capture = tmp_path / "request.json"
    script = f"""
import json
import sys

request = json.loads(sys.stdin.readline())
open({json.dumps(str(capture))}, "w", encoding="utf-8").write(json.dumps(request))
print(json.dumps({{
    "version": 1,
    "id": request["id"],
    "ok": True,
    "result": {{
        "argv": request["argv"],
        "adapter": "fake",
        "enforcement": "full",
        "denial_signatures": [],
        "runner_failure_rules": [],
    }},
}}), flush=True)
"""
    client = _client(script)
    try:
        client.confine(
            argv=["true"],
            mode="read-only",
            workspace_root=tmp_path,
            protected_endpoints=[tmp_path / "docker.sock"],
        )
    finally:
        client.close()

    request = json.loads(capture.read_text(encoding="utf-8"))
    assert set(request) == {
        "version",
        "id",
        "method",
        "argv",
        "mode",
        "workspace_root",
        "protected_endpoints",
    }
    assert request["version"] == 1
    assert request["method"] == "confine"
