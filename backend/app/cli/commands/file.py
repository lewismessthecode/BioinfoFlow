"""bif file — Unix-like file operations on project workspaces."""

from __future__ import annotations

from pathlib import Path

import typer

from app.cli.api_helpers import api_delete, api_download, api_get, api_post, api_upload
from app.cli.errors import handle_errors
from app.cli.helpers import require_project, unpack_ctx

file_app = typer.Typer(name="file", help="File operations.", no_args_is_help=True)


@file_app.command("ls")
@handle_errors
def file_ls(
    ctx: typer.Context,
    path: str = typer.Argument(".", help="Directory path"),
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="List recursively"),
    pattern: str | None = typer.Option(None, help="Glob pattern filter"),
) -> None:
    """List files in a project workspace."""
    cli_ctx, r = unpack_ctx(ctx)
    pid = require_project(cli_ctx, project_id)
    params: dict = {"project_id": pid, "path": path, "recursive": recursive}
    if pattern:
        params["pattern"] = pattern
    resp = cli_ctx.run(api_get(cli_ctx, "/files", params))
    data = resp.data or {}
    files = data.get("files", []) if isinstance(data, dict) else data
    if isinstance(files, list):
        cols = [
            {"key": "name", "header": "Name"},
            {"key": "type", "header": "Type"},
            {"key": "size_bytes", "header": "Size"},
        ]
        r.table(cols, files, resp)
    else:
        r.detail({"Path": path, "Files": str(files)}, title="Files", raw=resp)


@file_app.command("cat")
@handle_errors
def file_cat(
    ctx: typer.Context,
    path: str = typer.Argument(help="File path"),
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
    lines: int = typer.Option(100, help="Number of lines to read"),
    offset: int = typer.Option(0, help="Line offset"),
) -> None:
    """Read file contents."""
    cli_ctx, r = unpack_ctx(ctx)
    pid = require_project(cli_ctx, project_id)
    params = {"project_id": pid, "path": path, "lines": lines, "offset": offset}
    resp = cli_ctx.run(api_get(cli_ctx, "/files/read", params))
    if r.is_json:
        r.emit_json(resp)
    else:
        data = resp.data or {}
        content = data.get("content", "") if isinstance(data, dict) else str(data)
        cli_ctx.console.print(content, highlight=False)
        if isinstance(data, dict) and data.get("truncated"):
            cli_ctx.console.print(
                f"[dim]... truncated ({data.get('total_lines', '?')} total lines)[/dim]"
            )


@file_app.command("download")
@handle_errors
def file_download(
    ctx: typer.Context,
    path: str = typer.Argument(help="File path to download"),
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
    dest: str = typer.Option(".", "--dest", "-o", help="Destination directory"),
) -> None:
    """Download a file from the workspace."""
    cli_ctx, r = unpack_ctx(ctx)
    pid = require_project(cli_ctx, project_id)
    dest_path = Path(dest) / Path(path).name
    with r.spinner(f"Downloading {path}..."):
        result = cli_ctx.run(
            api_download(
                cli_ctx, "/files/download", dest_path, {"project_id": pid, "path": path}
            )
        )
    r.success(f"Downloaded to {result}")


@file_app.command("upload")
@handle_errors
def file_upload(
    ctx: typer.Context,
    local_path: str = typer.Argument(help="Local file to upload"),
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
    remote_path: str | None = typer.Option(
        None, "--path", help="Remote destination path"
    ),
    overwrite: bool = typer.Option(False, help="Overwrite existing file"),
) -> None:
    """Upload a file to the workspace."""
    cli_ctx, r = unpack_ctx(ctx)
    pid = require_project(cli_ctx, project_id)
    file_path = Path(local_path)
    if not file_path.is_file():
        raise typer.BadParameter(f"File not found: {local_path}")
    fields = {"project_id": pid, "overwrite": str(overwrite).lower()}
    if remote_path:
        fields["path"] = remote_path
    with r.spinner(f"Uploading {file_path.name}..."):
        resp = cli_ctx.run(api_upload(cli_ctx, "/files/upload", file_path, fields))
    r.success(f"Uploaded {file_path.name}.", raw=resp)


@file_app.command("scan")
@handle_errors
def file_scan(
    ctx: typer.Context,
    path: str = typer.Argument(".", help="Directory to scan"),
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
    file_types: str | None = typer.Option(None, help="Comma-separated file types"),
) -> None:
    """Scan workspace for samples and file types."""
    cli_ctx, r = unpack_ctx(ctx)
    pid = require_project(cli_ctx, project_id)
    payload: dict = {"project_id": pid, "path": path}
    if file_types:
        payload["file_types"] = [ft.strip() for ft in file_types.split(",")]
    resp = cli_ctx.run(api_post(cli_ctx, "/files/scan", payload))
    data = resp.data or {}
    samples = data.get("detected_samples", []) if isinstance(data, dict) else []
    if samples:
        cols = [
            {"key": "sample_id", "header": "Sample ID"},
            {"key": "file_count", "header": "Files"},
        ]
        rows = [
            {"sample_id": s.get("sample_id", ""), "file_count": len(s.get("files", []))}
            for s in samples
        ]
        r.table(cols, rows, resp)
    else:
        r.success(
            f"Scan complete: {data.get('total_samples', 0)} samples found.", raw=resp
        )


@file_app.command("rm")
@handle_errors
def file_rm(
    ctx: typer.Context,
    path: str = typer.Argument(help="File path to delete"),
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a file from the workspace."""
    cli_ctx, r = unpack_ctx(ctx)
    pid = require_project(cli_ctx, project_id)
    if not force and cli_ctx.output_mode == "human":
        typer.confirm(f"Delete {path}?", abort=True)
    resp = cli_ctx.run(api_delete(cli_ctx, "/files", {"project_id": pid, "path": path}))
    r.success(f"Deleted {path}.", raw=resp)
