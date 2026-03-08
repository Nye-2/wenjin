"""Tests for literature context middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.academic.literature.index_service import IndexService
from src.agents.middlewares.literature_context import LiteratureContextMiddleware
from src.agents.thread_state import ThreadState


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    return AsyncMock()


@pytest.fixture
def index_service(mock_db_session):
    """Create an IndexService instance with mock db."""
    return IndexService(mock_db_session)


@pytest.fixture
def literature_middleware(index_service):
    """Create a LiteratureContextMiddleware instance with mock service."""
    return LiteratureContextMiddleware(index_service)


# ============================================================
# IndexService Tests
# ============================================================

class TestIndexServiceGetWorkspaceTocSummary:
    """Tests for IndexService.get_workspace_toc_summary."""

    @pytest.mark.asyncio
    async def test_returns_formatted_toc_summary(self, index_service, mock_db_session):
        """Test that get_workspace_toc_summary returns properly formatted TOC."""
        # Setup mock papers
        mock_paper1 = MagicMock()
        mock_paper1.id = "paper-1"
        mock_paper1.title = "Attention Is All You Need"
        mock_paper1.year = 2017
        mock_paper1.authors = [{"name": "Vaswani et al."}]

        mock_paper2 = MagicMock()
        mock_paper2.id = "paper-2"
        mock_paper2.title = "BERT"
        mock_paper2.year = 2019
        mock_paper2.authors = [{"name": "Devlin et al."}]

        # Mock extraction with TOC data
        mock_extraction1 = MagicMock()
        mock_extraction1.structured_data = {
            "toc": [
                {"number": "1", "title": "Introduction"},
                {"number": "2", "title": "Background"},
                {"number": "3", "title": "Model Architecture"},
                {"number": "4", "title": "Experiments"},
            ]
        }

        mock_extraction2 = MagicMock()
        mock_extraction2.structured_data = {
            "toc": [
                {"number": "1", "title": "Introduction"},
                {"number": "2", "title": "Related Work"},
                {"number": "3", "title": "BERT"},
                {"number": "4", "title": "Experiments"},
            ]
        }

        # Configure mock to return papers
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_paper1, mock_paper2]
        mock_db_session.execute.return_value = mock_result

        # Mock get_paper_toc to return TOC items
        with patch.object(index_service, 'get_paper_toc') as mock_get_toc:
            mock_get_toc.side_effect = [
                mock_extraction1.structured_data["toc"],
                mock_extraction2.structured_data["toc"],
            ]

            result = await index_service.get_workspace_toc_summary("workspace-1")

        assert "## 文献库概览" in result
        assert "### [1] Attention Is All You Need (2017)" in result
        assert "### [2] BERT (2019)" in result
        assert "1. Introduction" in result
        assert "2. Background" in result
        assert "3. Model Architecture" in result
        assert "4. Experiments" in result

    @pytest.mark.asyncio
    async def test_returns_empty_string_for_no_papers(self, index_service, mock_db_session):
        """Test that get_workspace_toc_summary returns empty string when no papers."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        result = await index_service.get_workspace_toc_summary("workspace-1")

        assert result == ""

    @pytest.mark.asyncio
    async def test_handles_paper_without_toc(self, index_service, mock_db_session):
        """Test that papers without TOC are handled gracefully."""
        mock_paper = MagicMock()
        mock_paper.id = "paper-1"
        mock_paper.title = "Paper Without TOC"
        mock_paper.year = 2020
        mock_paper.authors = [{"name": "Author"}]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_paper]
        mock_db_session.execute.return_value = mock_result

        with patch.object(index_service, 'get_paper_toc', return_value=[]):
            result = await index_service.get_workspace_toc_summary("workspace-1")

        assert "### [1] Paper Without TOC (2020)" in result


class TestIndexServiceGetPaperToc:
    """Tests for IndexService.get_paper_toc."""

    @pytest.mark.asyncio
    async def test_returns_toc_list(self, index_service, mock_db_session):
        """Test that get_paper_toc returns list of TOC items."""
        mock_extraction = MagicMock()
        mock_extraction.structured_data = {
            "toc": [
                {"number": "1", "title": "Introduction"},
                {"number": "2", "title": "Methods"},
            ]
        }

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_extraction
        mock_db_session.execute.return_value = mock_result

        result = await index_service.get_paper_toc("paper-1")

        assert len(result) == 2
        assert result[0] == {"number": "1", "title": "Introduction"}
        assert result[1] == {"number": "2", "title": "Methods"}

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_no_extraction(self, index_service, mock_db_session):
        """Test that get_paper_toc returns empty list when no extraction exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await index_service.get_paper_toc("paper-1")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_extraction_without_toc(self, index_service, mock_db_session):
        """Test that get_paper_toc returns empty list when extraction has no TOC."""
        mock_extraction = MagicMock()
        mock_extraction.structured_data = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_extraction
        mock_db_session.execute.return_value = mock_result

        result = await index_service.get_paper_toc("paper-1")

        assert result == []


class TestIndexServiceGetPaperSection:
    """Tests for IndexService.get_paper_section."""

    @pytest.mark.asyncio
    async def test_returns_section_content(self, index_service, mock_db_session):
        """Test that get_paper_section returns section content."""
        mock_extraction = MagicMock()
        mock_extraction.structured_data = {
            "sections": {
                "1": {
                    "title": "Introduction",
                    "content": "This is the introduction section content."
                },
                "2": {
                    "title": "Methods",
                    "content": "This is the methods section content."
                }
            }
        }

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_extraction
        mock_db_session.execute.return_value = mock_result

        result = await index_service.get_paper_section("paper-1", "1")

        assert result is not None
        assert result["title"] == "Introduction"
        assert "introduction section content" in result["content"]

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_section(self, index_service, mock_db_session):
        """Test that get_paper_section returns None for nonexistent section."""
        mock_extraction = MagicMock()
        mock_extraction.structured_data = {
            "sections": {
                "1": {"title": "Introduction", "content": "..."}
            }
        }

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_extraction
        mock_db_session.execute.return_value = mock_result

        result = await index_service.get_paper_section("paper-1", "99")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_no_extraction(self, index_service, mock_db_session):
        """Test that get_paper_section returns None when no extraction exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await index_service.get_paper_section("paper-1", "1")

        assert result is None


# ============================================================
# LiteratureContextMiddleware Tests
# ============================================================

class TestLiteratureContextMiddleware:
    """Tests for LiteratureContextMiddleware."""

    @pytest.mark.asyncio
    async def test_injects_literature_context(self, literature_middleware, index_service):
        """Test that middleware injects _literature_context with TOC summary."""
        state = ThreadState(
            messages=[],
            workspace_id="workspace-1",
        )
        config = {"configurable": {}}

        with patch.object(
            index_service,
            'get_workspace_toc_summary',
            return_value="## 文献库概览\n\n### [1] Test Paper (2020)\n- 目录: 1. Intro"
        ):
            result = await literature_middleware.before_model(state, config)

        assert "_literature_context" in result
        assert "## 文献库概览" in result["_literature_context"]

    @pytest.mark.asyncio
    async def test_skips_without_workspace_id(self, literature_middleware):
        """Test that middleware skips when no workspace_id is present."""
        state = ThreadState(messages=[])
        config = {"configurable": {}}

        result = await literature_middleware.before_model(state, config)

        # Should return state without adding literature context
        assert "_literature_context" not in result or result.get("_literature_context") == ""

    @pytest.mark.asyncio
    async def test_handles_empty_workspace(self, literature_middleware, index_service):
        """Test that middleware handles workspace with no papers gracefully."""
        state = ThreadState(
            messages=[],
            workspace_id="workspace-empty",
        )
        config = {"configurable": {}}

        with patch.object(
            index_service,
            'get_workspace_toc_summary',
            return_value=""
        ):
            result = await literature_middleware.before_model(state, config)

        # When there are no papers, the context should be empty or not set
        assert result.get("_literature_context") in ["", None] or "_literature_context" not in result

    @pytest.mark.asyncio
    async def test_context_format_matches_spec(self, literature_middleware, index_service):
        """Test that context format matches the specification."""
        state = ThreadState(
            messages=[],
            workspace_id="workspace-1",
        )
        config = {"configurable": {}}

        expected_context = """## 文献库概览

### [1] Attention Is All You Need (2017)
- 目录: 1. Introduction, 2. Background, 3. Model Architecture, 4. Experiments

### [2] BERT (2019)
- 目录: 1. Introduction, 2. Related Work, 3. BERT, 4. Experiments"""

        with patch.object(
            index_service,
            'get_workspace_toc_summary',
            return_value=expected_context
        ):
            result = await literature_middleware.before_model(state, config)

        assert result["_literature_context"] == expected_context


class TestLiteratureContextMiddlewareIntegration:
    """Integration tests for LiteratureContextMiddleware."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, mock_db_session):
        """Test full workflow from middleware to formatted context."""
        # Create real IndexService with mock db
        index_service = IndexService(mock_db_session)
        middleware = LiteratureContextMiddleware(index_service)

        # Setup mock data
        mock_paper = MagicMock()
        mock_paper.id = "paper-1"
        mock_paper.title = "Transformer Paper"
        mock_paper.year = 2017
        mock_paper.authors = [{"name": "Vaswani"}]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_paper]
        mock_db_session.execute.return_value = mock_result

        # Mock get_paper_toc
        with patch.object(
            index_service,
            'get_paper_toc',
            return_value=[
                {"number": "1", "title": "Introduction"},
                {"number": "2", "title": "Model"},
            ]
        ):
            state = ThreadState(
                messages=[],
                workspace_id="workspace-1",
            )
            config = {"configurable": {}}

            result = await middleware.before_model(state, config)

        assert "_literature_context" in result
        assert "Transformer Paper" in result["_literature_context"]
        assert "2017" in result["_literature_context"]
