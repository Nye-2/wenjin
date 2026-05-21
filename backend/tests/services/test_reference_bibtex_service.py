"""Tests for SourceBibliographyService."""

from __future__ import annotations

import pytest

from src.services.references.service import _extract_citation_keys


class TestExtractCitationKeys:
    """Unit tests for _extract_citation_keys."""

    def test_single_key(self) -> None:
        content = r"This is a test \cite{Yao2023}."
        assert _extract_citation_keys(content) == {"Yao2023"}

    def test_multiple_keys_same_command(self) -> None:
        content = r"\cite{Yao2023, Smith2024, Doe2025}"
        assert _extract_citation_keys(content) == {"Yao2023", "Smith2024", "Doe2025"}

    def test_citet_command(self) -> None:
        content = r"\citet{Yao2023} said something."
        assert _extract_citation_keys(content) == {"Yao2023"}

    def test_citep_command(self) -> None:
        content = r"\citep{Yao2023}"
        assert _extract_citation_keys(content) == {"Yao2023"}

    def test_cite_with_optional(self) -> None:
        content = r"\citet[see][page~42]{Yao2023}"
        assert _extract_citation_keys(content) == {"Yao2023"}

    def test_cite_author_year(self) -> None:
        content = r"\citeauthor{Yao2023} and \citeyear{Yao2023}"
        assert _extract_citation_keys(content) == {"Yao2023"}

    def test_multiple_commands(self) -> None:
        content = r"\cite{Yao2023} and \citep{Smith2024} and \citet{Doe2025}"
        assert _extract_citation_keys(content) == {"Yao2023", "Smith2024", "Doe2025"}

    def test_empty_content(self) -> None:
        assert _extract_citation_keys("") == set()

    def test_no_citations(self) -> None:
        content = r"This is plain text without any citations."
        assert _extract_citation_keys(content) == set()

    def test_whitespace_around_keys(self) -> None:
        content = r"\cite{ Yao2023 , Smith2024 }"
        assert _extract_citation_keys(content) == {"Yao2023", "Smith2024"}


class TestValidateBibtexRoute:
    """Integration tests for the /bibtex/validate endpoint."""

    @pytest.mark.asyncio
    async def test_validate_bibtex_without_latex_content(self, mock_db_session) -> None:
        """When no latex_content is provided, fall back to key integrity check."""
        pass

    @pytest.mark.asyncio
    async def test_validate_citations_with_latex_content(self, mock_db_session) -> None:
        """When latex_content is provided, validate cite keys."""
        pass
