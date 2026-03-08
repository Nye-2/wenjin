"""Tests for PDF extraction service with TOC support."""

import pytest
from unittest.mock import MagicMock, patch

from src.academic.literature.extraction.pdf_extractor import PDFExtractor


class TestPDFExtractor:
    """Tests for PDFExtractor class."""

    @pytest.fixture
    def extractor(self):
        """Create PDFExtractor instance."""
        return PDFExtractor()

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
            [1, "Background", 2],
            [1, "Model Architecture", 3],
            [2, "Encoder", 4],
            [2, "Decoder", 5],
            [1, "Experiments", 8],
            [1, "Conclusion", 12],
        ]

        return mock_doc

    @pytest.fixture
    def mock_pdf_no_toc(self):
        """Create a mock PDF document without TOC."""
        mock_doc = MagicMock()
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=None)

        mock_doc.metadata = {
            "title": "",
            "author": "",
        }
        mock_doc.page_count = 10
        mock_doc.get_toc.return_value = []

        return mock_doc


class TestExtractToc(TestPDFExtractor):
    """Tests for extract_toc method."""

    def test_extract_toc_with_valid_toc(self, extractor, mock_pdf_document):
        """Test TOC extraction with a valid TOC."""
        with patch("fitz.open", return_value=mock_pdf_document):
            result = extractor.extract_toc("/path/to/paper.pdf")

        assert len(result) == 7
        assert result[0] == {"title": "Introduction", "page": 1, "level": 1}
        assert result[3] == {"title": "Encoder", "page": 4, "level": 2}

    def test_extract_toc_empty_toc(self, extractor, mock_pdf_no_toc):
        """Test TOC extraction when PDF has no TOC."""
        with patch("fitz.open", return_value=mock_pdf_no_toc):
            result = extractor.extract_toc("/path/to/paper.pdf")

        assert result == []

    def test_extract_toc_file_not_found(self, extractor):
        """Test TOC extraction with non-existent file."""
        with patch("fitz.open", side_effect=FileNotFoundError("File not found")):
            with pytest.raises(FileNotFoundError):
                extractor.extract_toc("/nonexistent/path.pdf")

    def test_extract_toc_structure(self, extractor, mock_pdf_document):
        """Test that TOC extraction returns correct structure."""
        with patch("fitz.open", return_value=mock_pdf_document):
            result = extractor.extract_toc("/path/to/paper.pdf")

        for entry in result:
            assert "title" in entry
            assert "page" in entry
            assert "level" in entry
            assert isinstance(entry["title"], str)
            assert isinstance(entry["page"], int)
            assert isinstance(entry["level"], int)


class TestExtractMetadata(TestPDFExtractor):
    """Tests for extract_metadata method."""

    def test_extract_metadata_complete(self, extractor, mock_pdf_document):
        """Test metadata extraction with complete metadata."""
        with patch("fitz.open", return_value=mock_pdf_document):
            result = extractor.extract_metadata("/path/to/paper.pdf")

        assert result["title"] == "Attention Is All You Need"
        assert result["authors"] == "Vaswani, Shazeer, Parmar"
        assert result["page_count"] == 15

    def test_extract_metadata_missing_fields(self, extractor, mock_pdf_no_toc):
        """Test metadata extraction with missing fields."""
        with patch("fitz.open", return_value=mock_pdf_no_toc):
            result = extractor.extract_metadata("/path/to/paper.pdf")

        assert result["title"] == ""
        assert result["authors"] == ""
        assert result["page_count"] == 10

    def test_extract_metadata_structure(self, extractor, mock_pdf_document):
        """Test that metadata extraction returns correct structure."""
        with patch("fitz.open", return_value=mock_pdf_document):
            result = extractor.extract_metadata("/path/to/paper.pdf")

        assert "title" in result
        assert "authors" in result
        assert "page_count" in result


class TestExtractSectionContent(TestPDFExtractor):
    """Tests for extract_section_content method."""

    @pytest.fixture
    def mock_pdf_with_pages(self):
        """Create a mock PDF with page content."""
        mock_doc = MagicMock()
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=None)
        mock_doc.page_count = 10

        # Create mock pages
        mock_pages = []
        for i in range(10):
            mock_page = MagicMock()
            mock_page.get_text.return_value = f"Content of page {i + 1}\n"
            mock_pages.append(mock_page)

        mock_doc.__getitem__ = lambda self, idx: mock_pages[idx]
        mock_doc.load_page = lambda idx: mock_pages[idx]

        return mock_doc

    def test_extract_section_content_single_page(self, extractor, mock_pdf_with_pages):
        """Test extracting content from a single page."""
        with patch("fitz.open", return_value=mock_pdf_with_pages):
            result = extractor.extract_section_content("/path/to/paper.pdf", 1)

        assert "Content of page 1" in result
        assert "Content of page 2" not in result

    def test_extract_section_content_page_range(self, extractor, mock_pdf_with_pages):
        """Test extracting content from a page range."""
        with patch("fitz.open", return_value=mock_pdf_with_pages):
            result = extractor.extract_section_content(
                "/path/to/paper.pdf", 1, page_end=3
            )

        assert "Content of page 1" in result
        assert "Content of page 2" in result
        assert "Content of page 3" in result
        assert "Content of page 4" not in result

    def test_extract_section_content_same_start_end(self, extractor, mock_pdf_with_pages):
        """Test extracting content when start and end are the same."""
        with patch("fitz.open", return_value=mock_pdf_with_pages):
            result = extractor.extract_section_content(
                "/path/to/paper.pdf", 5, page_end=5
            )

        assert "Content of page 5" in result

    def test_extract_section_content_no_end_page(self, extractor, mock_pdf_with_pages):
        """Test extracting content without end page (only start page)."""
        with patch("fitz.open", return_value=mock_pdf_with_pages):
            result = extractor.extract_section_content("/path/to/paper.pdf", 3)

        assert "Content of page 3" in result
        assert "Content of page 4" not in result

    def test_extract_section_content_invalid_page(self, extractor, mock_pdf_with_pages):
        """Test extracting content with invalid page number."""
        with patch("fitz.open", return_value=mock_pdf_with_pages):
            # Page numbers are 1-indexed for user, should handle gracefully
            result = extractor.extract_section_content("/path/to/paper.pdf", 0)
            # Should handle this gracefully (either empty or first page)
            assert isinstance(result, str)


class TestSplitIntoSections(TestPDFExtractor):
    """Tests for split_into_sections method."""

    @pytest.fixture
    def mock_pdf_for_split(self):
        """Create a mock PDF for section splitting tests."""
        mock_doc = MagicMock()
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=None)
        mock_doc.page_count = 12

        # Create mock pages with section content
        page_contents = {
            0: "Introduction content about the paper...",
            1: "More introduction...",
            2: "Background on transformers...",
            3: "Model Architecture description...",
            4: "Encoder details...",
            5: "More encoder...",
            6: "Decoder details...",
            7: "Experiments section...",
            8: "Results and analysis...",
            9: "Discussion...",
            10: "Conclusion...",
            11: "References...",
        }

        mock_pages = []
        for i in range(12):
            mock_page = MagicMock()
            mock_page.get_text.return_value = page_contents.get(i, f"Page {i + 1}")
            mock_pages.append(mock_page)

        mock_doc.__getitem__ = lambda self, idx: mock_pages[idx]
        mock_doc.load_page = lambda idx: mock_pages[idx]

        return mock_doc

    @pytest.fixture
    def sample_toc(self):
        """Sample TOC for testing."""
        return [
            {"title": "Introduction", "page": 1, "level": 1},
            {"title": "Background", "page": 3, "level": 1},
            {"title": "Model Architecture", "page": 4, "level": 1},
            {"title": "Encoder", "page": 5, "level": 2},
            {"title": "Decoder", "page": 7, "level": 2},
            {"title": "Experiments", "page": 8, "level": 1},
            {"title": "Conclusion", "page": 11, "level": 1},
        ]

    def test_split_into_sections_basic(self, extractor, mock_pdf_for_split, sample_toc):
        """Test basic section splitting."""
        with patch("fitz.open", return_value=mock_pdf_for_split):
            result = extractor.split_into_sections("/path/to/paper.pdf", sample_toc)

        assert len(result) == 7

        # Check first section (Introduction: pages 1-2)
        intro_section = result[0]
        assert intro_section["title"] == "Introduction"
        assert intro_section["page_start"] == 1
        assert intro_section["page_end"] == 2
        assert "Introduction content" in intro_section["content"]
        assert "level" in intro_section
        assert intro_section["level"] == 1

    def test_split_into_sections_last_section(self, extractor, mock_pdf_for_split, sample_toc):
        """Test that last section gets correct page_end (end of document)."""
        with patch("fitz.open", return_value=mock_pdf_for_split):
            result = extractor.split_into_sections("/path/to/paper.pdf", sample_toc)

        last_section = result[-1]
        assert last_section["title"] == "Conclusion"
        assert last_section["page_start"] == 11
        assert last_section["page_end"] == 12  # Should extend to end of document

    def test_split_into_sections_nested_levels(self, extractor, mock_pdf_for_split, sample_toc):
        """Test that nested sections (level 2) are handled correctly."""
        with patch("fitz.open", return_value=mock_pdf_for_split):
            result = extractor.split_into_sections("/path/to/paper.pdf", sample_toc)

        encoder_section = result[3]
        assert encoder_section["title"] == "Encoder"
        assert encoder_section["level"] == 2
        assert encoder_section["page_start"] == 5
        assert encoder_section["page_end"] == 6

    def test_split_into_sections_empty_toc(self, extractor, mock_pdf_for_split):
        """Test splitting with empty TOC."""
        with patch("fitz.open", return_value=mock_pdf_for_split):
            result = extractor.split_into_sections("/path/to/paper.pdf", [])

        assert result == []

    def test_split_into_sections_structure(self, extractor, mock_pdf_for_split, sample_toc):
        """Test that each section has required fields."""
        with patch("fitz.open", return_value=mock_pdf_for_split):
            result = extractor.split_into_sections("/path/to/paper.pdf", sample_toc)

        required_fields = {"title", "page_start", "page_end", "content", "level"}
        for section in result:
            for field in required_fields:
                assert field in section, f"Missing field: {field}"

    def test_split_into_sections_preserves_order(self, extractor, mock_pdf_for_split, sample_toc):
        """Test that sections are returned in TOC order."""
        with patch("fitz.open", return_value=mock_pdf_for_split):
            result = extractor.split_into_sections("/path/to/paper.pdf", sample_toc)

        titles = [s["title"] for s in result]
        expected_titles = ["Introduction", "Background", "Model Architecture",
                          "Encoder", "Decoder", "Experiments", "Conclusion"]
        assert titles == expected_titles

    def test_split_into_sections_single_section(self, extractor, mock_pdf_for_split):
        """Test splitting with single section."""
        toc = [{"title": "Full Document", "page": 1, "level": 1}]

        with patch("fitz.open", return_value=mock_pdf_for_split):
            result = extractor.split_into_sections("/path/to/paper.pdf", toc)

        assert len(result) == 1
        assert result[0]["page_start"] == 1
        assert result[0]["page_end"] == 12  # Should be total page count
