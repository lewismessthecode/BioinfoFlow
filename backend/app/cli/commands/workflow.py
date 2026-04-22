"""bif workflow — manage workflows."""

from __future__ import annotations

import typer

from app.cli.api_helpers import api_delete, api_get, api_post
from app.cli.errors import handle_errors
from app.cli.helpers import unpack_ctx
from app.cli.jsonio import read_spec

workflow_app = typer.Typer(
    name="workflow", help="Manage workflows.", no_args_is_help=True
)

_COLUMNS = [
    {"key": "id", "header": "ID"},
    {"key": "name", "header": "Name"},
    {"key": "source", "header": "Source"},
    {"key": "engine", "header": "Engine"},
    {"key": "version", "header": "Version"},
]


@workflow_app.command("list")
@handle_errors
def workflow_list(
    ctx: typer.Context,
    limit: int = typer.Option(20, help="Max results"),
    cursor: str | None = typer.Option(None, help="Pagination cursor"),
    search: str | None = typer.Option(None, help="Search by name"),
    source: str | None = typer.Option(
        None, help="Filter by source (nf-core, github, local)"
    ),
) -> None:
    """List registered workflows."""
    cli_ctx, r = unpack_ctx(ctx)
    params: dict = {"limit": limit}
    if cursor:
        params["cursor"] = cursor
    if search:
        params["search"] = search
    if source:
        params["source"] = source
    resp = cli_ctx.run(api_get(cli_ctx, "/workflows", params))
    rows = resp.data if isinstance(resp.data, list) else []
    r.table(_COLUMNS, rows, resp)


@workflow_app.command("register")
@handle_errors
def workflow_register(
    ctx: typer.Context,
    source: str = typer.Option(..., help="Source: nf-core, github, or local"),
    name: str | None = typer.Option(None, help="Workflow name"),
    version: str | None = typer.Option(None, help="Version tag"),
    engine: str | None = typer.Option(None, help="Engine: nextflow or wdl"),
    source_ref: str | None = typer.Option(None, "--ref", help="Remote source ref or local entry file"),
    bundle_path: str | None = typer.Option(None, "--bundle", help="Local workflow bundle directory"),
    entrypoint_relpath: str | None = typer.Option(None, "--entrypoint", help="Entrypoint relative path inside bundle"),
    description: str | None = typer.Option(None, help="Description"),
    spec: str | None = typer.Option(
        None, "--spec", help="JSON spec file or - for stdin"
    ),
) -> None:
    """Register a new workflow."""
    cli_ctx, r = unpack_ctx(ctx)
    payload = read_spec(spec) or {}
    payload["source"] = source
    if name:
        payload["name"] = name
    if version:
        payload["version"] = version
    if engine:
        payload["engine"] = engine
    if source_ref:
        payload["source_ref"] = source_ref
    if bundle_path:
        payload["bundle_path"] = bundle_path
    if entrypoint_relpath:
        payload["entrypoint_relpath"] = entrypoint_relpath
    if description:
        payload["description"] = description
    resp = cli_ctx.run(api_post(cli_ctx, "/workflows", payload))
    r.detail(_fields(resp.data), title="Workflow Registered", raw=resp)


@workflow_app.command("show")
@handle_errors
def workflow_show(
    ctx: typer.Context,
    workflow_id: str = typer.Argument(help="Workflow ID"),
) -> None:
    """Show workflow details."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, f"/workflows/{workflow_id}"))
    r.detail(_fields(resp.data), title="Workflow", raw=resp)


@workflow_app.command("source")
@handle_errors
def workflow_source(
    ctx: typer.Context,
    workflow_id: str = typer.Argument(help="Workflow ID"),
) -> None:
    """Show workflow source code."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, f"/workflows/{workflow_id}/source"))
    if r.is_json:
        r.emit_json(resp)
    else:
        content = resp.data.get("content", "") if resp.data else ""
        cli_ctx.console.print(content)


@workflow_app.command("bind")
@handle_errors
def workflow_bind(
    ctx: typer.Context,
    workflow_id: str = typer.Argument(help="Workflow ID"),
    project_id: str | None = typer.Option(
        None, "--project", help="Project ID (uses default if set)"
    ),
) -> None:
    """Bind a workflow to a project."""
    cli_ctx, r = unpack_ctx(ctx)
    pid = project_id or cli_ctx.project_id
    if not pid:
        raise typer.BadParameter(
            "--project is required (or set a default with: bif config use-project)"
        )
    resp = cli_ctx.run(
        api_post(cli_ctx, f"/projects/{pid}/workflows/{workflow_id}:bind")
    )
    r.success(f"Workflow {workflow_id} bound to project {pid}.", raw=resp)


@workflow_app.command("unbind")
@handle_errors
def workflow_unbind(
    ctx: typer.Context,
    workflow_id: str = typer.Argument(help="Workflow ID"),
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
) -> None:
    """Unbind a workflow from a project."""
    cli_ctx, r = unpack_ctx(ctx)
    pid = project_id or cli_ctx.project_id
    if not pid:
        raise typer.BadParameter(
            "--project is required (or set a default with: bif config use-project)"
        )
    resp = cli_ctx.run(
        api_delete(cli_ctx, f"/projects/{pid}/workflows/{workflow_id}:unbind")
    )
    r.success(f"Workflow {workflow_id} unbound from project {pid}.", raw=resp)


@workflow_app.command("pin")
@handle_errors
def workflow_pin(
    ctx: typer.Context,
    workflow_id: str = typer.Argument(help="Workflow ID to pin"),
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
) -> None:
    """Pin a specific workflow version for a project."""
    cli_ctx, r = unpack_ctx(ctx)
    pid = project_id or cli_ctx.project_id
    if not pid:
        raise typer.BadParameter("--project is required")
    resp = cli_ctx.run(
        api_post(
            cli_ctx,
            f"/projects/{pid}/workflow-pins",
            {"pinned_workflow_id": workflow_id},
        )
    )
    r.success(f"Workflow {workflow_id} pinned in project {pid}.", raw=resp)


def _fields(data: dict | None) -> dict:
    if not data:
        return {}
    return {
        "ID": data.get("id", ""),
        "Name": data.get("name", ""),
        "Source": data.get("source", ""),
        "Engine": data.get("engine", ""),
        "Version": data.get("version", ""),
        "Description": data.get("description", ""),
        "Source Ref": data.get("source_ref", ""),
        "Entrypoint": data.get("entrypoint_relpath", ""),
        "Created": data.get("created_at", ""),
    }
