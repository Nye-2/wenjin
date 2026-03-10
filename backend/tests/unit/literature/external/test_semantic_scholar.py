# tests/unit/literature/external/test_semantic_scholar.py
"""Tests for Semantic Scholar client."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.academic.literature.external.semantic_scholar import SemanticScholarClient


@pytest.fixture
def client():
    """Create client instance."""
    return SemanticScholarClient()


class TestSemanticScholarClient:
    """Tests for SemanticScholarClient."""

    def test_name_properties(self, client):
        """Test client name properties."""
        assert client.name == "semantic_scholar"
        assert client.display_name == "Semantic Scholar"

    @pytest.mark.asyncio
    async def test_search_returns_results(self, client):
        """Test search returns formatted results."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {
                    "paperId": "abc123",
                    "title": "Test Paper",
                    "authors": [{"name": "Author One"}],
                    "year": 2024,
                    "doi": "10.1234/test",
                    "url": "https://example.com",
                    "abstract": "Abstract text",
                    "citationCount": 100,
                    "venue": "ICML",
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = await client.search("machine learning", limit=5)

        assert len(results) == 1
        assert results[0].title == "Test Paper"
        assert results[0].source == "semantic_scholar"
        assert results[0].citations_count == 100

    @pytest.mark.asyncio
    async def test_get_by_doi_returns_paper(self, client):
        """Test get_by_doi returns paper when found."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "paperId": "abc123",
            "title": "DOI Paper",
            "authors": [],
            "year": 2023,
            "doi": "10.1234/doi-test",
        }
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.get_by_doi("10.1234/doi-test")

        assert result is not None
        assert result.title == "DOI Paper"

    @pytest.mark.asyncio
    async def test_get_by_doi_returns_none_when_not_found(self, client):
        """Test get_by_doi returns None when not found."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.get_by_doi("10.1234/not-found")

        assert result is None
