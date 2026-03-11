"""Tests for DOI MCP tool."""

import pytest
from unittest.mock import patch, AsyncMock


class TestDOITools:
    """Tests for DOI MCP tools."""

    @pytest.mark.asyncio
    async def test_resolve_doi_valid(self):
        """Should resolve valid DOI."""
        try:
            from src.mcp.tools.doi import resolve_doi
        except ImportError:
            pytest.skip("DOI tool not implemented yet")
        
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = AsyncMock(
                status_code=200,
                json=lambda: {"title": "Test Paper"}
            )
            result = await resolve_doi("10.1000/test")
            assert result is not None

    @pytest.mark.asyncio
    async def test_resolve_doi_invalid(self):
        """Should handle invalid DOI."""
        try:
            from src.mcp.tools.doi import resolve_doi
        except ImportError:
            pytest.skip("DOI tool not implemented yet")
        
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = AsyncMock(status_code=404)
            result = await resolve_doi("invalid-doi")
            assert result is None or "error" in result

    @pytest.mark.asyncio
    async def test_get_doi_metadata(self):
        """Should get DOI metadata."""
        try:
            from src.mcp.tools.doi import get_doi_metadata
        except ImportError:
            pytest.skip("DOI tool not implemented yet")
        
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = AsyncMock(
                status_code=200,
                json=lambda: {
                    "title": ["Test Paper"],
                    "author": [{"given": "John", "family": "Doe"}],
                    "published": {"date-parts": [[2024]]}
                }
            )
            result = await get_doi_metadata("10.1000/test")
            assert result.get("title") == "Test Paper"
