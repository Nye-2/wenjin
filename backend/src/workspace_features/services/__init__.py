"""Reusable service layer for workspace feature handlers."""

from .patent_feature_service import (
    build_patent_outline_payload,
    build_prior_art_search_payload,
)
from .proposal_feature_service import (
    build_background_research_payload,
    build_experiment_design_payload,
    build_proposal_outline_payload,
)
from .sci_feature_service import (
    build_framework_outline_payload,
    build_journal_recommend_payload,
    build_literature_search_payload,
    build_paper_analysis_payload,
    build_peer_review_payload,
    build_sci_literature_review_payload,
    build_sci_writing_payload,
)
from .software_copyright_feature_service import (
    build_copyright_materials_payload,
    build_technical_description_payload,
)

__all__ = [
    "build_background_research_payload",
    "build_experiment_design_payload",
    "build_framework_outline_payload",
    "build_journal_recommend_payload",
    "build_literature_search_payload",
    "build_peer_review_payload",
    "build_paper_analysis_payload",
    "build_patent_outline_payload",
    "build_prior_art_search_payload",
    "build_proposal_outline_payload",
    "build_copyright_materials_payload",
    "build_sci_literature_review_payload",
    "build_sci_writing_payload",
    "build_technical_description_payload",
]
