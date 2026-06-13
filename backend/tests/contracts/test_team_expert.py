"""Tests for Workbench expert runtime public contracts."""

from __future__ import annotations

from src.contracts.team_expert import (
    ExpertThoughtSnapshotV1,
    sanitize_expert_preview_item,
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
