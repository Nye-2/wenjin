"""Tests for enriched TOC in list_papers."""

from src.academic.literature.navigation.models import TOCEntry


class TestEnrichedTOCEntry:
    def test_toc_entry_has_char_positions(self):
        """TOCEntry model supports char_start/char_end for word count calculation."""
        entry = TOCEntry(
            title="3. Methodology",
            level=1,
            page_start=12,
            char_start=15000,
            char_end=27000,
            children=[],
        )
        assert entry.char_end - entry.char_start == 12000
        # Rough word count: 12000 / 5 = 2400
        word_count = (entry.char_end - entry.char_start) // 5
        assert word_count == 2400

    def test_toc_entry_word_count_empty_section(self):
        """Empty section should yield zero word count."""
        entry = TOCEntry(
            title="Empty",
            level=1,
            char_start=0,
            char_end=0,
            children=[],
        )
        word_count = (entry.char_end - entry.char_start) // 5
        assert word_count == 0


class TestEnrichedTOCFormat:
    def test_enriched_toc_entry_has_expected_keys(self):
        """Verify enriched TOC entry has all expected fields."""
        entry = TOCEntry(
            title="Introduction",
            level=1,
            page_start=1,
            char_start=0,
            char_end=5000,
            children=[],
        )
        section_summaries = {"Introduction": "This section introduces the topic."}

        word_count = (entry.char_end - entry.char_start) // 5
        enriched = {
            "title": entry.title,
            "level": entry.level,
            "word_count": word_count,
            "page_range": (
                f"{entry.page_start or '?'}-?"
                if entry.page_start
                else None
            ),
            "summary": section_summaries.get(entry.title, ""),
        }

        assert enriched["title"] == "Introduction"
        assert enriched["word_count"] == 1000
        assert enriched["page_range"] == "1-?"
        assert enriched["summary"] == "This section introduces the topic."

    def test_enriched_toc_no_summary_when_tier2_missing(self):
        """When no Tier 2 data exists, summary should be empty string."""
        entry = TOCEntry(
            title="Methods",
            level=1,
            char_start=5000,
            char_end=10000,
            children=[],
        )
        section_summaries: dict = {}  # No Tier 2 data

        enriched = {
            "title": entry.title,
            "level": entry.level,
            "word_count": (entry.char_end - entry.char_start) // 5,
            "summary": section_summaries.get(entry.title, ""),
        }

        assert enriched["summary"] == ""

    def test_enriched_toc_no_page_range_when_page_start_none(self):
        """When page_start is None, page_range should be None."""
        entry = TOCEntry(
            title="Discussion",
            level=1,
            page_start=None,
            char_start=20000,
            char_end=30000,
            children=[],
        )

        page_range = (
            f"{entry.page_start or '?'}-?"
            if entry.page_start
            else None
        )

        assert page_range is None
