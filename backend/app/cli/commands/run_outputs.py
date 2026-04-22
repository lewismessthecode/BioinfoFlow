"""bif run outputs — list and download run output files."""

from __future__ import annotations

from pathlib import Path

import typer

from app.cli.api_helpers import api_download, api_get
from app.cli.errors import handle_errors
from app.cli.helpers import unpack_ctx

outputs_app = typer.Typer(
    name="outputs", help="Manage run output files.", no_args_is_help=True
)


@outputs_app.command("list")
@handle_errors
def outputs_list(
    ctx: typer.Context,
    run_id: str = typer.Argument(help="Run ID"),
) -> None:
    """List output files for a run."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, f"/runs/{run_id}/outputs"))
    data = resp.data
    if isinstance(data, list):
        cols = [
            {"key": "name", "header": "Name"},
            {"key": "path", "header": "Path"},
            {"key": "size_bytes", "header": "Size"},
        ]
        r.table(cols, data, resp)
    else:
        r.detail({"Outputs": str(data)}, title="Run Outputs", raw=resp)


@outputs_app.command("download")
@handle_errors
def outputs_download(
    ctx: typer.Context,
    run_id: str = typer.Argument(help="Run ID"),
    file: str | None = typer.Option(None, help="Specific file to download"),
    dest: str = typer.Option(".", "--dest", "-o", help="Destination directory"),
    fmt: str = typer.Option("tar.gz", "--format", help="Archive format"),
) -> None:
    """Download run outputs."""
    cli_ctx, r = unpack_ctx(ctx)
    params: dict = {"format": fmt}
    if file:
        params["file"] = file
    filename = f"{run_id}_outputs.{fmt}" if not file else Path(file).name
    dest_path = Path(dest) / filename
    with r.spinner(f"Downloading outputs to {dest_path}..."):
        result = cli_ctx.run(
            api_download(cli_ctx, f"/runs/{run_id}/outputs/download", dest_path, params)
        )
    r.success(f"Downloaded to {result}")
