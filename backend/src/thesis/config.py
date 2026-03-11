# src/thesis/config.py
"""Configuration management for thesis generation module.

This module provides centralized configuration for thesis generation,
supporting environment variable overrides with THESIS_ prefix.
"""

from pydantic_settings import BaseSettings


class ThesisSettings(BaseSettings):
    """Configuration settings for thesis generation.

    All settings can be overridden via environment variables with
    the THESIS_ prefix. For example:
    - THESIS_MIN_REFERENCES=15
    - THESIS_RECOMMENDED_REFERENCES=30

    Attributes:
        min_references: Minimum number of references required.
        recommended_references: Recommended number of references.
        default_target_words: Default target word count per section.
        max_section_words: Maximum word count per section.
        latex_compiler: LaTeX compiler to use (xelatex, pdflatex, etc.).
        bibliography_style: Bibliography style for citations.
        task_timeout_hours: Maximum hours before task timeout.
        max_concurrent_tasks: Maximum number of concurrent thesis tasks.
    """

    # Literature configuration
    min_references: int = 10
    recommended_references: int = 20

    # Section configuration
    default_target_words: int = 2000
    max_section_words: int = 5000

    # LaTeX configuration
    latex_compiler: str = "xelatex"
    bibliography_style: str = "gbt7714"

    # Task configuration
    task_timeout_hours: int = 24
    max_concurrent_tasks: int = 10

    model_config = {"env_prefix": "THESIS_"}


# Global instance for easy access throughout the application
thesis_settings = ThesisSettings()
