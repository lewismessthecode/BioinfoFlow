from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.agent_core.tools.web.providers import (
    DuckDuckGoSearchProvider,
    WebSearchProvider,
)
from app.services.agent_core.tools.web.public_url_policy import (
    PublicUrl,
    validate_public_url,
)


class SearchWebTool:
    spec = AgentToolSpec(
        name="web.search",
        description="Search the public web and return top results.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "url": {"type": "string"},
                            "snippet": {"type": "string"},
                        },
                        "required": ["title", "url", "snippet"],
                        "additionalProperties": False,
                    },
                },
                "error": {"type": "string"},
            },
            "required": ["results"],
        },
        risk_level="read",
        read_scope=["web"],
        audit="Search the public web.",
        timeout_seconds=30,
        parallel_safe=True,
    )

    def __init__(
        self,
        *,
        provider: WebSearchProvider | None = None,
        url_validator: Callable[[str], Awaitable[PublicUrl]] = validate_public_url,
        validation_concurrency: int = 5,
    ) -> None:
        self._provider = provider or DuckDuckGoSearchProvider()
        self._url_validator = url_validator
        self._validation_concurrency = max(1, validation_concurrency)

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        del context
        query = str(input["query"])
        max_results = int(input.get("max_results") or 5)
        try:
            raw_results = await self._provider.search(query, max_results)
        except Exception as exc:  # noqa: BLE001 - provider errors are model-readable data
            return {"results": [], "error": f"{exc.__class__.__name__}: {exc}"}

        semaphore = asyncio.Semaphore(self._validation_concurrency)

        async def normalize(item: Mapping[str, Any]) -> dict[str, str] | None:
            url = str(item.get("href") or item.get("url") or "").strip()
            async with semaphore:
                try:
                    validated = await self._url_validator(url)
                except Exception:  # noqa: BLE001 - discard one unsafe/broken result
                    return None
            return {
                "title": str(item.get("title") or "").strip(),
                "url": validated.url,
                "snippet": str(item.get("body") or item.get("snippet") or "").strip(),
            }

        normalized = await asyncio.gather(*(normalize(item) for item in raw_results))
        return {
            "results": [item for item in normalized if item is not None][:max_results]
        }
