"""Tests for paper extraction service."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import uuid

from src.academic.services.extraction_service import (
    ExtractionService,
    ExtractionError,
    FileNotFoundError,
)
from src.database import Paper, PaperExtraction, PaperSection


from src.academic.literature.extraction.pdf_extractor import PDFExtractor


class TestExtractionService:
    """Tests for ExtractionService class."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create ExtractionService instance."""
        return ExtractionService(mock_db_session)

    @pytest.fixture
    def sample_paper_id(self):
        """Sample paper UUID."""
        return str(uuid.uuid4())

    @pytest.fixture
    def sample_workspace_id(self):
        """Sample workspace UUID."""
        return str(uuid.uuid4())

    @pytest.fixture
    def mock_paper(self, sample_paper_id):
        """Create a mock Paper instance."""
        paper = MagicMock(spec=Paper)
        paper.id = sample_paper_id
        paper.file_path = "/path/to/paper.pdf"
        return paper

    @pytest.fixture
    def mock_pdf_document(self):
        """Create a mock PDF document with TOC."""
        mock_doc = MagicMock()
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=None)

        # Mock metadata
        mock_doc.metadata = {
            "title": "Attention Is All You Need",
            "author": "Vaswani, Shazeer, Parmar",
            "format": "PDF 1.4",
        }
        mock_doc.page_count = 15

        # Mock TOC
        mock_doc.get_toc.return_value = [
            [1, "Introduction", 1],
            [1, "Background", 3],
            [1, "Model Architecture", 4],
            [2, "Encoder", 5],
            [2, "Decoder", 7],
            [1, "Experiments", 8],
            [1, "Conclusion", 12],
        ]

        return mock_doc


class TestExtractPaper(TestExtractionService):
    """Tests for extract_paper method."""

    def test_extract_paper_file_not_found(self, service, sample_paper_id):
        """Test extraction with non-existent file."""
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(FileNotFoundError) as exc_info:
                import asyncio
                asyncio.run(service.extract_paper(sample_paper_id, "/nonexistent.pdf"))

            assert "PDF file not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_paper_returns_existing(
        self,
        service,
        sample_paper_id,
        mock_db_session,
    ):
        """Test that extract_paper returns existing extraction if found."""
        # Mock existing extraction
        existing_extraction = MagicMock(spec=PaperExtraction)
        existing_extraction.paper_id = sample_paper_id
        existing_extraction.tier = 1

        # Mock get_extraction to return existing
        with patch.object(
            service,
            "get_extraction",
            return_value=existing_extraction,
        ):
            with patch("pathlib.Path.exists", return_value=True):
                result = await service.extract_paper(
                    sample_paper_id,
                    "/path/to/paper.pdf",
                    tier=1,
                )

        assert result == existing_extraction

    @pytest.mark.asyncio
    async def test_extract_paper_tier1_creates_extraction(
        self,
        service,
        sample_paper_id,
        mock_db_session,
    ):
        """Test Tier 1 extraction creates PaperExtraction record."""
        # Mock PDFExtractor methods
        mock_metadata = {
            "title": "Attention Is All You Need",
            "authors": "Vaswani, Shazeer, Parmar",
            "page_count": 15,
        }
        mock_toc = [
            {"title": "Introduction", "page": 1, "level": 1},
            {"title": "Background", "page": 3, "level": 1},
            {"title": "Conclusion", "page": 12, "level": 1},
        ]
        mock_sections = [
            {"title": "Introduction", "page_start": 1, "page_end": 2, "content": "Intro content", "level": 1},
            {"title": "Background", "page_start": 3, "page_end": 11, "content": "Background content", "level": 1},
            {"title": "Conclusion", "page_start": 12, "page_end": 15, "content": "Conclusion content", "level": 1},
        ]

        with patch.object(service, "get_extraction", return_value=None):
            with patch.object(
                service.pdf_extractor,
                "extract_metadata",
                return_value=mock_metadata,
            ):
                with patch.object(
                    service.pdf_extractor,
                    "extract_toc",
                    return_value=mock_toc,
                ):
                    with patch.object(
                        service.pdf_extractor,
                        "split_into_sections",
                        return_value=mock_sections,
                    ):
                        with patch("pathlib.Path.exists", return_value=True):
                            result = await service.extract_paper(
                                sample_paper_id,
                                "/path/to/paper.pdf",
                                tier=1,
                            )

        # Verify extraction was added to database
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

        # Verify extraction properties
        added_extraction = mock_db_session.add.call_args[0][0]
        assert added_extraction.paper_id == sample_paper_id
        assert added_extraction.tier == 1
        assert added_extraction.model_used == "pymupdf"
        assert "metadata" in added_extraction.structured_data
        assert "toc" in added_extraction.structured_data
        assert "full_text" in added_extraction.structured_data

    @pytest.mark.asyncio
    async def test_extract_paper_tier2_depends_on_tier1(
        self,
        service,
        sample_paper_id,
        mock_db_session,
    ):
        """Test Tier 2 extraction uses Tier 1 as base."""
        # Mock Tier 1 extraction
        tier1_extraction = MagicMock(spec=PaperExtraction)
        tier1_extraction.structured_data = {
            "metadata": {"title": "Test"},
            "toc": [],
            "full_text": "Test content",
        }

        def mock_get_extraction(paper_id, tier=None):
            """Return different values based on tier parameter."""
            if tier == 2:
                return None  # No existing Tier 2 extraction
            elif tier == 1:
                return tier1_extraction
            return None

        with patch.object(
            service,
            "get_extraction",
            side_effect=mock_get_extraction,
        ):
            with patch("pathlib.Path.exists", return_value=True):
                result = await service.extract_paper(
                    sample_paper_id,
                    "/path/to/paper.pdf",
                    tier=2,
                )

        # Verify extraction was added
        mock_db_session.add.assert_called_once()
        added_extraction = mock_db_session.add.call_args[0][0]
        assert added_extraction.tier == 2
        assert added_extraction.structured_data.get("llm_enhanced") is True

    @pytest.mark.asyncio
    async def test_extract_paper_invalid_tier(
        self,
        service,
        sample_paper_id,
        mock_db_session,
    ):
        """Test extraction with invalid tier raises error."""
        with patch.object(service, "get_extraction", return_value=None):
            with patch("pathlib.Path.exists", return_value=True):
                with pytest.raises(ExtractionError) as exc_info:
                    await service.extract_paper(
                        sample_paper_id,
                        "/path/to/paper.pdf",
                        tier=3,
                    )

                assert "Invalid extraction tier" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_paper_records_processing_time(
        self,
        service,
        sample_paper_id,
        mock_db_session,
    ):
        """Test that extraction records processing time."""
        with patch.object(service, "get_extraction", return_value=None):
            with patch("pathlib.Path.exists", return_value=True):
                with patch.object(service, "_extract_tier1") as mock_extract_tier1:
                    result = await service.extract_paper(
                        sample_paper_id,
                        "/path/to/paper.pdf",
                        tier=1,
                    )

        # Processing time should be set
        assert result.processing_time_ms is not None
        assert result.processing_time_ms >= 0


class TestExtractSections(TestExtractionService):
    """Tests for extract_sections method."""

    @pytest.mark.asyncio
    async def test_extract_sections_file_not_found(
        self,
        service,
        sample_paper_id,
        sample_workspace_id,
    ):
        """Test section extraction with non-existent file."""
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(FileNotFoundError) as exc_info:
                await service.extract_sections(
                    sample_paper_id,
                    sample_workspace_id,
                    "/nonexistent.pdf",
                )

            assert "PDF file not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_sections_returns_existing(
        self,
        service,
        sample_paper_id,
        sample_workspace_id,
        mock_db_session,
    ):
        """Test that extract_sections returns existing sections if found."""
        existing_sections = [MagicMock(spec=PaperSection)]

        with patch.object(
            service,
            "_get_existing_sections",
            return_value=existing_sections,
        ):
            with patch("pathlib.Path.exists", return_value=True):
                result = await service.extract_sections(
                    sample_paper_id,
                    sample_workspace_id,
                    "/path/to/paper.pdf",
                )

        assert result == existing_sections
        # Should not add new sections
        mock_db_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_sections_creates_paper_sections(
        self,
        service,
        sample_paper_id,
        sample_workspace_id,
        mock_db_session,
        mock_pdf_document,
    ):
        """Test that extract_sections creates PaperSection records."""
        with patch.object(service, "_get_existing_sections", return_value=[]):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("fitz.open", return_value=mock_pdf_document):
                    # Setup mock pages
                    mock_pages = []
                    for i in range(15):
                        mock_page = MagicMock()
                        mock_page.get_text.return_value = f"Content of page {i + 1}"
                        mock_pages.append(mock_page)

                    mock_doc = mock_pdf_document
                    mock_doc.load_page = lambda idx: mock_pages[idx]

                    result = await service.extract_sections(
                        sample_paper_id,
                        sample_workspace_id,
                        "/path/to/paper.pdf",
                    )

        # Verify sections were created
        assert mock_db_session.add.call_count == 7  # 7 TOC entries
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_sections_rolls_back_on_error(
        self,
        service,
        sample_paper_id,
        sample_workspace_id,
        mock_db_session,
    ):
        """Test that extraction rolls back on error."""
        with patch.object(service, "_get_existing_sections", return_value=[]):
            with patch("pathlib.Path.exists", return_value=True):
                with patch(
                    "fitz.open",
                    side_effect=Exception("PDF read error"),
                ):
                    with pytest.raises(ExtractionError):
                        await service.extract_sections(
                            sample_paper_id,
                            sample_workspace_id,
                            "/path/to/paper.pdf",
                        )

        mock_db_session.rollback.assert_called_once()


class TestGetOrExtract(TestExtractionService):
    """Tests for get_or_extract method."""

    @pytest.mark.asyncio
    async def test_get_or_extract_with_file(
        self,
        service,
        mock_paper,
        sample_workspace_id,
        mock_db_session,
        mock_pdf_document,
    ):
        """Test get_or_extract with a paper that has a file."""
        mock_extraction = MagicMock(spec=PaperExtraction)
        mock_sections = [MagicMock(spec=PaperSection)]

        with patch.object(
            service,
            "extract_paper",
            return_value=mock_extraction,
        ):
            with patch.object(
                service,
                "extract_sections",
                return_value=mock_sections,
            ):
                extraction, sections = await service.get_or_extract(
                    mock_paper,
                    sample_workspace_id,
                    tier=1,
                )

        assert extraction == mock_extraction
        assert sections == mock_sections

    @pytest.mark.asyncio
    async def test_get_or_extract_without_file(
        self,
        service,
        sample_workspace_id,
    ):
        """Test get_or_extract with a paper without file."""
        paper = MagicMock(spec=Paper)
        paper.id = str(uuid.uuid4())
        paper.file_path = None

        extraction, sections = await service.get_or_extract(
            paper,
            sample_workspace_id,
            tier=1,
        )

        assert extraction is None
        assert sections == []

    @pytest.mark.asyncio
    async def test_get_or_extract_handles_extraction_error(
        self,
        service,
        mock_paper,
        sample_workspace_id,
        mock_db_session,
    ):
        """Test that get_or_extract handles extraction errors gracefully."""
        with patch.object(
            service,
            "extract_paper",
            side_effect=ExtractionError("Extraction failed"),
        ):
            with patch.object(
                service,
                "extract_sections",
                return_value=[],
            ):
                extraction, sections = await service.get_or_extract(
                    mock_paper,
                    sample_workspace_id,
                    tier=1,
                )

        assert extraction is None
        assert sections == []


class TestGetExtraction(TestExtractionService):
    """Tests for get_extraction method."""

    @pytest.mark.asyncio
    async def test_get_extraction_returns_latest(
        self,
        service,
        sample_paper_id,
        mock_db_session,
    ):
        """Test that get_extraction returns latest extraction."""
        mock_extraction = MagicMock(spec=PaperExtraction)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_extraction

        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_extraction(sample_paper_id, tier=1)

        assert result == mock_extraction

    @pytest.mark.asyncio
    async def test_get_extraction_without_tier(
        self,
        service,
        sample_paper_id,
        mock_db_session,
    ):
        """Test get_extraction without tier filter."""
        mock_extraction = MagicMock(spec=PaperExtraction)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_extraction

        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_extraction(sample_paper_id)

        assert result == mock_extraction


class TestGetSections(TestExtractionService):
    """Tests for get_sections and get_section_by_path methods."""

    @pytest.mark.asyncio
    async def test_get_sections(
        self,
        service,
        sample_paper_id,
        sample_workspace_id,
        mock_db_session,
    ):
        """Test get_sections returns sections."""
        mock_sections = [MagicMock(spec=PaperSection)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_sections

        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_sections(sample_paper_id, sample_workspace_id)

        assert result == mock_sections

    @pytest.mark.asyncio
    async def test_get_section_by_path(
        self,
        service,
        sample_paper_id,
        sample_workspace_id,
        mock_db_session,
    ):
        """Test get_section_by_path returns correct section."""
        mock_section = MagicMock(spec=PaperSection)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_section

        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_section_by_path(
            sample_paper_id,
            sample_workspace_id,
            "1.2.3",
        )

        assert result == mock_section


class TestDeleteOperations(TestExtractionService):
    """Tests for delete operations."""

    @pytest.mark.asyncio
    async def test_delete_extractions(
        self,
        service,
        sample_paper_id,
        mock_db_session,
    ):
        """Test delete_extractions removes extractions."""
        mock_extraction = MagicMock(spec=PaperExtraction)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_extraction]

        mock_db_session.execute = AsyncMock(return_value=mock_result)

        count = await service.delete_extractions(sample_paper_id, tier=1)

        assert count == 1
        mock_db_session.delete.assert_called_once_with(mock_extraction)
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_sections(
        self,
        service,
        sample_paper_id,
        sample_workspace_id,
        mock_db_session,
    ):
        """Test delete_sections removes sections."""
        mock_section = MagicMock(spec=PaperSection)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_section]

        mock_db_session.execute = AsyncMock(return_value=mock_result)

        count = await service.delete_sections(sample_paper_id, sample_workspace_id)

        assert count == 1
        mock_db_session.delete.assert_called_once_with(mock_section)
        mock_db_session.commit.assert_called_once()


class TestRefreshExtraction(TestExtractionService):
    """Tests for refresh_extraction method."""

    @pytest.mark.asyncio
    async def test_refresh_extraction(
        self,
        service,
        sample_paper_id,
        mock_db_session,
        mock_pdf_document,
    ):
        """Test refresh_extraction deletes and re-extracts."""
        new_extraction = MagicMock(spec=PaperExtraction)

        with patch.object(
            service,
            "delete_extractions",
            return_value=1,
        ):
            with patch.object(
                service,
                "extract_paper",
                return_value=new_extraction,
            ):
                result = await service.refresh_extraction(
                    sample_paper_id,
                    "/path/to/paper.pdf",
                    tier=1,
                )

        assert result == new_extraction


class TestGenerateSectionPath(TestExtractionService):
    """Tests for _generate_section_path method."""

    def test_generate_section_path_simple(self, service):
        """Test path generation for simple TOC."""
        toc = [
            {"title": "Introduction", "page": 1, "level": 1},
            {"title": "Background", "page": 3, "level": 1},
            {"title": "Conclusion", "page": 5, "level": 1},
        ]

        assert service._generate_section_path(0, toc) == "1"
        assert service._generate_section_path(1, toc) == "2"
        assert service._generate_section_path(2, toc) == "3"

    def test_generate_section_path_nested(self, service):
        """Test path generation for nested TOC."""
        toc = [
            {"title": "Introduction", "page": 1, "level": 1},
            {"title": "Background", "page": 2, "level": 1},
            {"title": "Related Work", "page": 2, "level": 2},
            {"title": "Method", "page": 4, "level": 1},
            {"title": "Architecture", "page": 4, "level": 2},
            {"title": "Details", "page": 5, "level": 3},
            {"title": "Experiments", "page": 8, "level": 1},
        ]

        assert service._generate_section_path(0, toc) == "1"
        assert service._generate_section_path(1, toc) == "2"
        assert service._generate_section_path(2, toc) == "2.1"
        assert service._generate_section_path(3, toc) == "3"
        assert service._generate_section_path(4, toc) == "3.1"
        assert service._generate_section_path(5, toc) == "3.1.1"
        assert service._generate_section_path(6, toc) == "4"

    def test_generate_section_path_empty_toc(self, service):
        """Test path generation with empty TOC."""
        assert service._generate_section_path(0, []) == "1"

    def test_generate_section_path_index_out_of_range(self, service):
        """Test path generation with index beyond TOC length."""
        toc = [{"title": "Intro", "page": 1, "level": 1}]
        assert service._generate_section_path(5, toc) == "6"


class TestTierConstants(TestExtractionService):
    """Tests for tier constants."""

    def test_tier_constants(self, service):
        """Test that tier constants are defined correctly."""
        assert service.TIER_ENGINEERING == 1
        assert service.TIER_LLM == 2

    def test_extraction_type_constants(self, service):
        """Test that extraction type constants are defined."""
        assert service.TYPE_METADATA == "metadata"
        assert service.TYPE_FULL_TEXT == "full_text"
        assert service.TYPE_TOC == "toc"
        assert service.TYPE_SECTIONS == "sections"

    def test_llm_model_constants(self, service):
        """Test that LLM model constants are defined."""
        assert service.LLM_MODEL_FAST == "claude-3-haiku"
        assert service.LLM_MODEL_BALANCED == "qwen-turbo"
