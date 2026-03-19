"""Tests for BibTeX exporter."""



def test_generate_citation_key_simple():
    """Test citation key generation returns simple format."""
    from src.academic.citation.bibtex.exporter import generate_citation_key

    paper = {
        "authors": [{"name": "John Smith"}],
        "year": 2024,
        "title": "Deep Learning Methods"
    }

    key = generate_citation_key(paper)
    assert key == "Smith2024"


def test_generate_citation_key_no_year():
    """Test citation key when year is missing."""
    from src.academic.citation.bibtex.exporter import generate_citation_key

    paper = {
        "authors": [{"name": "Jane Doe"}],
        "title": "Important Paper"
    }

    key = generate_citation_key(paper)
    assert key == "Doen.d."


def test_generate_citation_key_multiple_authors():
    """Test citation key uses first author only."""
    from src.academic.citation.bibtex.exporter import generate_citation_key

    paper = {
        "authors": [
            {"name": "Alice Johnson"},
            {"name": "Bob Williams"}
        ],
        "year": 2023,
    }

    key = generate_citation_key(paper)
    assert key == "Johnson2023"


def test_generate_citation_key_no_authors_no_year():
    """Test citation key returns Unknown when both authors and year are missing."""
    from src.academic.citation.bibtex.exporter import generate_citation_key

    paper = {
        "title": "Anonymous Paper"
    }

    key = generate_citation_key(paper)
    assert key == "Unknown"


def test_generate_citation_key_empty_author_name():
    """Test citation key handles empty author name."""
    from src.academic.citation.bibtex.exporter import generate_citation_key

    paper = {
        "authors": [{"name": ""}],
        "year": 2024,
    }

    key = generate_citation_key(paper)
    # Empty name means no author part, just year
    assert key == "2024"


class TestBibTeXExporter:
    """Tests for BibTeXExporter class."""

    def test_export_single_paper(self):
        """Test exporting a single paper."""
        from src.academic.citation.bibtex.exporter import BibTeXExporter

        exporter = BibTeXExporter()
        papers = [{
            "authors": [{"name": "John Smith"}],
            "title": "Test Paper",
            "year": 2024,
            "venue": "Test Conference"
        }]

        result = exporter.export(papers)

        # "Conference" in venue triggers inproceedings type
        assert "@inproceedings{Smith2024," in result
        assert "author = {John Smith}" in result
        assert "title = {Test Paper}" in result
        assert "year = {2024}" in result

    def test_export_uses_generate_citation_key(self):
        """Test that export uses generate_citation_key for key generation."""
        from src.academic.citation.bibtex.exporter import BibTeXExporter

        exporter = BibTeXExporter()
        papers = [{
            "authors": [{"name": "Jane Doe"}],
            "title": "Another Paper",
            "year": 2023,
        }]

        result = exporter.export(papers)

        # Should use Doe2023, not doe_2023_another
        assert "@misc{Doe2023," in result
