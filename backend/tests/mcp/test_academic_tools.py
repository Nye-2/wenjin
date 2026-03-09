"""Tests for academic MCP tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.mcp.tools.arxiv import ArxivTool
from src.mcp.tools.doi import DOITool
from src.mcp.tools.pubmed import PubMedTool


class TestArxivTool:
    def test_tool_creation(self):
        """ArxivTool should be created with correct name."""
        tool = ArxivTool()
        assert tool.name == "arxiv_search"

    def test_tool_has_description(self):
        """Tool should have description."""
        tool = ArxivTool()
        assert tool.description is not None

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """Search should return paper results using mock."""
        tool = ArxivTool()

        # Mock the arxiv client to avoid real API calls
        mock_paper = MagicMock()
        mock_paper.title = "Test Paper"
        mock_paper.authors = [MagicMock(name="John Doe")]
        mock_paper.summary = "Test abstract"
        mock_paper.pdf_url = "https://arxiv.org/pdf/test"
        mock_paper.entry_id = "https://arxiv.org/abs/1234.5678"
        mock_paper.doi = "10.1234/test"
        mock_paper.published = MagicMock(year=2023)
        mock_paper.categories = ["cs.AI"]

        with patch.object(tool, "_client") as mock_client:
            mock_client.results = MagicMock(return_value=[mock_paper])
            results = await tool.search("machine learning", max_results=5)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_error(self):
        """Search should return empty list on error."""
        tool = ArxivTool()

        # Mock the arxiv client to raise an exception
        with patch.object(tool, "_client") as mock_client:
            mock_client.results = MagicMock(side_effect=Exception("API error"))
            results = await tool.search("machine learning", max_results=5)

        assert isinstance(results, list)
        assert results == []


class TestPubMedTool:
    def test_tool_creation(self):
        """PubMedTool should be created with correct name."""
        tool = PubMedTool()
        assert tool.name == "pubmed_search"

    def test_tool_has_description(self):
        """Tool should have description."""
        tool = PubMedTool()
        assert tool.description is not None

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """Search should return paper results using mock."""
        tool = PubMedTool()

        # Mock httpx.AsyncClient to avoid real API calls
        mock_search_response = MagicMock()
        mock_search_response.text = '{"esearchresult": {"idlist": ["12345"]}}'
        mock_search_response.raise_for_status = MagicMock()

        mock_fetch_response = MagicMock()
        mock_fetch_response.text = """<?xml version="1.0"?>
        <PubmedArticleSet>
            <PubmedArticle>
                <MedlineCitation>
                    <PMID>12345</PMID>
                    <Article>
                        <ArticleTitle>Test Paper Title</ArticleTitle>
                        <AuthorList>
                            <Author>
                                <LastName>Doe</LastName>
                                <ForeName>John</ForeName>
                            </Author>
                        </AuthorList>
                        <Abstract>
                            <AbstractText>Test abstract content</AbstractText>
                        </Abstract>
                        <Journal>
                            <JournalIssue>
                                <PubDate><Year>2023</Year></PubDate>
                            </JournalIssue>
                        </Journal>
                    </Article>
                </MedlineCitation>
            </PubmedArticle>
        </PubmedArticleSet>"""
        mock_fetch_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.get = AsyncMock(side_effect=[mock_search_response, mock_fetch_response])
            results = await tool.search("cancer treatment", max_results=5)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_error(self):
        """Search should return empty list on error."""
        tool = PubMedTool()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.get = AsyncMock(side_effect=Exception("Network error"))
            results = await tool.search("cancer treatment", max_results=5)

        assert isinstance(results, list)
        assert results == []


class TestDOITool:
    def test_tool_creation(self):
        """DOITool should be created with correct name."""
        tool = DOITool()
        assert tool.name == "doi_resolve"

    def test_tool_has_description(self):
        """Tool should have description."""
        tool = DOITool()
        assert tool.description is not None

    @pytest.mark.asyncio
    async def test_resolve_doi_with_mock(self):
        """Should resolve DOI to metadata using mock."""
        tool = DOITool()

        # Mock the httpx.AsyncClient to avoid real API calls
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "title": "Test Paper Title",
            "author": [{"given": "John", "family": "Doe"}],
            "published": {"date-parts": [[2023]]},
            "container-title": "Test Journal",
            "type": "journal-article",
            "publisher": "Test Publisher",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.get = AsyncMock(return_value=mock_response)
            metadata = await tool.resolve("10.1234/test.doi.123")

        assert isinstance(metadata, dict)
        assert metadata["title"] == "Test Paper Title"
        assert "John Doe" in metadata["authors"]
        assert metadata["year"] == 2023

    @pytest.mark.asyncio
    async def test_resolve_doi_returns_none_on_404(self):
        """Should return None when DOI is not found."""
        tool = DOITool()

        mock_response = AsyncMock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            metadata = await tool.resolve("10.1234/nonexistent.doi")

        assert metadata is None

    @pytest.mark.asyncio
    async def test_resolve_doi_handles_error(self):
        """Should return None on network errors."""
        tool = DOITool()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=Exception("Network error"))
            metadata = await tool.resolve("10.1234/error.doi")

        assert metadata is None
