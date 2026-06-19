"""Tests for Workbench expert runtime public contracts."""

from __future__ import annotations

from src.contracts.team_expert import (
    ExpertThoughtSnapshotV1,
    sanitize_expert_preview_item,
    sanitize_expert_report,
    sanitize_expert_snapshot,
)


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


def test_sanitize_expert_report_bounds_claims_and_evidence() -> None:
    report = sanitize_expert_report(
        {
            "schema_version": "wenjin.expert_report.v1",
            "expert_id": "literature_synthesizer.v1",
            "skill_id": "literature-synthesizer",
            "task_focus": "Synthesize papers into themes and gaps.",
            "summary": "token=secret-value " + ("summary " * 200),
            "claims": [
                {
                    "claim_id": "claim-1",
                    "text": "FedLoRA reduces communication but heterogeneity remains open.",
                    "support_level": "supported",
                    "evidence_ids": ["ev-1"],
                    "citation_keys": ["smith2025fedlora"],
                    "limitations": ["mostly SFT evidence"],
                }
            ],
            "evidence": [
                {
                    "evidence_id": "ev-1",
                    "source_type": "library_reference",
                    "source_id": "source-1",
                    "citation_key": "smith2025fedlora",
                    "relevance": "high",
                    "risk": "low",
                    "bounded_excerpt": "reports communication reduction",
                    "used_for": ["claim-1"],
                }
            ],
            "artifacts": [],
            "review_items": [],
            "quality_gates_checked": ["citation_strength"],
            "uncertainties": ["privacy-utility evidence is weaker"],
            "next_actions": ["audit two candidate papers"],
        }
    )

    assert report.schema_version == "wenjin.expert_report.v1"
    assert "secret-value" not in report.summary
    assert len(report.summary) <= 700
    assert report.claims[0].support_level == "supported"
    assert report.evidence[0].source_id == "source-1"


def test_sanitize_expert_report_accepts_nested_academic_harness_payloads() -> None:
    report = sanitize_expert_report(
        {
            "schema_version": "wenjin.expert_report.v1",
            "expert_id": "literature_synthesizer.v1",
            "skill_id": "literature-synthesizer",
            "task_focus": "Synthesize FedLLM literature.",
            "summary": "Built claim and evidence packets.",
            "research_brief_delta": {
                "perspectives": [
                    {
                        "perspective_id": "p-communication",
                        "label": "通信效率",
                        "questions": ["FedLoRA 如何降低通信？"],
                    }
                ],
                "handoff_notes": ["需要补充 AAAI 近两年论文。"],
            },
            "claim_inventory": {
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "claim_type": "literature_position",
                        "text": "Communication efficiency is a key FedLLM bottleneck.",
                        "support_status": "supported",
                        "evidence_refs": ["ev-1"],
                    }
                ]
            },
            "evidence_packet": {
                "packet_id": "evidence-1",
                "items": [
                    {
                        "evidence_id": "ev-1",
                        "evidence_type": "library_source",
                        "title": "FedLoRA",
                        "source_key": "library:paper-1",
                        "support_strength": "high",
                        "relevance": "direct",
                    }
                ],
                "links": [
                    {
                        "claim_id": "claim-1",
                        "evidence_id": "ev-1",
                        "support_relation": "supports",
                        "confidence": "high",
                    }
                ],
            },
        }
    )

    assert report.research_brief_delta is not None
    assert report.research_brief_delta.perspectives[0].label == "通信效率"
    assert report.claim_inventory is not None
    assert report.claim_inventory.claims[0].support_status == "supported"
    assert report.evidence_packet is not None
    assert report.evidence_packet.items[0].source_key == "library:paper-1"
