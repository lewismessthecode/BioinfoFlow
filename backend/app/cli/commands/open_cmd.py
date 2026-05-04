"""bif open — open a Bioinfoflow page in the system browser."""

from __future__ import annotations

import os
import webbrowser
from urllib.parse import urlsplit

import typer

from app.cli.config_store import ConfigStore
from app.cli.errors import handle_errors
from app.cli.helpers import unpack_ctx

open_app = typer.Typer(
    name="open",
    help="Open Bioinfoflow web pages in your browser.",
    no_args_is_help=True,
)


def _web_root() -> str:
    """Resolve the frontend base URL with the standard CLI precedence."""
    raw = (
        os.environ.get("BIOFLOW_WEB_URL")
        or ConfigStore().get("web_url")
        or "http://localhost:3000"
    )
    parts = urlsplit(raw.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise typer.BadParameter(
            f"Invalid web URL: {raw!r}. Set with --web-url, "
            "$BIOFLOW_WEB_URL, or `bif config set web_url <url>`."
        )
    # Strip trailing slash from path so `_join` produces clean URLs.
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"


def _join(root: str, path: str) -> str:
    return f"{root}/{path.lstrip('/')}"


def _emit(ctx_typer: typer.Context, kind: str, url: str, *, no_browser: bool) -> None:
    cli_ctx, r = unpack_ctx(ctx_typer)
    if r.is_json:
        r.emit_data({"kind": kind, "url": url, "opened": not no_browser})
    elif no_browser:
        # Print the URL plainly — useful for piping or remote shells where
        # webbrowser.open can't actually launch anything.
        cli_ctx.console.print(url, highlight=False)
    else:
        cli_ctx.console.print(f"[dim]Opening:[/dim] {url}")

    if no_browser:
        return
    if not webbrowser.open(url):
        # Fall back to printing — never fail just because there's no browser.
        if not r.is_json:
            cli_ctx.console.print(
                f"[yellow]Could not launch a browser. Open manually:[/yellow] {url}"
            )


_NO_BROWSER_OPT = typer.Option(
    False,
    "--no-browser",
    help="Print the URL instead of launching a browser.",
)
_WEB_URL_OPT = typer.Option(
    None,
    "--web-url",
    help="Override the frontend base URL (also $BIOFLOW_WEB_URL / `config set web_url`).",
)


def _resolve_root(override: str | None) -> str:
    if override:
        parts = urlsplit(override.strip())
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise typer.BadParameter(f"Invalid --web-url: {override!r}")
        return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"
    return _web_root()


@open_app.command("dashboard")
@handle_errors
def open_dashboard(
    ctx: typer.Context,
    no_browser: bool = _NO_BROWSER_OPT,
    web_url: str | None = _WEB_URL_OPT,
) -> None:
    """Open the dashboard page."""
    _emit(ctx, "dashboard", _join(_resolve_root(web_url), "dashboard"), no_browser=no_browser)


@open_app.command("run")
@handle_errors
def open_run(
    ctx: typer.Context,
    run_id: str = typer.Argument(help="Run ID"),
    no_browser: bool = _NO_BROWSER_OPT,
    web_url: str | None = _WEB_URL_OPT,
) -> None:
    """Open a run's detail page."""
    _emit(ctx, "run", _join(_resolve_root(web_url), f"runs/{run_id}"), no_browser=no_browser)


@open_app.command("workflow")
@handle_errors
def open_workflow(
    ctx: typer.Context,
    workflow_id: str = typer.Argument(help="Workflow ID"),
    no_browser: bool = _NO_BROWSER_OPT,
    web_url: str | None = _WEB_URL_OPT,
) -> None:
    """Open a workflow's detail page."""
    _emit(
        ctx,
        "workflow",
        _join(_resolve_root(web_url), f"workflows/{workflow_id}"),
        no_browser=no_browser,
    )


@open_app.command("agent")
@handle_errors
def open_agent(
    ctx: typer.Context,
    no_browser: bool = _NO_BROWSER_OPT,
    web_url: str | None = _WEB_URL_OPT,
) -> None:
    """Open the agent chat page."""
    _emit(ctx, "agent", _join(_resolve_root(web_url), "agent"), no_browser=no_browser)


@open_app.command("scheduler")
@handle_errors
def open_scheduler(
    ctx: typer.Context,
    no_browser: bool = _NO_BROWSER_OPT,
    web_url: str | None = _WEB_URL_OPT,
) -> None:
    """Open the scheduler page."""
    _emit(ctx, "scheduler", _join(_resolve_root(web_url), "scheduler"), no_browser=no_browser)
