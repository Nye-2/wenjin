"""Tests for Redis cache in section loading."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.academic.literature.navigation.models import PaperTOC, TOCEntry
from src.academic.literature.navigation.section_loader import SectionLoader


def _make_toc():
    return PaperTOC(
        paper_id="paper-1",
        title="Test Paper",
        abstract="Abstract",
        total_chars=5000,
        entries=[
            TOCEntry(
                title="Introduction",
                level=1,
                char_start=0,
                char_end=100,
                children=[],
            ),
        ],
    )


class TestSectionLoaderCache:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_content(self):
        """When Redis has cached data, return it without DB query."""
        cached_data = json.dumps({
            "paper_id": "paper-1",
            "section_title": "Introduction",
            "content": "Cached content",
            "word_count": 2,
            "has_subsections": False,
        })

        mock_redis = MagicMock()
        mock_redis.client = AsyncMock()
        mock_redis.client.get = AsyncMock(return_value=cached_data)

        db = AsyncMock()
        loader = SectionLoader(db, redis_client=mock_redis)

        toc = _make_toc()
        result = await loader.load_section(toc, "Introduction")

        assert result is not None
        assert result.content == "Cached content"
        assert result.paper_id == "paper-1"
        assert result.section_title == "Introduction"
        # DB should NOT have been queried
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_queries_db_and_stores(self):
        """When cache misses, load from DB and store in cache."""
        mock_redis = MagicMock()
        mock_redis.client = AsyncMock()
        mock_redis.client.get = AsyncMock(return_value=None)
        mock_redis.client.setex = AsyncMock()

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value={
            "full_text": "Introduction content here for testing purposes"
        })
        db.execute = AsyncMock(return_value=mock_result)

        loader = SectionLoader(db, redis_client=mock_redis)

        toc = PaperTOC(
            paper_id="paper-1",
            title="Test",
            abstract="",
            total_chars=100,
            entries=[
                TOCEntry(
                    title="Introduction",
                    level=1,
                    char_start=0,
                    char_end=47,
                    children=[],
                ),
            ],
        )

        result = await loader.load_section(toc, "Introduction")

        assert result is not None
        assert result.content == "Introduction content here for testing purposes"
        # Should have queried DB
        db.execute.assert_called_once()
        # Should have stored in cache
        mock_redis.client.setex.assert_called_once()
        call_args = mock_redis.client.setex.call_args
        assert call_args[0][0] == "section:paper-1:Introduction"
        assert call_args[0][1] == 3600  # TTL

    @pytest.mark.asyncio
    async def test_works_without_redis(self):
        """When no redis_client provided, loads from DB directly."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value={
            "full_text": "Some text content"
        })
        db.execute = AsyncMock(return_value=mock_result)

        loader = SectionLoader(db, redis_client=None)

        toc = PaperTOC(
            paper_id="paper-1",
            title="Test",
            abstract="",
            total_chars=100,
            entries=[
                TOCEntry(
                    title="Introduction",
                    level=1,
                    char_start=0,
                    char_end=17,
                    children=[],
                ),
            ],
        )

        result = await loader.load_section(toc, "Introduction")
        assert result is not None
        assert "text content" in result.content

    @pytest.mark.asyncio
    async def test_cache_error_falls_through_to_db(self):
        """When Redis raises an error, fall through to DB."""
        mock_redis = MagicMock()
        mock_redis.client = AsyncMock()
        mock_redis.client.get = AsyncMock(side_effect=ConnectionError("Redis down"))
        mock_redis.client.setex = AsyncMock(side_effect=ConnectionError("Redis down"))

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value={
            "full_text": "Fallback content from database"
        })
        db.execute = AsyncMock(return_value=mock_result)

        loader = SectionLoader(db, redis_client=mock_redis)

        toc = PaperTOC(
            paper_id="paper-1",
            title="Test",
            abstract="",
            total_chars=100,
            entries=[
                TOCEntry(
                    title="Introduction",
                    level=1,
                    char_start=0,
                    char_end=30,
                    children=[],
                ),
            ],
        )

        result = await loader.load_section(toc, "Introduction")
        assert result is not None
        assert "Fallback content" in result.content

    @pytest.mark.asyncio
    async def test_load_section_by_entry_uses_cache(self):
        """load_section_by_entry also benefits from caching."""
        cached_data = json.dumps({
            "paper_id": "paper-1",
            "section_title": "Introduction",
            "content": "Cached via entry",
            "word_count": 3,
            "has_subsections": False,
        })

        mock_redis = MagicMock()
        mock_redis.client = AsyncMock()
        mock_redis.client.get = AsyncMock(return_value=cached_data)

        db = AsyncMock()
        loader = SectionLoader(db, redis_client=mock_redis)

        toc = _make_toc()
        entry = toc.entries[0]
        result = await loader.load_section_by_entry(toc, entry)

        assert result is not None
        assert result.content == "Cached via entry"
        db.execute.assert_not_called()
