"""bif doctor — health check across backend, scheduler, GPU, and local binaries."""

from __future__ import annotations

import shutil
from typing import Any

import typer
from rich.table import Table

from app.cli.context import CliContext
from app.cli.errors import handle_errors
from app.cli.helpers import unpack_ctx
from app.cli.types import ApiError, ConnectionFailed

doctor_help = "Check backend health, scheduler, GPU, and local tool availability."


@handle_errors
def doctor(ctx: typer.Context) -> None:
    """Run diagnostics on backend connectivity and local tools."""
    cli_ctx, r = unpack_ctx(ctx)
    checks = cli_ctx.run(_run_checks(cli_ctx))

    if r.is_json:
        r.emit_data(checks)
        return

    t = Table(title="Doctor", show_header=True, header_style="bold cyan")
    t.add_column("Check")
    t.add_column("Status")
    t.add_column("Details")

    for name, info in checks.items():
        status = "[green]pass[/green]" if info["ok"] else "[red]fail[/red]"
        t.add_row(name, status, info.get("detail", ""))

    cli_ctx.console.print(t)

    fails = [n for n, i in checks.items() if not i["ok"]]
    if fails:
        cli_ctx.console.print(
            f"\n[yellow]Issues detected in: {', '.join(fails)}[/yellow]"
        )
    else:
        cli_ctx.console.print("\n[green]All checks passed.[/green]")


async def _run_checks(cli_ctx: CliContext) -> dict[str, Any]:
    results: dict[str, Any] = {}
    backend_available = False

    # Backend health
    try:
        resp = await cli_ctx.client.get("/system/health")
        data = resp.data or {}
        backend_available = True
        results["backend"] = {
            "ok": True,
            "detail": data.get("status", "healthy"),
        }
    except ConnectionFailed:
        results["backend"] = {"ok": False, "detail": "Cannot connect to backend"}
    except ApiError as exc:
        results["backend"] = {"ok": False, "detail": exc.message}

    # Scheduler
    if backend_available:
        try:
            resp = await cli_ctx.client.get("/scheduler/status")
            data = resp.data or {}
            results["scheduler"] = {
                "ok": True,
                "detail": f"mode={data.get('mode', '?')}, queue={data.get('queue_depth', '?')}",
            }
        except (ConnectionFailed, ApiError) as exc:
            detail = "not reachable" if isinstance(exc, ConnectionFailed) else exc.message
            results["scheduler"] = {"ok": False, "detail": detail}
    else:
        results["scheduler"] = {
            "ok": True,
            "detail": "skipped (backend unavailable)",
        }

    # GPU
    if backend_available:
        try:
            resp = await cli_ctx.client.get("/system/gpu")
            data = resp.data or {}
            available = data.get("available", False)
            results["gpu"] = {
                "ok": True,
                "detail": "available" if available else "not detected",
            }
        except (ConnectionFailed, ApiError):
            results["gpu"] = {"ok": True, "detail": "skipped (backend unavailable)"}
    else:
        results["gpu"] = {"ok": True, "detail": "skipped (backend unavailable)"}

    # Local binaries
    for binary in ["nextflow", "miniwdl", "docker"]:
        path = shutil.which(binary)
        results[binary] = {
            "ok": path is not None,
            "detail": path or "not found in PATH",
        }

    return results
