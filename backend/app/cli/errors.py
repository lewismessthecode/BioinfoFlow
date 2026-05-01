"""Shared CLI utilities — error handling decorator, exit codes."""

from __future__ import annotations

import json
import sys
from functools import wraps
from typing import Any, Callable

import typer

from app.cli.client import ApiError, ConnectionFailed
from app.cli.context import CliContext
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
        cli_ctx = _find_cli_ctx(args, kwargs)
        try:
            return fn(*args, **kwargs)
        except ApiError as exc:
            _emit_error(cli_ctx, exc.message, exc.code, status=exc.status_code)
            raise typer.Exit(EXIT_BACKEND) from exc
        except ConnectionFailed as exc:
            _emit_error(
                cli_ctx,
                _connection_hint(str(exc)),
                "CONNECTION_FAILED",
            )
            raise typer.Exit(EXIT_CONNECTION) from exc
        except SpecError as exc:
            _emit_error(cli_ctx, str(exc), "SPEC_ERROR")
            raise typer.Exit(EXIT_USER_INPUT) from exc
        except KeyboardInterrupt:
            raise typer.Exit(EXIT_OK)
        except typer.Exit:
            raise
        except typer.Abort:
            raise typer.Exit(EXIT_OK)
        except Exception as exc:
            _emit_error(cli_ctx, str(exc), "UNEXPECTED")
            raise typer.Exit(EXIT_GENERAL) from exc
        finally:
            _close_client(cli_ctx)

    return wrapper


def _find_cli_ctx(args: tuple[Any, ...], kwargs: dict[str, Any]) -> CliContext | None:
    """Locate the CliContext attached to a typer.Context arg, if any."""
    ctx = kwargs.get("ctx")
    if ctx is None:
        for arg in args:
            if isinstance(arg, typer.Context):
                ctx = arg
                break
    if not isinstance(ctx, typer.Context):
        return None
    cli_ctx = getattr(ctx, "obj", None)
    return cli_ctx if isinstance(cli_ctx, CliContext) else None


def _close_client(cli_ctx: CliContext | None) -> None:
    if cli_ctx is None or getattr(cli_ctx, "client", None) is None:
        return
    try:
        cli_ctx.close()
    except Exception as exc:
        if cli_ctx.verbose and cli_ctx.console:
            cli_ctx.console.print(f"[dim]Warning: client close: {exc}[/dim]")


def _emit_error(
    cli_ctx: CliContext | None,
    message: str,
    code: str,
    *,
    status: int | None = None,
) -> None:
    """Print a structured error.

    JSON mode: emit a `{success, error, ...}` envelope on stderr so machine
    consumers can parse it (matches the success envelope shape).
    Human mode: prefix with `[CODE]` on stderr.
    """
    if cli_ctx is not None and cli_ctx.output_mode == "json":
        envelope: dict[str, Any] = {
            "success": False,
            "error": {"code": code, "message": message},
        }
        if status is not None:
            envelope["error"]["status_code"] = status
        sys.stderr.write(json.dumps(envelope, default=str) + "\n")
        sys.stderr.flush()
        return
    typer.echo(f"[{code}] {message}", err=True)


def _connection_hint(detail: str) -> str:
    """Append a friendly hint about transport modes to a connection error."""
    base = detail or "Cannot reach the backend."
    return (
        f"{base}\n"
        "Hint: start the backend (uvicorn app.main:app), or run with "
        "--mode local to use the in-process ASGI transport."
    )
