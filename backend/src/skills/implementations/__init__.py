"""Skill implementations for AcademiaGPT.

This module contains concrete skill implementations that provide
specialized academic research capabilities.
"""

from .deep_research import DeepResearchSkill
from .framework_designer import FrameworkDesignerSkill
from .fullpaper_writer import PAPER_SECTIONS, SECTION_PROMPTS, FullpaperWriterSkill, MockLLMService
from .literature_review import LiteratureReviewSkill

__all__ = [
    "DeepResearchSkill",
    "FrameworkDesignerSkill",
    "FullpaperWriterSkill",
    "LiteratureReviewSkill",
    "MockLLMService",
    "PAPER_SECTIONS",
    "SECTION_PROMPTS",
]
