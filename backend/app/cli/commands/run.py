"""bif run — manage pipeline runs."""

from __future__ import annotations

import json
from typing import Any

import typer

from app.cli.api_helpers import api_get, api_post
from app.cli.constants import TERMINAL_RUN_STATUSES
from app.cli.context import CliContext
from app.cli.errors import handle_errors
from app.cli.helpers import require_project, unpack_ctx
from app.cli.jsonio import SpecError, read_spec
from app.cli.render import Renderer
from app.cli.run_spec import detect_legacy_run_keys

run_app = typer.Typer(name="run", help="Manage pipeline runs.", no_args_is_help=True)

_COLUMNS = [
    {"key": "run_id", "header": "Run ID"},
    {"key": "workflow_id", "header": "Workflow"},
    {"key": "status", "header": "Status"},
    {"key": "current_task", "header": "Task"},
    {"key": "created_at", "header": "Created"},
]


@run_app.command("list")
@handle_errors
def run_list(
    ctx: typer.Context,
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
    workflow_id: str | None = typer.Option(
        None, "--workflow", help="Filter by workflow"
    ),
    status: str | None = typer.Option(None, help="Filter by status (comma-separated)"),
    limit: int = typer.Option(20, help="Max results"),
    cursor: str | None = typer.Option(None, help="Pagination cursor"),
) -> None:
    """List runs."""
    cli_ctx, r = unpack_ctx(ctx)
    params: dict = {"limit": limit}
    pid = project_id or cli_ctx.project_id
    if pid:
        params["project_id"] = pid
    if workflow_id:
        params["workflow_id"] = workflow_id
    if status:
        params["status"] = status
    if cursor:
        params["cursor"] = cursor
    resp = cli_ctx.run(api_get(cli_ctx, "/runs", params))
    rows = resp.data if isinstance(resp.data, list) else []
    r.table(_COLUMNS, rows, resp)


@run_app.command("submit")
@handle_errors
def run_submit(
    ctx: typer.Context,
    workflow_id: str = typer.Option(..., "--workflow", help="Workflow ID"),
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
    values: str | None = typer.Option(None, "--values", help="JSON values object"),
    spec: str | None = typer.Option(
        None, "--spec", help="JSON spec file or - for stdin"
    ),
) -> None:
    """Submit a new run."""
    cli_ctx, r = unpack_ctx(ctx)
    pid = require_project(cli_ctx, project_id)
    payload = _normalize_run_payload(
        read_spec(spec) or {},
        project_id=pid,
        workflow_id=workflow_id,
    )
    if values:
        try:
            parsed = json.loads(values)
        except json.JSONDecodeError as exc:
            raise SpecError(f"Invalid JSON in --values: {exc}") from exc
        if not isinstance(parsed, dict):
            raise SpecError("--values must be a JSON object")
        payload["values"].update(parsed)
    resp = cli_ctx.run(api_post(cli_ctx, "/runs", payload))
    r.detail(_run_fields(resp.data), title="Run Submitted", raw=resp)


@run_app.command("wizard")
@handle_errors
def run_wizard(
    ctx: typer.Context,
    spec: str = typer.Option(..., "--spec", help="JSON spec file or - for stdin"),
) -> None:
    """Submit a run from a complete spec (project, workflow, values, options)."""
    cli_ctx, r = unpack_ctx(ctx)
    payload = _normalize_run_payload(read_spec(spec) or {})
    resp = cli_ctx.run(api_post(cli_ctx, "/runs", payload))
    r.detail(_run_fields(resp.data), title="Wizard Run Submitted", raw=resp)


@run_app.command("show")
@handle_errors
def run_show(
    ctx: typer.Context,
    run_id: str = typer.Argument(help="Run ID"),
) -> None:
    """Show run details."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, f"/runs/{run_id}"))
    r.detail(_run_fields(resp.data), title="Run", raw=resp)


@run_app.command("watch")
@handle_errors
def run_watch(
    ctx: typer.Context,
    run_id: str = typer.Argument(help="Run ID"),
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
) -> None:
    """Watch a run in real-time via SSE events."""
    cli_ctx, r = unpack_ctx(ctx)
    pid = project_id or cli_ctx.project_id
    # First fetch current state
    resp = cli_ctx.run(api_get(cli_ctx, f"/runs/{run_id}"))
    data = resp.data or {}
    status = data.get("status", "")
    if status in TERMINAL_RUN_STATUSES:
        r.detail(_run_fields(data), title=f"Run ({status})", raw=resp)
        return
    if not pid:
        pid = data.get("project_id")
    if not pid:
        raise typer.BadParameter("--project is required for streaming")
    r.detail(_run_fields(data), title="Watching Run", raw=resp)
    cli_ctx.run(_watch_stream(cli_ctx, r, run_id, pid))


@run_app.command("logs")
@handle_errors
def run_logs(
    ctx: typer.Context,
    run_id: str = typer.Argument(help="Run ID"),
    tail: int = typer.Option(100, help="Number of log lines"),
    task: str | None = typer.Option(None, help="Filter by task name"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Stream new logs"),
    project_id: str | None = typer.Option(
        None, "--project", help="Project ID (for --follow)"
    ),
) -> None:
    """Show run logs. Use --follow to stream."""
    cli_ctx, r = unpack_ctx(ctx)
    params: dict = {"tail": tail}
    if task:
        params["task"] = task
    resp = cli_ctx.run(api_get(cli_ctx, f"/runs/{run_id}/logs", params))
    if r.is_json and not follow:
        r.emit_json(resp)
    else:
        data = resp.data
        if isinstance(data, list):
            for line in data:
                cli_ctx.console.print(str(line))
        elif isinstance(data, str):
            cli_ctx.console.print(data)
        elif isinstance(data, dict):
            for line in data.get("lines", [data]):
                cli_ctx.console.print(str(line))
    if follow:
        pid = project_id or cli_ctx.project_id
        if not pid:
            # Try to get from run data
            run_resp = cli_ctx.run(api_get(cli_ctx, f"/runs/{run_id}"))
            pid = (run_resp.data or {}).get("project_id")
        if not pid:
            raise typer.BadParameter("--project is required for --follow")
        cli_ctx.run(_follow_logs(cli_ctx, r, run_id, pid))


@run_app.command("cancel")
@handle_errors
def run_cancel(
    ctx: typer.Context,
    run_id: str = typer.Argument(help="Run ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Cancel a running pipeline."""
    cli_ctx, r = unpack_ctx(ctx)
    if not force and cli_ctx.output_mode == "human":
        typer.confirm(f"Cancel run {run_id}?", abort=True)
    resp = cli_ctx.run(api_post(cli_ctx, f"/runs/{run_id}/cancel"))
    r.success(f"Run {run_id} cancelled.", raw=resp)


@run_app.command("retry")
@handle_errors
def run_retry(
    ctx: typer.Context,
    run_id: str = typer.Argument(help="Run ID"),
    spec: str | None = typer.Option(None, "--spec", help="JSON overrides"),
) -> None:
    """Retry a failed run."""
    cli_ctx, r = unpack_ctx(ctx)
    payload = read_spec(spec)
    resp = cli_ctx.run(api_post(cli_ctx, f"/runs/{run_id}/retry", payload))
    r.detail(
        _retry_fields(resp.data),
        title="Run Retried",
        raw=resp,
    )


@run_app.command("resume")
@handle_errors
def run_resume(
    ctx: typer.Context,
    run_id: str = typer.Argument(help="Run ID"),
    spec: str | None = typer.Option(None, "--spec", help="JSON config overrides"),
) -> None:
    """Resume a failed run from checkpoint."""
    cli_ctx, r = unpack_ctx(ctx)
    payload = read_spec(spec)
    resp = cli_ctx.run(api_post(cli_ctx, f"/runs/{run_id}/resume", payload))
    r.detail(
        _retry_fields(resp.data),
        title="Run Resumed",
        raw=resp,
    )


@run_app.command("cleanup")
@handle_errors
def run_cleanup(
    ctx: typer.Context,
    run_id: str = typer.Argument(help="Run ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Clean up run resources."""
    cli_ctx, r = unpack_ctx(ctx)
    if not force and cli_ctx.output_mode == "human":
        typer.confirm(f"Clean up run {run_id}?", abort=True)
    resp = cli_ctx.run(api_post(cli_ctx, f"/runs/{run_id}/cleanup"))
    r.success(f"Run {run_id} cleaned up.", raw=resp)


_STATUS_STYLES: dict[str, str] = {
    "completed": "green",
    "running": "cyan",
    "queued": "yellow",
    "pending": "yellow",
    "submitted": "yellow",
    "failed": "red",
    "cancelled": "magenta",
}


def _style_status(status: str) -> str:
    if not status:
        return ""
    style = _STATUS_STYLES.get(status.lower())
    return f"[{style}]{status}[/{style}]" if style else status


def _run_fields(data: dict | None) -> dict:
    if not data:
        return {}
    return {
        "Run ID": data.get("run_id", ""),
        "Project": data.get("project_id", ""),
        "Workflow": data.get("workflow_id", ""),
        "Status": _style_status(data.get("status", "")),
        "Task": data.get("current_task", ""),
        "Created": data.get("created_at", ""),
    }


def _retry_fields(data: dict | None) -> dict:
    if not data:
        return {}
    return {
        "Original Run": data.get("run_id", ""),
        "New Run": data.get("new_run_id", ""),
        "Status": data.get("status", ""),
        "Message": data.get("message", ""),
    }


def _normalize_run_payload(
    payload: dict[str, Any],
    *,
    project_id: str | None = None,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    normalized = dict(payload)
    if project_id is not None:
        normalized["project_id"] = project_id
    if workflow_id is not None:
        normalized["workflow_id"] = workflow_id

    legacy_keys = detect_legacy_run_keys(normalized)
    if legacy_keys:
        joined = ", ".join(legacy_keys)
        raise SpecError(
            f"legacy run keys are not supported: {joined}. Use values/options instead."
        )

    values = normalized.get("values")
    if values is None:
        normalized["values"] = {}
    elif not isinstance(values, dict):
        raise SpecError("spec.values must be a JSON object")

    options = normalized.get("options")
    if options is not None and not isinstance(options, dict):
        raise SpecError("spec.options must be a JSON object")

    return normalized


async def _watch_stream(
    cli_ctx: CliContext, r: Renderer, run_id: str, project_id: str
) -> None:
    """Stream SSE events for a run until it reaches a terminal status."""
    try:
        async for event in cli_ctx.client.stream_sse(
            "/events/stream", {"project_id": project_id, "run_id": run_id}
        ):
            r.stream_event(event)
            # Check for terminal status in run.status events
            if event.event == "run.status":
                try:
                    data = json.loads(event.data)
                    status = data.get("data", {}).get("status") or data.get("status")
                    if status in TERMINAL_RUN_STATUSES:
                        if not r.is_json:
                            cli_ctx.console.print(
                                f"\nRun finished: {_style_status(status)}"
                            )
                        break
                except (json.JSONDecodeError, TypeError):
                    pass
    except KeyboardInterrupt:
        pass


async def _follow_logs(
    cli_ctx: CliContext, r: Renderer, run_id: str, project_id: str
) -> None:
    """Stream log events until the run finishes."""
    try:
        async for event in cli_ctx.client.stream_sse(
            "/events/stream", {"project_id": project_id, "run_id": run_id}
        ):
            if event.event == "run.log":
                r.stream_event(event)
            elif event.event == "run.status":
                try:
                    data = json.loads(event.data)
                    status = data.get("data", {}).get("status") or data.get("status")
                    if status in TERMINAL_RUN_STATUSES:
                        break
                except (json.JSONDecodeError, TypeError):
                    pass
    except KeyboardInterrupt:
        pass
