"""HTTP transport for the Bioinfoflow CLI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from urllib.parse import urlparse

import httpx


class BaseTransport(ABC):
    """Abstract transport providing an httpx.AsyncClient."""

    @abstractmethod
    async def get_client(self) -> httpx.AsyncClient: ...

    @abstractmethod
    async def close(self) -> None: ...


class RemoteTransport(BaseTransport):
    """HTTP transport to a running backend server."""

    def __init__(self, base_url: str, *, bearer_token: str | None = None) -> None:
        self._base_url = base_url
        self._bearer_token = bearer_token
        self._client: httpx.AsyncClient | None = None

    def __repr__(self) -> str:
        return f"RemoteTransport(base_url={self._base_url!r})"

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = (
                {"Authorization": f"Bearer {self._bearer_token}"}
                if self._bearer_token
                else None
            )
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=httpx.Timeout(30.0, connect=5.0),
                trust_env=not _is_loopback_url(self._base_url),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


def _is_loopback_url(url: str) -> bool:
    host = urlparse(url).hostname
    return host in {"localhost", "127.0.0.1", "::1"}
