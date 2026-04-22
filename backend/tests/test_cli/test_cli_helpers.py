"""Tests for api_helpers wrappers and shared helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.cli.client import ApiClient
from app.cli.context import CliContext
from tests.test_cli.conftest import make_envelope


class TestApiHelpers:
    """Direct tests for the thin async wrappers in api_helpers.py.

    Note: close() is no longer called per-helper — it is handled by the
    handle_errors decorator.  These tests verify the helpers delegate
    correctly to the client methods.
    """

    @pytest.fixture
    def ctx(self) -> CliContext:
        from rich.console import Console

        mock_client = AsyncMock(spec=ApiClient)
        mock_client.close = AsyncMock()
        mock_client.get = AsyncMock(return_value=make_envelope({"items": []}))
        mock_client.post = AsyncMock(return_value=make_envelope({"id": "new"}))
        mock_client.patch = AsyncMock(return_value=make_envelope({"updated": True}))
        mock_client.delete = AsyncMock(return_value=make_envelope(None))
        mock_client.upload = AsyncMock(return_value=make_envelope({"file_id": "f1"}))
        mock_client.download = AsyncMock(return_value=Path("/tmp/out.txt"))
        return CliContext(
            client=mock_client,
            output_mode="human",
            project_id="p-1",
            verbose=False,
            console=Console(),
        )

    @pytest.mark.asyncio
    async def test_api_get(self, ctx: CliContext) -> None:
        from app.cli.api_helpers import api_get

        result = await api_get(ctx, "/things", {"limit": 10})
        assert result.success is True
        ctx.client.get.assert_called_once_with("/things", {"limit": 10})

    @pytest.mark.asyncio
    async def test_api_post(self, ctx: CliContext) -> None:
        from app.cli.api_helpers import api_post

        result = await api_post(ctx, "/things", {"name": "test"})
        assert result.data == {"id": "new"}
        ctx.client.post.assert_called_once_with("/things", {"name": "test"})

    @pytest.mark.asyncio
    async def test_api_patch(self, ctx: CliContext) -> None:
        from app.cli.api_helpers import api_patch

        result = await api_patch(ctx, "/things/1", {"name": "updated"})
        assert result.data == {"updated": True}
        ctx.client.patch.assert_called_once()

    @pytest.mark.asyncio
    async def test_api_delete(self, ctx: CliContext) -> None:
        from app.cli.api_helpers import api_delete

        await api_delete(ctx, "/things/1")
        ctx.client.delete.assert_called_once_with("/things/1", None)

    @pytest.mark.asyncio
    async def test_api_upload(self, ctx: CliContext) -> None:
        from app.cli.api_helpers import api_upload

        result = await api_upload(
            ctx, "/files/upload", Path("/tmp/f.csv"), {"project_id": "p1"}
        )
        assert result.data == {"file_id": "f1"}
        ctx.client.upload.assert_called_once()

    @pytest.mark.asyncio
    async def test_api_download(self, ctx: CliContext) -> None:
        from app.cli.api_helpers import api_download

        result = await api_download(
            ctx, "/files/download", Path("/tmp/out.txt"), {"id": "f1"}
        )
        assert result == Path("/tmp/out.txt")
        ctx.client.download.assert_called_once()

    @pytest.mark.asyncio
    async def test_helpers_do_not_close_client(self, ctx: CliContext) -> None:
        """Helpers no longer close the client — that's the decorator's job."""
        from app.cli.api_helpers import api_get

        await api_get(ctx, "/things")
        ctx.client.close.assert_not_called()


class TestHandleErrorsClientClose:
    """Verify handle_errors closes via CliContext in its finally block."""

    def test_close_on_success(self) -> None:
        import typer
        import click
        from rich.console import Console
        from app.cli.errors import handle_errors

        mock_client = AsyncMock(spec=ApiClient)
        mock_client.close = AsyncMock()
        cli_ctx = CliContext(
            client=mock_client,
            output_mode="human",
            project_id=None,
            verbose=False,
            console=Console(file=SimpleNamespace(write=lambda *_args, **_kwargs: None)),
        )

        @handle_errors
        def _cmd(ctx) -> str:
            cli_ctx.run(_noop())
            return "ok"

        async def _noop() -> None:
            return None

        click_ctx = click.Context(click.Command("test"))
        typer_ctx = typer.Context(click_ctx.command, parent=click_ctx.parent)
        typer_ctx.obj = cli_ctx

        result = _cmd(typer_ctx)
        assert result == "ok"
        mock_client.close.assert_awaited_once()

    def test_close_on_error(self) -> None:
        import typer
        import click
        from rich.console import Console
        from app.cli.errors import handle_errors
        from app.cli.client import ApiError

        mock_client = AsyncMock(spec=ApiClient)
        mock_client.close = AsyncMock()
        cli_ctx = CliContext(
            client=mock_client,
            output_mode="human",
            project_id=None,
            verbose=False,
            console=Console(file=SimpleNamespace(write=lambda *_args, **_kwargs: None)),
        )

        click_ctx = click.Context(click.Command("test"))
        typer_ctx = typer.Context(click_ctx.command, parent=click_ctx.parent)
        typer_ctx.obj = cli_ctx

        @handle_errors
        def _cmd(ctx) -> None:
            cli_ctx.run(_noop())
            raise ApiError(code="ERR", message="fail", status_code=500)

        async def _noop() -> None:
            return None

        with pytest.raises(typer.Exit):
            _cmd(typer_ctx)
        mock_client.close.assert_awaited_once()


class TestSharedHelpers:
    """Tests for helpers.unpack_ctx and helpers.require_project."""

    def test_unpack_ctx(self) -> None:
        import click
        import typer
        from rich.console import Console
        from app.cli.helpers import unpack_ctx

        cli_ctx = CliContext(
            client=AsyncMock(spec=ApiClient),
            output_mode="json",
            project_id="p-1",
            verbose=False,
            console=Console(),
        )
        click_ctx = click.Context(click.Command("test"))
        ctx = typer.Context(click_ctx.command, parent=click_ctx.parent)
        ctx.obj = cli_ctx
        result_ctx, renderer = unpack_ctx(ctx)
        assert result_ctx is cli_ctx
        assert renderer.is_json is True

    def test_require_project_with_explicit(self) -> None:
        from app.cli.helpers import require_project

        cli_ctx = CliContext(
            client=AsyncMock(spec=ApiClient),
            output_mode="human",
            project_id="default-p",
            verbose=False,
            console=AsyncMock(),
        )
        assert require_project(cli_ctx, "explicit-p") == "explicit-p"

    def test_require_project_falls_back_to_default(self) -> None:
        from app.cli.helpers import require_project

        cli_ctx = CliContext(
            client=AsyncMock(spec=ApiClient),
            output_mode="human",
            project_id="default-p",
            verbose=False,
            console=AsyncMock(),
        )
        assert require_project(cli_ctx, None) == "default-p"

    def test_require_project_raises_when_missing(self) -> None:
        import typer
        from app.cli.helpers import require_project

        cli_ctx = CliContext(
            client=AsyncMock(spec=ApiClient),
            output_mode="human",
            project_id=None,
            verbose=False,
            console=AsyncMock(),
        )
        with pytest.raises(typer.BadParameter):
            require_project(cli_ctx, None)
