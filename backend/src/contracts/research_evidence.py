"""Typed evidence surfaces consumed by stage quality and review policy."""

from __future__ import annotations

from typing import Any, Literal, cast, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.contracts.review_policy import ReviewMode

ResearchSurface = Literal[
    "literature",
    "experiment",
    "writing",
    "workflow_trace",
    "citation_strength",
    "experiment_interpretation",
    "paper_relevance",
    "statistical_robustness",
    "writing_semantic_preservation",
    "writing_academic_style",
    "output_ref_reuse",
    "claim_evidence_alignment",
    "experiment_reproducibility",
    "figure_data_consistency",
    "review_packet_completeness",
    "argument_chain",
    "protected_section_safety",
    "prior_art_provenance",
    "claim_support",
    "enablement_support",
    "drawing_consistency",
    "feasibility_evidence",
    "risk_evidence",
    "milestone_realism",
    "source_provenance",
    "screenshot_provenance",
    "non_fabrication_evidence",
    "ai_use_disclosure",
]
ResearchSurfaceEnforcement = Literal["required_runtime", "required_final", "diagnostic"]
EvidenceStatus = Literal["verified", "unverified", "contradicted", "missing"]
ClaimSupportStatus = Literal[
    "supported",
    "partially_supported",
    "unsupported",
    "contradicted",
]
OperationStatus = Literal["success", "partial", "error"]
ReviewRiskCategory = Literal[
    "citation",
    "claim",
    "evidence",
    "statistics",
    "reproducibility",
    "prism_structure",
    "patent_claim",
    "long_term_memory",
    "visual_output",
    "ordinary_draft",
]


NON_BYPASSABLE_REVIEW_RISKS = frozenset(
    {
        "citation",
        "claim",
        "evidence",
        "statistics",
        "reproducibility",
        "prism_structure",
        "patent_claim",
        "long_term_memory",
        "visual_output",
    }
)
DEFAULT_RESEARCH_SURFACES: tuple[ResearchSurface, ...] = (
    "literature",
    "citation_strength",
    "paper_relevance",
    "claim_evidence_alignment",
)
KNOWN_RESEARCH_SURFACES = frozenset(str(item) for item in get_args(ResearchSurface))
KNOWN_RESEARCH_SURFACE_ENFORCEMENT = frozenset(str(item) for item in get_args(ResearchSurfaceEnforcement))


class ResearchSurfaceRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    surface: ResearchSurface
    enforcement: ResearchSurfaceEnforcement = "required_final"


class EvidenceRecord(BaseModel):
    """One provider/tool/source-backed evidence item, not model prose."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str
    surface: ResearchSurface
    kind: str
    status: EvidenceStatus
    source_ref: str | None = None
    claim_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("evidence_id", "kind")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("evidence_id and kind must be non-empty")
        return value


class ArtifactRecord(BaseModel):
    """A bounded artifact manifest projection suitable for deterministic checks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str
    kind: str
    content_hash: str | None = None
    manifest_ref: str | None = None
    script_ref: str | None = None
    data_refs: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("artifact_id", "kind")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("artifact_id and kind must be non-empty")
        return value


class ClaimRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str
    claim_type: str
    support_status: ClaimSupportStatus
    evidence_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()


class MissionOutputEvidence(BaseModel):
    """Evidence-bearing projection of a MissionOutput candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    output_id: str
    kind: str
    claim_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    risk_categories: tuple[ReviewRiskCategory, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class MissionReviewEvidence(BaseModel):
    """Review projection without depending on the persistence-layer model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    review_item_id: str
    output_ref: str
    risk_categories: tuple[ReviewRiskCategory, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    requires_user_review: bool = True


class OperationEvidence(BaseModel):
    """Terminal tool/subagent receipt used by workflow-trace checks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: str
    producer: str
    status: OperationStatus
    evidence_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    payload_ref: str | None = None


class ResearchEvidenceBundle(BaseModel):
    """Mission-native input to deterministic research quality evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence: tuple[EvidenceRecord, ...] = ()
    artifacts: tuple[ArtifactRecord, ...] = ()
    claims: tuple[ClaimRecord, ...] = ()
    outputs: tuple[MissionOutputEvidence, ...] = ()
    review_items: tuple[MissionReviewEvidence, ...] = ()
    operations: tuple[OperationEvidence, ...] = ()

    @model_validator(mode="after")
    def validate_unique_ids(self) -> ResearchEvidenceBundle:
        groups = {
            "evidence": [item.evidence_id for item in self.evidence],
            "artifact": [item.artifact_id for item in self.artifacts],
            "claim": [item.claim_id for item in self.claims],
            "output": [item.output_id for item in self.outputs],
            "review": [item.review_item_id for item in self.review_items],
            "operation": [item.operation_id for item in self.operations],
        }
        for label, values in groups.items():
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label} ids are not allowed")
        return self


def requires_user_review(
    risk_categories: tuple[ReviewRiskCategory, ...] | list[ReviewRiskCategory],
    *,
    review_mode: ReviewMode,
) -> bool:
    """High-trust academic writes are reviewable in every user-selected mode."""

    risks = set(risk_categories)
    if risks & NON_BYPASSABLE_REVIEW_RISKS:
        return True
    return review_mode in {"review_all", "balanced_default"}


def validate_research_surfaces(
    values: Any,
    *,
    field_name: str = "required_evidence_surfaces",
) -> list[str]:
    surfaces = normalize_research_surfaces(values)
    invalid = [surface for surface in surfaces if surface not in KNOWN_RESEARCH_SURFACES]
    if invalid:
        raise ValueError(f"unknown research evidence surfaces in {field_name}: {', '.join(_unique(invalid))}")
    return surfaces


def validate_research_surface_enforcement(
    value: Any,
) -> dict[str, ResearchSurfaceEnforcement]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("surface enforcement must be an object")
    result: dict[str, ResearchSurfaceEnforcement] = {}
    for raw_surface, raw_level in value.items():
        surface = _clean_text(raw_surface)
        level = _clean_text(raw_level)
        if surface not in KNOWN_RESEARCH_SURFACES:
            raise ValueError(f"unknown research evidence surface: {surface}")
        if level not in KNOWN_RESEARCH_SURFACE_ENFORCEMENT:
            raise ValueError(f"unknown research surface enforcement: {level}")
        result[surface] = cast(ResearchSurfaceEnforcement, level)
    return result


def normalize_research_surfaces(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, list | tuple | set | frozenset):
        raw = list(value)
    else:
        return []
    return _unique([text for item in raw for text in (_clean_text(item),) if text])


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else ""
