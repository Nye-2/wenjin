"""Tests for citation extraction and validation."""

from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

from src.agents.middlewares.citation_context import CitationContextMiddleware


class TestCitationExtraction:
    def setup_method(self):
        self.middleware = CitationContextMiddleware(reference_service=None)

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

    def test_extract_latex_cite_keys(self):
        citations = self.middleware._extract_citations(r"Prior work \cite{smith2026,doe2025}.")
        assert "smith2026" in citations
        assert "doe2025" in citations

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
        middleware = CitationContextMiddleware(reference_service=None)
        state = {"messages": []}
        result = await middleware.after_model(state, {})
        assert result == dict(state)

    async def test_after_model_skips_without_messages(self):
        middleware = CitationContextMiddleware(reference_service=None)
        state = {"workspace_id": "ws-1", "messages": []}
        result = await middleware.after_model(state, {})
        assert result == dict(state)

    async def test_after_model_ignores_legacy_reference_usage_contract(self):
        class _Reference:
            id = "reference-1"

        reference_service = type("ReferenceService", (), {})()
        reference_service.search_in_workspace = AsyncMock(return_value=[_Reference()])
        reference_service.record_reference_usage = AsyncMock()
        middleware = CitationContextMiddleware(reference_service=reference_service)
        state = {
            "workspace_id": "ws-1",
            "messages": [AIMessage(content="Prior work reported this effect [1].")],
        }

        result = await middleware.after_model(
            state,
            {"configurable": {"execution_id": "exec-1", "task_id": "task-1"}},
        )

        assert result["cited_references"] == []
        reference_service.search_in_workspace.assert_not_awaited()
        reference_service.record_reference_usage.assert_not_awaited()

    async def test_after_model_records_source_citation_usage(self):
        class _Source:
            id = "source-1"

        reference_service = type("SourceService", (), {})()
        reference_service.list_sources = AsyncMock(return_value=[_Source()])
        reference_service.record_citation_usage = AsyncMock()
        middleware = CitationContextMiddleware(reference_service=reference_service)
        state = {
            "workspace_id": "ws-1",
            "messages": [AIMessage(content=r"Prior work \cite{source2026}.")],
        }

        result = await middleware.after_model(
            state,
            {"configurable": {"execution_id": "exec-1", "task_id": "task-1"}},
        )

        assert result["cited_references"] == ["source-1"]
        reference_service.record_citation_usage.assert_awaited_once()
        command = reference_service.record_citation_usage.await_args.args[0]
        assert command.workspace_id == "ws-1"
        assert command.citation_keys == ["source2026"]
        assert command.execution_id == "exec-1"
        assert command.task_id == "task-1"


class TestCitationLogging:
    def test_extraction_logs_count(self, caplog):
        import logging
        middleware = CitationContextMiddleware(reference_service=None)
        with caplog.at_level(logging.DEBUG, logger="src.agents.middlewares.citation_context"):
            middleware._extract_citations("(Smith, 2023) and [1]")
        assert any("citation" in r.message.lower() for r in caplog.records)
