"""Contract checks for chat-facing workspace skill definitions."""

from __future__ import annotations

from src.workspace_features import CANONICAL_WORKSPACE_TYPES, get_workspace_feature, list_workspace_features
from src.workspace_features.skills import (
    get_default_skill_for_feature,
    get_skill_by_id,
    list_workspace_thread_skills,
)


def test_every_thread_skill_maps_to_registered_workspace_feature() -> None:
    missing: list[str] = []
    for workspace_type in CANONICAL_WORKSPACE_TYPES:
        for skill in list_workspace_thread_skills(workspace_type):
            if get_workspace_feature(workspace_type, skill.feature_id) is None:
                missing.append(f"{workspace_type}.{skill.id}->{skill.feature_id}")

    assert not missing, "Thread skills mapped to missing features: " + ", ".join(missing)


def test_every_feature_has_valid_default_thread_skill() -> None:
    missing: list[str] = []
    mismatched: list[str] = []

    for workspace_type in CANONICAL_WORKSPACE_TYPES:
        for feature in list_workspace_features(workspace_type):
            default_skill_id = get_default_skill_for_feature(workspace_type, feature.id)
            if not default_skill_id:
                missing.append(f"{workspace_type}.{feature.id}")
                continue
            skill = get_skill_by_id(workspace_type, default_skill_id)
            if skill is None or skill.feature_id != feature.id:
                mismatched.append(f"{workspace_type}.{feature.id}->{default_skill_id}")

    assert not missing, "Features without default thread skill: " + ", ".join(missing)
    assert not mismatched, "Default skills do not map back to feature: " + ", ".join(mismatched)


def test_follow_up_skills_stay_within_workspace_skill_catalog() -> None:
    invalid: list[str] = []

    for workspace_type in CANONICAL_WORKSPACE_TYPES:
        known_ids = {
            skill.id
            for skill in list_workspace_thread_skills(workspace_type)
        }
        for skill in list_workspace_thread_skills(workspace_type):
            for follow_up in skill.follow_up_skills:
                if follow_up not in known_ids:
                    invalid.append(f"{workspace_type}.{skill.id}->{follow_up}")

    assert not invalid, "Invalid follow-up skill ids: " + ", ".join(invalid)


def test_skill_guidance_uses_compute_proposal_contract() -> None:
    missing_markers: list[str] = []
    legacy_phrases: list[str] = []
    forbidden_phrases = (
        "主动开始执行",
        "确认后直接开始",
        "收集完毕后生成",
        "根据需求开始",
        "明确后开始",
        "信息齐备后生成",
    )

    for workspace_type in CANONICAL_WORKSPACE_TYPES:
        for skill in list_workspace_thread_skills(workspace_type):
            guidance = skill.guidance_prompt
            markers = (
                "launch_feature",
                "最小缺失信息",
                "输出产物",
                "不要编造",
            )
            for marker in markers:
                if marker not in guidance:
                    missing_markers.append(f"{workspace_type}.{skill.id}:{marker}")
            for phrase in forbidden_phrases:
                if phrase in guidance:
                    legacy_phrases.append(f"{workspace_type}.{skill.id}:{phrase}")

    assert not missing_markers, "Skill guidance missing contract markers: " + ", ".join(missing_markers)
    assert not legacy_phrases, "Skill guidance still contains legacy executor wording: " + ", ".join(legacy_phrases)
