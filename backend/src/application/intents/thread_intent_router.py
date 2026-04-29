"""Deterministic routing from thread turns into free-thread / feature launch / feature resume."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from src.application.results import ThreadTurnRequest
from src.services.workspace_skill_labels import normalize_workspace_type
from src.workspace_features import get_workspace_feature, list_workspace_features
from src.workspace_features.skills import get_skill_by_id, list_workspace_thread_skills

_SUPPORTED_ORCHESTRATION_INTENTS = {"launch", "resume"}
_FEATURE_WORK_TERMS = (
    "开始",
    "启动",
    "生成",
    "检索",
    "搜索",
    "分析",
    "撰写",
    "写",
    "推荐",
    "评审",
    "设计",
    "整理",
    "产出",
    "帮我",
)
_FEATURE_PARAM_BY_KIND = {
    "deep_research": "query",
    "literature_management": "query",
    "opening_research": "topic",
    "thesis_writing": "topic",
    "literature_search": "query",
    "paper_analysis": "paper_title",
    "writing": "topic",
    "literature_review": "topic",
    "framework_outline": "topic",
    "figure_generation": "description",
    "peer_review": "manuscript_excerpt",
    "journal_recommend": "abstract",
    "proposal_outline": "topic",
    "background_research": "topic",
    "experiment_design": "objective",
    "copyright_materials": "software_name",
    "technical_description": "software_name",
    "patent_outline": "innovation_description",
    "prior_art_search": "keywords",
}


def _normalize_match_text(value: Any) -> str:
    return "".join(str(value or "").strip().lower().split())


def _looks_like_feature_work_request(normalized_text: str) -> bool:
    return any(term in normalized_text for term in _FEATURE_WORK_TERMS)


def _proposal_aliases(
    *,
    skill_id: str,
    skill_name: str,
    feature_id: str,
    feature_name: str,
) -> tuple[str, ...]:
    aliases = {
        _normalize_match_text(skill_id),
        _normalize_match_text(skill_id.replace("-", "")),
        _normalize_match_text(skill_name),
        _normalize_match_text(feature_id),
        _normalize_match_text(feature_id.replace("_", "")),
        _normalize_match_text(feature_name),
    }
    for label in (skill_name, feature_name):
        normalized = _normalize_match_text(label)
        if len(normalized) >= 4:
            aliases.add(normalized[:2])
            aliases.add(normalized[-2:])
    return tuple(alias for alias in aliases if len(alias) >= 2)


def _score_feature_candidate(normalized_text: str, *, aliases: tuple[str, ...]) -> int:
    score = 0
    for alias in aliases:
        if alias and alias in normalized_text:
            score = max(score, len(alias))
    return score


def _params_from_proposal_message(feature_id: str, message: str) -> dict[str, Any]:
    normalized_message = str(message or "").strip()
    if not normalized_message:
        return {}
    param_key = _FEATURE_PARAM_BY_KIND.get(feature_id, "topic")
    return {param_key: normalized_message}


@dataclass(frozen=True, slots=True)
class ThreadIntentDecision:
    """Normalized routing decision for a thread turn."""

    mode: Literal["free_thread", "launch_feature", "resume_feature", "propose_feature"]
    reason: str
    feature_id: str | None = None
    execution_session_id: str | None = None
    skill_id: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0


class ThreadIntentRouter:
    """Resolve whether a thread turn should remain freeform or launch/resume a feature."""

    @staticmethod
    def _normalize_intent(value: Any) -> str | None:
        normalized = str(value or "").strip().lower()
        return normalized if normalized in _SUPPORTED_ORCHESTRATION_INTENTS else None

    @classmethod
    def _read_seed(
        cls,
        request: ThreadTurnRequest,
    ) -> tuple[str | None, str | None, str | None, dict[str, Any], str | None]:
        metadata = request.metadata if isinstance(request.metadata, Mapping) else {}
        orchestration = metadata.get("orchestration")
        if not isinstance(orchestration, Mapping):
            return None, None, None, {}, None
        feature_id = str(orchestration.get("feature_id") or "").strip() or None
        execution_session_id = str(orchestration.get("execution_session_id") or "").strip() or None
        skill_id = str(orchestration.get("skill_id") or orchestration.get("entry_skill_id") or "").strip() or None
        params = orchestration.get("params")
        intent = cls._normalize_intent(orchestration.get("intent"))
        return (
            feature_id,
            execution_session_id,
            skill_id,
            dict(params) if isinstance(params, Mapping) else {},
            intent,
        )

    @classmethod
    def _apply_explicit_skill_contract(
        cls,
        *,
        workspace_type: str | None,
        explicit_skill: str | None,
        feature_id: str | None,
        params: dict[str, Any],
    ) -> tuple[str | None, str | None, dict[str, Any], str | None]:
        """Merge skill defaults and validate feature/skill consistency."""
        normalized_skill = str(explicit_skill or "").strip()
        if not normalized_skill:
            return feature_id, None, dict(params), None

        skill_def = get_skill_by_id(workspace_type, normalized_skill)
        if skill_def is None:
            return feature_id, None, dict(params), "unknown_skill"

        merged_params = {**dict(skill_def.defaults), **dict(params)}
        if feature_id is None:
            return skill_def.feature_id, skill_def.id, merged_params, None

        if feature_id != skill_def.feature_id:
            return feature_id, None, dict(params), "skill_feature_mismatch"

        return feature_id, skill_def.id, merged_params, None

    @classmethod
    def _detect_feature_proposal(
        cls,
        *,
        request: ThreadTurnRequest,
        workspace_type: str | None,
    ) -> ThreadIntentDecision | None:
        normalized_workspace_type = normalize_workspace_type(workspace_type)
        if not normalized_workspace_type:
            return None

        text = _normalize_match_text(request.message)
        if not text:
            return None

        explicit_skill = str(request.skill or "").strip() or None
        if explicit_skill:
            skill_def = get_skill_by_id(normalized_workspace_type, explicit_skill)
            if skill_def is not None and _looks_like_feature_work_request(text):
                return ThreadIntentDecision(
                    mode="propose_feature",
                    reason="explicit_skill_feature_proposal",
                    feature_id=skill_def.feature_id,
                    skill_id=skill_def.id,
                    params=_params_from_proposal_message(skill_def.feature_id, request.message),
                    confidence=0.92,
                )

        if not _looks_like_feature_work_request(text):
            return None

        features_by_id = {
            feature.id: feature
            for feature in list_workspace_features(normalized_workspace_type)
        }
        best: tuple[int, str, str | None] | None = None
        for skill in list_workspace_thread_skills(normalized_workspace_type):
            feature = features_by_id.get(skill.feature_id)
            score = _score_feature_candidate(
                text,
                aliases=_proposal_aliases(
                    skill_id=skill.id,
                    skill_name=skill.name,
                    feature_id=skill.feature_id,
                    feature_name=str(getattr(feature, "name", "") or ""),
                ),
            )
            if score <= 0:
                continue
            candidate = (score, skill.feature_id, skill.id)
            if best is None or candidate[0] > best[0]:
                best = candidate

        if best is None:
            return None

        score, feature_id, skill_id = best
        return ThreadIntentDecision(
            mode="propose_feature",
            reason="message_feature_proposal",
            feature_id=feature_id,
            skill_id=skill_id,
            params=_params_from_proposal_message(feature_id, request.message),
            confidence=min(0.9, 0.55 + score / 40),
        )

    @classmethod
    def route(
        cls,
        *,
        request: ThreadTurnRequest,
        workspace: Any | None = None,
        workspace_type: str | None = None,
    ) -> ThreadIntentDecision:
        resolved_workspace_type = normalize_workspace_type(workspace_type or getattr(workspace, "type", None))
        (
            seed_feature_id,
            seed_execution_session_id,
            seed_skill_id,
            seed_params,
            intent,
        ) = cls._read_seed(request)
        params = dict(seed_params)
        feature_id = seed_feature_id
        skill_id = seed_skill_id

        if intent == "resume":
            return ThreadIntentDecision(
                mode="resume_feature",
                reason="explicit_resume_intent",
                feature_id=feature_id,
                execution_session_id=seed_execution_session_id,
                skill_id=skill_id,
                params=params,
            )

        if intent != "launch":
            if seed_feature_id or seed_execution_session_id or seed_skill_id or seed_params:
                return ThreadIntentDecision(
                    mode="free_thread",
                    reason="no_orchestration_intent",
                )
            proposal = cls._detect_feature_proposal(
                request=request,
                workspace_type=resolved_workspace_type,
            )
            if proposal is not None:
                return proposal
            return ThreadIntentDecision(
                mode="free_thread",
                reason="no_orchestration_intent",
            )

        explicit_skill = str(request.skill or skill_id or "").strip() or None
        if explicit_skill:
            (
                feature_id,
                skill_id,
                params,
                skill_contract_error,
            ) = cls._apply_explicit_skill_contract(
                workspace_type=resolved_workspace_type,
                explicit_skill=explicit_skill,
                feature_id=feature_id,
                params=params,
            )
            if skill_contract_error == "skill_feature_mismatch":
                return ThreadIntentDecision(
                    mode="free_thread",
                    reason="skill_feature_mismatch",
                )
            if skill_contract_error == "unknown_skill":
                return ThreadIntentDecision(
                    mode="free_thread",
                    reason="unknown_skill",
                )

        if feature_id is None:
            return ThreadIntentDecision(
                mode="free_thread",
                reason="launch_intent_missing_feature_id",
            )

        if resolved_workspace_type and get_workspace_feature(resolved_workspace_type, feature_id) is None:
            return ThreadIntentDecision(
                mode="free_thread",
                reason="feature_not_available_for_workspace_type",
            )

        return ThreadIntentDecision(
            mode="launch_feature",
            reason="explicit_launch_intent",
            feature_id=feature_id,
            skill_id=skill_id,
            params=params,
        )
