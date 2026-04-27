from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

from app.engine.adapters.nextflow import NextflowAdapter
from app.engine.local import LocalBackend
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class NextflowConfig:
    pipeline: str
    params: dict
    run_id: str
    profile: str | None = None
    work_dir: str | None = None
    resume: bool = False
    resume_from: str | None = None
    config_overrides: dict | None = None
    dag_path: str | None = None
    trace_path: str | None = None


class NextflowService:
    """Compatibility wrapper around the engine adapter implementation."""

    def __init__(self, *, adapter: NextflowAdapter | None = None) -> None:
        self.adapter = adapter or NextflowAdapter()

    @property
    def bin(self) -> str:
        return self.adapter.binary

    @bin.setter
    def bin(self, value: str) -> None:
        self.adapter._binary = value

    async def run(self, config: NextflowConfig, workspace: str) -> AsyncIterator[dict]:
        backend = LocalBackend()
        payload = {
            "pipeline": config.pipeline,
            "run_id": config.run_id,
            "profile": config.profile,
            "work_dir": config.work_dir,
            "resume": config.resume,
            "resume_from": config.resume_from,
            "config_overrides": dict(config.config_overrides or {}),
            "params": dict(config.params or {}),
            "request": {
                "params": dict(config.params or {}),
                "inputs": {},
                "config_overrides": dict(config.config_overrides or {}),
            },
            "runtime": {},
            "dag_path": config.dag_path,
            "trace_path": config.trace_path,
        }
        async for event in backend.submit(self.adapter, payload, workspace):
            yield {
                "event": event.type.value,
                **event.data,
            }

    async def cancel(self, *, pid: int | None = None, run_name: str | None = None) -> bool:
        return await self.adapter.cancel(pid=pid, run_name=run_name)

    async def _build_command(self, config: NextflowConfig, workspace: str) -> list[str]:
        payload = {
            "pipeline": config.pipeline,
            "run_id": config.run_id,
            "profile": config.profile,
            "work_dir": config.work_dir,
            "resume": config.resume,
            "resume_from": config.resume_from,
            "config_overrides": dict(config.config_overrides or {}),
            "params": dict(config.params or {}),
            "request": {
                "params": dict(config.params or {}),
                "inputs": {},
                "config_overrides": dict(config.config_overrides or {}),
            },
        }
        return await self.adapter.build_command(payload, workspace)

    def _parse_output_line(self, line: str) -> dict | None:
        event = self.adapter.parse_event(line, "stdout")
        if event is None:
            return None
        return {"event": event.type.value, **event.data}
