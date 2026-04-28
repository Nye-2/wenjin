"""Feature output quality evaluation.

This module provides a lightweight, deterministic quality gate for workspace
features. The goal is to ensure each feature returns meaningful payload
signals before downstream artifact persistence and UI projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_META_KEYS = {
    "generation_mode",
    "generated_at",
    "schema_version",
    "model_id",
    "generation_error",
    "leader_workflow",
    "file_changes",
    "latex_project_id",
    "main_file",
}


@dataclass(frozen=True, slots=True)
class FeatureQualityProfile:
    """Quality profile for one feature output contract."""

    core_signal_keys: tuple[str, ...]
    preferred_signal_keys: tuple[str, ...] = ()
    min_semantic_signals: int = 1
    min_text_lengths: tuple[tuple[str, int], ...] = ()
    require_core_signal: bool = False


@dataclass(frozen=True, slots=True)
class FeatureQualityIssue:
    """Normalized quality issue item."""

    severity: str
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


_DEFAULT_PROFILE = FeatureQualityProfile(
    core_signal_keys=(
        "summary",
        "sections",
        "content",
        "items",
        "results",
        "next_actions",
    ),
    preferred_signal_keys=("summary", "next_actions"),
)

_FEATURE_QUALITY_PROFILES: dict[str, FeatureQualityProfile] = {
    "thesis.deep_research": FeatureQualityProfile(
        core_signal_keys=("corpus", "discovery", "ideas", "gaps", "recommended_actions", "topic"),
        preferred_signal_keys=("recommended_actions", "cross_validation", "summary"),
    ),
    "thesis.literature_management": FeatureQualityProfile(
        core_signal_keys=("summary", "top_cited", "recommended_actions", "smart_recommendations"),
        preferred_signal_keys=("topic_clusters", "coverage_gaps"),
    ),
    "thesis.opening_research": FeatureQualityProfile(
        core_signal_keys=("sections", "summary", "methodology_plan", "topic"),
        preferred_signal_keys=("next_actions", "references"),
    ),
    "thesis.thesis_writing": FeatureQualityProfile(
        core_signal_keys=("outline", "chapter", "chapters", "paper_title"),
        preferred_signal_keys=("summary", "next_actions"),
        min_text_lengths=(("content", 200), ("markdown", 200)),
    ),
    "thesis.figure_generation": FeatureQualityProfile(
        core_signal_keys=("render_data", "source_code", "prompt", "description"),
        preferred_signal_keys=("status",),
    ),
    "sci.literature_search": FeatureQualityProfile(
        core_signal_keys=("papers", "top_hits", "summary", "query"),
        preferred_signal_keys=("filters",),
    ),
    "sci.paper_analysis": FeatureQualityProfile(
        core_signal_keys=("sections", "summary", "insights"),
        preferred_signal_keys=("key_points", "limitations"),
    ),
    "sci.writing": FeatureQualityProfile(
        core_signal_keys=("content", "section_title", "references"),
        preferred_signal_keys=("summary",),
        min_text_lengths=(("content", 240),),
    ),
    "sci.literature_review": FeatureQualityProfile(
        core_signal_keys=("sections", "summary", "research_gaps"),
        preferred_signal_keys=("next_actions", "key_papers"),
    ),
    "sci.framework_outline": FeatureQualityProfile(
        core_signal_keys=("sections", "abstract", "keywords"),
        preferred_signal_keys=("contributions",),
    ),
    "sci.peer_review": FeatureQualityProfile(
        core_signal_keys=("weaknesses", "strengths", "revision_actions", "summary"),
        preferred_signal_keys=("score",),
    ),
    "sci.journal_recommend": FeatureQualityProfile(
        core_signal_keys=("journals", "summary"),
        preferred_signal_keys=("submission_tips", "fit_explanation"),
    ),
    "sci.figure_generation": FeatureQualityProfile(
        core_signal_keys=("render_data", "source_code", "prompt", "description"),
        preferred_signal_keys=("status",),
    ),
    "proposal.proposal_outline": FeatureQualityProfile(
        core_signal_keys=("sections", "summary", "milestones"),
        preferred_signal_keys=("risks", "next_actions"),
    ),
    "proposal.background_research": FeatureQualityProfile(
        core_signal_keys=("sections", "references", "summary", "keywords"),
        preferred_signal_keys=("next_actions",),
    ),
    "proposal.experiment_design": FeatureQualityProfile(
        core_signal_keys=("variables", "summary", "evaluation_plan"),
        preferred_signal_keys=("risks", "next_actions"),
    ),
    "proposal.figure_generation": FeatureQualityProfile(
        core_signal_keys=("render_data", "source_code", "prompt", "description"),
        preferred_signal_keys=("status",),
    ),
    "software_copyright.copyright_materials": FeatureQualityProfile(
        core_signal_keys=("required_materials", "review_checklist", "software_profile"),
        preferred_signal_keys=("summary", "next_actions"),
    ),
    "software_copyright.technical_description": FeatureQualityProfile(
        core_signal_keys=("sections", "summary", "software_name"),
        preferred_signal_keys=("next_actions",),
    ),
    "software_copyright.figure_generation": FeatureQualityProfile(
        core_signal_keys=("render_data", "source_code", "prompt", "description"),
        preferred_signal_keys=("status",),
    ),
    "patent.patent_outline": FeatureQualityProfile(
        core_signal_keys=("sections", "claims_draft", "innovation_description"),
        preferred_signal_keys=("evidence_points_needed", "next_steps"),
    ),
    "patent.prior_art_search": FeatureQualityProfile(
        core_signal_keys=("comparison_table", "novelty_risks", "avoidance_suggestions", "search_scope"),
        preferred_signal_keys=("next_steps", "summary"),
    ),
    "patent.figure_generation": FeatureQualityProfile(
        core_signal_keys=("render_data", "source_code", "prompt", "description"),
        preferred_signal_keys=("status",),
    ),
}


def _feature_key(workspace_type: str, feature_id: str) -> str:
    return f"{workspace_type}.{feature_id}"


def _has_semantic_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_has_semantic_value(item) for item in value)
    if isinstance(value, dict):
        return bool(value)
    return value is not None


def _text_length(value: Any) -> int:
    if isinstance(value, str):
        return len(value.strip())
    return 0


def _result_semantic_keys(result: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for key, value in result.items():
        if key in _META_KEYS:
            continue
        if _has_semantic_value(value):
            keys.append(str(key))
    return keys


def evaluate_feature_output_quality(
    *,
    workspace_type: str,
    feature_id: str,
    result: Any,
) -> dict[str, Any]:
    """Evaluate output quality for a feature execution result."""
    issues: list[FeatureQualityIssue] = []
    feature_key = _feature_key(workspace_type, feature_id)
    profile = _FEATURE_QUALITY_PROFILES.get(feature_key, _DEFAULT_PROFILE)

    if not isinstance(result, dict):
        issues.append(
            FeatureQualityIssue(
                severity="error",
                code="result_not_mapping",
                message="feature result must be a dict payload",
            )
        )
        return {
            "status": "fail",
            "score": 0,
            "feature_key": feature_key,
            "semantic_signals": [],
            "core_hits": [],
            "preferred_hits": [],
            "issues": [item.as_dict() for item in issues],
            "summary": "输出结构无效",
        }

    semantic_keys = _result_semantic_keys(result)
    if not semantic_keys:
        issues.append(
            FeatureQualityIssue(
                severity="error",
                code="no_semantic_signals",
                message="feature result has no semantic signals",
            )
        )

    if len(semantic_keys) < max(1, profile.min_semantic_signals):
        issues.append(
            FeatureQualityIssue(
                severity="warning",
                code="too_few_semantic_signals",
                message=(
                    f"semantic signals too few: {len(semantic_keys)} < "
                    f"{max(1, profile.min_semantic_signals)}"
                ),
            )
        )

    core_hits = [
        key
        for key in profile.core_signal_keys
        if _has_semantic_value(result.get(key))
    ]
    if not core_hits:
        issues.append(
            FeatureQualityIssue(
                severity="error" if profile.require_core_signal else "warning",
                code="core_signal_missing",
                message="none of the core feature signals were returned",
            )
        )

    preferred_hits = [
        key
        for key in profile.preferred_signal_keys
        if _has_semantic_value(result.get(key))
    ]
    if profile.preferred_signal_keys and not preferred_hits:
        issues.append(
            FeatureQualityIssue(
                severity="warning",
                code="preferred_signal_missing",
                message="preferred quality signals are missing",
            )
        )

    for field_name, min_chars in profile.min_text_lengths:
        text_len = _text_length(result.get(field_name))
        if text_len == 0:
            continue
        if text_len < max(1, int(min_chars)):
            issues.append(
                FeatureQualityIssue(
                    severity="warning",
                    code="text_too_short",
                    message=f"{field_name} is too short ({text_len} < {min_chars})",
                )
            )

    error_count = sum(1 for item in issues if item.severity == "error")
    warning_count = sum(1 for item in issues if item.severity == "warning")

    if error_count > 0:
        status = "fail"
    elif warning_count > 0:
        status = "warn"
    else:
        status = "pass"

    score = max(0, 100 - error_count * 40 - warning_count * 10)
    summary = (
        "质量门禁未通过"
        if status == "fail"
        else "质量有待改进"
        if status == "warn"
        else "质量检查通过"
    )

    return {
        "status": status,
        "score": score,
        "feature_key": feature_key,
        "semantic_signals": semantic_keys,
        "core_hits": core_hits,
        "preferred_hits": preferred_hits,
        "issues": [item.as_dict() for item in issues],
        "summary": summary,
    }

