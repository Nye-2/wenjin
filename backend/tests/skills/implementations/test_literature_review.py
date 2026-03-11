"""Tests for literature review skill."""

import pytest
from unittest.mock import MagicMock, AsyncMock


class TestLiteratureReviewSkill:
    """Tests for LiteratureReviewSkill."""

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session."""
        return MagicMock()

    @pytest.fixture
    def skill(self, mock_db_session):
        """Create skill instance with mocked dependencies."""
        try:
            from src.skills.implementations.literature_review import LiteratureReviewSkill
            return LiteratureReviewSkill(db=mock_db_session)
        except ImportError:
            pytest.skip("LiteratureReviewSkill not implemented yet")

    def test_skill_name(self, skill):
        """Should have correct name."""
        assert skill.name == "literature_review"

    def test_skill_description(self, skill):
        """Should have description."""
        assert len(skill.description) > 0

    @pytest.mark.asyncio
    async def test_execute_empty_query(self, skill):
        """Should handle empty query."""
        result = await skill.execute(query="")
        assert result is not None
