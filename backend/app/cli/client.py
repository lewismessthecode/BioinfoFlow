"""API client — wraps transport with envelope parsing and error handling."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator
from uuid import uuid4

import httpx

from app.cli.transport import BaseTransport


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApiResponse:
    """Parsed API envelope."""

    success: bool
    data: Any
    error: dict[str, Any] | None
    meta: dict[str, Any] | None
    status_code: int


@dataclass(frozen=True)
class SSEEvent:
    """A single Server-Sent Event."""

    id: str | None
    event: str
    data: str


class ApiError(Exception):
    """Structured error from the API."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ConnectionFailed(Exception):
    """Transport-level connection failure."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ApiClient:
    """High-level API client with envelope parsing."""

    def __init__(self, transport: BaseTransport) -> None:
        self._transport = transport

    async def close(self) -> None:
        await self._transport.close()

    # -- HTTP verbs ----------------------------------------------------------

    async def get(self, path: str, params: dict[str, Any] | None = None) -> ApiResponse:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json: dict[str, Any] | None = None) -> ApiResponse:
        return await self._request("POST", path, json=json)

    async def patch(self, path: str, json: dict[str, Any] | None = None) -> ApiResponse:
        return await self._request("PATCH", path, json=json)

    async def delete(
        self, path: str, params: dict[str, Any] | None = None
    ) -> ApiResponse:
        return await self._request("DELETE", path, params=params)

    async def upload(
        self,
        path: str,
        file_path: Path,
        fields: dict[str, str] | None = None,
    ) -> ApiResponse:
        client = await self._get_client()
        data = dict(fields) if fields else {}
        file_bytes = await asyncio.to_thread(file_path.read_bytes)
        files = {"file": (file_path.name, file_bytes)}
        resp = await client.post(
            path,
            data=data,
            files=files,
            headers={"X-Request-ID": str(uuid4())},
        )
        return self._parse(resp)

    async def download(
        self,
        path: str,
        dest: Path,
        params: dict[str, Any] | None = None,
    ) -> Path:
        client = await self._get_client()
        resp = await client.get(
            path,
            params=params,
            headers={"X-Request-ID": str(uuid4())},
        )
        if resp.status_code >= 400:
            parsed = self._parse(resp)
            err = parsed.error or {}
            raise ApiError(
                code=err.get("code", "DOWNLOAD_ERROR"),
                message=err.get("message", f"Download failed: {resp.status_code}"),
                status_code=resp.status_code,
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        return dest

    async def stream_sse(
        self, path: str, params: dict[str, Any] | None = None
    ) -> AsyncIterator[SSEEvent]:
        """Stream Server-Sent Events from the API."""
        from httpx_sse import aconnect_sse

        client = await self._get_client()
        async with aconnect_sse(
            client, "GET", path, params=params or {}
        ) as event_source:
            async for sse in event_source.aiter_sse():
                if sse.event == "ping" or not sse.data:
                    continue
                yield SSEEvent(id=sse.id, event=sse.event, data=sse.data)

    # -- Internal ------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        try:
            return await self._transport.get_client()
        except (httpx.ConnectError, OSError) as exc:
            raise ConnectionFailed(str(exc)) from exc

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> ApiResponse:
        client = await self._get_client()
        try:
            resp = await client.request(
                method,
                path,
                params=params,
                json=json,
                headers={"X-Request-ID": str(uuid4())},
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ConnectionFailed(str(exc)) from exc
        return self._parse(resp)

    @staticmethod
    def _parse(resp: httpx.Response) -> ApiResponse:
        """Parse API envelope from response."""
        if resp.status_code == 204:
            return ApiResponse(
                success=True, data=None, error=None, meta=None, status_code=204
            )

        try:
            body = resp.json()
        except Exception:
            if resp.status_code >= 400:
                raise ApiError(
                    code="UNKNOWN",
                    message=resp.text or f"HTTP {resp.status_code}",
                    status_code=resp.status_code,
                )
            return ApiResponse(
                success=True,
                data=resp.text,
                error=None,
                meta=None,
                status_code=resp.status_code,
            )

        success = body.get("success", resp.status_code < 400)
        data = body.get("data")
        error = body.get("error")
        meta = body.get("meta")

        if not success and error:
            raise ApiError(
                code=error.get("code", "UNKNOWN"),
                message=error.get("message", "Unknown error"),
                status_code=resp.status_code,
            )

        return ApiResponse(
            success=success,
            data=data,
            error=error,
            meta=meta,
            status_code=resp.status_code,
        )
