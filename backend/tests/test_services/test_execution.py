from __future__ import annotations

import pytest

from app.engine.backend import EngineEvent, EngineEventType
from app.services.miniwdl_service import MiniWDLConfig
from app.services.miniwdl_service import MiniWDLService
from app.services.nextflow_service import NextflowConfig
from app.services.nextflow_service import NextflowService


def test_nextflow_parse_output():
    service = NextflowService()

    started = service._parse_output_line(
        "Launching `demo/main.nf` [mighty_curie] - revision: xyz"
    )
    assert started["event"] == "started"
    assert started["run_name"] == "mighty_curie"

    task = service._parse_output_line("[12/abcd] process > FASTP (sample) [100%]")
    assert task["event"] == "task"
    assert task["name"] == "FASTP"
    assert task["status"] == "completed"

    error = service._parse_output_line("ERROR ~ something broke")
    assert error["event"] == "error"


def test_miniwdl_parse_output():
    service = MiniWDLService()

    completed = service._parse_output_line("workflow done")
    assert completed["event"] == "completed"

    error = service._parse_output_line("error: bad input")
    assert error["event"] == "error"


@pytest.mark.asyncio
async def test_miniwdl_run_surfaces_subprocess_failure(tmp_path):
    # miniwdl now runs as `python -m app.engine._miniwdl_entry` to pre-register
    # our container backend, so a missing `miniwdl` binary is no longer a
    # failure mode. We still need a terminal error event when the miniwdl
    # subprocess itself fails (e.g. the workflow file does not exist).
    service = MiniWDLService()
    config = MiniWDLConfig(
        workflow_path="workflow.wdl",
        inputs={},
        run_id="run_abc",
    )
    events = [event async for event in service.run(config, str(tmp_path))]
    assert events[-1]["event"] == "error"
    assert events[-1].get("message")


@pytest.mark.asyncio
async def test_nextflow_build_command_forwards_resume_and_trace_payload(tmp_path):
    captured: dict[str, object] = {}

    class StubAdapter:
        binary = "nextflow"

        async def build_command(self, config: dict, workspace: str) -> list[str]:
            captured["config"] = config
            captured["workspace"] = workspace
            return ["nextflow", "run", config["pipeline"]]

        def parse_event(self, line: str, stream: str):  # pragma: no cover - unused
            del line, stream
            return None

        async def cancel(self, **kwargs):  # pragma: no cover - unused
            del kwargs
            return True

    service = NextflowService(adapter=StubAdapter())  # type: ignore[arg-type]
    config = NextflowConfig(
        pipeline="demo/main.nf",
        params={"reads": "samples.csv"},
        run_id="run-123",
        profile="docker",
        work_dir=str(tmp_path / "work"),
        resume=True,
        resume_from="session-xyz",
        config_overrides={"docker.enabled": True},
        dag_path=str(tmp_path / "dag.dot"),
        trace_path=str(tmp_path / "trace.txt"),
    )

    command = await service._build_command(config, str(tmp_path))

    assert command == ["nextflow", "run", "demo/main.nf"]
    assert captured["workspace"] == str(tmp_path)
    assert captured["config"] == {
        "pipeline": "demo/main.nf",
        "run_id": "run-123",
        "profile": "docker",
        "work_dir": str(tmp_path / "work"),
        "resume": True,
        "resume_from": "session-xyz",
        "config_overrides": {"docker.enabled": True},
        "params": {"reads": "samples.csv"},
        "request": {
            "params": {"reads": "samples.csv"},
            "inputs": {},
            "config_overrides": {"docker.enabled": True},
        },
    }


@pytest.mark.asyncio
async def test_nextflow_run_delegates_to_local_backend_and_normalizes_events(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    async def fake_submit(self, adapter, config: dict, workspace: str):
        del self
        captured["adapter"] = adapter
        captured["config"] = config
        captured["workspace"] = workspace
        yield EngineEvent(EngineEventType.STARTED, {"run_name": "mighty-curie"})
        yield EngineEvent(EngineEventType.LOG, {"message": "launching"})

    monkeypatch.setattr("app.engine.local.LocalBackend.submit", fake_submit)

    service = NextflowService()
    config = NextflowConfig(
        pipeline="demo/main.nf",
        params={"genome": "GRCh38"},
        run_id="run-abc",
        dag_path=str(tmp_path / "dag.dot"),
        trace_path=str(tmp_path / "trace.txt"),
    )

    events = [event async for event in service.run(config, str(tmp_path))]

    assert captured["adapter"] is service.adapter
    assert captured["workspace"] == str(tmp_path)
    assert captured["config"] == {
        "pipeline": "demo/main.nf",
        "run_id": "run-abc",
        "profile": None,
        "work_dir": None,
        "resume": False,
        "resume_from": None,
        "config_overrides": {},
        "params": {"genome": "GRCh38"},
        "request": {
            "params": {"genome": "GRCh38"},
            "inputs": {},
            "config_overrides": {},
        },
        "runtime": {},
        "dag_path": str(tmp_path / "dag.dot"),
        "trace_path": str(tmp_path / "trace.txt"),
    }
    assert events == [
        {"event": "started", "run_name": "mighty-curie"},
        {"event": "log", "message": "launching"},
    ]


@pytest.mark.asyncio
async def test_miniwdl_build_command_preserves_outdir_and_inputs(tmp_path):
    captured: dict[str, object] = {}

    class StubAdapter:
        binary = "miniwdl"

        async def build_command(self, config: dict, workspace: str) -> list[str]:
            captured["config"] = config
            captured["workspace"] = workspace
            return ["python", "-m", "miniwdl"]

        def parse_event(self, line: str, stream: str):  # pragma: no cover - unused
            del line, stream
            return None

        async def cancel(self, **kwargs):  # pragma: no cover - unused
            del kwargs
            return True

    service = MiniWDLService(adapter=StubAdapter())  # type: ignore[arg-type]
    config = MiniWDLConfig(
        workflow_path="workflow.wdl",
        inputs={"sample_id": "NA12878", "output_dir": "results"},
        run_id="run-wdl",
        options={"verbose": True},
        outdir="results",
    )

    command = await service._build_command(config, str(tmp_path))

    assert command == ["python", "-m", "miniwdl"]
    assert captured["workspace"] == str(tmp_path)
    assert captured["config"] == {
        "workflow_path": "workflow.wdl",
        "run_id": "run-wdl",
        "options": {"verbose": True},
        "outdir": "results",
        "params": {"outdir": "results"},
        "inputs": {"sample_id": "NA12878", "output_dir": "results"},
        "request": {
            "params": {"outdir": "results"},
            "inputs": {"sample_id": "NA12878", "output_dir": "results"},
            "config_overrides": {},
        },
    }


@pytest.mark.asyncio
async def test_miniwdl_run_delegates_to_local_backend_and_normalizes_events(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    async def fake_submit(self, adapter, config: dict, workspace: str):
        del self
        captured["adapter"] = adapter
        captured["config"] = config
        captured["workspace"] = workspace
        yield EngineEvent(EngineEventType.PROCESS_INFO, {"pid": 42, "engine": "wdl"})
        yield EngineEvent(EngineEventType.COMPLETED, {"success": True})

    monkeypatch.setattr("app.engine.local.LocalBackend.submit", fake_submit)

    service = MiniWDLService()
    config = MiniWDLConfig(
        workflow_path="workflow.wdl",
        inputs={"sample_id": "NA12878"},
        run_id="run-wdl",
        options={"verbose": True},
        outdir="results",
    )

    events = [event async for event in service.run(config, str(tmp_path))]

    assert captured["adapter"] is service.adapter
    assert captured["workspace"] == str(tmp_path)
    assert captured["config"] == {
        "workflow_path": "workflow.wdl",
        "run_id": "run-wdl",
        "options": {"verbose": True},
        "outdir": "results",
        "params": {"outdir": "results"},
        "inputs": {"sample_id": "NA12878"},
        "request": {
            "params": {"outdir": "results"},
            "inputs": {"sample_id": "NA12878"},
            "config_overrides": {},
        },
        "runtime": {},
    }
    assert events == [
        {"event": "process", "pid": 42, "engine": "wdl"},
        {"event": "completed", "success": True},
    ]
