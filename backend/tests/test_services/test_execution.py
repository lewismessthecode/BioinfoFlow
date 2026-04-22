from __future__ import annotations

import pytest

from app.services.miniwdl_service import MiniWDLConfig
from app.services.miniwdl_service import MiniWDLService
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
