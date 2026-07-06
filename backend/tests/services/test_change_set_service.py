"""Tests for building workspace ChangeSets from TaskReport outputs."""

from __future__ import annotations

from src.agents.contracts.task_report import (
    DecisionData,
    DecisionOutput,
    DocumentData,
    DocumentOutput,
    MemoryFactData,
    MemoryFactOutput,
    ReviewPacket,
    ReviewPacketItem,
    TaskReport,
)
from src.services.change_set_service import build_change_set_from_task_report


def _report(
    *,
    outputs: list | None = None,
    review_packet: ReviewPacket | None = None,
    review_items: list[dict] | None = None,
) -> TaskReport:
    return TaskReport(
        execution_id="exec-1",
        capability_id="cap-1",
        status="completed",
        duration_seconds=3,
        narrative="完成研究任务。",
        outputs=outputs or [],
        review_items=review_items or [],
        review_packet=review_packet,
    )


def test_auto_draft_stages_document_output_unit() -> None:
    report = _report(
        outputs=[
            DocumentOutput(
                id="doc-1",
                kind="document",
                preview="Draft introduction",
                data=DocumentData(
                    name="intro.md",
                    doc_kind="draft",
                    content="# Intro",
                ),
            )
        ],
    )

    change_set = build_change_set_from_task_report(
        report,
        workspace_id="ws-1",
        write_mode="auto_draft",
    )

    assert change_set is not None
    assert change_set.write_mode == "auto_draft"
    assert len(change_set.units) == 1
    unit = change_set.units[0]
    assert unit.id == "output-doc-1"
    assert unit.target.room == "documents"
    assert unit.target.object_type == "document_draft"
    assert unit.action == "create"
    assert unit.risk == "low"
    assert unit.default_apply_state == "staged"
    assert unit.requires_confirmation is True
    assert unit.materialization is not None
    assert unit.materialization.operation == "documents.upsert_prism_file"
    assert unit.materialization.payload["name"] == "intro.md"
    assert unit.materialization.payload["content_inline"] == "# Intro"


def test_ask_workspace_write_stages_document_but_allows_sandbox_provenance_draft() -> None:
    packet = ReviewPacket(
        packet_id="packet-1",
        execution_id="exec-1",
        capability_id="cap-1",
        title="Review packet",
        summary="Artifact ready.",
        completion_status="complete",
        items=[
            ReviewPacketItem(
                item_id="artifact-1",
                kind="artifact",
                title="Figure artifact",
                summary="Generated chart.",
                preview={"path": "/workspace/artifacts/figure.png"},
                risk={"level": "low", "reasons": []},
                default_checked=True,
                can_commit=True,
                provenance={"sha256": "abc123", "tool": "sandbox"},
            )
        ],
    )
    report = _report(
        outputs=[
            DocumentOutput(
                id="doc-1",
                kind="document",
                preview="Draft introduction",
                data=DocumentData(name="intro.md", doc_kind="draft", content="# Intro"),
            )
        ],
        review_packet=packet,
    )

    change_set = build_change_set_from_task_report(
        report,
        workspace_id="ws-1",
        write_mode="ask_workspace_write",
    )

    assert change_set is not None
    units_by_id = {unit.id: unit for unit in change_set.units}
    assert units_by_id["output-doc-1"].default_apply_state == "staged"
    assert units_by_id["output-doc-1"].requires_confirmation is True
    assert units_by_id["review-artifact-1"].target.room == "sandbox"
    assert units_by_id["review-artifact-1"].target.object_type == "artifact"
    assert units_by_id["review-artifact-1"].default_apply_state == "draft_applied"
    assert units_by_id["review-artifact-1"].requires_confirmation is False


def test_strict_review_stages_low_risk_sandbox_artifact() -> None:
    packet = ReviewPacket(
        packet_id="packet-1",
        execution_id="exec-1",
        capability_id="cap-1",
        title="Review packet",
        summary="Artifact ready.",
        completion_status="complete",
        items=[
            ReviewPacketItem(
                item_id="artifact-1",
                kind="artifact",
                title="Figure artifact",
                summary="Generated chart.",
                preview={"path": "/workspace/artifacts/figure.png"},
                risk={"level": "low", "reasons": []},
                provenance={"sha256": "abc123"},
            )
        ],
    )

    change_set = build_change_set_from_task_report(
        _report(review_packet=packet),
        workspace_id="ws-1",
        write_mode="strict_review",
    )

    assert change_set is not None
    assert change_set.units[0].default_apply_state == "staged"
    assert change_set.units[0].requires_confirmation is True


def test_legacy_sandbox_review_item_with_provenance_is_draft_applied() -> None:
    report = _report(
        review_items=[
            {
                "id": "review-1",
                "kind": "sandbox_artifact",
                "status": "pending",
                "title": "Accept sandbox artifact: sandbox_report",
                "summary": "/workspace/reports/analysis.md",
                "source": {
                    "type": "sandbox_job",
                    "execution_id": "exec-1",
                    "job_id": "job-1",
                },
                "target": {
                    "kind": "sandbox_artifact",
                    "path": "/workspace/reports/analysis.md",
                    "sandbox_artifact_id": "artifact-1",
                },
                "preview": {
                    "mode": "artifact",
                    "path": "/workspace/reports/analysis.md",
                    "content_hash": "sha256:analysis",
                },
                "reproducibility": {
                    "source_task_id": "experiment_runner",
                    "content_hash": "sha256:analysis",
                },
                "actions": [
                    {"action": "accept_sandbox_artifact", "label": "保存到产物库"},
                    {"action": "reject_sandbox_artifact", "label": "忽略"},
                ],
            }
        ]
    )

    change_set = build_change_set_from_task_report(
        report,
        workspace_id="ws-1",
        write_mode="auto_draft",
    )

    assert change_set is not None
    unit = change_set.units[0]
    assert unit.id == "review-review-1"
    assert unit.target.room == "sandbox"
    assert unit.target.object_type == "sandbox_artifact"
    assert unit.target.path == "/workspace/reports/analysis.md"
    assert unit.default_apply_state == "draft_applied"
    assert unit.requires_confirmation is False
    assert unit.materialization is not None
    assert unit.materialization.operation == "sandbox.materialize_artifact"
    assert unit.materialization.payload == {
        "artifact_id": "artifact-1",
        "review_item_id": "review-1",
        "path": "/workspace/reports/analysis.md",
    }
    assert unit.provenance["reproducibility"]["content_hash"] == "sha256:analysis"


def test_legacy_settings_review_item_builds_typed_materialization() -> None:
    report = _report(
        review_items=[
            {
                "id": "settings-write-mode",
                "kind": "workspace_settings",
                "title": "切换写入模式",
                "summary": "改为提交前询问。",
                "status": "pending",
                "risk": "medium",
                "target": {
                    "kind": "workspace_settings",
                    "setting_key": "write_mode",
                },
                "updates": {
                    "write_mode": "ask_workspace_write",
                    "thinking_enabled": False,
                },
                "default_checked": False,
                "can_commit": True,
            }
        ]
    )

    change_set = build_change_set_from_task_report(
        report,
        workspace_id="ws-1",
        write_mode="auto_draft",
    )

    assert change_set is not None
    unit = change_set.units[0]
    assert unit.id == "review-settings-write-mode"
    assert unit.target.room == "settings"
    assert unit.target.object_type == "workspace_settings"
    assert unit.default_apply_state == "staged"
    assert unit.materialization is not None
    assert unit.materialization.operation == "settings.update"
    assert unit.materialization.payload == {
        "write_mode": "ask_workspace_write",
        "thinking_enabled": False,
    }


def test_legacy_sandbox_review_item_with_string_risk_is_not_draft_applied() -> None:
    report = _report(
        review_items=[
            {
                "id": "review-unsafe",
                "kind": "sandbox_artifact",
                "status": "pending",
                "risk": "high",
                "target": {
                    "kind": "sandbox_artifact",
                    "path": "/workspace/reports/unsafe.md",
                },
                "source": {"type": "sandbox_job", "job_id": "job-1"},
                "actions": [{"action": "accept_sandbox_artifact", "label": "保存"}],
            }
        ]
    )

    change_set = build_change_set_from_task_report(
        report,
        workspace_id="ws-1",
        write_mode="auto_draft",
    )

    assert change_set is not None
    unit = change_set.units[0]
    assert unit.risk == "high"
    assert unit.default_apply_state == "staged"
    assert unit.requires_confirmation is True


def test_legacy_nested_contract_risk_is_preserved() -> None:
    report = _report(
        review_items=[
            {
                "id": "review-risk-contract",
                "kind": "prism_file_change",
                "status": "pending",
                "target": {
                    "kind": "prism_file_change",
                    "logical_key": "project:main",
                    "file_path": "main.tex",
                },
                "preview": {
                    "mode": "diff",
                    "semantic_contract": {
                        "risk": "high",
                        "reasons": ["semantic drift detected"],
                    },
                },
                "actions": [{"action": "apply_prism_change", "label": "应用到 Prism"}],
            }
        ]
    )

    change_set = build_change_set_from_task_report(
        report,
        workspace_id="ws-1",
        write_mode="auto_draft",
    )

    assert change_set is not None
    unit = change_set.units[0]
    assert unit.risk == "high"
    assert unit.default_apply_state == "blocked"
    assert unit.requires_confirmation is True
    assert "semantic drift detected" in unit.risk_reasons


def test_legacy_prism_file_change_is_staged_even_in_auto_draft() -> None:
    report = _report(
        review_items=[
            {
                "id": "review-prism-1",
                "kind": "prism_file_change",
                "status": "pending",
                "title": "Revise main.tex",
                "summary": "Full manuscript revision",
                "source": {
                    "type": "review_batch",
                    "execution_id": "exec-1",
                    "task_id": "writer",
                },
                "target": {
                    "kind": "prism_file_change",
                    "logical_key": "project:main",
                    "file_path": "main.tex",
                },
                "preview": {
                    "mode": "diff",
                    "pending_hash": "sha256:new",
                    "content_contract": {"path": "main.tex", "latex_shape": "document"},
                },
                "actions": [
                    {"action": "preview_prism_change", "label": "预览 diff"},
                    {"action": "apply_prism_change", "label": "应用到 Prism"},
                    {"action": "reject_prism_change", "label": "忽略并保护"},
                ],
            }
        ]
    )

    change_set = build_change_set_from_task_report(
        report,
        workspace_id="ws-1",
        write_mode="auto_draft",
    )

    assert change_set is not None
    unit = change_set.units[0]
    assert unit.target.room == "documents"
    assert unit.target.object_type == "draft_section"
    assert unit.target.path == "main.tex"
    assert unit.action == "apply_prism_change"
    assert unit.risk == "medium"
    assert unit.default_apply_state == "staged"
    assert unit.requires_confirmation is True


def test_memory_and_decision_outputs_require_confirmation() -> None:
    report = _report(
        outputs=[
            MemoryFactOutput(
                id="mem-1",
                kind="memory_fact",
                preview="Remember topic",
                data=MemoryFactData(content="User studies RAG evaluation."),
            ),
            DecisionOutput(
                id="dec-1",
                kind="decision",
                preview="Use qualitative analysis",
                data=DecisionData(key="method", value="qualitative"),
            ),
        ],
    )

    change_set = build_change_set_from_task_report(
        report,
        workspace_id="ws-1",
        write_mode="auto_draft",
    )

    assert change_set is not None
    units_by_id = {unit.id: unit for unit in change_set.units}
    assert units_by_id["output-mem-1"].target.room == "memory"
    assert units_by_id["output-mem-1"].default_apply_state == "staged"
    assert units_by_id["output-mem-1"].requires_confirmation is True
    assert units_by_id["output-mem-1"].materialization is not None
    assert units_by_id["output-mem-1"].materialization.operation == "memory.merge_items"
    assert units_by_id["output-mem-1"].materialization.payload["items"][0]["content"] == (
        "User studies RAG evaluation."
    )
    assert units_by_id["output-dec-1"].target.room == "decisions"
    assert units_by_id["output-dec-1"].default_apply_state == "staged"
    assert units_by_id["output-dec-1"].requires_confirmation is True
    assert units_by_id["output-dec-1"].materialization is not None
    assert units_by_id["output-dec-1"].materialization.operation == "decisions.set"
    assert units_by_id["output-dec-1"].materialization.payload["key"] == "method"


def test_unsafe_review_item_is_blocked_and_not_draft_applied() -> None:
    packet = ReviewPacket(
        packet_id="packet-1",
        execution_id="exec-1",
        capability_id="cap-1",
        title="Review packet",
        summary="Unsupported claim.",
        completion_status="partial",
        items=[
            ReviewPacketItem(
                item_id="claim-warning-1",
                kind="warning",
                title="Unsupported claim",
                summary="A claim has no evidence.",
                claim_refs=["claim-1"],
                risk={"level": "high", "reasons": ["unsupported claim"]},
                default_checked=False,
                can_commit=False,
                provenance={"execution_id": "exec-1"},
            )
        ],
    )

    change_set = build_change_set_from_task_report(
        _report(review_packet=packet),
        workspace_id="ws-1",
        write_mode="auto_draft",
    )

    assert change_set is not None
    unit = change_set.units[0]
    assert unit.target.room == "review"
    assert unit.risk == "high"
    assert unit.default_apply_state == "blocked"
    assert unit.requires_confirmation is True
    assert any("cannot be committed" in reason for reason in unit.risk_reasons)


def test_final_gate_review_item_projects_to_blocked_change_unit() -> None:
    report = _report(
        review_items=[
            {
                "id": "final-gate-claim_evidence_alignment-0",
                "kind": "warning",
                "title": "科研质量门未通过",
                "summary": "No claim-bearing Review Packet item was produced.",
                "status": "blocked",
                "source": {
                    "phase": "final_research_evidence",
                    "execution_id": "exec-1",
                    "surface": "claim_evidence_alignment",
                },
                "target": {
                    "kind": "research_evidence_gate",
                    "surface": "claim_evidence_alignment",
                },
                "preview": {
                    "format": "text",
                    "excerpt": "No claim-bearing Review Packet item was produced.",
                },
                "risk": {
                    "level": "high",
                    "reasons": ["No claim-bearing Review Packet item was produced."],
                },
                "quality_surfaces": ["claim_evidence_alignment"],
                "default_checked": False,
                "can_commit": False,
            }
        ]
    )

    change_set = build_change_set_from_task_report(
        report,
        workspace_id="ws-1",
        write_mode="auto_draft",
    )

    assert change_set is not None
    unit = change_set.units[0]
    assert unit.id == "review-final-gate-claim_evidence_alignment-0"
    assert unit.target.room == "review"
    assert unit.target.object_type == "warning"
    assert unit.default_apply_state == "blocked"
    assert unit.requires_confirmation is True
    assert unit.risk == "high"
    assert "No claim-bearing Review Packet item was produced." in unit.risk_reasons
    assert unit.materialization is None


def test_returns_none_when_report_has_no_reviewable_units() -> None:
    change_set = build_change_set_from_task_report(
        _report(),
        workspace_id="ws-1",
        write_mode=None,
    )

    assert change_set is None


def test_change_set_preview_is_capped_at_contract_limit() -> None:
    report = _report(
        outputs=[
            DocumentOutput(
                id=f"doc-{index}",
                kind="document",
                preview=f"Draft {index}",
                data=DocumentData(name=f"doc-{index}.md", doc_kind="draft", content="# Draft"),
            )
            for index in range(205)
        ],
    )

    change_set = build_change_set_from_task_report(
        report,
        workspace_id="ws-1",
        write_mode="auto_draft",
    )

    assert change_set is not None
    assert len(change_set.units) == 200
    assert "5 omitted from preview" in change_set.summary


def test_long_output_ids_and_paths_are_bounded_for_contract() -> None:
    long_id = "doc-" + ("x" * 300)
    long_name = "reports/" + ("very-long-section-name-" * 40) + ".md"
    report = _report(
        outputs=[
            DocumentOutput(
                id=long_id,
                kind="document",
                preview="Long path draft",
                data=DocumentData(name=long_name, doc_kind="draft", content="# Draft"),
            )
        ],
    )

    change_set = build_change_set_from_task_report(
        report,
        workspace_id="ws-1",
        write_mode="auto_draft",
    )

    assert change_set is not None
    unit = change_set.units[0]
    assert len(unit.id) <= 160
    assert len(unit.target.object_id or "") <= 160
    assert len(unit.target.path or "") <= 500
