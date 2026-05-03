"""bif config — manage CLI configuration."""

from __future__ import annotations

import typer
from rich.table import Table

from app.cli.config_store import ConfigStore
from app.cli.errors import handle_errors
from app.cli.helpers import unpack_ctx

config_app = typer.Typer(
    name="config", help="Manage CLI configuration.", no_args_is_help=True
)

_VALID_KEYS = {"mode", "base_url", "output", "project_id"}
_KEY_VALUES: dict[str, set[str]] = {
    "mode": {"auto", "remote", "local"},
    "output": {"human", "json"},
}


def _check_key(key: str) -> None:
    if key not in _VALID_KEYS:
        raise typer.BadParameter(
            f"Unknown key: {key!r}. Valid: {', '.join(sorted(_VALID_KEYS))}"
        )


def _check_value(key: str, value: str) -> None:
    allowed = _KEY_VALUES.get(key)
    if allowed is not None and value not in allowed:
        raise typer.BadParameter(
            f"Invalid value for {key!r}: {value!r}. "
            f"Valid: {', '.join(sorted(allowed))}"
        )


@config_app.command("init")
@handle_errors
def config_init(ctx: typer.Context) -> None:
    """Create the default config file at ~/.config/bioinfoflow/cli.toml."""
    cli_ctx, r = unpack_ctx(ctx)
    store = ConfigStore()
    store.init()
    if r.is_json:
        r.emit_data({"path": str(store.path)})
    else:
        cli_ctx.console.print(f"[green]Config created:[/green] {store.path}")


@config_app.command("set")
@handle_errors
def config_set(
    ctx: typer.Context,
    key: str = typer.Argument(help="Config key to set"),
    value: str = typer.Argument(help="Value to set"),
) -> None:
    """Set a config value."""
    _check_key(key)
    _check_value(key, value)
    cli_ctx, r = unpack_ctx(ctx)
    store = ConfigStore()
    store.set(key, value)
    if r.is_json:
        r.emit_data({key: value})
    else:
        cli_ctx.console.print(f"[green]{key}[/green] = {value}")


@config_app.command("get")
@handle_errors
def config_get(
    ctx: typer.Context,
    key: str = typer.Argument(help="Config key to read"),
) -> None:
    """Get a config value."""
    _check_key(key)
    cli_ctx, r = unpack_ctx(ctx)
    store = ConfigStore()
    value = store.get(key)
    if r.is_json:
        r.emit_data({key: value})
        return
    if value is None:
        cli_ctx.console.print(f"[dim]{key} is not set[/dim]")
    else:
        cli_ctx.console.print(f"[bold]{key}[/bold] = {value}")


@config_app.command("unset")
@handle_errors
def config_unset(
    ctx: typer.Context,
    key: str = typer.Argument(help="Config key to remove"),
) -> None:
    """Remove a config value."""
    _check_key(key)
    cli_ctx, r = unpack_ctx(ctx)
    store = ConfigStore()
    removed = store.unset(key)
    if r.is_json:
        r.emit_data({"key": key, "removed": removed})
        return
    if removed:
        cli_ctx.console.print(f"[green]Unset[/green] {key}")
    else:
        cli_ctx.console.print(f"[dim]{key} was not set[/dim]")


@config_app.command("show")
@handle_errors
def config_show(ctx: typer.Context) -> None:
    """Show all config values."""
    cli_ctx, r = unpack_ctx(ctx)
    store = ConfigStore()
    data = store.load()
    if r.is_json:
        r.emit_data(data)
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
@handle_errors
def config_use_project(
    ctx: typer.Context,
    project_id: str = typer.Argument(help="Project ID to set as default"),
) -> None:
    """Set the default project for all commands."""
    cli_ctx, r = unpack_ctx(ctx)
    store = ConfigStore()
    store.set("project_id", project_id)
    if r.is_json:
        r.emit_data({"project_id": project_id})
    else:
        cli_ctx.console.print(f"[green]Default project set:[/green] {project_id}")
