"""Tests for client and transport layers — unit tests for parsing and error handling."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.cli.client import ApiClient, ApiError, ConnectionFailed, SSEEvent
from app.cli.context import CliContext
from app.cli.transport import RemoteTransport

# Intentionally a mock URL for unit tests — no real server runs on this port.
# Used only to construct transport objects; all HTTP calls are mocked.
TEST_BASE_URL = "http://localhost:9999/api/v1"


class TestCliContextRunner:
    def test_reuses_runner_and_closes_client(self) -> None:
        close_calls: list[int] = []
        run_loops: list[int] = []

        class StubClient:
            async def close(self) -> None:
                import asyncio

                close_calls.append(id(asyncio.get_running_loop()))

        async def current_loop_id() -> int:
            import asyncio

            return id(asyncio.get_running_loop())

        ctx = CliContext(
            client=StubClient(),
            output_mode="human",
            project_id=None,
            verbose=False,
            console=SimpleNamespace(),
        )

        run_loops.append(ctx.run(current_loop_id()))
        run_loops.append(ctx.run(current_loop_id()))
        ctx.close()

        assert run_loops[0] == run_loops[1]
        assert close_calls == [run_loops[0]]


class TestApiResponseParsing:
    """Test ApiClient._parse static method directly."""

    def test_parses_success_envelope(self) -> None:
        resp = httpx.Response(
            200,
            json={
                "success": True,
                "data": {"id": "1"},
                "meta": {"request_id": "r1", "timestamp": "t"},
            },
        )
        result = ApiClient._parse(resp)
        assert result.success is True
        assert result.data == {"id": "1"}
        assert result.status_code == 200

    def test_parses_204_no_content(self) -> None:
        resp = httpx.Response(204)
        result = ApiClient._parse(resp)
        assert result.success is True
        assert result.data is None
        assert result.status_code == 204

    def test_error_envelope_raises_api_error(self) -> None:
        resp = httpx.Response(
            404,
            json={
                "success": False,
                "error": {"code": "NOT_FOUND", "message": "Not found"},
                "meta": {"request_id": "r1", "timestamp": "t"},
            },
        )
        with pytest.raises(ApiError) as exc_info:
            ApiClient._parse(resp)
        assert exc_info.value.code == "NOT_FOUND"
        assert exc_info.value.status_code == 404

    def test_non_json_error_raises(self) -> None:
        resp = httpx.Response(500, text="Internal Server Error")
        with pytest.raises(ApiError) as exc_info:
            ApiClient._parse(resp)
        assert exc_info.value.status_code == 500

    def test_non_json_success_returns_text(self) -> None:
        resp = httpx.Response(200, text="OK plain text")
        result = ApiClient._parse(resp)
        assert result.success is True
        assert result.data == "OK plain text"

    def test_success_without_explicit_flag(self) -> None:
        resp = httpx.Response(200, json={"data": [1, 2, 3]})
        result = ApiClient._parse(resp)
        assert result.success is True
        assert result.data == [1, 2, 3]

    def test_pagination_in_meta(self) -> None:
        resp = httpx.Response(
            200,
            json={
                "success": True,
                "data": [],
                "meta": {
                    "request_id": "r1",
                    "timestamp": "t",
                    "pagination": {"limit": 20, "has_more": True, "next_cursor": "abc"},
                },
            },
        )
        result = ApiClient._parse(resp)
        assert result.meta["pagination"]["has_more"] is True
        assert result.meta["pagination"]["next_cursor"] == "abc"


class TestRemoteTransport:
    @pytest.mark.asyncio
    async def test_creates_client(self) -> None:
        transport = RemoteTransport(TEST_BASE_URL)
        client = await transport.get_client()
        assert isinstance(client, httpx.AsyncClient)
        await transport.close()

    @pytest.mark.asyncio
    async def test_close_idempotent(self) -> None:
        transport = RemoteTransport(TEST_BASE_URL)
        await transport.get_client()
        await transport.close()
        await transport.close()  # should not raise


class TestApiError:
    def test_api_error_str(self) -> None:
        err = ApiError(code="OOPS", message="Something broke", status_code=400)
        assert str(err) == "Something broke"
        assert err.code == "OOPS"
        assert err.status_code == 400

    def test_connection_failed_str(self) -> None:
        err = ConnectionFailed("refused")
        assert str(err) == "refused"


class TestApiClientHttpVerbs:
    """Test ApiClient HTTP method wrappers using a mock transport."""

    @pytest.fixture
    def mock_transport(self):
        transport = AsyncMock()
        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        transport.get_client.return_value = mock_http_client
        transport.close = AsyncMock()
        return transport, mock_http_client

    @pytest.mark.asyncio
    async def test_get(self, mock_transport) -> None:
        transport, http_client = mock_transport
        http_client.request.return_value = httpx.Response(
            200, json={"success": True, "data": {"x": 1}, "meta": None}
        )
        client = ApiClient(transport)
        result = await client.get("/things", {"limit": 10})
        assert result.success is True
        assert result.data == {"x": 1}
        http_client.request.assert_called_once()
        call_args = http_client.request.call_args
        assert call_args[0][0] == "GET"
        assert call_args[0][1] == "/things"

    @pytest.mark.asyncio
    async def test_post(self, mock_transport) -> None:
        transport, http_client = mock_transport
        http_client.request.return_value = httpx.Response(
            201, json={"success": True, "data": {"id": "new"}, "meta": None}
        )
        client = ApiClient(transport)
        result = await client.post("/things", {"name": "test"})
        assert result.data == {"id": "new"}

    @pytest.mark.asyncio
    async def test_patch(self, mock_transport) -> None:
        transport, http_client = mock_transport
        http_client.request.return_value = httpx.Response(
            200, json={"success": True, "data": {"updated": True}, "meta": None}
        )
        client = ApiClient(transport)
        result = await client.patch("/things/1", {"name": "updated"})
        assert result.data == {"updated": True}

    @pytest.mark.asyncio
    async def test_delete(self, mock_transport) -> None:
        transport, http_client = mock_transport
        http_client.request.return_value = httpx.Response(204)
        client = ApiClient(transport)
        result = await client.delete("/things/1")
        assert result.success is True
        assert result.status_code == 204

    @pytest.mark.asyncio
    async def test_request_connect_error_raises_connection_failed(
        self, mock_transport
    ) -> None:
        transport, http_client = mock_transport
        http_client.request.side_effect = httpx.ConnectError("refused")
        client = ApiClient(transport)
        with pytest.raises(ConnectionFailed):
            await client.get("/health")

    @pytest.mark.asyncio
    async def test_request_timeout_raises_connection_failed(
        self, mock_transport
    ) -> None:
        transport, http_client = mock_transport
        http_client.request.side_effect = httpx.TimeoutException("timed out")
        client = ApiClient(transport)
        with pytest.raises(ConnectionFailed):
            await client.get("/health")

    @pytest.mark.asyncio
    async def test_get_client_connect_error(self) -> None:
        transport = AsyncMock()
        transport.get_client.side_effect = httpx.ConnectError("refused")
        client = ApiClient(transport)
        with pytest.raises(ConnectionFailed):
            await client.get("/test")

    @pytest.mark.asyncio
    async def test_get_client_os_error(self) -> None:
        transport = AsyncMock()
        transport.get_client.side_effect = OSError("socket error")
        client = ApiClient(transport)
        with pytest.raises(ConnectionFailed):
            await client.get("/test")

    @pytest.mark.asyncio
    async def test_close_delegates(self, mock_transport) -> None:
        transport, _ = mock_transport
        client = ApiClient(transport)
        await client.close()
        transport.close.assert_called_once()


class TestApiClientUpload:
    @pytest.mark.asyncio
    async def test_upload_success(self, tmp_path: Path) -> None:
        test_file = tmp_path / "data.csv"
        test_file.write_text("a,b\n1,2\n")

        transport = AsyncMock()
        http_client = AsyncMock(spec=httpx.AsyncClient)
        transport.get_client.return_value = http_client
        http_client.post.return_value = httpx.Response(
            200, json={"success": True, "data": {"file_id": "f1"}, "meta": None}
        )

        client = ApiClient(transport)
        result = await client.upload("/files/upload", test_file, {"project_id": "p1"})
        assert result.data == {"file_id": "f1"}
        http_client.post.assert_called_once()


class TestCliContext:
    def test_close_uses_same_runner_as_command_execution(self) -> None:
        transport = AsyncMock()
        http_client = AsyncMock(spec=httpx.AsyncClient)
        transport.get_client.return_value = http_client
        transport.close = AsyncMock()
        http_client.request.return_value = httpx.Response(
            200, json={"success": True, "data": {"ok": True}, "meta": None}
        )

        cli_ctx = CliContext(
            client=ApiClient(transport),
            output_mode="human",
            project_id=None,
            verbose=False,
            console=SimpleNamespace(print=lambda *args, **kwargs: None),
        )

        try:
            resp = cli_ctx.run(cli_ctx.client.get("/system/health"))
            assert resp.data == {"ok": True}
        finally:
            cli_ctx.close()

        transport.close.assert_awaited_once()


class TestApiClientDownload:
    @pytest.mark.asyncio
    async def test_download_success(self, tmp_path: Path) -> None:
        transport = AsyncMock()
        http_client = AsyncMock(spec=httpx.AsyncClient)
        transport.get_client.return_value = http_client
        http_client.get.return_value = httpx.Response(200, content=b"file contents")

        client = ApiClient(transport)
        dest = tmp_path / "out" / "result.txt"
        result_path = await client.download("/files/download", dest, {"id": "f1"})
        assert result_path == dest
        assert dest.read_text() == "file contents"

    @pytest.mark.asyncio
    async def test_download_error(self, tmp_path: Path) -> None:
        transport = AsyncMock()
        http_client = AsyncMock(spec=httpx.AsyncClient)
        transport.get_client.return_value = http_client
        http_client.get.return_value = httpx.Response(
            404,
            json={
                "success": False,
                "error": {"code": "NOT_FOUND", "message": "No file"},
                "meta": None,
            },
        )

        client = ApiClient(transport)
        dest = tmp_path / "out.txt"
        with pytest.raises(ApiError) as exc_info:
            await client.download("/files/download", dest, {"id": "bad"})
        assert exc_info.value.status_code == 404


class TestRemoteTransportReuse:
    @pytest.mark.asyncio
    async def test_reuses_client(self) -> None:
        transport = RemoteTransport(TEST_BASE_URL)
        client1 = await transport.get_client()
        client2 = await transport.get_client()
        assert client1 is client2
        await transport.close()

    @pytest.mark.asyncio
    async def test_recreates_after_close(self) -> None:
        transport = RemoteTransport(TEST_BASE_URL)
        client1 = await transport.get_client()
        await transport.close()
        client2 = await transport.get_client()
        assert client1 is not client2
        await transport.close()

    @pytest.mark.asyncio
    async def test_close_when_no_client(self) -> None:
        transport = RemoteTransport(TEST_BASE_URL)
        await transport.close()  # no client created yet, should not raise

    @pytest.mark.asyncio
    async def test_localhost_remote_transport_ignores_proxy_env(self) -> None:
        transport = RemoteTransport("http://localhost:8000/api/v1")
        client = await transport.get_client()
        assert client.trust_env is False
        await transport.close()


class TestSSEEvent:
    def test_sse_event_fields(self) -> None:
        event = SSEEvent(id="1", event="run.status", data='{"status": "running"}')
        assert event.id == "1"
        assert event.event == "run.status"
        assert event.data == '{"status": "running"}'
