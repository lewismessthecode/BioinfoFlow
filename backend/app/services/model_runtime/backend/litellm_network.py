from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
from aiohttp import ClientRequest, ClientResponse, ClientSession, TCPConnector
from aiohttp.abc import AbstractResolver, ResolveResult
from litellm.llms.custom_httpx.aiohttp_transport import LiteLLMAiohttpTransport
from litellm.llms.custom_httpx.http_handler import AsyncHTTPHandler
from yarl import URL

from app.services.model_runtime.network import (
    ensure_public_network_host,
    resolve_public_address_infos,
)
from app.services.model_runtime.contracts import NetworkAccessPolicy


class PublicNetworkResolver(AbstractResolver):
    """Resolve once, validate every answer, and return the exact connect targets."""

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: int = socket.AF_INET,
    ) -> list[ResolveResult]:
        addr_infos = await asyncio.to_thread(
            resolve_public_address_infos,
            host,
            port,
            family=family,
        )
        results: list[ResolveResult] = []
        seen: set[tuple[int, int, str, int]] = set()
        for resolved_family, _type, proto, _canonname, sockaddr in addr_infos:
            address = str(sockaddr[0])
            resolved_port = int(sockaddr[1]) if len(sockaddr) > 1 else port
            key = (resolved_family, proto, address, resolved_port)
            if key in seen:
                continue
            seen.add(key)
            results.append(
                ResolveResult(
                    hostname=host,
                    host=address,
                    port=resolved_port,
                    family=resolved_family,
                    proto=proto,
                    flags=0,
                )
            )
        return results

    async def close(self) -> None:
        return None


def ensure_public_request_url(url: URL) -> None:
    if url.scheme not in {"http", "https"}:
        ensure_public_network_host("")
    ensure_public_network_host(url.host or "")


async def public_network_middleware(
    request: ClientRequest,
    handler: Callable[[ClientRequest], Awaitable[ClientResponse]],
) -> ClientResponse:
    # Client middleware runs for the original request and every redirect. It
    # closes the IP-literal redirect gap that aiohttp intentionally skips in its
    # DNS resolver fast path.
    ensure_public_request_url(request.url)
    return await handler(request)


def _public_network_session() -> ClientSession:
    connector = TCPConnector(
        resolver=PublicNetworkResolver(),
        use_dns_cache=False,
    )
    return ClientSession(
        connector=connector,
        connector_owner=True,
        trust_env=False,
        middlewares=(public_network_middleware,),
    )


class PublicNetworkAiohttpTransport(LiteLLMAiohttpTransport):
    """LiteLLM transport that never delegates public-only requests to a proxy."""

    async def _get_proxy_settings(self, request: httpx.Request) -> None:
        del request
        return None


class PublicNetworkHTTPHandler(AsyncHTTPHandler):
    """LiteLLM HTTP handler confined to public connect and redirect targets."""

    network_access = "public_only"

    def __init__(self, *, timeout: float | httpx.Timeout | None = None) -> None:
        self._policy_session = _public_network_session()
        self._closed = False
        super().__init__(timeout=timeout)

    @property
    def closed(self) -> bool:
        return self._closed

    def create_client(
        self,
        timeout: float | httpx.Timeout | None,
        event_hooks: Any,
        ssl_verify: Any = None,
        shared_session: ClientSession | None = None,
    ) -> httpx.AsyncClient:
        del ssl_verify, shared_session
        transport = PublicNetworkAiohttpTransport(
            client=self._policy_session,
            owns_session=False,
        )
        return httpx.AsyncClient(
            transport=transport,
            event_hooks=event_hooks,
            timeout=timeout or httpx.Timeout(600.0, connect=5.0),
            follow_redirects=True,
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await super().close()
        await self._policy_session.close()


@asynccontextmanager
async def network_policy_http_client(
    *,
    network_access: NetworkAccessPolicy,
    timeout: float,
) -> AsyncIterator[AsyncHTTPHandler | httpx.AsyncClient]:
    """Yield an HTTP client whose transport enforces the resolved policy."""
    if network_access == "public_only":
        client = PublicNetworkHTTPHandler(timeout=timeout)
        try:
            yield client
        finally:
            await client.close()
        return
    async with httpx.AsyncClient(timeout=timeout) as client:
        yield client


__all__ = [
    "PublicNetworkAiohttpTransport",
    "PublicNetworkHTTPHandler",
    "PublicNetworkResolver",
    "ensure_public_request_url",
    "network_policy_http_client",
    "public_network_middleware",
]
