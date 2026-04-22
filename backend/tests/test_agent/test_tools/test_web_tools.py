"""Tests for WebSearchTool."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.tools.web_tools import (
    ChemblSearchTool,
    PubMedSearchTool,
    WebFetchTool,
    WebSearchTool,
)


class TestWebSearchTool:
    """Tests for WebSearchTool."""

    @pytest.mark.asyncio
    async def test_tool_name(self, db_session) -> None:
        """Tool name should be 'web_search'."""
        tool = WebSearchTool(db_session, project_id="test")
        assert tool.name == "web_search"

    @pytest.mark.asyncio
    async def test_schema_has_required_fields(self, db_session) -> None:
        """Schema should have query and max_results."""
        tool = WebSearchTool(db_session, project_id="test")
        schema = tool.get_schema()

        assert "query" in schema
        assert schema["query"]["required"] is True
        assert "max_results" in schema

    @pytest.mark.asyncio
    async def test_empty_query_fails(self, db_session) -> None:
        """Should fail with empty query."""
        tool = WebSearchTool(db_session, project_id="test")
        result = await tool.execute(query="")

        assert result.success is False
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_search_returns_results(self, db_session) -> None:
        """Should return search results (mocked)."""
        tool = WebSearchTool(db_session, project_id="test")

        mock_results = [
            {"title": "FASTQ format", "href": "https://example.com/fastq", "body": "FASTQ format description"},
            {"title": "BWA manual", "href": "https://example.com/bwa", "body": "BWA alignment tool"},
        ]

        with patch.object(tool, "_do_search", new_callable=AsyncMock, return_value=mock_results):
            result = await tool.execute(query="FASTQ format bioinformatics")

        assert result.success is True
        assert result.data["total_results"] == 2
        assert len(result.data["results"]) == 2
        assert result.data["results"][0]["title"] == "FASTQ format"

    @pytest.mark.asyncio
    async def test_search_handles_api_error(self, db_session) -> None:
        """Should handle search API errors gracefully."""
        tool = WebSearchTool(db_session, project_id="test")

        with patch.object(
            tool, "_do_search", new_callable=AsyncMock,
            side_effect=Exception("API rate limit exceeded"),
        ):
            result = await tool.execute(query="test query")

        assert result.success is False
        assert "error" in result.error.lower() or "rate limit" in result.error.lower()

    @pytest.mark.asyncio
    async def test_search_respects_max_results(self, db_session) -> None:
        """Should cap results at max_results."""
        tool = WebSearchTool(db_session, project_id="test")

        mock_results = [
            {"title": f"Result {i}", "href": f"https://example.com/{i}", "body": f"Body {i}"}
            for i in range(10)
        ]

        with patch.object(tool, "_do_search", new_callable=AsyncMock, return_value=mock_results):
            result = await tool.execute(query="test", max_results=3)

        assert result.success is True
        assert len(result.data["results"]) == 3

    @pytest.mark.asyncio
    async def test_definition(self, db_session) -> None:
        """Should return valid tool definition."""
        tool = WebSearchTool(db_session, project_id="test")
        definition = tool.get_definition()

        assert definition["name"] == "web_search"
        assert "description" in definition
        assert "args" in definition


class TestWebFetchTool:
    @pytest.mark.asyncio
    async def test_fetch_returns_clean_page_content(self, db_session) -> None:
        tool = WebFetchTool(db_session, project_id="test")

        with patch.object(
            tool,
            "_fetch_url",
            new_callable=AsyncMock,
            return_value={
                "url": "https://example.org/paper",
                "status_code": 200,
                "title": "Example Paper",
                "published_at": "2026-04-01",
                "content": "Fresh content body",
            },
        ):
            result = await tool.execute(url="https://example.org/paper")

        assert result.success is True
        assert result.data["title"] == "Example Paper"
        assert result.data["published_at"] == "2026-04-01"
        assert "Fresh content body" in result.data["content"]


class TestPubMedSearchTool:
    @pytest.mark.asyncio
    async def test_pubmed_search_returns_ranked_results(self, db_session) -> None:
        tool = PubMedSearchTool(db_session, project_id="test")
        esearch_payload = {"esearchresult": {"idlist": ["12345", "67890"]}}
        esummary_payload = {
            "result": {
                "uids": ["12345", "67890"],
                "12345": {
                    "uid": "12345",
                    "title": "Recent base editing paper",
                    "pubdate": "2026 Apr",
                    "fulljournalname": "Nature Biotechnology",
                },
                "67890": {
                    "uid": "67890",
                    "title": "Another recent paper",
                    "pubdate": "2025 Nov",
                    "fulljournalname": "Cell",
                },
            }
        }

        with patch.object(
            tool,
            "_request_json",
            new_callable=AsyncMock,
            side_effect=[esearch_payload, esummary_payload],
        ):
            result = await tool.execute(query="CRISPR base editing", max_results=2)

        assert result.success is True
        assert result.data["total_results"] == 2
        assert result.data["results"][0]["pmid"] == "12345"
        assert result.data["results"][0]["url"].endswith("/12345/")


class TestChemblSearchTool:
    @pytest.mark.asyncio
    async def test_chembl_search_returns_compounds_and_target(self, db_session) -> None:
        tool = ChemblSearchTool(db_session, project_id="test")
        target_payload = {
            "targets": [
                {
                    "target_chembl_id": "CHEMBL203",
                    "pref_name": "Epidermal growth factor receptor erbB1",
                }
            ]
        }
        activity_payload = {
            "activities": [
                {
                    "molecule_chembl_id": "CHEMBL25",
                    "canonical_smiles": "CCN",
                    "standard_value": "12.3",
                    "standard_units": "nM",
                    "standard_type": "IC50",
                }
            ]
        }

        with patch.object(
            tool,
            "_request_json",
            new_callable=AsyncMock,
            side_effect=[target_payload, activity_payload],
        ):
            result = await tool.execute(target="EGFR", ic50_lt_nM=50, max_results=10)

        assert result.success is True
        assert result.data["target"]["chembl_id"] == "CHEMBL203"
        assert result.data["results"][0]["molecule_chembl_id"] == "CHEMBL25"
        assert result.data["results"][0]["activity_url"].endswith("/CHEMBL25")
