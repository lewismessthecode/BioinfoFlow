"""Tests for the handle_errors decorator and error exit codes."""

from __future__ import annotations

import pytest
import typer

from app.cli.client import ApiError, ConnectionFailed
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
