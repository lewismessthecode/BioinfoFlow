from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

from app.engine.adapters.wdl import WDLAdapter
from app.engine.local import LocalBackend


@dataclass
class MiniWDLConfig:
    workflow_path: str
    inputs: dict
    run_id: str
    options: dict | None = None
    outdir: str | None = None


class MiniWDLService:
    """Compatibility wrapper around the engine adapter implementation."""

    def __init__(
        self, *, miniwdl_bin: str | None = None, adapter: WDLAdapter | None = None
    ) -> None:
        self.adapter = adapter or WDLAdapter(miniwdl_bin=miniwdl_bin)

    @property
    def bin(self) -> str:
        return self.adapter.binary

    @bin.setter
    def bin(self, value: str) -> None:
        self.adapter._binary = value

    async def run(self, config: MiniWDLConfig, workspace: str) -> AsyncIterator[dict]:
        backend = LocalBackend()
        payload = {
            "workflow_path": config.workflow_path,
            "run_id": config.run_id,
            "options": dict(config.options or {}),
            "outdir": config.outdir,
            "params": {"outdir": config.outdir} if config.outdir else {},
            "inputs": dict(config.inputs or {}),
            "request": {
                "params": {"outdir": config.outdir} if config.outdir else {},
                "inputs": dict(config.inputs or {}),
                "config_overrides": {},
            },
            "runtime": {},
        }
        async for event in backend.submit(self.adapter, payload, workspace):
            yield {"event": event.type.value, **event.data}

    async def cancel(self, *, pid: int | None = None) -> bool:
        return await self.adapter.cancel(pid=pid)

    async def _build_command(
        self, config: MiniWDLConfig, workspace: str, work_dir=None
    ) -> list[str]:
        del work_dir
        payload = {
            "workflow_path": config.workflow_path,
            "run_id": config.run_id,
            "options": dict(config.options or {}),
            "outdir": config.outdir,
            "params": {"outdir": config.outdir} if config.outdir else {},
            "inputs": dict(config.inputs or {}),
            "request": {
                "params": {"outdir": config.outdir} if config.outdir else {},
                "inputs": dict(config.inputs or {}),
                "config_overrides": {},
            },
        }
        return await self.adapter.build_command(payload, workspace)

    def _parse_output_line(self, line: str) -> dict | None:
        event = self.adapter.parse_event(line, "stdout")
        if event is None:
            return None
        return {"event": event.type.value, **event.data}
