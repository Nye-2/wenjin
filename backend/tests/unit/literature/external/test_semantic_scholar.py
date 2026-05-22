# tests/unit/literature/external/test_semantic_scholar.py
"""Tests for Semantic Scholar client."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.academic.literature.external import semantic_scholar
from src.academic.literature.external.semantic_scholar import SemanticScholarClient


@pytest.fixture
def client():
    """Create client instance."""
    return SemanticScholarClient()


@pytest.fixture(autouse=True)
def reset_rate_limit_state():
    """Reset module-level rate limiting state between tests."""
    semantic_scholar._next_request_at = 0.0


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
                    "externalIds": {"DOI": "10.1234/test"},
                    "url": "https://example.com",
                    "abstract": "Abstract text",
                    "citationCount": 100,
                    "venue": "ICML",
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("src.academic.literature.external.semantic_scholar._http") as mock_http:
            mock_http.get = AsyncMock(return_value=mock_response)

            results = await client.search("machine learning", limit=5)

        assert mock_http.get.await_args.kwargs["params"]["fields"] == (
            "paperId,title,authors,year,externalIds,url,abstract,citationCount,venue"
        )
        assert len(results) == 1
        assert results[0].title == "Test Paper"
        assert results[0].source == "semantic_scholar"
        assert results[0].external_id == "abc123"
        assert results[0].doi == "10.1234/test"
        assert results[0].citations_count == 100

    @pytest.mark.asyncio
    async def test_search_normalizes_null_optional_fields(self, client):
        """Semantic Scholar can return null for optional text fields."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {
                    "paperId": "abc123",
                    "title": "Paper With Null Abstract",
                    "authors": [{"name": "Author One"}],
                    "year": 2024,
                    "externalIds": {},
                    "url": None,
                    "abstract": None,
                    "citationCount": 12,
                    "venue": None,
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("src.academic.literature.external.semantic_scholar._http") as mock_http:
            mock_http.get = AsyncMock(return_value=mock_response)

            results = await client.search("federated learning", limit=5)

        assert len(results) == 1
        assert results[0].abstract == ""
        assert results[0].url is None
        assert results[0].venue is None

    @pytest.mark.asyncio
    async def test_search_sends_api_key_header_when_configured(self, client):
        """Test search includes the Semantic Scholar API key header."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": []}
        mock_response.raise_for_status = MagicMock()
        settings = SimpleNamespace(
            semantic_scholar_api_key="test-semantic-key",
            semantic_scholar_rate_limit_delay=0.0,
        )

        with (
            patch("src.academic.literature.external.semantic_scholar._http") as mock_http,
            patch("src.academic.literature.external.semantic_scholar.get_settings", return_value=settings),
        ):
            mock_http.get = AsyncMock(return_value=mock_response)

            await client.search("federated learning", limit=3)

        mock_http.get.assert_awaited_once()
        assert mock_http.get.await_args.kwargs["headers"] == {"x-api-key": "test-semantic-key"}

    @pytest.mark.asyncio
    async def test_search_respects_configured_rate_limit_delay(self, client):
        """Test back-to-back searches wait for the configured interval."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": []}
        mock_response.raise_for_status = MagicMock()
        settings = SimpleNamespace(
            semantic_scholar_api_key=None,
            semantic_scholar_rate_limit_delay=1.0,
        )

        with (
            patch("src.academic.literature.external.semantic_scholar._http") as mock_http,
            patch("src.academic.literature.external.semantic_scholar.get_settings", return_value=settings),
            patch("src.academic.literature.external.semantic_scholar.asyncio.sleep", new_callable=AsyncMock) as sleep,
            patch(
                "src.academic.literature.external.semantic_scholar.time.monotonic",
                side_effect=[100.0, 100.2],
            ),
        ):
            mock_http.get = AsyncMock(return_value=mock_response)

            await client.search("first query")
            await client.search("second query")

        sleep.assert_awaited_once()
        assert sleep.await_args.args[0] == pytest.approx(0.8, abs=1e-6)

    @pytest.mark.asyncio
    async def test_get_by_doi_returns_paper(self, client):
        """Test get_by_doi returns paper when found."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "paperId": "abc123",
            "title": "DOI Paper",
            "authors": [],
            "year": 2023,
            "externalIds": {"DOI": "10.1234/doi-test"},
        }
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("src.academic.literature.external.semantic_scholar._http") as mock_http:
            mock_http.get = AsyncMock(return_value=mock_response)

            result = await client.get_by_doi("10.1234/doi-test")

        assert mock_http.get.await_args.kwargs["params"]["fields"] == (
            "paperId,title,authors,year,externalIds,url,abstract,citationCount,venue"
        )
        assert result is not None
        assert result.title == "DOI Paper"
        assert result.doi == "10.1234/doi-test"
        assert result.external_id == "abc123"

    @pytest.mark.asyncio
    async def test_get_citations_extracts_doi_from_external_ids(self, client):
        """Test citations payload uses externalIds for DOI metadata."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {
                    "citingPaper": {
                        "paperId": "cite-1",
                        "title": "Citing Paper",
                        "authors": [{"name": "Author Two"}],
                        "year": 2025,
                        "externalIds": {"DOI": "10.9999/cite"},
                        "url": "https://example.com/citing",
                        "abstract": "Citing abstract",
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("src.academic.literature.external.semantic_scholar._http") as mock_http:
            mock_http.get = AsyncMock(return_value=mock_response)

            results = await client.get_citations("paper-123", limit=2)

        assert mock_http.get.await_args.kwargs["params"]["fields"] == (
            "paperId,title,authors,year,externalIds,url,abstract"
        )
        assert len(results) == 1
        assert results[0].doi == "10.9999/cite"

    @pytest.mark.asyncio
    async def test_get_by_doi_returns_none_when_not_found(self, client):
        """Test get_by_doi returns None when not found."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("src.academic.literature.external.semantic_scholar._http") as mock_http:
            mock_http.get = AsyncMock(return_value=mock_response)

            result = await client.get_by_doi("10.1234/not-found")

        assert result is None
