from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator


class EngineEventType(str, Enum):
    STARTED = "started"
    PROCESS_INFO = "process"
    TASK_UPDATE = "task"
    LOG = "log"
    ERROR = "error"
    COMPLETED = "completed"


@dataclass(frozen=True)
class EngineEvent:
    type: EngineEventType
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def message(self) -> str | None:
        message = self.data.get("message")
        return str(message) if message is not None else None

    @property
    def task_name(self) -> str | None:
        name = self.data.get("name")
        return str(name) if name is not None else None

    @property
    def task_status(self) -> str | None:
        status = self.data.get("status")
        return str(status) if status is not None else None

    @property
    def pid(self) -> int | None:
        pid = self.data.get("pid")
        return int(pid) if isinstance(pid, int) else None

    @property
    def exit_code(self) -> int | None:
        exit_code = self.data.get("exit_code")
        return int(exit_code) if isinstance(exit_code, int) else None


class ExecutionBackend(ABC):
    @abstractmethod
    async def submit(
        self,
        adapter,
        config: dict,
        workspace: str,
    ) -> AsyncIterator[EngineEvent]: ...

    @abstractmethod
    async def cancel(
        self,
        adapter,
        *,
        pid: int | None,
        **kwargs,
    ) -> bool: ...
