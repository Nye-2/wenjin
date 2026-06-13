"""Tests for Workbench expert-system public contracts."""

from __future__ import annotations

from pydantic import ValidationError

from src.contracts.team_expert import (
    CapabilityTeamPresentationV1,
    ExpertProfileV1,
    ExpertThoughtSnapshotV1,
    sanitize_expert_preview_item,
    sanitize_expert_snapshot,
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


def test_sanitize_expert_snapshot_bounds_content_and_scrubs_sensitive_values() -> None:
    snapshot = sanitize_expert_snapshot(
        {
            "schema_version": "wenjin.team.expert_snapshot.v1",
            "snapshot_id": "snap-1",
            "execution_id": "exec-1",
            "workspace_id": "ws-1",
            "agent_invocation_id": "agent-1",
            "agent_template_id": "research_scout.v1",
            "role_key": "research_scout",
            "role_name": "文献检索专家",
            "status": "running",
            "update_kind": "finding",
            "stage": {"label": "检索中"},
            "headline": "发现联邦学习和大模型结合的隐私保护方向",
            "body": "api_key=sk-test-123 /Users/ze/private/file.txt " + ("很长" * 400),
            "chips": [{"label": f"chip-{idx}", "value": "x"} for idx in range(8)],
            "evidence_refs": [
                {"label": "internal", "ref_type": "file", "path": "/workspace/tmp/tasks/.harness/outputs/a.json"},
                {"label": "dataset", "ref_type": "dataset", "path": "/workspace/datasets/a.csv"},
            ],
            "created_at": "2026-06-13T00:00:00Z",
        }
    )

    assert isinstance(snapshot, ExpertThoughtSnapshotV1)
    assert "sk-test" not in snapshot.body
    assert "/Users/ze" not in snapshot.body
    assert len(snapshot.body) <= 500
    assert len(snapshot.chips) == 5
    assert len(snapshot.evidence_refs) == 1
    assert snapshot.evidence_refs[0].path == "/workspace/datasets/a.csv"


def test_sanitize_expert_preview_item_keeps_summary_small_and_scrubs_refs() -> None:
    preview = sanitize_expert_preview_item(
        {
            "schema_version": "wenjin.team.expert_preview_item.v1",
            "preview_item_id": "preview-1",
            "execution_id": "exec-1",
            "workspace_id": "ws-1",
            "owner_agent_invocation_id": "agent-1",
            "owner_role_name": "文献检索专家",
            "title": "候选文献列表",
            "kind": "literature_list",
            "summary": "包含 token=secret-value " + ("文献" * 400),
            "preview_payload_ref": "/workspace/tmp/tasks/.harness/outputs/raw.json",
            "source_refs": [
                {"label": "paper", "ref_type": "paper", "ref_id": "paper-1"},
                {"label": "host", "ref_type": "file", "path": "/Users/ze/private.csv"},
            ],
            "status": "ready",
            "created_at": "2026-06-13T00:00:00Z",
        }
    )

    assert "secret-value" not in preview.summary
    assert len(preview.summary) <= 500
    assert preview.preview_payload_ref is None
    assert len(preview.source_refs) == 1
    assert preview.source_refs[0].ref_id == "paper-1"
