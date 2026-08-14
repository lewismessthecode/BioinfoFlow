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
    "Start backend: uv run uvicorn app.main:app --reload --reload-dir app --port 8000 "
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

    try:
        resp = await cli_ctx.client.get("/system/readiness")
        readiness = resp.data or {}
        readiness_checks = readiness.get("checks")
        if isinstance(readiness_checks, list):
            for check in readiness_checks:
                if not isinstance(check, dict):
                    continue
                check_id = str(check.get("id") or "check")
                status = _readiness_status(str(check.get("status") or "fail"))
                detail, hint = _readiness_detail(check_id, check)
                result = _result(
                    status,
                    detail,
                    hint=hint,
                )
                if check.get("docs_link"):
                    result["docs_link"] = str(check["docs_link"])
                results[check_id] = result
            backend_available = True
    except ConnectionFailed:
        results["backend"] = _result(
            "fail",
            "Cannot connect to backend",
            hint=_START_BACKEND_HINT,
        )
    except ApiError as exc:
        if exc.status_code != 404:
            results["backend"] = _result(
                "fail",
                exc.message,
                hint="Check backend logs, then re-run doctor.",
            )

    if results and "backend" in results and _check_status(results["backend"]) == "fail":
        results["scheduler"] = _result("skip", "requires backend")
        results["gpu"] = _result("skip", "requires backend")
        _add_local_binary_checks(results)
        return results

    if backend_available:
        _add_local_binary_checks(results)
        return results

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
            detail = (
                "not reachable" if isinstance(exc, ConnectionFailed) else exc.message
            )
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
            detail = (
                "not reachable" if isinstance(exc, ConnectionFailed) else exc.message
            )
            results["gpu"] = _result("warn", detail)
    else:
        results["gpu"] = _result("skip", "requires backend")

    _add_local_binary_checks(results)

    return results


def _readiness_status(status: str) -> str:
    normalized = status.lower()
    if normalized in {"pass", "fail", "warn", "skip"}:
        return normalized
    if normalized == "ready":
        return "pass"
    if normalized == "warning":
        return "warn"
    return "fail"


def _add_local_binary_checks(results: dict[str, Any]) -> None:
    for binary in ["nextflow", "miniwdl", "docker"]:
        path = shutil.which(binary)
        results[binary] = _result(
            "pass" if path is not None else "fail",
            path or "not found in PATH",
            hint=None if path is not None else _binary_hint(binary),
        )


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


def _readiness_detail(check_id: str, check: dict[str, Any]) -> tuple[str, str | None]:
    facts = check.get("facts") if isinstance(check.get("facts"), dict) else {}

    if check_id == "backend":
        return "Backend is responding", None
    if check_id == "provider_key":
        if facts.get("configured"):
            return "At least one AI provider key is configured", None
        return (
            "No AI provider key is configured",
            "Configure a supported AI provider from Settings > AI Providers before the first run.",
        )
    if check_id == "docker":
        if facts.get("available"):
            return "Docker is available", None
        return (
            "Docker is not reachable from the backend",
            "Start Docker Desktop or the Docker daemon, then re-run doctor.",
        )
    if check_id == "scheduler":
        if facts.get("available"):
            return "Persistent scheduler is active", None
        return (
            "Persistent scheduler is unavailable",
            "Restart the backend and inspect scheduler startup logs.",
        )
    if check_id == "project":
        count = int(facts.get("count") or 0)
        if count > 0:
            return f"{count} project(s) exist", None
        return "No project exists yet", "Create a project before the first run."
    if check_id == "workflow_registry":
        count = int(facts.get("count") or 0)
        if count > 0:
            return f"{count} workflow(s) registered", None
        return "No workflows are registered yet", "Import or register a workflow."
    if check_id == "workflow_binding":
        count = int(facts.get("count") or 0)
        if count > 0:
            return f"{count} project workflow binding(s) exist", None
        return (
            "No workflow is enabled for a project yet",
            "Bind a workflow to a project before submitting a run.",
        )
    if check_id == "gpu":
        state = str(facts.get("state") or "")
        if facts.get("usable_for_gpu_workflows"):
            gpu_names = ", ".join(facts.get("gpu_names") or [])
            return f"GPU workflows are ready ({gpu_names or 'GPU visible'})", None
        if (
            facts.get("runtime_visible_to_backend")
            and int(facts.get("gpu_count") or 0) > 0
        ):
            gpu_names = ", ".join(facts.get("gpu_names") or [])
            return (
                f"GPU visible to backend ({gpu_names or 'optional capability'})",
                "GPU is optional unless your workflow requires acceleration.",
            )
        if state == "disabled":
            return (
                "GPU discovery is disabled",
                "Set BIOINFOFLOW_GPU_MODE=auto and recreate the backend to enable it.",
            )
        if state == "docker_unavailable":
            return (
                "Docker GPU capability could not be checked",
                "Restore backend access to the local Docker socket.",
            )
        if state == "toolkit_unavailable":
            return (
                "Docker cannot allocate an NVIDIA GPU",
                "Install NVIDIA Container Toolkit, verify 'docker run --rm --gpus all ...', then recreate the backend.",
            )
        if state == "no_gpus":
            return (
                "Docker reported no NVIDIA GPUs",
                "Check 'nvidia-smi -L' on the host; CPU workflows can still run.",
            )
        if state == "policy_invalid":
            return (
                "GPU selection is invalid",
                "Update BIOINFOFLOW_GPU_DEVICES with detected UUIDs and recreate the backend.",
            )
        if state == "probe_failed":
            return "GPU probe failed", "Check backend logs and host driver health."
        if facts.get("docker_nvidia_runtime"):
            return (
                "NVIDIA runtime detected on host, but GPU is not exposed to backend",
                str(
                    facts.get("recommendation")
                    or "Check NVIDIA Container Toolkit and recreate the backend."
                ),
            )
        return (
            "No GPU is visible to the backend",
            "CPU workflows can still run normally.",
        )
    return "", None


def _binary_hint(binary: str) -> str:
    if binary == "nextflow":
        return "Install Nextflow or add it to PATH before starting the backend."
    if binary == "miniwdl":
        return "Run uv sync from backend/ so miniwdl is installed in the project environment."
    if binary == "docker":
        return "Install Docker Desktop or add the docker CLI to PATH."
    return f"Install {binary} or add it to PATH."
