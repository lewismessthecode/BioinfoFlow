"""bif — Bioinfoflow CLI entry point."""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from typing import Optional

import typer
from rich.console import Console

from app.cli.config_store import ConfigStore
from app.cli.context import CliContext
from app.cli.errors import EXIT_USER_INPUT

# Note: app.cli.client and app.cli.transport are imported lazily inside the
# main callback below. They pull httpx (~50ms cold), and bif --version /
# bif --help return without ever needing them.


def _bif_version() -> str:
    try:
        return _pkg_version("bioinfoflow-backend")
    except PackageNotFoundError:
        return "0.0.0+unknown"


# -- App ----------------------------------------------------------------------

app = typer.Typer(
    name="bif",
    help="Bioinfoflow CLI — manage projects, workflows, and pipeline runs.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"bif {_bif_version()}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    mode: Optional[str] = typer.Option(
        None,
        "--mode",
        help="Transport mode: auto, remote, or local.",
    ),
    base_url: Optional[str] = typer.Option(
        None,
        "--base-url",
        help="Backend API URL.",
    ),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID to use (overrides default from config).",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        help="Output format: human or json.",
    ),
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help="Disable color output.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress non-essential output (errors and data still printed).",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show debug info (request/response details).",
    ),
    show_version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show CLI version and exit.",
    ),
) -> None:
    """Bioinfoflow CLI — manage projects, workflows, and pipeline runs."""
    store = ConfigStore()

    resolved_mode = store.resolve("mode", mode, "BIOFLOW_MODE") or "auto"
    resolved_url = (
        store.resolve("base_url", base_url, "BIOFLOW_API_URL")
        or "http://localhost:8000/api/v1"
    )
    resolved_project = store.resolve("project_id", project, "BIOFLOW_PROJECT")
    resolved_output = store.resolve("output", output, "BIOFLOW_OUTPUT") or "human"

    if resolved_output not in ("human", "json"):
        typer.echo(
            f"Invalid output mode: {resolved_output}. Use 'human' or 'json'.",
            err=True,
        )
        raise typer.Exit(EXIT_USER_INPUT)

    if resolved_mode not in ("auto", "remote", "local"):
        typer.echo(
            f"Invalid mode: {resolved_mode}. Use 'auto', 'remote', or 'local'.",
            err=True,
        )
        raise typer.Exit(EXIT_USER_INPUT)

    # Lazy-import the network stack so `bif --version` / `bif --help` never
    # pay for httpx + asyncio + the FastAPI ASGI graph.
    from app.cli.client import ApiClient
    from app.cli.transport import AutoTransport, LocalTransport, RemoteTransport

    if resolved_mode == "remote":
        transport = RemoteTransport(resolved_url)
    elif resolved_mode == "local":
        transport = LocalTransport()
    else:
        transport = AutoTransport(resolved_url)

    effective_no_color = no_color or os.environ.get("NO_COLOR") is not None
    console = Console(no_color=effective_no_color, stderr=resolved_output == "json")

    ctx.obj = CliContext(
        client=ApiClient(transport),
        output_mode=resolved_output,
        project_id=resolved_project,
        verbose=verbose,
        console=console,
        quiet=quiet,
    )


# -- Register subcommands ---------------------------------------------------

from app.cli.commands.agent import agent_app  # noqa: E402
from app.cli.commands.agent_approvals import approvals_app  # noqa: E402
from app.cli.commands.config_cmd import config_app  # noqa: E402
from app.cli.commands.doctor import doctor  # noqa: E402
from app.cli.commands.events import events_app  # noqa: E402
from app.cli.commands.file import file_app  # noqa: E402
from app.cli.commands.open_cmd import open_app  # noqa: E402
from app.cli.commands.project import project_app  # noqa: E402
from app.cli.commands.run import run_app  # noqa: E402
from app.cli.commands.run_batch import batch_app  # noqa: E402
from app.cli.commands.run_outputs import outputs_app  # noqa: E402
from app.cli.commands.system import system_app  # noqa: E402
from app.cli.commands.workflow import workflow_app  # noqa: E402

app.add_typer(config_app, name="config")
app.add_typer(project_app, name="project")
app.add_typer(workflow_app, name="workflow")
app.add_typer(file_app, name="file")
app.add_typer(system_app, name="system")
app.add_typer(events_app, name="events")
app.add_typer(open_app, name="open")

# Nest run sub-apps
run_app.add_typer(outputs_app, name="outputs")
run_app.add_typer(batch_app, name="batch")
app.add_typer(run_app, name="run")

# Nest agent sub-apps
agent_app.add_typer(approvals_app, name="approvals")
app.add_typer(agent_app, name="agent")

app.command("doctor", help="Check backend health, scheduler, GPU, and local tools.")(
    doctor
)
