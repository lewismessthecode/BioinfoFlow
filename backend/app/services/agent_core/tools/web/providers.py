from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from duckduckgo_search import DDGS


class WebSearchProvider(Protocol):
    async def search(self, query: str, max_results: int) -> list[Mapping[str, Any]]: ...


class DuckDuckGoSearchProvider:
    def __init__(
        self,
        *,
        client_factory: Callable[[], Any] = DDGS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client_factory = client_factory
        self._sleep = sleep

    async def search(self, query: str, max_results: int) -> list[Mapping[str, Any]]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return await asyncio.to_thread(self._search_once, query, max_results)
            except Exception as exc:  # noqa: BLE001 - provider failures are retried
                last_error = exc
                if attempt == 0:
                    await self._sleep(0.5)
        assert last_error is not None
        raise last_error

    def _search_once(self, query: str, max_results: int) -> list[Mapping[str, Any]]:
        with self._client_factory() as client:
            return list(client.text(query, max_results=max_results))


__all__ = ["DuckDuckGoSearchProvider", "WebSearchProvider"]
