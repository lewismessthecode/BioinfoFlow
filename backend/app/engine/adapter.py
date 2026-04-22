from __future__ import annotations

from abc import ABC, abstractmethod

from app.engine.backend import EngineEvent


class EngineAdapter(ABC):
    @property
    @abstractmethod
    def engine_name(self) -> str: ...

    @property
    def display_name(self) -> str:
        return self.engine_name

    @property
    @abstractmethod
    def binary(self) -> str: ...

    @property
    @abstractmethod
    def supports_native_resume(self) -> bool: ...

    @property
    def supports_best_effort_resume(self) -> bool:
        return False

    @abstractmethod
    async def build_command(self, config: dict, workspace: str) -> list[str]: ...

    @abstractmethod
    def parse_event(self, line: str, stream: str) -> EngineEvent | None: ...

    @abstractmethod
    async def cancel(self, *, pid: int | None, **kwargs) -> bool: ...

    def get_resume_token(self, run_config: dict) -> str | None:
        return None

    async def pre_submit(self, config: dict, workspace: str) -> dict:
        return config

    async def post_complete(self, config: dict, workspace: str, status: str) -> None:
        return None

    async def extract_schema(self, source: str | None, **kwargs) -> dict | None:
        """Best-effort engine-native schema extraction."""
        return None
