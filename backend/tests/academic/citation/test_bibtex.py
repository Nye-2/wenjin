"""Tests for BibTeX parser and exporter."""

import pytest
from src.academic.citation.bibtex.parser import BibTeXParser


class TestBibTeXParser:
    """Tests for BibTeX parser."""

    @pytest.fixture
    def parser(self):
        return BibTeXParser()

    @pytest.fixture
    def sample_bibtex(self):
        return """
@article{vaswani2017attention,
  author = {Ashish Vaswani and Noam Shazeer and Niki Parmar},
  title = {Attention Is All You Need},
  journal = {Advances in Neural Information Processing Systems},
  year = {2017},
  doi = {10.48550/arXiv.1706.03762}
}

@inproceedings{smith2024test,
  author = {John Smith and Jane Doe},
  title = {A Test Paper},
  booktitle = {Test Conference},
  year = {2024}
}
"""

    def test_parse_entries_count(self, parser, sample_bibtex):
        """Test that parser extracts correct number of entries."""
        entries = parser.parse(sample_bibtex)
        assert len(entries) == 2

    def test_parse_entry_type(self, parser, sample_bibtex):
        """Test that parser extracts entry types."""
        entries = parser.parse(sample_bibtex)
        assert entries[0]["type"] == "article"
        assert entries[1]["type"] == "inproceedings"

    def test_parse_entry_key(self, parser, sample_bibtex):
        """Test that parser extracts entry keys."""
        entries = parser.parse(sample_bibtex)
        assert entries[0]["key"] == "vaswani2017attention"
        assert entries[1]["key"] == "smith2024test"

    def test_parse_entry_fields(self, parser, sample_bibtex):
        """Test that parser extracts entry fields."""
        entries = parser.parse(sample_bibtex)
        assert entries[0]["title"] == "Attention Is All You Need"
        assert entries[0]["year"] == "2017"
        assert entries[0]["doi"] == "10.48550/arXiv.1706.03762"

    def test_to_paper_dict(self, parser):
        """Test conversion of BibTeX entry to paper dict."""
        bibtex_entry = {
            "type": "article",
            "key": "test2024",
            "title": "Test Paper",
            "author": "John Smith and Jane Doe",
            "year": "2024",
            "journal": "Test Journal",
            "doi": "10.1234/test",
        }
        paper = parser.to_paper_dict(bibtex_entry)
        assert paper["title"] == "Test Paper"
        assert len(paper["authors"]) == 2
        assert paper["authors"][0]["name"] == "John Smith"
        assert paper["year"] == 2024
        assert paper["venue"] == "Test Journal"
        assert paper["doi"] == "10.1234/test"
        assert paper["source"] == "bibtex_import"

    def test_parse_authors(self, parser):
        """Test author parsing."""
        authors = parser._parse_authors("John Smith and Jane Doe and Bob Wilson")
        assert len(authors) == 3
        assert authors[0]["name"] == "John Smith"
        assert authors[1]["name"] == "Jane Doe"
        assert authors[2]["name"] == "Bob Wilson"

    def test_parse_year_valid(self, parser):
        """Test year parsing with valid year."""
        year = parser._parse_year("2024")
        assert year == 2024

    def test_parse_year_invalid(self, parser):
        """Test year parsing with invalid year."""
        year = parser._parse_year("invalid")
        assert year is None

    def test_parse_year_none(self, parser):
        """Test year parsing with None."""
        year = parser._parse_year(None)
        assert year is None


from src.academic.citation.bibtex.exporter import BibTeXExporter


class TestBibTeXExporter:
    """Tests for BibTeX exporter."""

    @pytest.fixture
    def exporter(self):
        return BibTeXExporter()

    @pytest.fixture
    def sample_papers(self):
        return [
            {
                "title": "Attention Is All You Need",
                "authors": [
                    {"name": "Ashish Vaswani"},
                    {"name": "Noam Shazeer"},
                ],
                "year": 2017,
                "venue": "NeurIPS",
                "doi": "10.48550/arXiv.1706.03762",
            },
            {
                "title": "A Conference Paper",
                "authors": [{"name": "John Smith"}],
                "year": 2024,
                "venue": "International Conference on Testing",
            },
        ]

    def test_export_creates_bibtex(self, exporter, sample_papers):
        """Test that exporter creates BibTeX format."""
        result = exporter.export(sample_papers)
        assert "@article" in result or "@inproceedings" in result
        assert "title = {Attention Is All You Need}" in result

    def test_export_authors(self, exporter, sample_papers):
        """Test that exporter formats authors correctly."""
        result = exporter.export(sample_papers)
        assert "Ashish Vaswani and Noam Shazeer" in result

    def test_export_year(self, exporter, sample_papers):
        """Test that exporter includes year."""
        result = exporter.export(sample_papers)
        assert "year = {2017}" in result

    def test_export_doi(self, exporter, sample_papers):
        """Test that exporter includes DOI."""
        result = exporter.export(sample_papers)
        assert "doi = {10.48550/arXiv.1706.03762}" in result

    def test_generate_key(self, exporter, sample_papers):
        """Test BibTeX key generation uses simple AuthorYear format."""
        key = exporter._generate_key(sample_papers[0])
        # New format: FirstAuthorYear (e.g., Vaswani2017)
        assert "vaswani" in key.lower()
        assert "2017" in key
        # Title word is no longer included in the key
        assert key == "Vaswani2017"

    def test_determine_type_article(self, exporter):
        """Test entry type detection for journal."""
        paper = {"venue": "Journal of Machine Learning Research"}
        assert exporter._determine_type(paper) == "article"

    def test_determine_type_inproceedings(self, exporter):
        """Test entry type detection for conference."""
        paper = {"venue": "International Conference on Machine Learning"}
        assert exporter._determine_type(paper) == "inproceedings"

    def test_determine_type_workshop(self, exporter):
        """Test entry type detection for workshop."""
        paper = {"venue": "ICML Workshop on Learning"}
        assert exporter._determine_type(paper) == "inproceedings"

    def test_determine_type_misc(self, exporter):
        """Test entry type detection for misc."""
        paper = {"venue": "arXiv"}
        assert exporter._determine_type(paper) == "misc"
