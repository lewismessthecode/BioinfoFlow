"""bif system — health, stats, scheduler, and GPU info."""

from __future__ import annotations

import typer

from app.cli.api_helpers import api_get
from app.cli.errors import handle_errors
from app.cli.helpers import unpack_ctx

system_app = typer.Typer(
    name="system", help="System information and health.", no_args_is_help=True
)


@system_app.command("health")
@handle_errors
def system_health(ctx: typer.Context) -> None:
    """Check backend health."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, "/system/health"))
    data = resp.data or {}
    r.detail(
        {
            "Status": data.get("status", "unknown"),
            "Docker": str(data.get("docker", {}).get("available", "?")),
            "NVIDIA Runtime": str(data.get("docker", {}).get("nvidia_runtime", "?")),
            "GPU Available": str(data.get("gpu", {}).get("available", "?")),
            "Parabricks": str(data.get("parabricks", {}).get("image_available", "?")),
        },
        title="System Health",
        raw=resp,
    )


@system_app.command("stats")
@handle_errors
def system_stats(ctx: typer.Context) -> None:
    """Show platform statistics."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, "/stats"))
    data = resp.data or {}
    runs = data.get("runs", {})
    r.detail(
        {
            "Total Runs": str(runs.get("total", 0)),
            "Running": str(runs.get("running", 0)),
            "Completed": str(runs.get("completed", 0)),
            "Failed": str(runs.get("failed", 0)),
            "Queued": str(runs.get("queued", 0)),
            "Workflows": str(data.get("workflows", {}).get("total", 0)),
            "Projects": str(data.get("projects", {}).get("total", 0)),
        },
        title="Platform Statistics",
        raw=resp,
    )


@system_app.command("scheduler-status")
@handle_errors
def scheduler_status(ctx: typer.Context) -> None:
    """Show scheduler status."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, "/scheduler/status"))
    data = resp.data or {}
    r.detail(
        {
            "Mode": data.get("mode", "?"),
            "Effective Mode": data.get("effective_mode", "?"),
            "Available": str(data.get("scheduler_available", "?")),
            "Resource Monitoring": str(data.get("resource_monitoring_enabled", "?")),
            "Workers": str(data.get("workers", "?")),
            "Queue Depth": str(data.get("queue_depth", "?")),
        },
        title="Scheduler Status",
        raw=resp,
    )


@system_app.command("scheduler-resources")
@handle_errors
def scheduler_resources(ctx: typer.Context) -> None:
    """Show scheduler resource availability."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, "/scheduler/resources"))
    data = resp.data or {}
    cpu = data.get("cpu", {})
    mem = data.get("memory", {})
    disk = data.get("disk", {})
    r.detail(
        {
            "Mode": data.get("mode", "?"),
            "Enabled": str(data.get("enabled", "?")),
            "CPU": f"{cpu.get('available', '?')}/{cpu.get('total', '?')} cores",
            "Memory": f"{mem.get('available_gb', '?')}/{mem.get('total_gb', '?')} GB",
            "Disk": f"{disk.get('available_gb', '?')}/{disk.get('total_gb', '?')} GB",
            "Sampled At": data.get("sampled_at", "never"),
        },
        title="Scheduler Resources",
        raw=resp,
    )


@system_app.command("gpu")
@handle_errors
def system_gpu(ctx: typer.Context) -> None:
    """Show GPU status."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, "/system/gpu"))
    data = resp.data or {}
    fields = {
        "Available": str(data.get("available", False)),
        "nvidia-smi": str(data.get("nvidia_smi_found", False)),
        "Docker NVIDIA": str(data.get("docker_nvidia_runtime", False)),
        "Parabricks OK": str(data.get("parabricks_compatible", False)),
        "Recommendation": data.get("recommendation", ""),
    }
    gpus = data.get("gpus", [])
    for i, gpu in enumerate(gpus):
        fields[f"GPU {i}"] = (
            f"{gpu.get('name', '?')} ({gpu.get('memory_total_mb', '?')} MB)"
        )
    r.detail(fields, title="GPU Status", raw=resp)
