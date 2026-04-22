"""CLI context — threaded through all commands via typer.Context.obj."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import Literal, TypeVar

from rich.console import Console

from app.cli.client import ApiClient

T = TypeVar("T")


@dataclass
class CliContext:
    """Resolved CLI state available to every command."""

    client: ApiClient
    output_mode: Literal["human", "json"]
    project_id: str | None
    verbose: bool
    console: Console
    _runner: asyncio.Runner | None = field(default=None, init=False, repr=False)

    def run(self, awaitable: Awaitable[T]) -> T:
        """Run async CLI work on a single shared event loop."""
        if self._runner is None:
            self._runner = asyncio.Runner()
        return self._runner.run(awaitable)

    def close(self) -> None:
        """Close the API client on the same loop used for command execution."""
        if self._runner is None:
            return
        try:
            self._runner.run(self.client.close())
        finally:
            self._runner.close()
            self._runner = None
