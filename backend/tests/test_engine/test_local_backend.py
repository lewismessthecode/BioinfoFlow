from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from app.engine.adapters.nextflow import NextflowAdapter
from app.engine.adapter import EngineAdapter
from app.engine.backend import EngineEvent, EngineEventType
from app.engine.local import LocalBackend


class _FakeStream:
    def __init__(self, lines: list[str]) -> None:
        self._lines = [line.encode("utf-8") for line in lines] + [b""]

    async def readline(self) -> bytes:
        await asyncio.sleep(0)
        return self._lines.pop(0)


@dataclass
class _FakeProcess:
    stdout: _FakeStream
    stderr: _FakeStream
    returncode: int
    pid: int = 4242

    async def wait(self) -> int:
        await asyncio.sleep(0)
        return self.returncode


class _FakeAdapter(EngineAdapter):
    def __init__(
        self,
        *,
        exit_event: EngineEvent | None = None,
        pre_submit_gate: asyncio.Event | None = None,
    ) -> None:
        self._exit_event = exit_event
        self._pre_submit_gate = pre_submit_gate
        self.pre_submit_calls: list[dict] = []
        self.post_complete_calls: list[tuple[dict, str, str]] = []

    @property
    def engine_name(self) -> str:
        return "fake"

    @property
    def display_name(self) -> str:
        return "Fake"

    @property
    def binary(self) -> str:
        return "/tmp/fake-bin"

    @property
    def supports_native_resume(self) -> bool:
        return False

    async def build_command(self, config: dict, workspace: str) -> list[str]:
        return [self.binary, "run", workspace]

    def parse_event(self, line: str, stream: str) -> EngineEvent | None:
        if stream == "stderr":
            return EngineEvent(
                EngineEventType.LOG,
                {"message": line, "level": "error"},
            )
        if line == "task running":
            return EngineEvent(
                EngineEventType.TASK_UPDATE,
                {"name": "align", "status": "running"},
            )
        if line == "done":
            return self._exit_event or EngineEvent(
                EngineEventType.COMPLETED, {"success": True}
            )
        if line:
            return EngineEvent(EngineEventType.LOG, {"message": line})
        return None

    async def cancel(self, *, pid: int | None, **kwargs) -> bool:
        return True

    async def pre_submit(self, config: dict, workspace: str) -> dict:
        self.pre_submit_calls.append(config)
        if self._pre_submit_gate is not None:
            await self._pre_submit_gate.wait()
        return config

    async def post_complete(self, config: dict, workspace: str, status: str) -> None:
        self.post_complete_calls.append((config, workspace, status))


@pytest.mark.asyncio
async def test_local_backend_submit_yields_process_and_adapter_events(
    monkeypatch, tmp_path
):
    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return _FakeProcess(
            stdout=_FakeStream(["task running\n", "done\n"]),
            stderr=_FakeStream([]),
            returncode=0,
        )

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    adapter = _FakeAdapter()
    backend = LocalBackend()

    events = [
        event
        async for event in backend.submit(adapter, {"run_id": "run_123"}, str(tmp_path))
    ]

    assert [event.type for event in events] == [
        EngineEventType.PROCESS_INFO,
        EngineEventType.TASK_UPDATE,
        EngineEventType.COMPLETED,
    ]
    assert events[0].pid == 4242
    assert adapter.post_complete_calls == [
        ({"run_id": "run_123"}, str(tmp_path), "completed")
    ]


@pytest.mark.asyncio
async def test_local_backend_emits_image_prepare_log_before_pre_submit(tmp_path):
    gate = asyncio.Event()
    adapter = _FakeAdapter(pre_submit_gate=gate)
    backend = LocalBackend()
    stream = backend.submit(
        adapter,
        {
            "run_id": "run_images",
            "runtime": {
                "required_images": [
                    "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1"
                ]
            },
        },
        str(tmp_path),
    )

    event = await asyncio.wait_for(anext(stream), timeout=0.1)
    gate.set()
    await stream.aclose()

    assert event.type == EngineEventType.LOG
    assert "Preparing required container images" in event.message
    assert "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1" in event.message


@pytest.mark.asyncio
async def test_local_backend_submit_emits_error_on_nonzero_exit_without_terminal_event(
    monkeypatch, tmp_path
):
    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return _FakeProcess(
            stdout=_FakeStream([]),
            stderr=_FakeStream(["stderr line one\n", "stderr line two\n"]),
            returncode=2,
        )

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    adapter = _FakeAdapter(exit_event=None)
    backend = LocalBackend()

    events = [
        event
        async for event in backend.submit(adapter, {"run_id": "run_456"}, str(tmp_path))
    ]

    assert events[0].type == EngineEventType.PROCESS_INFO
    assert events[1].type == EngineEventType.LOG
    assert events[-1].type == EngineEventType.ERROR
    assert events[-1].exit_code == 2
    assert "stderr line one" in (events[-1].message or "")


@pytest.mark.asyncio
async def test_nextflow_adapter_pre_submit_injects_retry_overrides(
    monkeypatch, tmp_path
):
    async def _docker_available(self) -> bool:
        return True

    monkeypatch.setattr(
        "app.services.docker_service.DockerService.is_available",
        _docker_available,
    )
    adapter = NextflowAdapter(nextflow_bin="/usr/bin/nextflow")
    config = {
        "request": {
            "config_overrides": {},
            "params": {"outdir": "results"},
        },
        "policy": {
            "retry": {
                "max_retries": 3,
            }
        },
    }

    updated = await adapter.pre_submit(config, str(tmp_path))

    overrides = updated["request"]["config_overrides"]
    assert overrides["process.errorStrategy"] == "'retry'"
    assert overrides["process.maxRetries"] == 3
