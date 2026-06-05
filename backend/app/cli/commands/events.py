"""bif events stream — raw SSE pass-through for agents and monitoring."""

from __future__ import annotations

import typer

from app.cli.context import CliContext
from app.cli.errors import handle_errors
from app.cli.helpers import unpack_ctx
from app.cli.render import Renderer

events_app = typer.Typer(name="events", help="Event streaming.", no_args_is_help=True)


@events_app.command("stream")
@handle_errors
def events_stream(
    ctx: typer.Context,
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
    run_id: str | None = typer.Option(None, "--run", help="Run ID filter"),
    session_id: str | None = typer.Option(
        None, "--session", help="AgentCore session ID filter"
    ),
    turn_id: str | None = typer.Option(
        None, "--turn", help="AgentCore turn ID filter"
    ),
) -> None:
    """Stream raw SSE events (NDJSON in json mode, styled in human mode)."""
    cli_ctx, r = unpack_ctx(ctx)
    pid = project_id or cli_ctx.project_id
    if not pid:
        raise typer.BadParameter("--project is required")
    params: dict = {"project_id": pid}
    if run_id:
        params["run_id"] = run_id
    if session_id:
        params["session_id"] = session_id
    if turn_id:
        params["turn_id"] = turn_id
    cli_ctx.run(_stream(cli_ctx, r, params))


async def _stream(cli_ctx: CliContext, r: Renderer, params: dict) -> None:
    try:
        async for event in cli_ctx.client.stream_sse("/events/stream", params):
            r.stream_event(event)
    except KeyboardInterrupt:
        pass
