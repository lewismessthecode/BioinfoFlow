"""Shared CLI utilities — error handling decorator, exit codes."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

import typer

from app.cli.client import ApiError, ConnectionFailed
from app.cli.jsonio import SpecError

# -- Exit codes ---------------------------------------------------------------

EXIT_OK = 0
EXIT_GENERAL = 1
EXIT_USER_INPUT = 2
EXIT_BACKEND = 3
EXIT_CONNECTION = 4


def handle_errors(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that catches CLI-specific exceptions and sets exit codes.

    Also ensures the API client is closed when the command finishes,
    regardless of success or failure.
    """

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except ApiError as exc:
            _print_error(exc.message, exc.code)
            raise typer.Exit(EXIT_BACKEND) from exc
        except ConnectionFailed as exc:
            _print_error(str(exc), "CONNECTION_FAILED")
            raise typer.Exit(EXIT_CONNECTION) from exc
        except SpecError as exc:
            _print_error(str(exc), "SPEC_ERROR")
            raise typer.Exit(EXIT_USER_INPUT) from exc
        except KeyboardInterrupt:
            raise typer.Exit(EXIT_OK)
        except typer.Exit:
            raise
        except typer.Abort:
            raise typer.Exit(EXIT_OK)
        except Exception as exc:
            _print_error(str(exc), "UNEXPECTED")
            raise typer.Exit(EXIT_GENERAL) from exc
        finally:
            _close_client(args, kwargs)

    return wrapper


def _close_client(args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    """Find a typer.Context in the args and close its API client."""
    ctx = kwargs.get("ctx")
    if ctx is None:
        for arg in args:
            if isinstance(arg, typer.Context):
                ctx = arg
                break
    if ctx is None or not isinstance(ctx, typer.Context):
        return
    cli_ctx = getattr(ctx, "obj", None)
    if cli_ctx is None:
        return
    client = getattr(cli_ctx, "client", None)
    if client is None:
        return
    try:
        cli_ctx.close()
    except Exception as exc:
        verbose = getattr(cli_ctx, "verbose", False)
        if verbose:
            console = getattr(cli_ctx, "console", None)
            if console:
                console.print(f"[dim]Warning: client close: {exc}[/dim]")


def _print_error(message: str, code: str) -> None:
    typer.echo(f"[{code}] {message}", err=True)
