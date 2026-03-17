# tests/unit/literature/external/test_arxiv.py
"""Tests for arXiv client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.academic.literature.external.arxiv import ArxivClient


@pytest.fixture
def client():
    """Create client instance."""
    return ArxivClient()


class TestArxivClient:
    """Tests for ArxivClient."""

    def test_name_properties(self, client):
        """Test client name properties."""
        assert client.name == "arxiv"
        assert client.display_name == "arXiv"

    @pytest.mark.asyncio
    async def test_search_returns_results(self, client):
        """Test search returns formatted results."""
        sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Test Paper on Machine Learning</title>
    <summary>This is the abstract of the test paper.</summary>
    <published>2024-01-15T00:00:00Z</published>
    <id>http://arxiv.org/abs/2401.12345</id>
    <author><name>Author One</name></author>
    <author><name>Author Two</name></author>
  </entry>
</feed>"""

        mock_response = MagicMock()
        mock_response.text = sample_xml
        mock_response.raise_for_status = MagicMock()

        with patch("src.academic.literature.external.arxiv._http") as mock_http:
            mock_http.get = AsyncMock(return_value=mock_response)

            results = await client.search("machine learning", limit=5)

            assert len(results) == 1
            assert results[0].title == "Test Paper on Machine Learning"
            assert results[0].source == "arxiv"
            assert len(results[0].authors) == 2

    @pytest.mark.asyncio
    async def test_get_citations_returns_empty(self, client):
        """Test that citations lookup returns empty (not supported)."""
        results = await client.get_citations("1234.5678", limit=10)

        assert results == []

    @pytest.mark.asyncio
    async def test_get_by_doi_extracts_arxiv_id(self, client):
        """Test get_by_doi extracts arXiv ID from DOI."""
        sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Paper by DOI</title>
    <summary>Abstract text</summary>
    <published>2023-06-01T00:00:00Z</published>
    <id>http://arxiv.org/abs/2306.12345</id>
    <author><name>Author</name></author>
  </entry>
</feed>"""

        mock_response = MagicMock()
        mock_response.text = sample_xml
        mock_response.raise_for_status = MagicMock()

        with patch("src.academic.literature.external.arxiv._http") as mock_http:
            mock_http.get = AsyncMock(return_value=mock_response)

            # arXiv DOI format: 10.48550/arXiv.2306.12345
            result = await client.get_by_doi("10.48550/arXiv.2306.12345")

            assert result is not None
            assert result.title == "Paper by DOI"
