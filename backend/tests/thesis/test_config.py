# tests/thesis/test_config.py
"""Tests for thesis configuration management."""

import pytest
from unittest.mock import patch
import os


class TestThesisSettings:
    """Tests for ThesisSettings configuration class."""

    def test_default_min_references(self):
        """Test default minimum references value."""
        from src.thesis.config import ThesisSettings

        settings = ThesisSettings()
        assert settings.min_references == 10

    def test_default_recommended_references(self):
        """Test default recommended references value."""
        from src.thesis.config import ThesisSettings

        settings = ThesisSettings()
        assert settings.recommended_references == 20

    def test_default_target_words(self):
        """Test default target words value."""
        from src.thesis.config import ThesisSettings

        settings = ThesisSettings()
        assert settings.default_target_words == 2000

    def test_default_max_section_words(self):
        """Test default max section words value."""
        from src.thesis.config import ThesisSettings

        settings = ThesisSettings()
        assert settings.max_section_words == 5000

    def test_default_latex_compiler(self):
        """Test default LaTeX compiler value."""
        from src.thesis.config import ThesisSettings

        settings = ThesisSettings()
        assert settings.latex_compiler == "xelatex"

    def test_default_bibliography_style(self):
        """Test default bibliography style value."""
        from src.thesis.config import ThesisSettings

        settings = ThesisSettings()
        assert settings.bibliography_style == "gbt7714"

    def test_default_task_timeout_hours(self):
        """Test default task timeout hours value."""
        from src.thesis.config import ThesisSettings

        settings = ThesisSettings()
        assert settings.task_timeout_hours == 24

    def test_default_max_concurrent_tasks(self):
        """Test default max concurrent tasks value."""
        from src.thesis.config import ThesisSettings

        settings = ThesisSettings()
        assert settings.max_concurrent_tasks == 10

    def test_env_prefix_is_thesis(self):
        """Test that environment prefix is THESIS_."""
        from src.thesis.config import ThesisSettings

        # The model_config should have env_prefix set to "THESIS_"
        assert ThesisSettings.model_config.get("env_prefix") == "THESIS_"

    def test_env_override_min_references(self):
        """Test that THESIS_MIN_REFERENCES env var overrides default."""
        from src.thesis.config import ThesisSettings

        with patch.dict(os.environ, {"THESIS_MIN_REFERENCES": "15"}):
            settings = ThesisSettings()
            assert settings.min_references == 15

    def test_env_override_recommended_references(self):
        """Test that THESIS_RECOMMENDED_REFERENCES env var overrides default."""
        from src.thesis.config import ThesisSettings

        with patch.dict(os.environ, {"THESIS_RECOMMENDED_REFERENCES": "30"}):
            settings = ThesisSettings()
            assert settings.recommended_references == 30


class TestGlobalInstance:
    """Tests for global thesis_settings instance."""

    def test_global_instance_exists(self):
        """Test that global thesis_settings instance exists."""
        from src.thesis.config import thesis_settings

        assert thesis_settings is not None

    def test_global_instance_is_thesis_settings(self):
        """Test that global instance is ThesisSettings type."""
        from src.thesis.config import thesis_settings, ThesisSettings

        assert isinstance(thesis_settings, ThesisSettings)

    def test_global_instance_has_correct_defaults(self):
        """Test that global instance has correct default values."""
        from src.thesis.config import thesis_settings

        assert thesis_settings.min_references == 10
        assert thesis_settings.recommended_references == 20
        assert thesis_settings.default_target_words == 2000
        assert thesis_settings.max_section_words == 5000
        assert thesis_settings.latex_compiler == "xelatex"
        assert thesis_settings.bibliography_style == "gbt7714"
        assert thesis_settings.task_timeout_hours == 24
        assert thesis_settings.max_concurrent_tasks == 10
