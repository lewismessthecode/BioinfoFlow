"""bif run batch — submit and manage batch runs."""

from __future__ import annotations

from typing import Any

import typer

from app.cli.api_helpers import api_get, api_post
from app.cli.errors import handle_errors
from app.cli.helpers import unpack_ctx
from app.cli.jsonio import SpecError, read_spec
from app.cli.run_spec import detect_legacy_run_keys

batch_app = typer.Typer(name="batch", help="Manage batch runs.", no_args_is_help=True)


@batch_app.command("submit")
@handle_errors
def batch_submit(
    ctx: typer.Context,
    spec: str = typer.Option(..., "--spec", help="JSON spec file or - for stdin"),
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
) -> None:
    """Submit a batch of runs from a JSON spec."""
    cli_ctx, r = unpack_ctx(ctx)
    payload = _normalize_batch_payload(read_spec(spec) or {})
    pid = project_id or cli_ctx.project_id
    if pid:
        payload["project_id"] = pid
    resp = cli_ctx.run(api_post(cli_ctx, "/runs/batch", payload))
    data = resp.data or {}
    r.detail(
        {
            "Batch ID": data.get("batch_id", ""),
            "Runs": str(data.get("run_count", len(data.get("runs", [])))),
            "Status": data.get("status", "submitted"),
        },
        title="Batch Submitted",
        raw=resp,
    )


@batch_app.command("show")
@handle_errors
def batch_show(
    ctx: typer.Context,
    batch_id: str = typer.Argument(help="Batch ID"),
) -> None:
    """Show batch details."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, f"/runs/batch/{batch_id}"))
    data = resp.data or {}
    r.detail(
        {
            "Batch ID": data.get("batch_id", ""),
            "Status": data.get("status", ""),
            "Runs": str(len(data.get("runs", []))),
            "Description": data.get("description", ""),
        },
        title="Batch",
        raw=resp,
    )


@batch_app.command("cancel")
@handle_errors
def batch_cancel(
    ctx: typer.Context,
    batch_id: str = typer.Argument(help="Batch ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Cancel all runs in a batch."""
    cli_ctx, r = unpack_ctx(ctx)
    if not force and cli_ctx.output_mode == "human":
        typer.confirm(f"Cancel all runs in batch {batch_id}?", abort=True)
    resp = cli_ctx.run(api_post(cli_ctx, f"/runs/batch/{batch_id}/cancel"))
    r.success(f"Batch {batch_id} cancelled.", raw=resp)


def _normalize_batch_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    runs = normalized.get("runs")
    if runs is None:
        normalized["runs"] = []
        return normalized
    if not isinstance(runs, list):
        raise SpecError("spec.runs must be a JSON array")

    normalized_runs: list[dict[str, Any]] = []
    for index, run in enumerate(runs):
        if not isinstance(run, dict):
            raise SpecError(f"spec.runs[{index}] must be a JSON object")
        legacy_keys = detect_legacy_run_keys(run)
        if legacy_keys:
            joined = ", ".join(legacy_keys)
            raise SpecError(
                f"legacy run keys are not supported in spec.runs[{index}]: {joined}. "
                "Use values/options instead."
            )
        normalized_run = dict(run)
        values = normalized_run.get("values")
        if values is None:
            normalized_run["values"] = {}
        elif not isinstance(values, dict):
            raise SpecError(f"spec.runs[{index}].values must be a JSON object")
        normalized_runs.append(normalized_run)

    normalized["runs"] = normalized_runs
    return normalized
