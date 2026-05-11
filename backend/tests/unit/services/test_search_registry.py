"""Tests for search source registry."""

import pytest

from src.services.search.registry import SEARCH_SOURCES, get_search_source, register_search_source


def test_get_unknown_source_raises():
    with pytest.raises(ValueError, match="Unknown search source"):
        get_search_source("nonexistent")


def test_register_and_get():
    class FakeSource:
        name = "fake"

        async def search(self, query, **kwargs):
            return []

    register_search_source("fake", FakeSource)
    try:
        src = get_search_source("fake")
        assert isinstance(src, FakeSource)
    finally:
        SEARCH_SOURCES.pop("fake", None)


def test_semantic_scholar_registered():
    import src.services.search.sources  # noqa: F401

    assert "semantic_scholar" in SEARCH_SOURCES
