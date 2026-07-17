"""Pure review-policy projection shared by Mission storage and runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ReviewMode(StrEnum):
    REVIEW_ALL = "review_all"
    BALANCED_DEFAULT = "balanced_default"
    AUTO_DRAFT = "auto_draft"


DEFAULT_REVIEW_MODE = ReviewMode.BALANCED_DEFAULT


def normalize_review_mode(value: object | None) -> ReviewMode:
    return ReviewMode(DEFAULT_REVIEW_MODE if value is None else str(value).strip())

_NON_BYPASS_KINDS = frozenset(
    {
        "citation",
        "claim",
        "evidence",
        "statistics",
        "statistical_result",
        "prism_structure",
        "prism_file_change",
        "prism_visual_insertion",
        "patent_claim",
        "long_term_memory",
        "memory_fact",
        "workspace_asset",
    }
)
_NON_BYPASS_ROOMS = frozenset({"library", "memory"})


@dataclass(frozen=True, slots=True)
class ReviewPolicyProjection:
    requires_explicit_review: bool
    batch_acceptable: bool
    suggested_selected: bool
    auto_draft_eligible: bool


def project_review_policy(
    *,
    review_mode: ReviewMode | str,
    target_kind: str,
    target_room: str | None,
    target_ref: str | None,
    risk_level: str,
) -> ReviewPolicyProjection:
    """Derive all review eligibility from canonical Mission and item facts."""

    mode = ReviewMode(review_mode)
    kind = target_kind.strip().lower()
    room = (target_room or "").strip().lower()
    non_bypassable = (
        risk_level == "high"
        or kind in _NON_BYPASS_KINDS
        or room in _NON_BYPASS_ROOMS
        or any(
            marker in kind
            for marker in ("citation", "claim", "evidence", "statistic", "patent")
        )
    )
    requires_explicit = non_bypassable or mode == ReviewMode.REVIEW_ALL
    batch_acceptable = not requires_explicit
    auto_draft_eligible = (
        mode == ReviewMode.AUTO_DRAFT
        and batch_acceptable
        and risk_level == "low"
        and kind == "document"
        and room == "documents"
        and target_ref is None
    )
    return ReviewPolicyProjection(
        requires_explicit_review=requires_explicit,
        batch_acceptable=batch_acceptable,
        suggested_selected=(
            batch_acceptable
            and not auto_draft_eligible
            and mode == ReviewMode.BALANCED_DEFAULT
        ),
        auto_draft_eligible=auto_draft_eligible,
    )


__all__ = [
    "DEFAULT_REVIEW_MODE",
    "ReviewMode",
    "ReviewPolicyProjection",
    "normalize_review_mode",
    "project_review_policy",
]
