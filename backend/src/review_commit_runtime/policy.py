"""Review policy that keeps trust-bearing writes under explicit user control."""

from __future__ import annotations

from dataclasses import dataclass

from src.dataservice_client.contracts.mission import (
    MissionReviewItemPayload,
    MissionReviewMode,
)

_NON_BYPASS_KINDS = frozenset(
    {
        "citation",
        "claim",
        "evidence",
        "statistics",
        "statistical_result",
        "prism_structure",
        "prism_file_change",
        "patent_claim",
        "long_term_memory",
        "memory_fact",
    }
)
_NON_BYPASS_ROOMS = frozenset({"library", "memory"})


@dataclass(frozen=True, slots=True)
class ReviewPolicyProjection:
    requires_explicit_review: bool
    batch_acceptable: bool
    suggested_selected: bool


def project_review_policy(
    *,
    review_mode: MissionReviewMode | str,
    target_kind: str,
    target_room: str | None,
    risk_level: str,
) -> ReviewPolicyProjection:
    mode = MissionReviewMode(review_mode)
    kind = target_kind.strip().lower()
    non_bypassable = (
        risk_level == "high"
        or kind in _NON_BYPASS_KINDS
        or (target_room or "").strip().lower() in _NON_BYPASS_ROOMS
        or any(
            marker in kind
            for marker in ("citation", "claim", "evidence", "statistic", "patent")
        )
    )
    requires_explicit = non_bypassable or mode == MissionReviewMode.REVIEW_ALL
    batch_acceptable = not requires_explicit
    suggested_selected = (
        batch_acceptable
        and mode in {
            MissionReviewMode.BALANCED_DEFAULT,
            MissionReviewMode.AUTO_DRAFT,
        }
    )
    return ReviewPolicyProjection(
        requires_explicit_review=requires_explicit,
        batch_acceptable=batch_acceptable,
        suggested_selected=suggested_selected,
    )


def requires_explicit_review(item: MissionReviewItemPayload) -> bool:
    return item.requires_explicit_review


def may_bulk_accept(item: MissionReviewItemPayload) -> bool:
    return item.batch_acceptable and not item.requires_explicit_review


__all__ = [
    "ReviewPolicyProjection",
    "may_bulk_accept",
    "project_review_policy",
    "requires_explicit_review",
]
