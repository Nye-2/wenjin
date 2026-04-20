"""Tests for workspace feature quality gate."""

from __future__ import annotations

from src.workspace_features.quality import evaluate_feature_output_quality


def test_quality_gate_passes_for_rich_framework_outline_payload() -> None:
    report = evaluate_feature_output_quality(
        workspace_type="sci",
        feature_id="framework_outline",
        result={
            "generation_mode": "llm",
            "abstract": "This paper studies multi-agent planning in constrained settings.",
            "keywords": ["multi-agent", "planning"],
            "sections": [{"title": "Introduction", "focus": "Context"}],
            "contributions": ["A new planning decomposition strategy."],
        },
    )

    assert report["status"] == "pass"
    assert int(report["score"]) >= 90
    assert report["core_hits"]


def test_quality_gate_warns_for_short_writing_content() -> None:
    report = evaluate_feature_output_quality(
        workspace_type="sci",
        feature_id="writing",
        result={
            "generation_mode": "llm",
            "section_title": "Introduction",
            "content": "Too short.",
            "references": [],
        },
    )

    assert report["status"] == "warn"
    issues = report.get("issues")
    assert isinstance(issues, list)
    assert any(
        isinstance(item, dict) and item.get("code") == "text_too_short"
        for item in issues
    )


def test_quality_gate_fails_when_only_meta_fields_returned() -> None:
    report = evaluate_feature_output_quality(
        workspace_type="thesis",
        feature_id="deep_research",
        result={
            "generation_mode": "llm",
            "generated_at": "2026-04-13T00:00:00+00:00",
            "model_id": "x",
        },
    )

    assert report["status"] == "fail"
    assert int(report["score"]) < 70
    issues = report.get("issues")
    assert isinstance(issues, list)
    assert any(
        isinstance(item, dict) and item.get("code") == "no_semantic_signals"
        for item in issues
    )

