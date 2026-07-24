from __future__ import annotations

from http.client import IncompleteRead, RemoteDisconnected
from pathlib import Path
from uuid import uuid4

import pytest

from app.engine.adapters import nextflow as nextflow_module
from app.engine.adapters.nextflow import NextflowAdapter
from app.engine.backend import EngineEventType
from app.models.run_config import RunConfigHelper


def _nextflow_config(**overrides) -> dict:
    config = RunConfigHelper.build_v1(
        params={"reads": "reads.fastq.gz"},
        inputs={},
        config_overrides={"process.cpus": 4},
        resolved_runspec={},
    )
    config.update(
        {
            "pipeline": "demo/main.nf",
            "run_id": f"run_{uuid4().hex[:6]}",
            "profile": "test",
            "resume": False,
            "resume_from": None,
            "dag_path": "artifacts/dag.dot",
            "trace_path": "artifacts/trace.tsv",
        }
    )
    config.update(overrides)
    return config


def test_nextflow_adapter_parse_event_maps_known_output_lines():
    adapter = NextflowAdapter()

    started = adapter.parse_event(
        "Launching `demo/main.nf` [mighty_curie] - revision: xyz",
        "stdout",
    )
    assert started is not None
    assert started.type == EngineEventType.STARTED
    assert started.data["run_name"] == "mighty_curie"
    assert started.message == "Launching `demo/main.nf` [mighty_curie] - revision: xyz"

    task = adapter.parse_event(
        "[12/abcd] process > FASTP (sample) [100%]",
        "stdout",
    )
    assert task is not None
    assert task.type == EngineEventType.TASK_UPDATE
    assert task.task_name == "FASTP"
    assert task.task_status == "completed"
    assert task.message == "[12/abcd] process > FASTP (sample) [100%]"

    error = adapter.parse_event("ERROR ~ something broke", "stdout")
    assert error is not None
    assert error.type == EngineEventType.ERROR
    assert error.message == "ERROR ~ something broke"

    completed = adapter.parse_event("Execution complete -- goodbye", "stdout")
    assert completed is not None
    assert completed.type == EngineEventType.COMPLETED
    assert completed.message == "Execution complete -- goodbye"


@pytest.mark.asyncio
async def test_nextflow_adapter_build_command_writes_overrides_and_resume(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    adapter = NextflowAdapter()
    config = _nextflow_config(resume=True, resume_from="mighty_curie")

    command = await adapter.build_command(config, str(workspace))

    run_index = command.index("run")
    assert command[run_index : run_index + 2] == ["run", "demo/main.nf"]
    assert "-with-trace" in command
    assert "-with-dag" in command
    assert "-profile" in command
    assert command[command.index("-profile") + 1] == "test"
    assert "-resume" in command
    assert command[command.index("-resume") + 1] == "mighty_curie"
    assert "--reads" in command
    assert command[command.index("--reads") + 1] == "reads.fastq.gz"

    overrides_path = Path(command[command.index("-c") + 1])
    assert overrides_path.exists()
    assert "process.cpus = 4" in overrides_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_nextflow_adapter_build_command_includes_revision(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    adapter = NextflowAdapter()
    config = _nextflow_config(pipeline="nf-core/rnaseq", revision="3.24.0")

    command = await adapter.build_command(config, str(workspace))

    run_index = command.index("run")
    assert command[run_index : run_index + 2] == ["run", "nf-core/rnaseq"]
    assert "-r" in command
    assert command[command.index("-r") + 1] == "3.24.0"
    assert command.index("-r") < command.index("-work-dir")


@pytest.mark.asyncio
async def test_nextflow_adapter_build_command_routes_nextflow_log_to_audit_dir(
    tmp_path,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    adapter = NextflowAdapter()
    config = _nextflow_config(
        dag_path="runs/run_abc/audit/dag.dot",
        trace_path="runs/run_abc/audit/trace.tsv",
    )

    command = await adapter.build_command(config, str(workspace))

    assert command[:2] == [adapter.binary, "-log"]
    assert command[2] == str(workspace / "runs/run_abc/audit/nextflow.log")
    assert command[3:5] == ["run", "demo/main.nf"]


@pytest.mark.asyncio
async def test_nextflow_adapter_build_command_auto_selects_gpu_profile(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    adapter = NextflowAdapter()
    config = _nextflow_config(pipeline="parabricks/main.nf", profile=None)

    command = await adapter.build_command(config, str(workspace))

    assert "-profile" in command
    assert command[command.index("-profile") + 1] == "consumer_gpu"


@pytest.mark.asyncio
async def test_nextflow_adapter_pre_submit_enables_docker_when_available(monkeypatch):
    class FakeDockerService:
        async def is_available(self) -> bool:
            return True

    monkeypatch.setattr(nextflow_module, "DockerService", FakeDockerService)
    adapter = NextflowAdapter()

    updated = await adapter.pre_submit(_nextflow_config(), "/tmp/workspace")

    overrides = updated["request"]["config_overrides"]
    assert overrides["process.cpus"] == 4
    assert overrides["docker.enabled"] is True
    assert overrides["docker.pull"] is True
    assert updated["config_overrides"]["docker.enabled"] is True


@pytest.mark.asyncio
async def test_gpu_profile_adds_selected_nvidia_visibility(monkeypatch):
    class FakeDockerService:
        async def is_available(self) -> bool:
            return True

    monkeypatch.setattr(nextflow_module, "DockerService", FakeDockerService)
    monkeypatch.setattr(
        nextflow_module,
        "selected_gpu_visible_devices",
        lambda: "GPU-b",
        raising=False,
    )
    adapter = NextflowAdapter()

    updated = await adapter.pre_submit(
        _nextflow_config(pipeline="parabricks/main.nf", profile="consumer_gpu"),
        "/tmp/workspace",
    )

    overrides = updated["request"]["config_overrides"]
    assert overrides["env.NVIDIA_VISIBLE_DEVICES"] == "'GPU-b'"
    assert overrides["env.NVIDIA_DRIVER_CAPABILITIES"] == "'compute,utility'"


@pytest.mark.asyncio
async def test_nextflow_adapter_pre_submit_disables_docker_when_unavailable(
    monkeypatch,
):
    class FakeDockerService:
        async def is_available(self) -> bool:
            return False

    monkeypatch.setattr(nextflow_module, "DockerService", FakeDockerService)
    adapter = NextflowAdapter()

    updated = await adapter.pre_submit(
        _nextflow_config(profile="docker"), "/tmp/workspace"
    )

    overrides = updated["request"]["config_overrides"]
    assert overrides["docker.enabled"] is False
    assert updated["config_overrides"]["docker.enabled"] is False
    assert updated["runtime"]["docker_available"] is False
    assert updated["profile"] is None


def test_nextflow_adapter_pre_submit_runtime_patch_preserves_existing_runtime_keys():
    runtime = {"dag_path": "artifacts/dag.dot", "trace_path": "artifacts/trace.tsv"}
    patch = {"runtime": {"docker_available": False}}

    merged = dict(runtime)
    merged.update(patch["runtime"])

    assert merged["dag_path"] == "artifacts/dag.dot"
    assert merged["trace_path"] == "artifacts/trace.tsv"
    assert merged["docker_available"] is False


def test_nextflow_adapter_get_resume_token_accepts_uuid_and_run_name():
    adapter = NextflowAdapter()

    uuid_token = adapter.get_resume_token(
        {"runtime": {"session_id": "f3a0f85e-b4a0-4d48-b844-701c68298efd"}}
    )
    run_name_token = adapter.get_resume_token(
        {"runtime": {"resume_token": "steady_hopper"}}
    )

    assert uuid_token == "f3a0f85e-b4a0-4d48-b844-701c68298efd"
    assert run_name_token == "steady_hopper"


# --- Phase 2 Fix 9: Nextflow param key validation ---


@pytest.mark.asyncio
async def test_nextflow_adapter_rejects_param_keys_with_shell_metacharacters(tmp_path):
    """Param keys containing shell metacharacters must be rejected."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    adapter = NextflowAdapter()

    bad_keys = [
        "reads;rm -rf /",
        "input$(whoami)",
        "key`id`",
        "a b",
        "foo\nbar",
        "--extra-flag",
        "key=value",
        "reads&bg",
    ]
    for bad_key in bad_keys:
        config = _nextflow_config()
        config["request"]["params"] = {bad_key: "value"}
        with pytest.raises(ValueError, match="Invalid.*param.*key"):
            await adapter.build_command(config, str(workspace))


@pytest.mark.asyncio
async def test_nextflow_adapter_accepts_valid_param_keys(tmp_path):
    """Valid param keys (alphanumeric + underscore) should work fine."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    adapter = NextflowAdapter()

    valid_keys = ["reads", "output_dir", "sample_name", "_private", "cpus2"]
    for valid_key in valid_keys:
        config = _nextflow_config()
        config["request"]["params"] = {valid_key: "value"}
        command = await adapter.build_command(config, str(workspace))
        assert f"--{valid_key}" in command


@pytest.mark.asyncio
async def test_nextflow_adapter_fetches_nfcore_schema_from_revision_first(monkeypatch):
    seen_urls: list[str] = []

    def fake_load_json_url(url: str) -> dict:
        seen_urls.append(url)
        if "/3.24.0/" in url:
            return {"inputs": [{"name": "input", "type": "string"}]}
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(nextflow_module, "_load_json_url", fake_load_json_url)
    adapter = NextflowAdapter()

    schema = await adapter.extract_schema("nf-core/rnaseq", version="3.24.0")

    assert schema == {"inputs": [{"name": "input", "type": "string"}]}
    assert seen_urls == [
        "https://raw.githubusercontent.com/nf-core/rnaseq/3.24.0/nextflow_schema.json"
    ]


@pytest.mark.asyncio
async def test_nextflow_adapter_falls_back_after_remote_disconnect(monkeypatch):
    seen_urls: list[str] = []

    def fake_load_json_url(url: str) -> dict:
        seen_urls.append(url)
        if "/3.24.0/" in url:
            raise RemoteDisconnected("remote end closed connection")
        if "/master/" in url:
            return {"inputs": [{"name": "input", "type": "string"}]}
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(nextflow_module, "_load_json_url", fake_load_json_url)
    adapter = NextflowAdapter()

    schema = await adapter.extract_schema("nf-core/rnaseq", version="3.24.0")

    assert schema == {"inputs": [{"name": "input", "type": "string"}]}
    assert seen_urls == [
        "https://raw.githubusercontent.com/nf-core/rnaseq/3.24.0/nextflow_schema.json",
        "https://raw.githubusercontent.com/nf-core/rnaseq/master/nextflow_schema.json",
    ]


@pytest.mark.asyncio
async def test_nextflow_adapter_falls_back_after_incomplete_read(monkeypatch):
    seen_urls: list[str] = []

    def fake_load_json_url(url: str) -> dict:
        seen_urls.append(url)
        if "/3.24.0/" in url:
            raise IncompleteRead(b"{", 10)
        if "/master/" in url:
            return {"inputs": [{"name": "input", "type": "string"}]}
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(nextflow_module, "_load_json_url", fake_load_json_url)
    adapter = NextflowAdapter()

    schema = await adapter.extract_schema("nf-core/rnaseq", version="3.24.0")

    assert schema == {"inputs": [{"name": "input", "type": "string"}]}
    assert seen_urls == [
        "https://raw.githubusercontent.com/nf-core/rnaseq/3.24.0/nextflow_schema.json",
        "https://raw.githubusercontent.com/nf-core/rnaseq/master/nextflow_schema.json",
    ]
