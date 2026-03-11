"""Tests for literature review skill."""

import pytest
from unittest.mock import MagicMock, AsyncMock


class TestLiteratureReviewSkill:
    """Tests for LiteratureReviewSkill."""

    @pytest.fixture
    def skill(self):
        """Create skill instance with mocked dependencies."""
        try:
            from src.skills.implementations.literature_review import LiteratureReviewSkill
            return LiteratureReviewSkill()
        except ImportError:
            pytest.skip("LiteratureReviewSkill not implemented yet")

    def test_skill_name(self, skill):
        """Should have correct name."""
        assert skill.name == "literature-review"

    def test_skill_description(self, skill):
        """Should have description."""
        assert len(skill.description) > 0

    def test_execute_empty_query(self, skill):
        """Should handle empty query."""
        from src.skills.base import SkillInput
        state = {"thread_data": {}}
        input_data = SkillInput(
            workspace_id="test-workspace",
            user_query="",
            context={}
        )
        result = skill.execute(input_data, state)
        assert result is not None
