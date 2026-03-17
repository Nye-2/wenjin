"""Tests for Tier 2 LLM extraction helpers.

These tests verify the three LLM-based extraction methods
(_extract_section_summaries, _extract_key_concepts, _extract_entities)
and the _get_llm fallback logic using mocked LLM responses.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.academic.services.extraction_service import ExtractionService


def _make_service():
    """Create an ExtractionService with a mocked database session."""
    db = AsyncMock()
    return ExtractionService(db)


# ------------------------------------------------------------------
# _extract_section_summaries
# ------------------------------------------------------------------


class TestExtractSectionSummaries:
    @pytest.mark.asyncio
    async def test_returns_summaries_dict(self):
        service = _make_service()
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content="This section discusses methodology."),
        )

        with patch.object(service, "_get_llm", return_value=mock_llm):
            result = await service._extract_section_summaries(
                "## Introduction\nSome text here\n## Methodology\nMore text",
                [{"title": "Introduction"}, {"title": "Methodology"}],
            )

        assert isinstance(result, dict)
        assert len(result) > 0
        # Both sections should have been summarized
        assert "Introduction" in result
        assert "Methodology" in result
        assert result["Introduction"] == "This section discusses methodology."

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_llm(self):
        service = _make_service()
        with patch.object(service, "_get_llm", return_value=None):
            result = await service._extract_section_summaries(
                "text", [{"title": "Intro"}],
            )
        assert result == {}

    @pytest.mark.asyncio
    async def test_skips_sections_not_found_in_text(self):
        service = _make_service()
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content="A summary."),
        )

        with patch.object(service, "_get_llm", return_value=mock_llm):
            result = await service._extract_section_summaries(
                "## Introduction\nSome text here",
                [{"title": "Introduction"}, {"title": "Nonexistent Section"}],
            )

        assert "Introduction" in result
        assert "Nonexistent Section" not in result

    @pytest.mark.asyncio
    async def test_handles_llm_error_per_section(self):
        """If one section fails, others should still be processed."""
        service = _make_service()
        mock_llm = AsyncMock()
        call_count = 0

        async def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("LLM error")
            return MagicMock(content="Summary for second section.")

        mock_llm.ainvoke = AsyncMock(side_effect=_side_effect)

        with patch.object(service, "_get_llm", return_value=mock_llm):
            result = await service._extract_section_summaries(
                "Introduction\ntext\nMethodology\nmore text",
                [{"title": "Introduction"}, {"title": "Methodology"}],
            )

        # First section failed, second should succeed
        assert "Introduction" not in result
        assert "Methodology" in result


# ------------------------------------------------------------------
# _extract_key_concepts
# ------------------------------------------------------------------


class TestExtractKeyConcepts:
    @pytest.mark.asyncio
    async def test_returns_list_of_strings(self):
        service = _make_service()
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content='["Transformer", "Attention Mechanism", "BERT"]',
            ),
        )

        with patch.object(service, "_get_llm", return_value=mock_llm):
            result = await service._extract_key_concepts(
                "Some paper text about transformers",
            )

        assert isinstance(result, list)
        assert len(result) == 3
        assert "Transformer" in result
        assert "Attention Mechanism" in result
        assert "BERT" in result

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_llm(self):
        service = _make_service()
        with patch.object(service, "_get_llm", return_value=None):
            result = await service._extract_key_concepts("text")
        assert result == []

    @pytest.mark.asyncio
    async def test_truncates_to_20_concepts(self):
        service = _make_service()
        mock_llm = AsyncMock()
        concepts = [f"concept_{i}" for i in range(30)]
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content=json.dumps(concepts)),
        )

        with patch.object(service, "_get_llm", return_value=mock_llm):
            result = await service._extract_key_concepts("text")

        assert len(result) == 20

    @pytest.mark.asyncio
    async def test_fallback_newline_parsing(self):
        """When LLM returns non-JSON, fall back to newline parsing."""
        service = _make_service()
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content="- Transformer\n- Attention\n- BERT",
            ),
        )

        with patch.object(service, "_get_llm", return_value=mock_llm):
            result = await service._extract_key_concepts("text")

        assert isinstance(result, list)
        assert len(result) == 3
        assert "Transformer" in result


# ------------------------------------------------------------------
# _extract_entities
# ------------------------------------------------------------------


class TestExtractEntities:
    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self):
        service = _make_service()
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content=json.dumps([
                    {"type": "method", "name": "Transformer"},
                    {"type": "dataset", "name": "ImageNet"},
                ]),
            ),
        )

        with patch.object(service, "_get_llm", return_value=mock_llm):
            result = await service._extract_entities(
                "Paper about transformers and ImageNet",
            )

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["type"] == "method"
        assert result[0]["name"] == "Transformer"
        assert result[1]["type"] == "dataset"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_llm(self):
        service = _make_service()
        with patch.object(service, "_get_llm", return_value=None):
            result = await service._extract_entities("text")
        assert result == []

    @pytest.mark.asyncio
    async def test_filters_invalid_entities(self):
        """Entities missing required keys should be filtered out."""
        service = _make_service()
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content=json.dumps([
                    {"type": "method", "name": "Transformer"},
                    {"invalid": "entry"},
                    {"type": "dataset"},  # missing "name"
                    "not a dict",
                ]),
            ),
        )

        with patch.object(service, "_get_llm", return_value=mock_llm):
            result = await service._extract_entities("text")

        assert len(result) == 1
        assert result[0]["name"] == "Transformer"

    @pytest.mark.asyncio
    async def test_returns_empty_on_invalid_json(self):
        service = _make_service()
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content="This is not JSON at all"),
        )

        with patch.object(service, "_get_llm", return_value=mock_llm):
            result = await service._extract_entities("text")

        assert result == []

    @pytest.mark.asyncio
    async def test_truncates_to_30_entities(self):
        service = _make_service()
        mock_llm = AsyncMock()
        entities = [
            {"type": "method", "name": f"method_{i}"} for i in range(40)
        ]
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content=json.dumps(entities)),
        )

        with patch.object(service, "_get_llm", return_value=mock_llm):
            result = await service._extract_entities("text")

        assert len(result) == 30


# ------------------------------------------------------------------
# _get_llm
# ------------------------------------------------------------------


class TestGetLlm:
    def test_returns_none_when_all_factories_fail(self):
        service = _make_service()
        with (
            patch(
                "src.academic.services.extraction_service.ExtractionService._get_llm",
                wraps=service._get_llm,
            ),
            patch(
                "src.models.factory.create_chat_model",
                side_effect=Exception("no config"),
            ),
            patch(
                "langchain_openai.ChatOpenAI",
                side_effect=Exception("no api key"),
            ),
        ):
            result = service._get_llm()
        assert result is None

    def test_returns_model_from_factory(self):
        service = _make_service()
        mock_model = MagicMock()
        with patch(
            "src.models.factory.create_chat_model",
            return_value=mock_model,
        ):
            result = service._get_llm()
        assert result is mock_model
