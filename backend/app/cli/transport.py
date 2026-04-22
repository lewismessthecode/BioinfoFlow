"""Dual-mode HTTP transport — remote, local, or auto-fallback."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

import httpx


class BaseTransport(ABC):
    """Abstract transport providing an httpx.AsyncClient."""

    @abstractmethod
    async def get_client(self) -> httpx.AsyncClient: ...

    @abstractmethod
    async def close(self) -> None: ...


class RemoteTransport(BaseTransport):
    """HTTP transport to a running backend server."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url
        self._client: httpx.AsyncClient | None = None

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(30.0, connect=5.0),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


class LocalTransport(BaseTransport):
    """In-process ASGI transport — no running server needed.

    Imports the FastAPI app, enters its lifespan (DB init, scheduler, etc.),
    and routes requests through httpx.ASGITransport.
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._lifespan_cm: Any = None
        self._app: object | None = None

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            from app.main import app as fastapi_app

            self._app = fastapi_app
            # Enter the app's lifespan so DB/scheduler/seeding run
            self._lifespan_cm = fastapi_app.router.lifespan_context(fastapi_app)
            await self._lifespan_cm.__aenter__()
            try:
                transport = httpx.ASGITransport(app=fastapi_app)  # type: ignore[arg-type]
                self._client = httpx.AsyncClient(
                    transport=transport,
                    base_url="http://local/api/v1",
                )
            except Exception:
                await self._lifespan_cm.__aexit__(None, None, None)
                self._lifespan_cm = None
                raise
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
        if self._lifespan_cm is not None:
            await self._lifespan_cm.__aexit__(None, None, None)
            self._lifespan_cm = None


class AutoTransport(BaseTransport):
    """Try remote first; fall back to local on connection failure only.

    HTTP errors (4xx/5xx) from a reachable remote server are NOT retried
    locally — they represent real API errors.
    """

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url
        self._delegate: BaseTransport | None = None

    async def get_client(self) -> httpx.AsyncClient:
        if self._delegate is not None:
            return await self._delegate.get_client()

        # Probe the remote server
        remote = RemoteTransport(self._base_url)
        try:
            client = await remote.get_client()
            await asyncio.wait_for(client.get("/system/health"), timeout=3.0)
            self._delegate = remote
            return client
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.TimeoutException,
            OSError,
            asyncio.TimeoutError,
        ):
            await remote.close()
            local = LocalTransport()
            self._delegate = local
            return await local.get_client()

    async def close(self) -> None:
        if self._delegate is not None:
            await self._delegate.close()
            self._delegate = None
