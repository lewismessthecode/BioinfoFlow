"""Shared command helpers — DRY context unpacking and project validation."""

from __future__ import annotations

import typer

from app.cli.context import CliContext
from app.cli.render import Renderer


def unpack_ctx(ctx: typer.Context) -> tuple[CliContext, Renderer]:
    """Extract CliContext and build a Renderer from a typer.Context."""
    cli_ctx: CliContext = ctx.obj
    return cli_ctx, Renderer(cli_ctx.console, cli_ctx.output_mode, cli_ctx.quiet)


def require_project(cli_ctx: CliContext, project_id: str | None) -> str:
    """Resolve a project ID or raise BadParameter if missing."""
    pid = project_id or cli_ctx.project_id
    if not pid:
        raise typer.BadParameter(
            "--project/-p is required, or set a default with "
            "`bif config use-project <id>` (also reads $BIOFLOW_PROJECT)."
        )
    return pid
