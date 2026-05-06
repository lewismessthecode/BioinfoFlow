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

_START_BACKEND_HINT = (
    "Start backend: uv run uvicorn app.main:app --reload --port 8000 "
    "(from backend/), or set --base-url / BIOFLOW_API_URL."
)

_STATUS_STYLES = {
    "pass": "[green]pass[/green]",
    "fail": "[red]fail[/red]",
    "warn": "[yellow]warn[/yellow]",
    "skip": "[dim]skip[/dim]",
}


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
        status = _check_status(info)
        detail = str(info.get("detail", ""))
        if info.get("hint"):
            detail = f"{detail}\n[dim]{info['hint']}[/dim]"
        t.add_row(name, _STATUS_STYLES.get(status, status), detail)

    cli_ctx.console.print(t)

    fails = [n for n, i in checks.items() if _check_status(i) == "fail"]
    warnings = [n for n, i in checks.items() if _check_status(i) == "warn"]
    skipped = [n for n, i in checks.items() if _check_status(i) == "skip"]
    if fails:
        cli_ctx.console.print(
            f"\n[yellow]Issues detected in: {', '.join(fails)}[/yellow]"
        )
    if warnings:
        cli_ctx.console.print(f"[yellow]Warnings: {', '.join(warnings)}[/yellow]")
    if skipped:
        cli_ctx.console.print(f"[dim]Skipped checks: {', '.join(skipped)}[/dim]")
    if not fails and not warnings:
        cli_ctx.console.print("\n[green]All checks passed.[/green]")


async def _run_checks(cli_ctx: CliContext) -> dict[str, Any]:
    results: dict[str, Any] = {}
    backend_available = False

    # Backend health
    try:
        resp = await cli_ctx.client.get("/system/health")
        data = resp.data or {}
        backend_available = True
        results["backend"] = _result("pass", data.get("status", "healthy"))
    except ConnectionFailed:
        results["backend"] = _result(
            "fail",
            "Cannot connect to backend",
            hint=_START_BACKEND_HINT,
        )
    except ApiError as exc:
        results["backend"] = _result(
            "fail",
            exc.message,
            hint="Check backend logs, then re-run doctor.",
        )

    # Scheduler
    if backend_available:
        try:
            resp = await cli_ctx.client.get("/scheduler/status")
            data = resp.data or {}
            results["scheduler"] = _result(
                "pass",
                f"mode={data.get('mode', '?')}, queue={data.get('queue_depth', '?')}",
            )
        except (ConnectionFailed, ApiError) as exc:
            detail = "not reachable" if isinstance(exc, ConnectionFailed) else exc.message
            results["scheduler"] = _result(
                "fail",
                detail,
                hint="Check backend scheduler logs and /scheduler/status.",
            )
    else:
        results["scheduler"] = _result("skip", "requires backend")

    # GPU
    if backend_available:
        try:
            resp = await cli_ctx.client.get("/system/gpu")
            data = resp.data or {}
            available = data.get("available", False)
            results["gpu"] = _result(
                "pass" if available else "warn",
                "available" if available else "not detected",
            )
        except (ConnectionFailed, ApiError) as exc:
            detail = "not reachable" if isinstance(exc, ConnectionFailed) else exc.message
            results["gpu"] = _result("warn", detail)
    else:
        results["gpu"] = _result("skip", "requires backend")

    # Local binaries
    for binary in ["nextflow", "miniwdl", "docker"]:
        path = shutil.which(binary)
        results[binary] = _result(
            "pass" if path is not None else "fail",
            path or "not found in PATH",
            hint=None if path is not None else _binary_hint(binary),
        )

    return results


def _check_status(info: dict[str, Any]) -> str:
    status = str(info.get("status") or "").lower()
    if status:
        return status
    return "pass" if info.get("ok") else "fail"


def _result(status: str, detail: str, *, hint: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": status not in {"fail"},
        "status": status,
        "detail": detail,
    }
    if hint:
        result["hint"] = hint
    return result


def _binary_hint(binary: str) -> str:
    if binary == "nextflow":
        return "Install Nextflow or add it to PATH before starting the backend."
    if binary == "miniwdl":
        return "Run uv sync from backend/ so miniwdl is installed in the project environment."
    if binary == "docker":
        return "Install Docker Desktop or add the docker CLI to PATH."
    return f"Install {binary} or add it to PATH."
