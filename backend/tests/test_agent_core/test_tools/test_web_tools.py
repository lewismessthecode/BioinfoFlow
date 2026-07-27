from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from app.services.agent_core.tools.specs import AgentToolContext
from app.services.agent_core.tools import build_default_tool_registry
from app.services.agent_core.tools.web.providers import DuckDuckGoSearchProvider
from app.services.agent_core.tools.web.resources import SearchWebTool
from app.services.agent_core.tools.web.public_url_policy import PublicUrl
from app.utils.exceptions import PermissionDeniedError


class _FakeProvider:
    def __init__(self, results: list[dict[str, Any]] | None = None) -> None:
        self.results = results or []
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        self.calls.append((query, max_results))
        return self.results


def _context() -> AgentToolContext:
    return cast(AgentToolContext, None)


def test_default_registry_exposes_search_without_legacy_fetch() -> None:
    registry = build_default_tool_registry()

    assert "web.search" in registry.names()
    assert "web.fetch" not in registry.names()


@pytest.mark.asyncio
async def test_search_tool_normalizes_provider_results_and_applies_limit() -> None:
    provider = _FakeProvider(
        [
            {"title": " One ", "href": "https://one.example/a", "body": " First "},
            {"title": None, "url": "https://two.example/b", "snippet": None},
            {"title": "three", "url": "https://three.example/c", "snippet": "third"},
        ]
    )

    async def allow(url: str) -> PublicUrl:
        return PublicUrl(url=url, host=url.split("/", 3)[2])

    result = await SearchWebTool(provider=provider, url_validator=allow).run(
        {"query": "bioinformatics", "max_results": 2}, _context()
    )

    assert provider.calls == [("bioinformatics", 2)]
    assert result == {
        "results": [
            {
                "title": "One",
                "url": "https://one.example/a",
                "snippet": "First",
            },
            {"title": "", "url": "https://two.example/b", "snippet": ""},
        ]
    }


@pytest.mark.asyncio
async def test_search_tool_filters_unsafe_urls_without_failing_whole_search() -> None:
    provider = _FakeProvider(
        [
            {"title": "private", "url": "http://127.0.0.1/admin", "snippet": "no"},
            {"title": "public", "url": "https://example.com", "snippet": "yes"},
        ]
    )
    active = 0
    peak = 0

    async def validate(url: str) -> PublicUrl:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0)
            if "127.0.0.1" in url:
                raise PermissionDeniedError("not a public URL")
            return PublicUrl(url=url, host="example.com")
        finally:
            active -= 1

    result = await SearchWebTool(
        provider=provider, url_validator=validate, validation_concurrency=1
    ).run({"query": "safe"}, _context())

    assert result == {
        "results": [{"title": "public", "url": "https://example.com", "snippet": "yes"}]
    }
    assert peak == 1


@pytest.mark.asyncio
async def test_search_tool_returns_provider_error_as_data() -> None:
    class FailingProvider:
        async def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
            del query, max_results
            raise RuntimeError("provider unavailable")

    result = await SearchWebTool(provider=FailingProvider()).run(
        {"query": "bioinformatics"}, _context()
    )

    assert result == {
        "results": [],
        "error": "RuntimeError: provider unavailable",
    }


@pytest.mark.asyncio
async def test_ddgs_provider_retries_once_then_succeeds() -> None:
    attempts = 0
    sleeps: list[float] = []

    class Client:
        def __enter__(self) -> "Client":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def text(self, query: str, *, max_results: int) -> list[dict[str, str]]:
            del query, max_results
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("transient")
            return [{"title": "ok", "href": "https://example.com"}]

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    provider = DuckDuckGoSearchProvider(client_factory=Client, sleep=sleep)
    result = await provider.search("query", 3)

    assert attempts == 2
    assert sleeps == [0.5]
    assert result[0]["title"] == "ok"


@pytest.mark.asyncio
async def test_ddgs_provider_raises_after_bounded_retry() -> None:
    attempts = 0

    class Client:
        def __enter__(self) -> "Client":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def text(self, query: str, *, max_results: int) -> list[dict[str, str]]:
            del query, max_results
            nonlocal attempts
            attempts += 1
            raise RuntimeError("still down")

    async def no_sleep(_delay: float) -> None:
        return None

    provider = DuckDuckGoSearchProvider(client_factory=Client, sleep=no_sleep)

    with pytest.raises(RuntimeError, match="still down"):
        await provider.search("query", 3)
    assert attempts == 2
