from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from app.engine.adapters.wdl import WDLAdapter
from app.engine.backend import EngineEventType
from app.models.run_config import RunConfigHelper

MINIWDL_ENTRY_PREFIX = [sys.executable, "-m", "app.engine._miniwdl_entry"]


def _wdl_config(**overrides) -> dict:
    config = RunConfigHelper.build_v1(
        params={"outdir": "results"},
        inputs={"sample": "S1"},
        config_overrides={},
        resolved_runspec={},
    )
    config.update(
        {
            "workflow_path": "workflow.wdl",
            "run_id": "run_wdl_123",
            "options": {"verbose": True},
        }
    )
    config.update(overrides)
    return config


def test_wdl_adapter_parse_event_maps_known_lines():
    adapter = WDLAdapter()

    completed = adapter.parse_event("workflow done", "stdout")
    assert completed is not None
    assert completed.type == EngineEventType.COMPLETED

    error = adapter.parse_event("error: bad input", "stdout")
    assert error is not None
    assert error.type == EngineEventType.ERROR

    log = adapter.parse_event("call foo started", "stdout")
    assert log is not None
    assert log.type == EngineEventType.LOG
    assert log.message == "call foo started"


# ---------------------------------------------------------------------------
# parse_event must translate miniwdl's task-scoped NOTICE/ERROR lines into
# TASK_UPDATE events so the frontend DAG can render per-task state. These
# tests use arbitrary workflow names to prove the parser is not pinned to
# Deaf_20; miniwdl emits this logger shape for every WDL it runs.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected_task", "expected_status"),
    [
        (
            '2026-04-17 09:16:19.405 wdl.w:MyWorkflow.t:call-PREPARATION NOTICE task setup :: name: "PREPARATION"',
            "PREPARATION",
            "submitted",
        ),
        (
            '2026-04-17 09:16:21.475 wdl.w:AnyPipeline.t:call-ALIGN NOTICE docker task running :: service: "abc"',
            "ALIGN",
            "running",
        ),
        (
            "2026-04-17 09:16:26.816 wdl.w:Demo.t:call-PREPARATION NOTICE done",
            "PREPARATION",
            "completed",
        ),
        (
            '2026-04-17 09:20:24.900 wdl.w:Demo.t:call-RESULT ERROR task RESULT (...) failed :: error: "OutputError"',
            "RESULT",
            "failed",
        ),
    ],
)
def test_wdl_adapter_parse_event_emits_task_updates_for_miniwdl_log_shape(
    line, expected_task, expected_status
):
    adapter = WDLAdapter()
    event = adapter.parse_event(line, "stderr")
    assert event is not None
    assert event.type == EngineEventType.TASK_UPDATE
    assert event.task_name == expected_task
    assert event.task_status == expected_status


def test_wdl_adapter_parse_event_preserves_scatter_index_in_task_name():
    # Under scatter, miniwdl suffixes each shard with -N. The frontend's
    # DagMatcher strips the suffix when matching DAG nodes, so we keep
    # the raw name in TASK_UPDATE to avoid cross-shard masking.
    adapter = WDLAdapter()
    line = (
        "2026-04-17 09:16:26.818 wdl.w:Demo.t:call-SPLIT-0 "
        'NOTICE docker task running :: service: "xyz"'
    )
    event = adapter.parse_event(line, "stderr")
    assert event is not None
    assert event.type == EngineEventType.TASK_UPDATE
    assert event.task_name == "SPLIT-0"


def test_wdl_adapter_parse_event_ignores_workflow_level_notices():
    # Workflow-scoped NOTICE lines (no `.t:call-...` segment) must NOT
    # produce a TASK_UPDATE — they'd misrepresent workflow-level events
    # as task events. They fall through to LOG handling.
    adapter = WDLAdapter()
    line = '2026-04-17 09:16:19.399 wdl.w:Demo NOTICE workflow start :: name: "Demo"'
    event = adapter.parse_event(line, "stderr")
    assert event is not None
    assert event.type == EngineEventType.LOG


def test_wdl_adapter_parse_event_ignores_noise_task_lines():
    # Lines like "mount added", "docker image :: tag: ..." all match the
    # task-scoped logger but are not lifecycle transitions we care about.
    # They must not produce spurious TASK_UPDATE events (would flip node
    # status back and forth).
    adapter = WDLAdapter()
    line = (
        "2026-04-17 09:16:19.447 wdl.w:Demo.t:call-PREPARATION "
        "NOTICE bioinfoflow mount added :: /srv/... -> /srv/... (ro=True)"
    )
    event = adapter.parse_event(line, "stderr")
    assert event is not None
    # Falls through to LOG (stderr-sourced), not TASK_UPDATE.
    assert event.type == EngineEventType.LOG


def test_wdl_adapter_parse_event_prefers_done_over_docker_exit_for_completion():
    # `docker task exit :: state: "complete"` fires even when miniwdl's
    # post-task output validation subsequently fails (this is how the
    # RESULT/OutputError bug first surfaced). We must NOT treat that line
    # as task completion — only `NOTICE done` means the task fully passed.
    adapter = WDLAdapter()
    docker_exit = (
        "2026-04-17 09:20:24.894 wdl.w:Demo.t:call-RESULT "
        'NOTICE docker task exit :: state: "complete", exit_code: 0'
    )
    event = adapter.parse_event(docker_exit, "stderr")
    # Must not emit TASK_UPDATE(completed) here — otherwise tasks_completed
    # double-counts and the failed RESULT task shows completed momentarily.
    assert event is not None
    assert event.type == EngineEventType.LOG


@pytest.mark.asyncio
async def test_wdl_adapter_build_command_writes_inputs_and_options(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    adapter = WDLAdapter()

    command = await adapter.build_command(_wdl_config(), str(workspace))

    # Must invoke miniwdl via our import-time registering module entry so the
    # bioinfoflow_docker_swarm backend is guaranteed to be loaded regardless of
    # whether the deployed Python environment's dist-info carries the
    # `miniwdl.plugin.container_backend` entry point. Invoking the raw
    # `miniwdl` binary silently falls back to the stock SwarmContainer in
    # deployments where entry-point discovery fails.
    assert command[: len(MINIWDL_ENTRY_PREFIX) + 2] == [
        *MINIWDL_ENTRY_PREFIX,
        "run",
        "workflow.wdl",
    ]
    assert "--dir" in command
    assert "-i" in command
    assert "--verbose" in command
    assert command[command.index("--verbose") + 1] == "True"

    inputs_path = Path(command[command.index("-i") + 1])
    assert inputs_path.exists()
    assert json.loads(inputs_path.read_text(encoding="utf-8")) == {"sample": "S1"}

    assert "--cfg" in command
    cfg_path = Path(command[command.index("--cfg") + 1])
    assert cfg_path.exists()
    cfg_text = cfg_path.read_text(encoding="utf-8")
    assert "[scheduler]" in cfg_text
    assert "container_backend = bioinfoflow_docker_swarm" in cfg_text
    assert "[file_io]" in cfg_text
    assert "allow_any_input = true" in cfg_text
    # task_runtime.as_user forces `--user {uid}:{gid}` on the task container
    # so images with a non-root USER directive can still write to the
    # backend-owned results dir. Without this, the deaf:V2.0.9.9 image runs
    # tasks as uid 1000 and every write to results/ fails with EACCES.
    assert "[task_runtime]" in cfg_text
    assert "as_user = true" in cfg_text


@pytest.mark.asyncio
async def test_wdl_adapter_build_command_reuses_resume_work_dir(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    adapter = WDLAdapter()

    command = await adapter.build_command(
        _wdl_config(
            resume=True,
            resume_type="best_effort",
            resume_work_dir="runs/shared-run/engine/wdl/work",
        ),
        str(workspace),
    )

    work_dir = Path(command[command.index("--dir") + 1])
    assert work_dir == workspace / "runs" / "shared-run" / "engine" / "wdl" / "work"


@pytest.mark.asyncio
async def test_wdl_adapter_build_command_absolutizes_qualified_output_dirs(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    adapter = WDLAdapter()

    command = await adapter.build_command(
        _wdl_config(
            request={
                "inputs": {
                    "sample": "S1",
                    "resource_stress_mini.outdir": "runs/run_wdl_123/results",
                }
            },
        ),
        str(workspace),
    )

    inputs_path = Path(command[command.index("-i") + 1])
    payload = json.loads(inputs_path.read_text(encoding="utf-8"))
    assert payload["resource_stress_mini.outdir"] == str(
        (workspace / "runs" / "run_wdl_123" / "results").resolve()
    )


@pytest.mark.asyncio
async def test_wdl_adapter_post_complete_copies_outputs_to_outdir(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output_file = (
        workspace
        / "runs"
        / "run_wdl_123"
        / "engine"
        / "wdl"
        / "work"
        / "out"
        / "report.txt"
    )
    output_file.parent.mkdir(parents=True)
    output_file.write_text("ok", encoding="utf-8")

    adapter = WDLAdapter()
    await adapter.post_complete(_wdl_config(), str(workspace), "completed")

    copied = workspace / "results" / "report.txt"
    assert copied.exists()
    assert copied.read_text(encoding="utf-8") == "ok"


@pytest.mark.asyncio
async def test_wdl_adapter_post_complete_uses_resume_work_dir_when_present(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output_file = (
        workspace
        / "runs"
        / "shared-run"
        / "engine"
        / "wdl"
        / "work"
        / "out"
        / "report.txt"
    )
    output_file.parent.mkdir(parents=True)
    output_file.write_text("ok", encoding="utf-8")

    adapter = WDLAdapter()
    await adapter.post_complete(
        _wdl_config(
            resume=True,
            resume_type="best_effort",
            resume_work_dir="runs/shared-run/engine/wdl/work",
        ),
        str(workspace),
        "completed",
    )

    copied = workspace / "results" / "report.txt"
    assert copied.exists()
    assert copied.read_text(encoding="utf-8") == "ok"


@pytest.mark.asyncio
async def test_wdl_adapter_post_complete_copies_outputs_when_outdir_missing(tmp_path):
    # When the WDL inputs don't carry an `outdir` value miniwdl leaves
    # outputs only under its work dir. Without this fallback the run's
    # `results/` (where the file browser reads) stays empty and the
    # frontend tree shows "no outputs" after reload.
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output_file = (
        workspace
        / "runs"
        / "run_wdl_123"
        / "engine"
        / "wdl"
        / "work"
        / "out"
        / "Result"
        / "sample_info.tsv"
    )
    output_file.parent.mkdir(parents=True)
    output_file.write_text("sample\tA\n", encoding="utf-8")

    config = _wdl_config()
    # Drop the default outdir so we exercise the no-outdir fallback path.
    config["params"] = {}
    config["request"]["params"] = {}

    adapter = WDLAdapter()
    await adapter.post_complete(config, str(workspace), "completed")

    copied = workspace / "results" / "Result" / "sample_info.tsv"
    assert copied.exists()
    assert copied.read_text(encoding="utf-8") == "sample\tA\n"


@pytest.mark.asyncio
async def test_wdl_adapter_post_complete_falls_back_to_outputs_json(tmp_path):
    # If miniwdl's `out/` staging dir is missing (e.g. resume from a stale
    # work dir) we still have outputs.json with absolute paths into the
    # work dir. Make sure those are copied into results/ as well.
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    work_dir = workspace / "runs" / "run_wdl_123" / "engine" / "wdl" / "work"
    real_output = work_dir / "call-RESULT" / "outputs" / "report.txt"
    real_output.parent.mkdir(parents=True)
    real_output.write_text("done", encoding="utf-8")

    outputs_json = work_dir / "outputs.json"
    outputs_json.write_text(
        json.dumps({"outputs": {"demo.report": str(real_output)}}),
        encoding="utf-8",
    )

    config = _wdl_config()
    config["params"] = {}
    config["request"]["params"] = {}

    adapter = WDLAdapter()
    await adapter.post_complete(config, str(workspace), "completed")

    copied = workspace / "results" / "report.txt"
    assert copied.exists()
    assert copied.read_text(encoding="utf-8") == "done"


@pytest.mark.asyncio
async def test_wdl_adapter_build_command_passes_paths_unchanged_under_identity_mount(
    tmp_path,
):
    # Under Path Contract v3 the backend, miniwdl runner, and task containers
    # all see identical absolute paths — inputs.json should carry the platform's
    # canonical paths verbatim, with no host/container translation.
    workspace = tmp_path / "projects" / "project-1"
    workflow_path = tmp_path / "state" / "workflows" / "demo.wdl"
    manifest_path = workspace / "runs" / "run_wdl_123" / "submission" / "sequence.list"

    workspace.mkdir(parents=True)
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text("version 1.0\nworkflow demo {}\n", encoding="utf-8")
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("sample\n", encoding="utf-8")

    outdir = workspace / "runs" / "run_wdl_123" / "results"

    config = _wdl_config(workflow_path=str(workflow_path))
    config["inputs"] = {
        "sequence_list": str(manifest_path),
        "outdir": str(outdir),
    }
    config["request"]["inputs"] = dict(config["inputs"])

    adapter = WDLAdapter()
    command = await adapter.build_command(config, str(workspace))

    # `command[0:3]` is the python -m entry; the workflow path is the first
    # positional arg to `miniwdl run`.
    assert command[: len(MINIWDL_ENTRY_PREFIX) + 1] == [
        *MINIWDL_ENTRY_PREFIX,
        "run",
    ]
    assert Path(command[len(MINIWDL_ENTRY_PREFIX) + 1]) == workflow_path

    work_dir = Path(command[command.index("--dir") + 1])
    assert work_dir == workspace / "runs" / "run_wdl_123" / "engine" / "wdl" / "work"
    assert work_dir.exists()

    inputs_path = Path(command[command.index("-i") + 1])
    payload = json.loads(inputs_path.read_text(encoding="utf-8"))
    assert payload["sequence_list"] == str(manifest_path)
    assert payload["outdir"] == str(outdir)


@pytest.mark.asyncio
async def test_wdl_adapter_extract_schema_from_content():
    adapter = WDLAdapter()
    schema = await adapter.extract_schema(
        None,
        content="""
        version 1.0

        task fastqc {
          input {
            String sample
          }
          command <<<
            echo "~{sample}" > report.txt
          >>>
          output {
            File report = "report.txt"
          }
          runtime {
            docker: "ubuntu:22.04"
          }
        }

        workflow demo {
          input {
            String sample
          }
          call fastqc
        }
        """,
        file_name="demo.wdl",
    )

    assert schema is not None
    assert schema["workflow_name"] == "demo"
    assert schema["tasks"] == [
        {
            "name": "fastqc",
            "inputs": ["sample"],
            "outputs": ["report"],
            "container": "ubuntu:22.04",
        }
    ]
    assert schema["inputs"][0]["name"] == "sample"


@pytest.mark.asyncio
async def test_wdl_adapter_extract_schema_prefers_real_source_for_relative_imports():
    repo_root = Path(__file__).resolve().parents[3]
    entrypoint = repo_root / "demo" / "subworkflow-import-mini" / "main.wdl"

    adapter = WDLAdapter()
    schema = await adapter.extract_schema(
        str(entrypoint),
        content=entrypoint.read_text(encoding="utf-8"),
        file_name=entrypoint.name,
    )

    assert schema is not None
    assert {task["name"] for task in schema["tasks"]} >= {
        "FASTQC",
        "TRIM",
        "POST_QC",
        "INDEX_REF",
        "BWA_MEM",
        "SORT_BAM",
        "REPORT",
    }


@pytest.mark.asyncio
async def test_wdl_adapter_pre_submit_pulls_missing_required_images():
    class FakeDockerService:
        def __init__(self):
            self.inspect_calls: list[str] = []
            self.pull_calls: list[tuple[str, str, str]] = []

        async def is_available(self) -> bool:
            return True

        async def inspect_image(self, full_name: str):
            self.inspect_calls.append(full_name)
            return None

        async def pull_image(self, name: str, tag: str, registry: str):
            self.pull_calls.append((name, tag, registry))
            yield {"status": "done"}

    adapter = WDLAdapter()
    docker_service = FakeDockerService()

    config = _wdl_config()
    config["runtime"] = {
        "required_images": ["ubuntu:22.04"],
    }

    with patch(
        "app.engine.adapters.wdl.DockerService",
        return_value=docker_service,
    ):
        updated = await adapter.pre_submit(config, "/workspace")

    assert updated["runtime"]["required_images"] == ["ubuntu:22.04"]
    assert docker_service.inspect_calls == ["ubuntu:22.04"]
    assert docker_service.pull_calls == [("ubuntu", "22.04", "docker.io")]
