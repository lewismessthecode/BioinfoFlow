"""bif config — manage CLI configuration."""

from __future__ import annotations

import typer
from rich.table import Table

from app.cli.config_store import ConfigStore
from app.cli.context import CliContext

config_app = typer.Typer(
    name="config", help="Manage CLI configuration.", no_args_is_help=True
)

_VALID_KEYS = {"mode", "base_url", "output", "project_id"}


def _store(ctx: typer.Context) -> ConfigStore:
    _: CliContext = ctx.obj
    return ConfigStore()


@config_app.command("init")
def config_init(ctx: typer.Context) -> None:
    """Create default config file at ~/.config/bioinfoflow/cli.toml."""
    store = ConfigStore()
    store.init()
    cli_ctx: CliContext = ctx.obj
    if cli_ctx.output_mode == "json":
        import json
        import sys

        sys.stdout.write(
            json.dumps({"success": True, "data": {"path": str(store.path)}}) + "\n"
        )
    else:
        cli_ctx.console.print(f"[green]Config created:[/green] {store.path}")


@config_app.command("set")
def config_set(
    ctx: typer.Context,
    key: str = typer.Argument(help="Config key to set"),
    value: str = typer.Argument(help="Value to set"),
) -> None:
    """Set a config value."""
    if key not in _VALID_KEYS:
        raise typer.BadParameter(
            f"Unknown key: {key}. Valid: {', '.join(sorted(_VALID_KEYS))}"
        )
    store = ConfigStore()
    store.set(key, value)
    cli_ctx: CliContext = ctx.obj
    if cli_ctx.output_mode == "json":
        import json
        import sys

        sys.stdout.write(json.dumps({"success": True, "data": {key: value}}) + "\n")
    else:
        cli_ctx.console.print(f"[green]{key}[/green] = {value}")


@config_app.command("get")
def config_get(
    ctx: typer.Context,
    key: str = typer.Argument(help="Config key to read"),
) -> None:
    """Get a config value."""
    store = ConfigStore()
    value = store.get(key)
    cli_ctx: CliContext = ctx.obj
    if cli_ctx.output_mode == "json":
        import json
        import sys

        sys.stdout.write(json.dumps({"success": True, "data": {key: value}}) + "\n")
    else:
        if value is None:
            cli_ctx.console.print(f"[dim]{key} is not set[/dim]")
        else:
            cli_ctx.console.print(f"[bold]{key}[/bold] = {value}")


@config_app.command("show")
def config_show(ctx: typer.Context) -> None:
    """Show all config values."""
    store = ConfigStore()
    data = store.load()
    cli_ctx: CliContext = ctx.obj
    if cli_ctx.output_mode == "json":
        import json
        import sys

        sys.stdout.write(json.dumps({"success": True, "data": data}) + "\n")
        return

    if not data:
        cli_ctx.console.print("[dim]No config set. Run: bif config init[/dim]")
        return

    t = Table(title="CLI Configuration", show_header=True, header_style="bold cyan")
    t.add_column("Key")
    t.add_column("Value")
    for k, v in sorted(data.items()):
        t.add_row(k, str(v))
    cli_ctx.console.print(t)
    cli_ctx.console.print(f"[dim]File: {store.path}[/dim]")


@config_app.command("use-project")
def config_use_project(
    ctx: typer.Context,
    project_id: str = typer.Argument(help="Project ID to set as default"),
) -> None:
    """Set default project for all commands."""
    store = ConfigStore()
    store.set("project_id", project_id)
    cli_ctx: CliContext = ctx.obj
    if cli_ctx.output_mode == "json":
        import json
        import sys

        sys.stdout.write(
            json.dumps({"success": True, "data": {"project_id": project_id}}) + "\n"
        )
    else:
        cli_ctx.console.print(f"[green]Default project set:[/green] {project_id}")
