"""Research evidence surface declarations and capability-policy parsing."""

from __future__ import annotations

from src.contracts.research_evidence import (
    DEFAULT_RESEARCH_SURFACES,
    KNOWN_RESEARCH_SURFACES,
    ResearchSurface,
    normalize_research_surfaces,
    required_surfaces_from_capability_policy,
    validate_research_surfaces,
)

__all__ = [
    "DEFAULT_RESEARCH_SURFACES",
    "KNOWN_RESEARCH_SURFACES",
    "ResearchSurface",
    "normalize_research_surfaces",
    "required_surfaces_from_capability_policy",
    "validate_research_surfaces",
]
