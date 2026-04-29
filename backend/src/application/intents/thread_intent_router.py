"""Deterministic routing from thread turns into free-thread / feature launch / feature resume."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from src.application.results import ThreadTurnRequest
from src.services.workspace_skill_labels import normalize_workspace_type
from src.workspace_features import get_workspace_feature
from src.workspace_features.skills import get_skill_by_id

_SUPPORTED_ORCHESTRATION_INTENTS = {"launch", "resume"}


@dataclass(frozen=True, slots=True)
class ThreadIntentDecision:
    """Normalized routing decision for a thread turn."""

    mode: Literal["free_thread", "launch_feature", "resume_feature"]
    reason: str
    feature_id: str | None = None
    execution_session_id: str | None = None
    skill_id: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


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
