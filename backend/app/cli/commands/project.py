"""bif project — manage projects."""

from __future__ import annotations

import typer

from app.cli.api_helpers import api_delete, api_get, api_post
from app.cli.errors import handle_errors
from app.cli.helpers import unpack_ctx

project_app = typer.Typer(name="project", help="Manage projects.", no_args_is_help=True)

_COLUMNS = [
    {"key": "id", "header": "ID"},
    {"key": "name", "header": "Name"},
    {"key": "storage_mode", "header": "Storage"},
    {"key": "created_at", "header": "Created"},
]


@project_app.command("list")
@handle_errors
def project_list(
    ctx: typer.Context,
    limit: int = typer.Option(20, help="Max results"),
    cursor: str | None = typer.Option(None, help="Pagination cursor"),
    search: str | None = typer.Option(None, help="Search by name"),
) -> None:
    """List all projects."""
    cli_ctx, r = unpack_ctx(ctx)
    params: dict = {"limit": limit}
    if cursor:
        params["cursor"] = cursor
    if search:
        params["search"] = search
    resp = cli_ctx.run(api_get(cli_ctx, "/projects", params))
    rows = resp.data if isinstance(resp.data, list) else []
    r.table(_COLUMNS, rows, resp)


@project_app.command("create")
@handle_errors
def project_create(
    ctx: typer.Context,
    name: str = typer.Option(..., help="Project name"),
    external_root: str | None = typer.Option(
        None, "--external-root", help="Admin-only external project root"
    ),
    description: str | None = typer.Option(None, help="Description"),
) -> None:
    """Create a new project."""
    cli_ctx, r = unpack_ctx(ctx)
    payload: dict = {"name": name}
    if description:
        payload["description"] = description
    if external_root:
        payload["external_root_path"] = external_root
    resp = cli_ctx.run(api_post(cli_ctx, "/projects", payload))
    r.detail(_fields(resp.data), title="Project Created", raw=resp)


@project_app.command("show")
@handle_errors
def project_show(
    ctx: typer.Context,
    project_id: str = typer.Argument(help="Project ID"),
) -> None:
    """Show project details."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, f"/projects/{project_id}"))
    r.detail(_fields(resp.data), title="Project", raw=resp)


@project_app.command("use")
@handle_errors
def project_use(
    ctx: typer.Context,
    project_id: str = typer.Argument(help="Project ID to set as default"),
) -> None:
    """Set a project as the default for all commands."""
    from app.cli.config_store import ConfigStore

    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, f"/projects/{project_id}"))
    store = ConfigStore()
    store.set("project_id", project_id)
    name = resp.data.get("name", project_id) if resp.data else project_id
    r.success(f"Default project set: {name} ({project_id})", raw=resp)


@project_app.command("delete")
@handle_errors
def project_delete(
    ctx: typer.Context,
    project_id: str = typer.Argument(help="Project ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a project."""
    cli_ctx, r = unpack_ctx(ctx)
    if not force and cli_ctx.output_mode == "human":
        typer.confirm(f"Delete project {project_id}?", abort=True)
    resp = cli_ctx.run(api_delete(cli_ctx, f"/projects/{project_id}"))
    r.success(f"Project {project_id} deleted.", raw=resp)


def _fields(data: dict | None) -> dict:
    if not data:
        return {}
    return {
        "ID": data.get("id", ""),
        "Name": data.get("name", ""),
        "Storage": data.get("storage_mode", ""),
        "External Root": data.get("external_root_path", ""),
        "Description": data.get("description", ""),
        "Created": data.get("created_at", ""),
    }
