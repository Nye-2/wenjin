"""Tests for dynamic module resolution."""

from src.reflection.resolvers import resolve_variable


class TestResolveVariable:
    def test_resolve_known_module(self):
        """Should resolve a known module:variable path."""
        result = resolve_variable("os.path:sep")
        assert isinstance(result, str)

    def test_resolve_missing_raises(self):
        """Should raise ImportError for unknown modules."""
        import pytest
        with pytest.raises(ImportError):
            resolve_variable("nonexistent_module:thing")

    def test_resolve_bad_format_raises(self):
        """Should raise ValueError for paths without colon."""
        import pytest
        with pytest.raises(ValueError):
            resolve_variable("no_colon_here")
