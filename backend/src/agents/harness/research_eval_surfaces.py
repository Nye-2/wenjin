"""Research evidence surface declarations and capability-policy parsing."""

from __future__ import annotations

from src.contracts.research_evidence import (
    DEFAULT_RESEARCH_SURFACES,
    KNOWN_RESEARCH_SURFACE_ENFORCEMENT,
    KNOWN_RESEARCH_SURFACES,
    ResearchSurface,
    ResearchSurfaceEnforcement,
    ResearchSurfaceRequirement,
    normalize_research_surfaces,
    required_surface_requirements_from_capability_policy,
    required_surfaces_from_capability_policy,
    validate_research_surface_enforcement,
    validate_research_surfaces,
)

__all__ = [
    "DEFAULT_RESEARCH_SURFACES",
    "KNOWN_RESEARCH_SURFACE_ENFORCEMENT",
    "KNOWN_RESEARCH_SURFACES",
    "ResearchSurface",
    "ResearchSurfaceEnforcement",
    "ResearchSurfaceRequirement",
    "normalize_research_surfaces",
    "required_surface_requirements_from_capability_policy",
    "required_surfaces_from_capability_policy",
    "validate_research_surface_enforcement",
    "validate_research_surfaces",
]
