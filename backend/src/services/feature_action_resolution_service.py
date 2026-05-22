"""Resolve action state for mission-level workspace capabilities.

The resolver is intentionally capability-id driven, not artifact-type driven:
mission reruns should preserve the user's launch intent and optionally carry a
source artifact for context, but old workflow-specific branching is not part of
the Super Agent Harness contract.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

MISSION_CAPABILITY_IDS: frozenset[str] = frozenset(
    {
        "idea_to_thesis_manuscript",
        "thesis_research_pack",
        "thesis_empirical_analysis",
        "thesis_revision_pass",
        "thesis_defense_pack",
        "thesis_reference_curation",
        "research_question_to_paper",
        "sci_literature_positioning",
        "sci_empirical_package",
        "sci_revision_for_journal",
        "journal_submission_strategy",
        "response_to_reviewers",
        "reproducibility_audit",
        "idea_to_proposal_package",
        "proposal_background_pack",
        "technical_route_package",
        "feasibility_and_risk_review",
        "proposal_polish_for_review",
        "software_copyright_application_pack",
        "software_technical_manual",
        "software_evidence_pack",
        "software_architecture_diagrams",
        "invention_to_patent_draft",
        "prior_art_and_novelty_pack",
        "claims_strategy",
        "embodiment_and_drawings",
        "office_action_response",
    }
)

_GOAL_KEYS = ("goal", "topic", "query", "paper_title", "software_name", "innovation_description")


def resolve_feature_action_state(
    *,
    feature_id: str,
    workspace: Any | None,
    artifacts: Sequence[Any],
    orchestration_params: Mapping[str, Any] | None = None,
    explicit_source_artifact_id: str | None = None,
    follow_up_prompt: str = "",
) -> dict[str, Any]:
    """Return launch/rerun state for a canonical mission capability."""

    capability_id = (feature_id or "").strip()
    params = _clean_mapping(orchestration_params)
    source_artifact = _resolve_source_artifact(
        artifacts=artifacts,
        explicit_source_artifact_id=explicit_source_artifact_id,
    )

    if capability_id not in MISSION_CAPABILITY_IDS:
        return _build_state(
            source_artifact_id=_artifact_id(source_artifact),
            follow_up_prompt=follow_up_prompt,
            route_params={},
            rerun_params=None,
            unavailable_reason=f"未知 capability：{capability_id or 'empty'}",
        )

    goal = _mission_goal(params, workspace)
    route_params = dict(params)
    if goal:
        route_params.setdefault("goal", goal)
    if source_artifact is not None:
        route_params["source_artifact_id"] = _artifact_id(source_artifact)

    context_artifact_ids = _context_artifact_ids(params, artifacts, source_artifact)
    if context_artifact_ids:
        route_params["context_artifact_ids"] = context_artifact_ids

    rerun_params = _rerun_params(params, goal)
    if rerun_params is None and source_artifact is not None:
        rerun_params = {"goal": _artifact_title(source_artifact) or goal or "继续处理来源材料"}

    unavailable_reason = None
    if rerun_params is None:
        unavailable_reason = "缺少可复用的 mission goal 或来源材料。"

    return _build_state(
        source_artifact_id=_artifact_id(source_artifact),
        follow_up_prompt=follow_up_prompt,
        route_params=route_params,
        rerun_params=rerun_params,
        unavailable_reason=unavailable_reason,
    )


def _build_state(
    *,
    source_artifact_id: str | None,
    follow_up_prompt: str,
    route_params: dict[str, Any],
    rerun_params: dict[str, Any] | None,
    unavailable_reason: str | None,
) -> dict[str, Any]:
    return {
        "source_artifact_id": source_artifact_id,
        "follow_up_prompt": follow_up_prompt,
        "route_params": route_params,
        "rerun_params": rerun_params,
        "rerun_unavailable_reason": unavailable_reason,
    }


def _clean_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(key, str) and item not in (None, "")
    }


def _resolve_source_artifact(
    *,
    artifacts: Sequence[Any],
    explicit_source_artifact_id: str | None,
) -> Any | None:
    explicit_id = (explicit_source_artifact_id or "").strip()
    if explicit_id:
        for artifact in artifacts:
            if _artifact_id(artifact) == explicit_id:
                return artifact
    return _latest_artifact(artifacts)


def _latest_artifact(artifacts: Sequence[Any]) -> Any | None:
    if not artifacts:
        return None
    return max(
        artifacts,
        key=lambda artifact: (
            getattr(artifact, "created_at", None) is not None,
            getattr(artifact, "created_at", None),
            _artifact_id(artifact) or "",
        ),
    )


def _artifact_id(artifact: Any | None) -> str | None:
    if artifact is None:
        return None
    artifact_id = getattr(artifact, "id", None)
    return str(artifact_id).strip() if artifact_id is not None else None


def _artifact_title(artifact: Any | None) -> str | None:
    if artifact is None:
        return None
    title = getattr(artifact, "title", None)
    if isinstance(title, str) and title.strip():
        return title.strip()
    content = getattr(artifact, "content", None)
    if isinstance(content, Mapping):
        for key in _GOAL_KEYS:
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _context_artifact_ids(
    params: Mapping[str, Any],
    artifacts: Sequence[Any],
    source_artifact: Any | None,
) -> list[str]:
    existing = params.get("context_artifact_ids")
    if isinstance(existing, list):
        return [str(item).strip() for item in existing if str(item).strip()]
    source_id = _artifact_id(source_artifact)
    return [
        artifact_id
        for artifact_id in (_artifact_id(artifact) for artifact in artifacts[:10])
        if artifact_id and artifact_id != source_id
    ]


def _mission_goal(params: Mapping[str, Any], workspace: Any | None) -> str:
    for key in _GOAL_KEYS:
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return _workspace_fallback(workspace)


def _workspace_fallback(workspace: Any | None) -> str:
    if workspace is not None:
        for attr in ("description", "name"):
            value = getattr(workspace, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "未命名任务"


def _rerun_params(params: Mapping[str, Any], goal: str) -> dict[str, Any] | None:
    rerun = {
        key: value
        for key, value in params.items()
        if key not in {"source_artifact_id", "context_artifact_ids"} and value not in (None, "")
    }
    if goal:
        rerun.setdefault("goal", goal)
    return rerun or None
