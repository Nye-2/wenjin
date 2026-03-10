"""Tests for literature navigation tools."""

from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from src.academic.literature import tools as literature_tools
from src.academic.literature.navigation.models import PaperTOC, TOCEntry, SectionContent


class TestListPapersFunction:
    """Tests for list_papers underlying function."""

    @pytest.mark.asyncio
    async def test_list_papers_with_papers(self):
        """Test listing papers with TOC."""
        # Mock database session
        mock_db = AsyncMock()

        # Mock paper objects
        mock_paper = MagicMock()
        mock_paper.id = "paper-123"
        mock_paper.title = "Attention Is All You Need"

        # Mock scalars result
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_paper]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        # Mock TocService
        mock_toc = PaperTOC(
            paper_id="paper-123",
            title="Attention Is All You Need",
            abstract="Abstract text",
            entries=[
                TOCEntry(title="1. Introduction", level=1, char_start=0, char_end=1000),
                TOCEntry(title="2. Methods", level=1, char_start=1000, char_end=2000),
            ],
        )

        with patch(
            "src.academic.literature.tools.TocService"
        ) as mock_toc_service_class:
            mock_toc_service = AsyncMock()
            mock_toc_service.get_paper_toc.return_value = mock_toc
            mock_toc_service_class.return_value = mock_toc_service

            # Call the underlying function directly, bypassing the tool wrapper
            result = await literature_tools.list_papers.coroutine(
                workspace_id="ws-123", db=mock_db
            )

        assert len(result) == 1
        assert result[0]["paper_id"] == "paper-123"
        assert result[0]["title"] == "Attention Is All You Need"
        assert len(result[0]["toc"]) == 2
        assert result[0]["toc"][0]["title"] == "1. Introduction"

    @pytest.mark.asyncio
    async def test_list_papers_empty_workspace(self):
        """Test listing papers in empty workspace."""
        mock_db = AsyncMock()

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        result = await literature_tools.list_papers.coroutine(
            workspace_id="ws-empty", db=mock_db
        )

        assert result == []


class TestGetSectionFunction:
    """Tests for get_section underlying function."""

    @pytest.mark.asyncio
    async def test_get_section_abstract(self):
        """Test getting abstract section."""
        mock_db = AsyncMock()

        mock_toc = PaperTOC(
            paper_id="paper-123",
            title="Test Paper",
            abstract="This is the abstract text.",
            entries=[],
        )

        mock_section_content = SectionContent(
            paper_id="paper-123",
            section_title="Abstract",
            content="This is the abstract text.",
            word_count=5,
        )

        with patch(
            "src.academic.literature.tools.TocService"
        ) as mock_toc_service_class, patch(
            "src.academic.literature.tools.SectionLoader"
        ) as mock_loader_class:
            mock_toc_service = AsyncMock()
            mock_toc_service.get_paper_toc.return_value = mock_toc
            mock_toc_service_class.return_value = mock_toc_service

            mock_loader = AsyncMock()
            mock_loader.get_abstract.return_value = mock_section_content
            mock_loader_class.return_value = mock_loader

            result = await literature_tools.get_section.coroutine(
                paper_id="paper-123", section_title="Abstract", db=mock_db
            )

        assert result == "This is the abstract text."

    @pytest.mark.asyncio
    async def test_get_section_specific_section(self):
        """Test getting a specific section."""
        mock_db = AsyncMock()

        mock_toc = PaperTOC(
            paper_id="paper-123",
            title="Test Paper",
            abstract="Abstract",
            entries=[
                TOCEntry(title="1. Introduction", level=1, char_start=0, char_end=500),
                TOCEntry(title="2. Methods", level=1, char_start=500, char_end=1500),
            ],
        )

        mock_section_content = SectionContent(
            paper_id="paper-123",
            section_title="2. Methods",
            content="## 2. Methods\n\nThis is the methods section.",
            word_count=10,
        )

        with patch(
            "src.academic.literature.tools.TocService"
        ) as mock_toc_service_class, patch(
            "src.academic.literature.tools.SectionLoader"
        ) as mock_loader_class:
            mock_toc_service = AsyncMock()
            mock_toc_service.get_paper_toc.return_value = mock_toc
            mock_toc_service_class.return_value = mock_toc_service

            mock_loader = AsyncMock()
            mock_loader.load_section.return_value = mock_section_content
            mock_loader_class.return_value = mock_loader

            result = await literature_tools.get_section.coroutine(
                paper_id="paper-123", section_title="2. Methods", db=mock_db
            )

        assert "2. Methods" in result
        assert "methods section" in result

    @pytest.mark.asyncio
    async def test_get_section_paper_not_found(self):
        """Test getting section when paper not found."""
        mock_db = AsyncMock()

        with patch(
            "src.academic.literature.tools.TocService"
        ) as mock_toc_service_class:
            mock_toc_service = AsyncMock()
            mock_toc_service.get_paper_toc.return_value = None
            mock_toc_service_class.return_value = mock_toc_service

            result = await literature_tools.get_section.coroutine(
                paper_id="nonexistent", section_title="Abstract", db=mock_db
            )

        assert "not found" in result

    @pytest.mark.asyncio
    async def test_get_section_not_found(self):
        """Test getting section that doesn't exist."""
        mock_db = AsyncMock()

        mock_toc = PaperTOC(
            paper_id="paper-123",
            title="Test Paper",
            abstract="Abstract",
            entries=[
                TOCEntry(title="1. Introduction", level=1, char_start=0, char_end=500),
            ],
        )

        with patch(
            "src.academic.literature.tools.TocService"
        ) as mock_toc_service_class, patch(
            "src.academic.literature.tools.SectionLoader"
        ) as mock_loader_class:
            mock_toc_service = AsyncMock()
            mock_toc_service.get_paper_toc.return_value = mock_toc
            mock_toc_service_class.return_value = mock_toc_service

            mock_loader = AsyncMock()
            mock_loader.load_section.return_value = None
            mock_loader_class.return_value = mock_loader

            result = await literature_tools.get_section.coroutine(
                paper_id="paper-123",
                section_title="Nonexistent Section",
                db=mock_db,
            )

        assert "not found" in result
        assert "Available sections" in result


class TestSearchExternalTool:
    """Tests for search_external tool."""

    @pytest.mark.asyncio
    async def test_search_external_semantic_scholar(self):
        """Test searching Semantic Scholar."""
        mock_client = AsyncMock()
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "title": "Test Paper",
            "doi": "10.1234/test",
        }
        mock_client.search.return_value = [mock_result]

        with patch(
            "src.academic.literature.tools.SemanticScholarClient",
            return_value=mock_client,
        ):
            result = await literature_tools.search_external.ainvoke(
                {"query": "machine learning", "source": "semantic_scholar", "limit": 5}
            )

        assert len(result) == 1
        assert result[0]["title"] == "Test Paper"

    @pytest.mark.asyncio
    async def test_search_external_all_sources(self):
        """Test searching all sources."""
        mock_results = [
            MagicMock(model_dump=lambda: {"title": f"Paper {i}", "source": "test"})
            for i in range(3)
        ]

        with patch(
            "src.academic.literature.tools.SemanticScholarClient"
        ) as mock_ss, patch(
            "src.academic.literature.tools.ArxivClient"
        ) as mock_arxiv, patch(
            "src.academic.literature.tools.CrossrefClient"
        ) as mock_cr, patch(
            "src.academic.literature.tools.OpenAlexClient"
        ) as mock_oa:
            # Setup mocks
            for mock_cls in [mock_ss, mock_arxiv, mock_cr, mock_oa]:
                mock_instance = AsyncMock()
                mock_instance.search.return_value = mock_results
                mock_cls.return_value = mock_instance

            result = await literature_tools.search_external.ainvoke(
                {"query": "test", "source": "all", "limit": 10}
            )

        # Should have results from all 4 sources
        assert len(result) == 12  # 3 results * 4 sources

    @pytest.mark.asyncio
    async def test_search_external_with_error(self):
        """Test search handles errors gracefully."""
        mock_client = AsyncMock()
        mock_client.search.side_effect = Exception("API Error")

        with patch(
            "src.academic.literature.tools.SemanticScholarClient",
            return_value=mock_client,
        ):
            result = await literature_tools.search_external.ainvoke(
                {"query": "test", "source": "semantic_scholar", "limit": 5}
            )

        # Should return empty list on error
        assert result == []


class TestGetPaperByDoiTool:
    """Tests for get_paper_by_doi tool."""

    @pytest.mark.asyncio
    async def test_get_paper_by_doi_found(self):
        """Test getting paper by DOI."""
        mock_client = AsyncMock()
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "title": "Test Paper",
            "doi": "10.1234/test",
        }
        mock_client.get_by_doi.return_value = mock_result

        with patch(
            "src.academic.literature.tools.SemanticScholarClient",
            return_value=mock_client,
        ), patch(
            "src.academic.literature.tools.CrossrefClient",
            return_value=AsyncMock(get_by_doi=AsyncMock(return_value=None)),
        ), patch(
            "src.academic.literature.tools.OpenAlexClient",
            return_value=AsyncMock(get_by_doi=AsyncMock(return_value=None)),
        ):
            result = await literature_tools.get_paper_by_doi.ainvoke(
                {"doi": "10.1234/test"}
            )

        assert result is not None
        assert result["title"] == "Test Paper"

    @pytest.mark.asyncio
    async def test_get_paper_by_doi_not_found(self):
        """Test getting paper by DOI when not found."""
        mock_client = AsyncMock()
        mock_client.get_by_doi.return_value = None

        with patch(
            "src.academic.literature.tools.SemanticScholarClient",
            return_value=mock_client,
        ), patch(
            "src.academic.literature.tools.CrossrefClient",
            return_value=AsyncMock(get_by_doi=AsyncMock(return_value=None)),
        ), patch(
            "src.academic.literature.tools.OpenAlexClient",
            return_value=AsyncMock(get_by_doi=AsyncMock(return_value=None)),
        ):
            result = await literature_tools.get_paper_by_doi.ainvoke(
                {"doi": "10.1234/nonexistent"}
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_paper_by_doi_fallback(self):
        """Test DOI lookup falls back to other sources."""
        # First client returns None, second returns result
        mock_client1 = AsyncMock()
        mock_client1.get_by_doi.return_value = None

        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "title": "Found in Crossref",
            "doi": "10.1234/test",
        }
        mock_client2 = AsyncMock()
        mock_client2.get_by_doi.return_value = mock_result

        with patch(
            "src.academic.literature.tools.SemanticScholarClient",
            return_value=mock_client1,
        ), patch(
            "src.academic.literature.tools.CrossrefClient",
            return_value=mock_client2,
        ), patch(
            "src.academic.literature.tools.OpenAlexClient",
            return_value=AsyncMock(get_by_doi=AsyncMock(return_value=None)),
        ):
            result = await literature_tools.get_paper_by_doi.ainvoke(
                {"doi": "10.1234/test"}
            )

        assert result is not None
        assert result["title"] == "Found in Crossref"


class TestToolDefinitions:
    """Tests for tool definitions and metadata."""

    def test_list_papers_tool_definition(self):
        """Test list_papers tool has correct definition."""
        assert literature_tools.list_papers.name == "list_papers"
        assert "workspace" in literature_tools.list_papers.description.lower()

    def test_get_section_tool_definition(self):
        """Test get_section tool has correct definition."""
        assert literature_tools.get_section.name == "get_section"
        assert "section" in literature_tools.get_section.description.lower()

    def test_search_external_tool_definition(self):
        """Test search_external tool has correct definition."""
        assert literature_tools.search_external.name == "search_external"
        assert "external" in literature_tools.search_external.description.lower()

    def test_get_paper_by_doi_tool_definition(self):
        """Test get_paper_by_doi tool has correct definition."""
        assert literature_tools.get_paper_by_doi.name == "get_paper_by_doi"
        assert "doi" in literature_tools.get_paper_by_doi.description.lower()


class TestCreateWorkspaceTool:
    """Tests for create_workspace tool."""

    @pytest.mark.asyncio
    async def test_create_workspace_basic(self):
        """Test creating a workspace with minimal args."""
        mock_db = AsyncMock()

        mock_workspace = MagicMock()
        mock_workspace.id = "ws-123"
        mock_workspace.name = "Test Workspace"
        mock_workspace.type = MagicMock()
        mock_workspace.type.value = "sci"
        mock_workspace.discipline = None
        mock_workspace.description = None

        with patch(
            "src.academic.literature.tools.WorkspaceService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.create.return_value = mock_workspace
            mock_service_class.return_value = mock_service

            result = await literature_tools.create_workspace.coroutine(
                name="Test Workspace", type="sci", db=mock_db
            )

        assert result["id"] == "ws-123"
        assert result["name"] == "Test Workspace"
        assert result["type"] == "sci"

    @pytest.mark.asyncio
    async def test_create_workspace_with_all_fields(self):
        """Test creating a workspace with all fields."""
        mock_db = AsyncMock()

        mock_workspace = MagicMock()
        mock_workspace.id = "ws-456"
        mock_workspace.name = "Thesis Workspace"
        mock_workspace.type = MagicMock()
        mock_workspace.type.value = "thesis"
        mock_workspace.discipline = "computer_science"
        mock_workspace.description = "My thesis work"

        with patch(
            "src.academic.literature.tools.WorkspaceService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.create.return_value = mock_workspace
            mock_service_class.return_value = mock_service

            result = await literature_tools.create_workspace.coroutine(
                name="Thesis Workspace",
                type="thesis",
                discipline="computer_science",
                description="My thesis work",
                db=mock_db,
            )

        assert result["discipline"] == "computer_science"
        assert result["description"] == "My thesis work"

    @pytest.mark.asyncio
    async def test_create_workspace_invalid_type(self):
        """Test creating workspace with invalid type returns error."""
        mock_db = AsyncMock()

        with patch(
            "src.academic.literature.tools.WorkspaceService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.create.side_effect = ValueError("Invalid workspace type")
            mock_service_class.return_value = mock_service

            result = await literature_tools.create_workspace.coroutine(
                name="Bad Workspace", type="invalid_type", db=mock_db
            )

        assert "error" in result
