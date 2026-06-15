from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from urllib import error as urllib_error
from urllib import request

from duckduckgo_search import DDGS

from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec


_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


class FetchWebPageTool:
    spec = AgentToolSpec(
        name="web.fetch",
        description="Fetch a web page and return a cleaned text body.",
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 50000},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "status_code": {"type": "integer"},
                "content": {"type": "string"},
                "error": {"type": "string"},
            },
            "required": ["url", "status_code", "content"],
        },
        risk_level="read",
        read_scope=["web"],
        audit="Fetch a web page over HTTP.",
        timeout_seconds=30,
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del context
        url = str(input["url"])
        max_chars = int(input.get("max_chars") or 12000)
        try:
            response = await asyncio.to_thread(_fetch_url, url)
        except urllib_error.HTTPError as exc:
            # Surface the status so the model understands 403/404/303 blocks
            # instead of guessing the page was empty.
            return {
                "url": url,
                "status_code": int(exc.code),
                "content": "",
                "error": f"HTTP {exc.code}: {exc.reason}",
            }
        except Exception as exc:  # noqa: BLE001 — network/parse errors are data, not crashes
            return {
                "url": url,
                "status_code": 0,
                "content": "",
                "error": f"{exc.__class__.__name__}: {exc}",
            }
        cleaned = _clean_text(response["text"])[:max_chars]
        return {
            "url": response["url"],
            "status_code": response["status_code"],
            "content": cleaned,
        }


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
                "results": {"type": "array"},
                "error": {"type": "string"},
            },
            "required": ["results"],
        },
        risk_level="read",
        read_scope=["web"],
        audit="Search the public web.",
        timeout_seconds=30,
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del context
        query = str(input["query"])
        max_results = int(input.get("max_results") or 5)
        try:
            results = await asyncio.to_thread(_search, query, max_results)
        except Exception as exc:  # noqa: BLE001 — return the error so the model can react
            return {
                "results": [],
                "error": f"{exc.__class__.__name__}: {exc}",
            }
        return {
            "results": [
                {
                    "title": str(item.get("title") or ""),
                    "url": str(item.get("href") or item.get("url") or ""),
                    "snippet": str(item.get("body") or item.get("snippet") or ""),
                }
                for item in results[:max_results]
            ]
        }


def _search(query: str, max_results: int) -> list[dict[str, Any]]:
    """Run a DDG text search with one backed-off retry before giving up."""
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))
        except Exception as exc:  # noqa: BLE001 — retry transient provider failures
            last_error = exc
            if attempt == 0:
                # Brief backoff so the retry doesn't immediately re-hit a
                # rate-limit. Runs in a worker thread, so blocking is fine.
                time.sleep(0.5)
    assert last_error is not None
    raise last_error


def _fetch_url(url: str) -> dict[str, Any]:
    req = request.Request(url, headers={"User-Agent": "Bioinfoflow-AgentCore/1.0"})
    with request.urlopen(req, timeout=20.0) as response:
        body = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return {
            "url": str(response.geturl()),
            "status_code": int(response.getcode() or 200),
            "text": body.decode(charset, errors="replace"),
        }


def _clean_text(raw: str) -> str:
    cleaned = _TAG_RE.sub(" ", raw)
    return _WHITESPACE_RE.sub(" ", cleaned).strip()
