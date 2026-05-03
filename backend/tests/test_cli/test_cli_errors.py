"""Tests for the handle_errors decorator and error exit codes."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import AsyncMock

import click
import pytest
import typer
from rich.console import Console

from app.cli.client import ApiClient, ApiError, ConnectionFailed
from app.cli.context import CliContext
from app.cli.errors import (
    EXIT_BACKEND,
    EXIT_CONNECTION,
    EXIT_GENERAL,
    EXIT_OK,
    EXIT_USER_INPUT,
    handle_errors,
)
from app.cli.jsonio import SpecError


class TestHandleErrors:
    def test_api_error_gives_exit_3(self) -> None:
        @handle_errors
        def _fn():
            raise ApiError(code="NOT_FOUND", message="Not found", status_code=404)

        with pytest.raises(typer.Exit) as exc_info:
            _fn()
        assert exc_info.value.exit_code == EXIT_BACKEND

    def test_connection_failed_gives_exit_4(self) -> None:
        @handle_errors
        def _fn():
            raise ConnectionFailed("refused")

        with pytest.raises(typer.Exit) as exc_info:
            _fn()
        assert exc_info.value.exit_code == EXIT_CONNECTION

    def test_spec_error_gives_exit_2(self) -> None:
        @handle_errors
        def _fn():
            raise SpecError("bad JSON")

        with pytest.raises(typer.Exit) as exc_info:
            _fn()
        assert exc_info.value.exit_code == EXIT_USER_INPUT

    def test_keyboard_interrupt_gives_exit_0(self) -> None:
        @handle_errors
        def _fn():
            raise KeyboardInterrupt()

        with pytest.raises(typer.Exit) as exc_info:
            _fn()
        assert exc_info.value.exit_code == EXIT_OK

    def test_typer_exit_propagates(self) -> None:
        @handle_errors
        def _fn():
            raise typer.Exit(42)

        with pytest.raises(typer.Exit) as exc_info:
            _fn()
        assert exc_info.value.exit_code == 42

    def test_typer_abort_gives_exit_0(self) -> None:
        @handle_errors
        def _fn():
            raise typer.Abort()

        with pytest.raises(typer.Exit) as exc_info:
            _fn()
        assert exc_info.value.exit_code == EXIT_OK

    def test_unexpected_error_gives_exit_1(self) -> None:
        @handle_errors
        def _fn():
            raise RuntimeError("oops")

        with pytest.raises(typer.Exit) as exc_info:
            _fn()
        assert exc_info.value.exit_code == EXIT_GENERAL

    def test_no_error_returns_normally(self) -> None:
        @handle_errors
        def _fn():
            return 42

        assert _fn() == 42

    def test_bad_parameter_propagates_to_click(self) -> None:
        """BadParameter must NOT be caught as a generic Exception — Click
        needs to handle it natively to produce the standard usage-error
        output and exit code 2."""
        import click

        @handle_errors
        def _fn():
            raise typer.BadParameter("nope")

        with pytest.raises(click.exceptions.BadParameter):
            _fn()

    def test_click_usage_error_propagates(self) -> None:
        import click

        @handle_errors
        def _fn():
            raise click.UsageError("bad usage")

        with pytest.raises(click.exceptions.UsageError):
            _fn()


def _ctx_with_mode(output_mode: str) -> typer.Context:
    """Build a typer.Context with a CliContext attached in the given mode."""
    mock_client = AsyncMock(spec=ApiClient)
    mock_client.close = AsyncMock()
    cli_ctx = CliContext(
        client=mock_client,
        output_mode=output_mode,  # type: ignore[arg-type]
        project_id=None,
        verbose=False,
        console=Console(file=StringIO(), no_color=True),
    )
    click_ctx = click.Context(click.Command("test"))
    typer_ctx = typer.Context(click_ctx.command, parent=click_ctx.parent)
    typer_ctx.obj = cli_ctx
    return typer_ctx


class TestErrorEnvelope:
    """JSON mode emits a parseable error envelope on stderr."""

    def test_json_mode_api_error_envelope(self, capsys) -> None:
        ctx = _ctx_with_mode("json")

        @handle_errors
        def _cmd(ctx) -> None:
            raise ApiError(code="NOT_FOUND", message="missing", status_code=404)

        with pytest.raises(typer.Exit):
            _cmd(ctx)
        captured = capsys.readouterr()
        parsed = json.loads(captured.err)
        assert parsed["success"] is False
        assert parsed["error"]["code"] == "NOT_FOUND"
        assert parsed["error"]["message"] == "missing"
        assert parsed["error"]["status_code"] == 404

    def test_json_mode_connection_failed_envelope(self, capsys) -> None:
        ctx = _ctx_with_mode("json")

        @handle_errors
        def _cmd(ctx) -> None:
            raise ConnectionFailed("refused")

        with pytest.raises(typer.Exit):
            _cmd(ctx)
        captured = capsys.readouterr()
        parsed = json.loads(captured.err)
        assert parsed["success"] is False
        assert parsed["error"]["code"] == "CONNECTION_FAILED"
        assert "refused" in parsed["error"]["message"]

    def test_human_mode_plain_text_error(self, capsys) -> None:
        ctx = _ctx_with_mode("human")

        @handle_errors
        def _cmd(ctx) -> None:
            raise ApiError(code="X", message="m", status_code=500)

        with pytest.raises(typer.Exit):
            _cmd(ctx)
        captured = capsys.readouterr()
        # Human mode should NOT be JSON-parseable; assert prefix format.
        assert "[X]" in captured.err
        with pytest.raises(json.JSONDecodeError):
            json.loads(captured.err)


class TestConnectionHint:
    def test_includes_local_mode_hint(self, capsys) -> None:
        ctx = _ctx_with_mode("human")

        @handle_errors
        def _cmd(ctx) -> None:
            raise ConnectionFailed("connect refused")

        with pytest.raises(typer.Exit):
            _cmd(ctx)
        captured = capsys.readouterr()
        assert "--mode local" in captured.err
