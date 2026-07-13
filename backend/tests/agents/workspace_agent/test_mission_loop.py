from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from src.agents.workspace_agent.mission_loop import (
    WorkspaceMissionLoopProtocolError,
    mission_decision_tool,
    parse_mission_decision,
)
from src.agents.workspace_agent.prompts.mission import render_workspace_mission_prompt


def test_mission_loop_never_parses_prose_or_multiple_frames() -> None:
    with pytest.raises(WorkspaceMissionLoopProtocolError, match="exactly one"):
        parse_mission_decision(AIMessage(content='{"kind":"complete"}'))

    with pytest.raises(WorkspaceMissionLoopProtocolError, match="exactly one"):
        parse_mission_decision(
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "mission_step", "args": {}, "id": "one"},
                    {"name": "mission_step", "args": {}, "id": "two"},
                ],
            )
        )


def test_mission_loop_rejects_malformed_provider_arguments() -> None:
    with pytest.raises(WorkspaceMissionLoopProtocolError, match="malformed"):
        parse_mission_decision(
            AIMessage(
                content="ignored provider prose",
                tool_calls=[
                    {
                        "name": "mission_step",
                        "args": {"kind": "complete"},
                        "id": "bad-frame",
                    }
                ],
            )
        )


def test_mission_loop_decodes_provider_json_object_fields() -> None:
    decision = parse_mission_decision(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "mission_step",
                    "args": {
                        "decision_id": "plan-1",
                        "kind": "continue",
                        "summary": "Plan the first stage",
                        "operation_id": None,
                        "stage_id": "materials_inventory",
                        "risk_level": None,
                        "plan_json": '{"next":"inspect materials"}',
                        "tool_name": None,
                        "tool_arguments_json": "{}",
                        "subagent_jobs": [],
                        "quality_candidate_refs": [],
                        "quality_criteria": [],
                        "quality_artifacts": [],
                        "quality_output_refs": [],
                        "quality_critiques": [],
                        "quality_blocking_user_inputs": [],
                        "review_summary": None,
                        "review_items": [],
                        "failure_reason": None,
                        "pause_request": None,
                    },
                    "id": "frame-1",
                }
            ],
        )
    )

    assert decision.payload_json == {"next": "inspect materials"}
    assert decision.snapshot_patch == {}


def test_mission_loop_provider_schema_is_strict_recursively() -> None:
    schema = mission_decision_tool()["function"]["parameters"]

    def assert_strict_objects(node: object) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("properties"), dict):
                assert node.get("additionalProperties") is False
                assert set(node["required"]) == set(node["properties"])
            assert "default" not in node
            for value in node.values():
                assert_strict_objects(value)
        elif isinstance(node, list):
            for value in node:
                assert_strict_objects(value)

    assert_strict_objects(schema)


def test_mission_prompt_projects_canonical_tool_schema_and_source_boundary() -> None:
    prompt = render_workspace_mission_prompt(
        {
            "mission_policy_snapshot": {"id": "math_modeling_solution"},
            "stage_contracts": {"problem_understanding": {"stage_id": "problem_understanding"}},
            "tool_policy": {
                "allowed_tool_ids": [
                    "source.import_candidate",
                    "sandbox.run_python",
                ]
            },
            "worker_skill_snapshots": {},
        }
    )

    assert "canonical_tool_contracts" in prompt
    assert '"citation_key"' in prompt
    assert '"verification_ref"' in prompt
    assert "raw review_item_id" in prompt
    assert "mission-review:<id> observation" in prompt
    assert '"script"' in prompt
    assert "A user chat message" in prompt
    assert "is Mission context, not a source candidate" in prompt


def test_mission_prompt_rejects_tool_without_canonical_schema() -> None:
    with pytest.raises(ValueError, match="no canonical input schema"):
        render_workspace_mission_prompt(
            {
                "mission_policy_snapshot": {"id": "test"},
                "stage_contracts": {"stage": {"stage_id": "stage"}},
                "tool_policy": {"allowed_tool_ids": ["unknown.tool"]},
                "worker_skill_snapshots": {},
            }
        )


def test_mission_loop_maps_typed_subagent_jobs_to_runtime_scope() -> None:
    decision = parse_mission_decision(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "mission_step",
                    "args": {
                        "decision_id": "delegate-1",
                        "kind": "subagent",
                        "summary": "Draft the grounded materials inventory",
                        "operation_id": "op-delegate-1",
                        "stage_id": "materials_inventory",
                        "risk_level": "low",
                        "plan_json": "{}",
                        "tool_name": None,
                        "tool_arguments_json": "{}",
                        "subagent_jobs": [
                            {
                                "display_name": "材料整理师",
                                "role_label": "软著材料专员",
                                "worker_skill_id": "software-documenter",
                                "task_summary": "Separate known facts from missing materials",
                                "task_input_json": '{"known_facts":["React"]}',
                                "selected_refs": ["mission-snapshot://intake"],
                                "budget": {
                                    "max_turns": 4,
                                    "max_tool_steps": 0,
                                    "max_context_bytes": 96000,
                                    "max_result_bytes": 64000,
                                },
                            }
                        ],
                        "quality_candidate_refs": [],
                        "quality_criteria": [],
                        "quality_artifacts": [],
                        "quality_output_refs": [],
                        "quality_critiques": [],
                        "quality_blocking_user_inputs": [],
                        "review_summary": None,
                        "review_items": [],
                        "failure_reason": None,
                        "pause_request": None,
                    },
                    "id": "frame-subagent",
                }
            ],
        )
    )

    job = decision.payload_json["input_scope"]["jobs"][0]
    assert job["worker_skill_id"] == "software-documenter"
    assert job["known_facts"] == ["React"]
    assert job["budget"]["max_turns"] == 4


def test_mission_loop_maps_typed_review_items_to_atomic_candidates() -> None:
    decision = parse_mission_decision(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "mission_step",
                    "args": {
                        "decision_id": "review-1",
                        "kind": "review",
                        "summary": "Prepare the materials inventory for review",
                        "operation_id": "op-review-1",
                        "stage_id": "materials_inventory",
                        "risk_level": "medium",
                        "plan_json": "{}",
                        "tool_name": None,
                        "tool_arguments_json": "{}",
                        "subagent_jobs": [],
                        "quality_candidate_refs": [],
                        "quality_criteria": [],
                        "quality_artifacts": [],
                        "quality_output_refs": [],
                        "quality_critiques": [],
                        "quality_blocking_user_inputs": [],
                        "review_summary": "One grounded draft is ready",
                        "review_items": [
                            {
                                "review_item_id": "review-item-1",
                                "source_item_seq": 8,
                                "target_kind": "document",
                                "target_room": "documents",
                                "target_ref": "软著材料盘点.md",
                                "base_revision_ref": None,
                                "base_hash": None,
                                "title": "软著材料盘点",
                                "summary": "Known facts and missing evidence",
                                "risk_level": "medium",
                                "review_required_reason": "Document write requires confirmation",
                                "preview_json": '{"format":"markdown","content":"# 材料盘点"}',
                                "preview_ref": None,
                            }
                        ],
                        "failure_reason": None,
                        "pause_request": None,
                    },
                    "id": "frame-review",
                }
            ],
        )
    )

    item = decision.payload_json["items"][0]
    assert item["target_room"] == "documents"
    assert item["preview_json"]["content"] == "# 材料盘点"


def test_mission_loop_maps_quality_assessment_without_snapshot_side_channel() -> None:
    base = {
        "decision_id": "quality-1",
        "kind": "quality",
        "summary": "Evaluate the materials inventory",
        "operation_id": "op-quality-1",
        "stage_id": "materials_inventory",
        "risk_level": "medium",
        "plan_json": "{}",
        "tool_name": None,
        "tool_arguments_json": "{}",
        "subagent_jobs": [],
        "quality_candidate_refs": ["mi-candidate-v1"],
        "quality_criteria": [
            {
                "criterion_id": "software_identity",
                "status": "pass",
                "supporting_refs": ["mi-candidate-v1"],
                "rationale": "Identity fields are explicit.",
            }
        ],
        "quality_artifacts": [
            {
                "artifact_id": "mi-candidate-v1",
                "kind": "software_evidence_inventory",
                "content_hash": "a" * 64,
                "manifest_ref": None,
                "script_ref": None,
                "data_refs": [],
                "metadata_json": '{"review_status":"pending"}',
            }
        ],
        "quality_output_refs": ["mi-candidate-v1"],
        "quality_critiques": [
            {
                "reviewer_role": "software_material_reviewer",
                "verdict": "pass",
                "criterion_ids": ["software_identity"],
                "note": "Candidate is reviewable.",
            }
        ],
        "quality_blocking_user_inputs": [],
        "review_summary": None,
        "review_items": [],
        "failure_reason": None,
        "pause_request": None,
    }
    decision = parse_mission_decision(
        AIMessage(
            content="",
            tool_calls=[{"name": "mission_step", "args": base, "id": "frame-quality"}],
        )
    )

    assessment = decision.payload_json["assessment"]
    assert assessment["criterion_assessments"][0]["criterion_id"] == "software_identity"
    assert assessment["artifacts"][0]["metadata"] == {"review_status": "pending"}
