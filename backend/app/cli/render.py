"""Renderer — Rich tables/panels for human mode, raw JSON for machine mode."""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from typing import Any, Iterator

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.cli.jsonio import try_parse_json
from app.cli.types import ApiResponse, SSEEvent


class Renderer:
    """Output formatter supporting human (Rich) and JSON modes."""

    def __init__(self, console: Console, mode: str, quiet: bool = False) -> None:
        self._console = console
        self._json = mode == "json"
        self._quiet = quiet

    @property
    def is_json(self) -> bool:
        return self._json

    @property
    def is_quiet(self) -> bool:
        return self._quiet

    def table(
        self,
        columns: list[dict[str, Any]],
        rows: list[dict[str, Any]],
        raw: ApiResponse,
    ) -> None:
        """Render a list of records as a table or JSON array."""
        if self._json:
            self.emit_json(raw)
            return

        if not rows:
            self._console.print("[dim]No results.[/dim]")
            return

        t = Table(show_header=True, header_style="bold cyan")
        for col in columns:
            t.add_column(col.get("header", col["key"]), **col.get("opts", {}))

        for row in rows:
            cells = [str(row.get(c["key"], "")) for c in columns]
            t.add_row(*cells)

        self._console.print(t)

        if raw.meta and raw.meta.get("pagination"):
            pg = raw.meta["pagination"]
            if pg.get("total_count") is not None:
                self._console.print(
                    f"[dim]Showing {len(rows)} of {pg['total_count']}[/dim]"
                )
            if pg.get("has_more"):
                cursor = pg.get("next_cursor", "")
                self._console.print(
                    f"[dim]More available — re-run with --cursor {cursor}[/dim]"
                )

    def detail(
        self,
        fields: dict[str, Any],
        title: str,
        raw: ApiResponse,
    ) -> None:
        """Render a single record as a panel or JSON object."""
        if self._json:
            self.emit_json(raw)
            return

        lines = [f"[bold]{k}:[/bold] {v}" for k, v in fields.items()]
        self._console.print(Panel("\n".join(lines), title=title, expand=False))

    def success(self, message: str, raw: ApiResponse | None = None) -> None:
        if self._json and raw is not None:
            self.emit_json(raw)
            return
        if self._quiet:
            return
        self._console.print(f"[green]{message}[/green]")

    def error(
        self,
        message: str,
        code: str | None = None,
        raw: ApiResponse | None = None,
    ) -> None:
        if self._json and raw is not None:
            self.emit_json(raw)
            return
        label = f"[{code}] " if code else ""
        self._console.print(f"[red]{label}{message}[/red]", highlight=False)

    @contextmanager
    def spinner(self, message: str) -> Iterator[None]:
        if self._json:
            yield
            return
        with self._console.status(message, spinner="dots"):
            yield

    def stream_event(self, event: SSEEvent) -> None:
        """Emit a single SSE event — NDJSON in json mode, styled in human mode."""
        if self._json:
            line = {"event": event.event, "data": try_parse_json(event.data)}
            if event.id:
                line["id"] = event.id
            sys.stdout.write(json.dumps(line, default=str) + "\n")
            sys.stdout.flush()
            return

        data = try_parse_json(event.data)
        preview = json.dumps(data, default=str) if isinstance(data, dict) else str(data)
        if len(preview) > 200:
            preview = preview[:200] + "..."
        self._console.print(f"[cyan]{event.event}[/cyan]  {preview}")

    def emit_json(self, raw: ApiResponse) -> None:
        envelope: dict[str, Any] = {"success": raw.success, "data": raw.data}
        if raw.error:
            envelope["error"] = raw.error
        if raw.meta:
            envelope["meta"] = raw.meta
        sys.stdout.write(json.dumps(envelope, default=str) + "\n")
        sys.stdout.flush()

    def emit_data(self, data: Any) -> None:
        """Emit a synthetic `{success, data}` envelope for client-side data.

        Use when there is no upstream ApiResponse — e.g. config values, doctor
        check summaries — but we still want JSON-mode consumers to receive a
        consistent envelope.
        """
        sys.stdout.write(
            json.dumps({"success": True, "data": data}, default=str) + "\n"
        )
        sys.stdout.flush()
