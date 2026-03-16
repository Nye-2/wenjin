"""Reusable service layer for workspace feature handlers."""

from .patent_feature_service import (
    build_patent_outline_payload,
    build_prior_art_search_payload,
)
from .proposal_feature_service import (
    build_background_research_payload,
    build_proposal_outline_payload,
)
from .sci_feature_service import (
    build_literature_search_payload,
    build_paper_analysis_payload,
)
from .software_copyright_feature_service import (
    build_technical_description_payload,
)
from .thesis_feature_service import (
    build_compile_payload,
    build_figure_payload,
    build_literature_management_payload,
    build_opening_report_payload,
)
from .thesis_writing_service import (
    build_chapter_payload,
    build_outline_payload,
)

__all__ = [
    "build_background_research_payload",
    "build_chapter_payload",
    "build_compile_payload",
    "build_figure_payload",
    "build_literature_search_payload",
    "build_literature_management_payload",
    "build_opening_report_payload",
    "build_outline_payload",
    "build_paper_analysis_payload",
    "build_patent_outline_payload",
    "build_prior_art_search_payload",
    "build_proposal_outline_payload",
    "build_technical_description_payload",
]
