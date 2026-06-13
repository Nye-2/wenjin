"""Tests for Workbench expert presentation public contracts."""

from __future__ import annotations

from pydantic import ValidationError

from src.contracts.team_presentation import (
    CapabilityTeamPresentationV1,
    ExpertProfileV1,
    resolve_expert_profile,
)


def test_expert_profile_accepts_restrained_public_identity() -> None:
    profile = ExpertProfileV1(
        public_name="码农哥 Kai",
        short_name="码农哥",
        role_title="实验工程师",
        avatar_label="码",
        tone="witty_professional",
        tagline="会写代码，也会把实验跑明白。",
        status_phrases={"running": "vibe coding 中"},
        preview_preferences={"primary_kinds": ["experiment_summary", "artifact"]},
    )

    assert profile.schema_version == "wenjin.team.expert_profile.v1"
    assert profile.public_name == "码农哥 Kai"
    assert profile.status_phrases["running"] == "vibe coding 中"


def test_expert_profile_rejects_unknown_status_phrase_key() -> None:
    try:
        ExpertProfileV1(
            public_name="Bad",
            role_title="Bad Role",
            status_phrases={"sleeping": "zzz"},
        )
    except ValidationError as exc:
        assert "status_phrases" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected validation error")


def test_expert_profile_rejects_blank_required_identity() -> None:
    try:
        ExpertProfileV1(public_name="   ", role_title="Bad Role")
    except ValidationError as exc:
        assert "public_name" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected validation error")


def test_capability_presentation_allows_display_overrides_only() -> None:
    presentation = CapabilityTeamPresentationV1(
        template_overrides={
            "literature_synthesizer.v1": {
                "public_name": "综述姐 Athena",
                "status_phrases": {"running": "织主题矩阵中"},
            }
        }
    )

    override = presentation.template_overrides["literature_synthesizer.v1"]
    assert override.public_name == "综述姐 Athena"
    assert override.status_phrases["running"] == "织主题矩阵中"

    try:
        CapabilityTeamPresentationV1(
            template_overrides={
                "research_scout.v1": {
                    "public_name": "文献猎手 Nora",
                    "default_skills": ["web_search"],
                }
            }
        )
    except ValidationError as exc:
        assert "default_skills" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected validation error")


def test_resolve_expert_profile_merges_override_and_fallbacks() -> None:
    base = ExpertProfileV1(
        public_name="文献专家",
        role_title="文献检索专家",
        status_phrases={"running": "检索中"},
    )
    resolved = resolve_expert_profile(
        base_profile=base,
        display_role="fallback role",
        override={"public_name": "文献猎手 Nora", "status_phrases": {"running": "扫文献雷达中"}},
    )

    assert resolved.public_name == "文献猎手 Nora"
    assert resolved.role_title == "文献检索专家"
    assert resolved.status_phrases["running"] == "扫文献雷达中"

    fallback = resolve_expert_profile(base_profile=None, display_role="质量评审专家")
    assert fallback.public_name == "质量评审专家"
    assert fallback.role_title == "质量评审专家"
    assert fallback.avatar_label == "质"


def test_resolve_expert_profile_ignores_blank_override_fields() -> None:
    base = ExpertProfileV1(public_name="文献专家", role_title="文献检索专家")

    resolved = resolve_expert_profile(
        base_profile=base,
        display_role="fallback role",
        override={"public_name": "   ", "tagline": "   "},
    )

    assert resolved.public_name == "文献专家"
    assert resolved.tagline is None
