"""Tests for citation LLM tools."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.academic.citation import tools as citation_tools


class TestFormatCitationTool:
    """Tests for format_citation tool."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def sample_paper_id(self):
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_format_citation_apa(self, mock_db, sample_paper_id):
        """Test format_citation with APA style."""
        # Mock paper
        mock_paper = MagicMock()
        mock_paper.id = sample_paper_id
        mock_paper.title = "Test Paper"
        mock_paper.authors = [{"name": "John Smith"}]
        mock_paper.year = 2024
        mock_paper.venue = "Test Journal"
        mock_paper.doi = "10.1234/test"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_paper
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Call the underlying coroutine directly
        result = await citation_tools.format_citation.coroutine(
            paper_id=sample_paper_id,
            style="apa",
            in_text=False,
            db=mock_db,
        )

        assert "Smith" in result
        assert "2024" in result

    @pytest.mark.asyncio
    async def test_format_citation_not_found(self, mock_db):
        """Test format_citation with non-existent paper."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await citation_tools.format_citation.coroutine(
            paper_id="non-existent",
            style="apa",
            in_text=False,
            db=mock_db,
        )

        assert "not found" in result.lower()


class TestFormatBibliographyTool:
    """Tests for format_bibliography tool."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def sample_workspace_id(self):
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_format_bibliography(self, mock_db, sample_workspace_id):
        """Test format_bibliography tool."""
        # Mock papers
        mock_paper = MagicMock()
        mock_paper.title = "First Paper"
        mock_paper.authors = [{"name": "John Smith"}]
        mock_paper.year = 2024
        mock_paper.venue = "Test Journal"
        mock_paper.doi = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_paper]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await citation_tools.format_bibliography.coroutine(
            workspace_id=sample_workspace_id,
            style="apa",
            db=mock_db,
        )

        assert "First Paper" in result

    @pytest.mark.asyncio
    async def test_format_bibliography_empty(self, mock_db, sample_workspace_id):
        """Test format_bibliography with empty workspace."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await citation_tools.format_bibliography.coroutine(
            workspace_id=sample_workspace_id,
            style="apa",
            db=mock_db,
        )

        assert "no papers" in result.lower()


class TestBibTeXTools:
    """Tests for BibTeX import/export tools."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def sample_workspace_id(self):
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_export_bibtex(self, mock_db, sample_workspace_id):
        """Test export_bibtex tool."""
        mock_paper = MagicMock()
        mock_paper.title = "Test Paper"
        mock_paper.authors = [{"name": "John Smith"}]
        mock_paper.year = 2024
        mock_paper.venue = "Test Journal"
        mock_paper.doi = "10.1234/test"
        mock_paper.abstract = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_paper]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await citation_tools.export_bibtex.coroutine(
            workspace_id=sample_workspace_id,
            db=mock_db,
        )

        assert "@article" in result or "@misc" in result
        assert "Test Paper" in result

    @pytest.mark.asyncio
    async def test_export_bibtex_empty(self, mock_db, sample_workspace_id):
        """Test export_bibtex with empty workspace."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await citation_tools.export_bibtex.coroutine(
            workspace_id=sample_workspace_id,
            db=mock_db,
        )

        assert "no papers" in result.lower()

    @pytest.mark.asyncio
    async def test_import_bibtex(self, mock_db, sample_workspace_id):
        """Test import_bibtex tool."""
        bibtex_content = """
@article{test2024,
  author = {John Smith},
  title = {Test Paper},
  journal = {Test Journal},
  year = {2024}
}
"""
        # Mock paper service
        with patch("src.academic.citation.tools.PaperService") as mock_service:
            mock_instance = mock_service.return_value
            mock_paper = MagicMock()
            mock_paper.title = "Test Paper"
            mock_instance.create = AsyncMock(return_value=mock_paper)
            mock_instance.add_to_workspace = AsyncMock()

            result = await citation_tools.import_bibtex.coroutine(
                bibtex_content=bibtex_content,
                workspace_id=sample_workspace_id,
                db=mock_db,
            )

            assert "imported" in result.lower() or "success" in result.lower()

    @pytest.mark.asyncio
    async def test_import_bibtex_empty(self, mock_db, sample_workspace_id):
        """Test import_bibtex with empty content."""
        result = await citation_tools.import_bibtex.coroutine(
            bibtex_content="",
            workspace_id=sample_workspace_id,
            db=mock_db,
        )

        assert "no valid" in result.lower()


class TestGetCitationGraphTool:
    """Tests for get_citation_graph tool."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def sample_paper_id(self):
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_citation_graph(self, mock_db, sample_paper_id):
        """Test get_citation_graph tool."""
        # Mock workspace association
        mock_workspace_result = MagicMock()
        mock_workspace_result.first.return_value = (str(uuid.uuid4()),)

        # Mock citations
        mock_citation = MagicMock()
        mock_citation.cited_paper_id = str(uuid.uuid4())
        mock_citation.citation_type = "explicit"

        mock_citation_result = MagicMock()
        mock_citation_result.scalars.return_value.all.return_value = [mock_citation]

        mock_empty_result = MagicMock()
        mock_empty_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(
            side_effect=[mock_workspace_result, mock_citation_result, mock_empty_result]
        )

        result = await citation_tools.get_citation_graph.coroutine(
            paper_id=sample_paper_id,
            depth=1,
            db=mock_db,
        )

        assert "nodes" in result
        assert "edges" in result

    @pytest.mark.asyncio
    async def test_get_citation_graph_not_found(self, mock_db):
        """Test get_citation_graph with non-existent paper."""
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await citation_tools.get_citation_graph.coroutine(
            paper_id="non-existent",
            depth=1,
            db=mock_db,
        )

        assert "error" in result


class TestAddCitationTool:
    """Tests for add_citation tool."""

    @pytest.fixture
    def mock_db(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.add = MagicMock()
        session.refresh = AsyncMock()
        return session

    @pytest.fixture
    def sample_ids(self):
        return {
            "paper_id": str(uuid.uuid4()),
            "cited_paper_id": str(uuid.uuid4()),
            "workspace_id": str(uuid.uuid4()),
        }

    @pytest.mark.asyncio
    async def test_add_citation_tool(self, mock_db, sample_ids):
        """Test add_citation tool."""
        # Mock paper existence checks - return True for both papers
        mock_result = MagicMock()
        mock_result.first.return_value = True
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await citation_tools.add_citation.coroutine(
            paper_id=sample_ids["paper_id"],
            cited_paper_id=sample_ids["cited_paper_id"],
            workspace_id=sample_ids["workspace_id"],
            citation_context="As shown in previous work",
            section="Related Work",
            db=mock_db,
        )

        assert "success" in result.lower() or "added" in result.lower()

    @pytest.mark.asyncio
    async def test_add_citation_paper_not_found(self, mock_db, sample_ids):
        """Test add_citation with non-existent paper."""
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await citation_tools.add_citation.coroutine(
            paper_id=sample_ids["paper_id"],
            cited_paper_id=sample_ids["cited_paper_id"],
            workspace_id=sample_ids["workspace_id"],
            db=mock_db,
        )

        assert "not found" in result.lower()


class TestToolDefinitions:
    """Tests for tool definitions and metadata."""

    def test_format_citation_tool_definition(self):
        """Test format_citation tool has correct definition."""
        assert citation_tools.format_citation.name == "format_citation"
        assert "citation" in citation_tools.format_citation.description.lower()

    def test_format_bibliography_tool_definition(self):
        """Test format_bibliography tool has correct definition."""
        assert citation_tools.format_bibliography.name == "format_bibliography"
        assert "bibliography" in citation_tools.format_bibliography.description.lower()

    def test_export_bibtex_tool_definition(self):
        """Test export_bibtex tool has correct definition."""
        assert citation_tools.export_bibtex.name == "export_bibtex"
        assert "bibtex" in citation_tools.export_bibtex.description.lower()

    def test_import_bibtex_tool_definition(self):
        """Test import_bibtex tool has correct definition."""
        assert citation_tools.import_bibtex.name == "import_bibtex"
        assert "bibtex" in citation_tools.import_bibtex.description.lower()

    def test_get_citation_graph_tool_definition(self):
        """Test get_citation_graph tool has correct definition."""
        assert citation_tools.get_citation_graph.name == "get_citation_graph"
        assert "graph" in citation_tools.get_citation_graph.description.lower()

    def test_add_citation_tool_definition(self):
        """Test add_citation tool has correct definition."""
        assert citation_tools.add_citation.name == "add_citation"
        assert "citation" in citation_tools.add_citation.description.lower()


class TestCitationToolsRegistration:
    """Tests for citation tools registration in lead agent."""

    def test_citation_tools_in_available_tools(self):
        """Test that citation tools are registered in get_available_tools."""
        from src.agents.lead_agent.agent import get_available_tools

        tools = get_available_tools()
        tool_names = [t.name for t in tools]

        assert "format_citation" in tool_names
        assert "format_bibliography" in tool_names
        assert "export_bibtex" in tool_names
        assert "import_bibtex" in tool_names
        assert "add_citation" in tool_names
