"""Web and reference retrieval tools for the agent."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from app.services.agent.tools.base import BaseTool, RiskLevel, ToolResult
from app.services.agent.tools import register_tool

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


MAX_RESULTS = 20
DEFAULT_HTTP_TIMEOUT = 20.0
_WHITESPACE_RE = re.compile(r"\s+")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META_PUBLISHED_PATTERNS = [
    re.compile(
        r'<meta[^>]+(?:name|property)=["\'](?:article:published_time|citation_publication_date|pubdate|date)["\'][^>]+content=["\']([^"\']+)["\']',
        re.IGNORECASE,
    ),
    re.compile(
        r'<time[^>]+datetime=["\']([^"\']+)["\']',
        re.IGNORECASE,
    ),
]


def _strip_html(html: str) -> str:
    stripped = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    stripped = re.sub(r"(?is)<[^>]+>", " ", stripped)
    return _WHITESPACE_RE.sub(" ", unescape(stripped)).strip()


def _extract_title(html: str) -> str:
    match = _TITLE_RE.search(html)
    if not match:
        return ""
    return _WHITESPACE_RE.sub(" ", unescape(match.group(1))).strip()


def _extract_published_at(html: str) -> str | None:
    for pattern in _META_PUBLISHED_PATTERNS:
        match = pattern.search(html)
        if match:
            return match.group(1).strip()
    return None


@register_tool
class WebSearchTool(BaseTool):
    """Tool to search the web using DuckDuckGo."""

    name = "web_search"
    description = (
        "Search the web for documentation, tools, protocols, and references. "
        "Useful for finding bioinformatics resources, tool documentation, "
        "and troubleshooting information."
    )
    risk_level = RiskLevel.READ

    def __init__(
        self,
        session: "AsyncSession",
        *,
        project_id: str,
        workspace_root: Path | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> None:
        super().__init__(
            session,
            project_id=project_id,
            workspace_root=workspace_root,
            user_id=user_id,
            workspace_id=workspace_id,
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "query": {
                "type": "string",
                "description": "Search query string",
                "required": True,
            },
            "max_results": {
                "type": "integer",
                "description": f"Maximum number of results to return (max: {MAX_RESULTS})",
                "default": 5,
            },
        }

    async def execute(
        self,
        *,
        query: str,
        max_results: int = 5,
    ) -> ToolResult:
        """Search the web using DuckDuckGo.

        Args:
            query: Search query string
            max_results: Maximum results to return

        Returns:
            ToolResult with search results
        """
        try:
            if not query.strip():
                return ToolResult(success=False, error="query cannot be empty")

            max_results = min(max_results, MAX_RESULTS)

            raw_results = await self._do_search(query, max_results)

            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
                for r in raw_results[:max_results]
            ]

            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "total_results": len(results),
                    "results": results,
                },
            )

        except Exception as e:
            return ToolResult(success=False, error=f"Search error: {e}")

    async def _do_search(
        self, query: str, max_results: int
    ) -> list[dict[str, Any]]:
        """Execute the DuckDuckGo search in a thread.

        Separated for easy mocking in tests.
        """
        from duckduckgo_search import DDGS

        def _search() -> list[dict[str, Any]]:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))

        return await asyncio.to_thread(_search)


@register_tool
class WebFetchTool(BaseTool):
    """Fetch and read the contents of a single webpage."""

    name = "web_fetch"
    description = (
        "Fetch a webpage and return the title, detected publish date, final URL, "
        "and cleaned page text. Use after web_search when freshness or source "
        "verification matters."
    )
    risk_level = RiskLevel.READ

    def __init__(
        self,
        session: "AsyncSession",
        *,
        project_id: str,
        workspace_root: Path | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> None:
        super().__init__(
            session,
            project_id=project_id,
            workspace_root=workspace_root,
            user_id=user_id,
            workspace_id=workspace_id,
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "url": {
                "type": "string",
                "description": "Absolute URL to fetch",
                "required": True,
            },
            "max_chars": {
                "type": "integer",
                "description": "Maximum number of characters of cleaned page text to return",
                "default": 12000,
            },
        }

    async def execute(self, *, url: str, max_chars: int = 12000) -> ToolResult:
        try:
            if not url.strip():
                return ToolResult(success=False, error="url cannot be empty")
            payload = await self._fetch_url(url.strip(), max_chars=max_chars)
            return ToolResult(success=True, data=payload)
        except Exception as exc:
            return ToolResult(success=False, error=f"Fetch error: {exc}")

    async def _fetch_url(self, url: str, *, max_chars: int) -> dict[str, Any]:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=DEFAULT_HTTP_TIMEOUT,
            headers={"User-Agent": "Bioinfoflow-Agent/1.0"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        html = response.text
        content = _strip_html(html)
        if len(content) > max_chars:
            content = content[:max_chars].rstrip() + "..."

        return {
            "url": str(response.url),
            "status_code": response.status_code,
            "title": _extract_title(html),
            "published_at": _extract_published_at(html),
            "content": content,
        }


@register_tool
class PubMedSearchTool(BaseTool):
    """Search PubMed using the official NCBI E-utilities API."""

    name = "pubmed_search"
    description = (
        "Search PubMed via the official NCBI API and return recent papers with "
        "PMIDs, journals, publication dates, and PubMed links."
    )
    risk_level = RiskLevel.READ

    def __init__(
        self,
        session: "AsyncSession",
        *,
        project_id: str,
        workspace_root: Path | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> None:
        super().__init__(
            session,
            project_id=project_id,
            workspace_root=workspace_root,
            user_id=user_id,
            workspace_id=workspace_id,
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "query": {
                "type": "string",
                "description": "PubMed search query",
                "required": True,
            },
            "max_results": {
                "type": "integer",
                "description": f"Maximum number of PubMed results to return (max: {MAX_RESULTS})",
                "default": 10,
            },
            "since_year": {
                "type": "integer",
                "description": "Minimum publication year to include",
                "default": datetime.now(timezone.utc).year - 2,
            },
        }

    async def execute(
        self,
        *,
        query: str,
        max_results: int = 10,
        since_year: int | None = None,
    ) -> ToolResult:
        try:
            if not query.strip():
                return ToolResult(success=False, error="query cannot be empty")

            current_year = datetime.now(timezone.utc).year
            effective_since_year = since_year or (current_year - 2)
            max_results = min(max_results, MAX_RESULTS)
            search_query = f"({query.strip()}) AND ({effective_since_year}:{current_year}[pdat])"

            esearch = await self._request_json(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                {
                    "db": "pubmed",
                    "retmode": "json",
                    "retmax": max_results,
                    "sort": "pub_date",
                    "term": search_query,
                },
            )
            ids = esearch.get("esearchresult", {}).get("idlist", [])
            if not ids:
                return ToolResult(
                    success=True,
                    data={"query": query, "total_results": 0, "results": []},
                )

            esummary = await self._request_json(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                {
                    "db": "pubmed",
                    "retmode": "json",
                    "id": ",".join(ids),
                },
            )

            results: list[dict[str, Any]] = []
            summary_result = esummary.get("result", {})
            for pmid in summary_result.get("uids", []):
                item = summary_result.get(pmid, {})
                pubdate = str(item.get("pubdate") or "")
                year_match = re.search(r"(20\d{2}|19\d{2})", pubdate)
                results.append(
                    {
                        "pmid": str(item.get("uid") or pmid),
                        "title": item.get("title", ""),
                        "journal": item.get("fulljournalname", ""),
                        "published_at": pubdate,
                        "year": int(year_match.group(1)) if year_match else None,
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{item.get('uid') or pmid}/",
                    }
                )

            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "since_year": effective_since_year,
                    "total_results": len(results),
                    "results": results,
                },
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"PubMed search error: {exc}")

    async def _request_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()


@register_tool
class ChemblSearchTool(BaseTool):
    """Retrieve activity data from the official ChEMBL API."""

    name = "chembl_search"
    description = (
        "Search ChEMBL via the official API for a target and return compound "
        "activities, including IC50-filtered molecules and report links."
    )
    risk_level = RiskLevel.READ

    def __init__(
        self,
        session: "AsyncSession",
        *,
        project_id: str,
        workspace_root: Path | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> None:
        super().__init__(
            session,
            project_id=project_id,
            workspace_root=workspace_root,
            user_id=user_id,
            workspace_id=workspace_id,
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "target": {
                "type": "string",
                "description": "Target name or symbol, e.g. EGFR",
                "required": True,
            },
            "ic50_lt_nM": {
                "type": "number",
                "description": "Upper IC50 threshold in nM",
                "default": 50,
            },
            "max_results": {
                "type": "integer",
                "description": f"Maximum number of activity records to return (max: {MAX_RESULTS})",
                "default": 25,
            },
        }

    async def execute(
        self,
        *,
        target: str,
        ic50_lt_nM: float = 50,
        max_results: int = 25,
    ) -> ToolResult:
        try:
            if not target.strip():
                return ToolResult(success=False, error="target cannot be empty")
            max_results = min(max_results, MAX_RESULTS)

            target_payload = await self._request_json(
                "https://www.ebi.ac.uk/chembl/api/data/target/search.json",
                {"q": target.strip()},
            )
            targets = target_payload.get("targets", [])
            if not targets:
                return ToolResult(
                    success=True,
                    data={"target": None, "total_results": 0, "results": []},
                )

            target_hit = targets[0]
            target_chembl_id = target_hit.get("target_chembl_id", "")
            activity_payload = await self._request_json(
                "https://www.ebi.ac.uk/chembl/api/data/activity.json",
                {
                    "target_chembl_id": target_chembl_id,
                    "standard_type": "IC50",
                    "standard_units": "nM",
                    "limit": max_results,
                },
            )

            activities = []
            for item in activity_payload.get("activities", []):
                try:
                    value = float(item.get("standard_value"))
                except (TypeError, ValueError):
                    continue
                if value >= ic50_lt_nM:
                    continue
                mol_id = str(item.get("molecule_chembl_id") or "")
                activities.append(
                    {
                        "molecule_chembl_id": mol_id,
                        "canonical_smiles": item.get("canonical_smiles", ""),
                        "standard_value": value,
                        "standard_units": item.get("standard_units", ""),
                        "standard_type": item.get("standard_type", ""),
                        "activity_url": f"https://www.ebi.ac.uk/chembl/compound_report_card/{mol_id}",
                    }
                )

            return ToolResult(
                success=True,
                data={
                    "target": {
                        "query": target,
                        "chembl_id": target_chembl_id,
                        "pref_name": target_hit.get("pref_name", ""),
                        "url": f"https://www.ebi.ac.uk/chembl/target_report_card/{target_chembl_id}/",
                    },
                    "threshold_nM": ic50_lt_nM,
                    "total_results": len(activities),
                    "results": activities[:max_results],
                },
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"ChEMBL search error: {exc}")

    async def _request_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
