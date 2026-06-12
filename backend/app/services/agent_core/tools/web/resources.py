from __future__ import annotations

import asyncio
import re
from typing import Any
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
        response = await asyncio.to_thread(_fetch_url, str(input["url"]))
        max_chars = int(input.get("max_chars") or 12000)
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
            "properties": {"results": {"type": "array"}},
            "required": ["results"],
        },
        risk_level="read",
        read_scope=["web"],
        audit="Search the public web.",
        timeout_seconds=30,
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del context
        max_results = int(input.get("max_results") or 5)
        with DDGS() as ddgs:
            results = list(ddgs.text(str(input["query"]), max_results=max_results))
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
