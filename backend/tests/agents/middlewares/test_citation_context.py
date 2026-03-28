"""Tests for citation extraction and validation."""

import pytest

from src.agents.middlewares.citation_context import CitationContextMiddleware


class TestCitationExtraction:
    def setup_method(self):
        self.middleware = CitationContextMiddleware(paper_service=None)

    def test_extract_author_year(self):
        citations = self.middleware._extract_citations("As shown by (Smith, 2023)")
        assert any("Smith" in c and "2023" in c for c in citations)

    def test_extract_numbered_citations(self):
        citations = self.middleware._extract_citations("As shown in [1] and [2]")
        assert "1" in citations
        assert "2" in citations

    def test_extract_doi(self):
        citations = self.middleware._extract_citations("doi:10.1234/test.5678")
        assert any("10.1234/test.5678" in c for c in citations)

    def test_extract_et_al(self):
        citations = self.middleware._extract_citations("(Smith et al., 2023)")
        assert any("Smith" in c and "2023" in c for c in citations)

    def test_empty_content_returns_empty(self):
        citations = self.middleware._extract_citations("")
        assert citations == []

    def test_no_citations_returns_empty(self):
        citations = self.middleware._extract_citations("This is plain text.")
        assert citations == []

    def test_deduplicates_citations(self):
        citations = self.middleware._extract_citations("[1] and again [1]")
        assert citations.count("1") == 1


@pytest.mark.asyncio
class TestCitationValidation:
    async def test_after_model_skips_without_workspace_id(self):
        middleware = CitationContextMiddleware(paper_service=None)
        state = {"messages": []}
        result = await middleware.after_model(state, {})
        assert result == dict(state)

    async def test_after_model_skips_without_messages(self):
        middleware = CitationContextMiddleware(paper_service=None)
        state = {"workspace_id": "ws-1", "messages": []}
        result = await middleware.after_model(state, {})
        assert result == dict(state)


class TestCitationLogging:
    def test_extraction_logs_count(self, caplog):
        import logging
        middleware = CitationContextMiddleware(paper_service=None)
        with caplog.at_level(logging.DEBUG, logger="src.agents.middlewares.citation_context"):
            middleware._extract_citations("(Smith, 2023) and [1]")
        assert any("citation" in r.message.lower() for r in caplog.records)
