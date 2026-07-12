"""Deterministic research evidence evaluation over Mission-native contracts."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.contracts.research_evidence import (
    DEFAULT_RESEARCH_SURFACES,
    NON_BYPASSABLE_REVIEW_RISKS,
    ResearchEvidenceBundle,
    ResearchSurface,
)

EvalStatus = Literal["pass", "fail"]


class ResearchTaskEvidenceEval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: EvalStatus
    coverage: dict[str, EvalStatus]
    findings: tuple[dict[str, Any], ...] = ()
    evidence: dict[str, dict[str, Any]] = Field(default_factory=dict)


def evaluate_research_task_evidence(
    bundle: ResearchEvidenceBundle,
    *,
    required_surfaces: tuple[ResearchSurface, ...] = DEFAULT_RESEARCH_SURFACES,
) -> ResearchTaskEvidenceEval:
    """Verify evidence and review structure without judging prose or calling a model."""

    checks: dict[
        ResearchSurface,
        Callable[[ResearchEvidenceBundle], tuple[bool, dict[str, Any], str]],
    ] = {
        "literature": _literature,
        "experiment": _experiment,
        "writing": _writing,
        "workflow_trace": _workflow_trace,
        "citation_strength": _citation_strength,
        "experiment_interpretation": _claim_alignment,
        "paper_relevance": _paper_relevance,
        "statistical_robustness": _statistical_robustness,
        "writing_semantic_preservation": _writing_semantic_preservation,
        "writing_academic_style": _writing_academic_style,
        "output_ref_reuse": _output_ref_reuse,
        "claim_evidence_alignment": _claim_alignment,
        "experiment_reproducibility": _experiment_reproducibility,
        "figure_data_consistency": _figure_data_consistency,
        "review_packet_completeness": _review_packet_completeness,
        "argument_chain": _claim_alignment,
        "protected_section_safety": _protected_section_safety,
        "prior_art_provenance": _citation_strength,
        "claim_support": _claim_alignment,
        "enablement_support": _claim_alignment,
        "drawing_consistency": _figure_data_consistency,
        "feasibility_evidence": _claim_alignment,
        "risk_evidence": _claim_alignment,
        "milestone_realism": _claim_alignment,
        "source_provenance": _citation_strength,
        "screenshot_provenance": _figure_data_consistency,
        "non_fabrication_evidence": _claim_alignment,
        "ai_use_disclosure": _ai_use_disclosure,
    }
    coverage: dict[str, EvalStatus] = {}
    findings: list[dict[str, Any]] = []
    evidence: dict[str, dict[str, Any]] = {}
    for surface in required_surfaces:
        passed, details, message = checks[surface](bundle)
        coverage[surface] = "pass" if passed else "fail"
        evidence[surface] = details
        if not passed:
            findings.append({"surface": surface, "severity": "high", "message": message})
    return ResearchTaskEvidenceEval(
        status="pass" if all(value == "pass" for value in coverage.values()) else "fail",
        coverage=coverage,
        findings=tuple(findings),
        evidence=evidence,
    )


def _verified(bundle: ResearchEvidenceBundle):
    return [item for item in bundle.evidence if item.status == "verified"]


def _literature(bundle: ResearchEvidenceBundle) -> tuple[bool, dict[str, Any], str]:
    items = [item for item in _verified(bundle) if item.kind in {"literature", "source", "citation"} and item.source_ref]
    return bool(items), {"evidence_ids": [item.evidence_id for item in items]}, ("No verified literature evidence with a stable source reference was produced.")


def _citation_strength(bundle: ResearchEvidenceBundle) -> tuple[bool, dict[str, Any], str]:
    citations = [item for item in bundle.evidence if item.kind in {"citation", "source", "prior_art"}]
    verified = [item for item in citations if item.status == "verified" and item.source_ref]
    rejected = [item for item in citations if item.status in {"contradicted", "missing"}]
    passed = bool(verified) and not rejected
    return (
        passed,
        {
            "verified": [item.evidence_id for item in verified],
            "rejected": [item.evidence_id for item in rejected],
        },
        "Citation evidence is missing, contradicted, or lacks stable provenance.",
    )


def _paper_relevance(bundle: ResearchEvidenceBundle) -> tuple[bool, dict[str, Any], str]:
    relevant = [item for item in _verified(bundle) if str(item.metadata.get("relevance") or "").lower() in {"aligned", "direct", "high"}]
    return bool(relevant), {"evidence_ids": [item.evidence_id for item in relevant]}, ("No verified evidence was explicitly screened as directly relevant.")


def _experiment(bundle: ResearchEvidenceBundle) -> tuple[bool, dict[str, Any], str]:
    artifacts = [item for item in bundle.artifacts if item.kind in {"experiment_result", "analysis_result", "model_result"} and item.content_hash]
    return bool(artifacts), {"artifact_ids": [item.artifact_id for item in artifacts]}, ("No content-addressed experiment or analysis result was produced.")


def _writing(bundle: ResearchEvidenceBundle) -> tuple[bool, dict[str, Any], str]:
    outputs = [item for item in bundle.outputs if item.kind in {"document", "manuscript", "prism_change"}]
    return bool(outputs), {"output_ids": [item.output_id for item in outputs]}, ("No reviewable writing output was produced.")


def _workflow_trace(bundle: ResearchEvidenceBundle) -> tuple[bool, dict[str, Any], str]:
    terminal = [item for item in bundle.operations if item.status in {"success", "partial"}]
    return bool(terminal), {"operation_ids": [item.operation_id for item in terminal]}, ("No terminal tool or subagent receipt was recorded.")


def _claim_alignment(bundle: ResearchEvidenceBundle) -> tuple[bool, dict[str, Any], str]:
    verified_ids = {item.evidence_id for item in _verified(bundle)}
    artifact_ids = {item.artifact_id for item in bundle.artifacts if item.content_hash}
    unsupported: list[str] = []
    for claim in bundle.claims:
        if claim.support_status != "supported":
            unsupported.append(claim.claim_id)
            continue
        if not (set(claim.evidence_refs) & verified_ids or set(claim.artifact_refs) & artifact_ids):
            unsupported.append(claim.claim_id)
    return (
        bool(bundle.claims) and not unsupported,
        {
            "claim_ids": [item.claim_id for item in bundle.claims],
            "unsupported": unsupported,
        },
        "One or more claims lack verified evidence or a content-addressed artifact.",
    )


def _statistical_robustness(
    bundle: ResearchEvidenceBundle,
) -> tuple[bool, dict[str, Any], str]:
    robust = [item for item in _verified(bundle) if item.kind == "statistic" and item.metadata.get("metric") and item.metadata.get("sample_size") and (item.metadata.get("uncertainty") or item.metadata.get("statistical_test"))]
    return bool(robust), {"evidence_ids": [item.evidence_id for item in robust]}, ("Statistical evidence must include metric, sample size, and uncertainty or a test.")


def _writing_semantic_preservation(
    bundle: ResearchEvidenceBundle,
) -> tuple[bool, dict[str, Any], str]:
    checked = [item.output_id for item in bundle.outputs if item.kind in {"document", "manuscript", "prism_change"} and item.metadata.get("semantic_preservation_checked") is True]
    return bool(checked), {"output_ids": checked}, "Writing changes lack semantic-preservation evidence."


def _writing_academic_style(
    bundle: ResearchEvidenceBundle,
) -> tuple[bool, dict[str, Any], str]:
    checked = [item.output_id for item in bundle.outputs if item.kind in {"document", "manuscript", "prism_change"} and item.metadata.get("academic_style_checked") is True]
    return bool(checked), {"output_ids": checked}, "Writing outputs lack an academic-style review receipt."


def _output_ref_reuse(bundle: ResearchEvidenceBundle) -> tuple[bool, dict[str, Any], str]:
    evidence_ids = {item.evidence_id for item in bundle.evidence}
    artifact_ids = {item.artifact_id for item in bundle.artifacts}
    broken = [item.output_id for item in bundle.outputs if not set(item.evidence_refs) <= evidence_ids or not set(item.artifact_refs) <= artifact_ids]
    return bool(bundle.outputs) and not broken, {"broken_output_ids": broken}, ("Outputs contain missing evidence or artifact references.")


def _experiment_reproducibility(
    bundle: ResearchEvidenceBundle,
) -> tuple[bool, dict[str, Any], str]:
    reproducible = [item.artifact_id for item in bundle.artifacts if item.kind in {"experiment_result", "analysis_result", "model_result"} and item.content_hash and item.manifest_ref and item.script_ref and item.data_refs]
    return bool(reproducible), {"artifact_ids": reproducible}, ("Experiment artifacts require content hash, manifest, script, and data refs.")


def _figure_data_consistency(
    bundle: ResearchEvidenceBundle,
) -> tuple[bool, dict[str, Any], str]:
    figures = [item for item in bundle.artifacts if item.kind in {"figure", "table"}]
    valid = [item.artifact_id for item in figures if item.content_hash and item.script_ref and item.data_refs]
    return bool(figures) and len(valid) == len(figures), {"artifact_ids": valid}, ("Figures and tables require content hash, generation script, and data refs.")


def _review_packet_completeness(
    bundle: ResearchEvidenceBundle,
) -> tuple[bool, dict[str, Any], str]:
    by_output = {item.output_ref: item for item in bundle.review_items}
    missing: list[str] = []
    unsafe: list[str] = []
    for output in bundle.outputs:
        risks = set(output.risk_categories)
        requires_review = bool(risks & NON_BYPASSABLE_REVIEW_RISKS)
        review_item = by_output.get(output.output_id)
        if requires_review and review_item is None:
            missing.append(output.output_id)
        elif requires_review and review_item and not review_item.requires_user_review:
            unsafe.append(review_item.review_item_id)
    passed = bool(bundle.outputs) and not missing and not unsafe
    return passed, {"missing_outputs": missing, "unsafe_review_items": unsafe}, ("High-trust outputs require explicit non-bypassable review items.")


def _protected_section_safety(
    bundle: ResearchEvidenceBundle,
) -> tuple[bool, dict[str, Any], str]:
    unsafe = [item.output_id for item in bundle.outputs if item.kind == "prism_change" and item.metadata.get("protected_section_safe") is not True]
    prism_outputs = [item for item in bundle.outputs if item.kind == "prism_change"]
    return bool(prism_outputs) and not unsafe, {"unsafe_output_ids": unsafe}, ("Prism structural changes lack protected-section safety evidence.")


def _ai_use_disclosure(bundle: ResearchEvidenceBundle) -> tuple[bool, dict[str, Any], str]:
    items = [item.evidence_id for item in _verified(bundle) if item.kind in {"ai_use_disclosure", "no_ai_declaration"}]
    return bool(items), {"evidence_ids": items}, "AI-use disclosure or no-AI declaration is missing."
