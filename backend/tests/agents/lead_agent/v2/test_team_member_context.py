from src.agents.contracts.task_brief import TaskBrief
from src.agents.lead_agent.v2.team.contracts import TeamBlackboard
from src.agents.lead_agent.v2.team.member_context import (
    build_team_member_context,
    project_research_brief_for_member_context,
    project_research_state_for_member_context,
    project_workspace_map_for_member_context,
)


def test_research_scout_context_derives_query_from_raw_message() -> None:
    payload = build_team_member_context(
        brief=TaskBrief(
            capability_id="sci_literature_positioning",
            workspace_id="ws-1",
            raw_message="联邦学习结合大模型 (Federated Learning combined with Large Language Models)",
            brief={},
        ),
        capability_name="文献定位与创新点",
        template_id="research_scout.v1",
        display_role="文献检索员",
        blackboard=TeamBlackboard(mission_summary="文献定位与创新点"),
    )

    assert payload["query"] == "Federated Learning combined with Large Language Models"
    assert payload["raw_message"].startswith("联邦学习")
    assert payload["task_focus"]
    assert payload["workspace_id"] == "ws-1"
    assert payload["capability_id"] == "sci_literature_positioning"
    assert payload["team_role"] == "文献检索员"


def test_member_context_preserves_explicit_query_and_filters_internal_refs() -> None:
    payload = build_team_member_context(
        brief=TaskBrief(
            capability_id="sci_literature_positioning",
            workspace_id="ws-1",
            raw_message="use my query",
            brief={
                "query": "privacy preserving LLM fine tuning",
                "topic": "federated LLM",
                "source_refs": [
                    "/workspace/reports/visible.md",
                    "/workspace/tmp/tasks/.harness/outputs/exec/node/raw.log",
                    "/workspace/.wenjin/manifest.json",
                ],
            },
        ),
        capability_name="文献定位与创新点",
        template_id="literature_synthesizer.v1",
        display_role="文献综合专家",
        blackboard=TeamBlackboard(
            mission_summary="文献定位与创新点",
            latest_leader_summary="检索到 federated LLM 来源。",
        ),
    )

    assert payload["query"] == "privacy preserving LLM fine tuning"
    assert payload["topic"] == "federated LLM"
    assert payload["upstream_context"]["latest_leader_summary"] == "检索到 federated LLM 来源。"
    assert "/workspace/reports/visible.md" in payload["source_refs"]
    assert all("/workspace/tmp/tasks/.harness/outputs" not in ref for ref in payload["source_refs"])
    assert all("/workspace/.wenjin" not in ref for ref in payload["source_refs"])


def test_member_context_projects_capability_research_evidence_requirements() -> None:
    payload = build_team_member_context(
        brief=TaskBrief(
            capability_id="sci_empirical_package",
            workspace_id="ws-1",
            raw_message="run a reproducible SCI analysis",
            brief={},
        ),
        capability_name="SCI 实证包",
        template_id="evidence_analyst.v1",
        display_role="实验分析工程师",
        blackboard=TeamBlackboard(mission_summary="SCI 实证包"),
        capability_policy={
            "research_evidence": {
                "required_surfaces": [
                    "workflow_trace",
                    "experiment_interpretation",
                    "output_ref_reuse",
                ]
            }
        },
    )

    assert payload["research_evidence_requirements"] == {
        "schema": "wenjin.team.research_evidence_requirements.v1",
        "quality_gate": "research_evidence_required",
        "required_surfaces": [
            "workflow_trace",
            "experiment_interpretation",
            "output_ref_reuse",
        ],
        "runtime_enforced_surfaces": [
            "workflow_trace",
            "experiment_interpretation",
            "output_ref_reuse",
        ],
        "guidance": [
            "Record completed tool activity through normal harness tools; do not summarize unsupported work.",
            "For experiments, return method, metric, verified result, limitation, artifact and dataset evidence aligned with reproducibility metadata.",
            "If a prior sandbox output ref is available, inspect it with sandbox.read_output_ref before rerunning expensive work.",
        ],
    }


def test_member_context_projects_quality_repair_context_from_failed_research_gate() -> None:
    recoverable_ref = "/workspace/tmp/tasks/.harness/outputs/exec-1/runner/stdout.txt"

    payload = build_team_member_context(
        brief=TaskBrief(
            capability_id="sci_empirical_package",
            workspace_id="ws-1",
            raw_message="continue the experiment",
            brief={},
        ),
        capability_name="SCI 实证包",
        template_id="evidence_analyst.v1",
        display_role="实验分析工程师",
        blackboard=TeamBlackboard(
            mission_summary="SCI 实证包",
            quality_gate_history=[
                {
                    "gate_id": "research_evidence_required",
                    "status": "fail",
                    "required_fixes": [
                        {
                            "message": "read the previous output ref",
                            "repair_context": {
                                "schema": "wenjin.team.quality_repair_context.v1",
                                "source_gates": ["research_evidence_required"],
                                "missing_research_surfaces": ["output_ref_reuse"],
                                "safe_output_refs": [
                                    recoverable_ref,
                                    "/workspace/.env",
                                    "/workspace/tmp/tasks/.harness/not-readable/raw.txt",
                                ],
                                "required_actions": [
                                    "Use sandbox.read_output_ref to inspect available output refs before rerunning expensive sandbox work.",
                                    "Do not expose raw stdout.",
                                ],
                            },
                        }
                    ],
                }
            ],
        ),
    )

    assert payload["upstream_context"]["quality_repair_context"] == {
        "schema": "wenjin.team.quality_repair_context.v1",
        "source_gates": ["research_evidence_required"],
        "missing_research_surfaces": ["output_ref_reuse"],
        "safe_output_refs": [recoverable_ref],
        "required_actions": [
            "Use sandbox.read_output_ref to inspect available output refs before rerunning expensive sandbox work.",
            "Do not expose raw stdout.",
        ],
    }


def test_member_context_includes_compact_research_state_for_later_batches() -> None:
    context = project_research_state_for_member_context(
        {
            "schema_version": "wenjin.research_state.v1",
            "execution_id": "exec-1",
            "goal": "AAAI paper on federated LLM fine-tuning",
            "research_brief": {"brief_id": "brief-1", "user_objective": "找 FedLLM 创新点"},
            "workspace_map_summary": {"topic_hints": ["FedLLM"]},
            "claims": [{"claim_id": "claim-1", "text": "FedLoRA reduces communication"}],
            "claim_inventory": [
                {
                    "claim_id": "claim-2",
                    "claim_type": "literature_position",
                    "text": "FedLLM communication remains open.",
                }
            ],
            "evidence_index": [{"evidence_id": "ev-1", "source_id": "source-1"}],
            "evidence_packet": [{"evidence_id": "ev-2", "source_key": "library:paper-1"}],
            "artifact_index": [],
            "open_questions": ["privacy evidence remains weak"],
            "unresolved_blockers": ["one novelty claim remains weak"],
            "quality_state": [{"surface": "citation_strength", "status": "warning"}],
        }
    )

    assert context is not None
    assert context["research_brief"]["brief_id"] == "brief-1"
    assert context["workspace_map_summary"]["topic_hints"] == ["FedLLM"]
    assert context["claims"][0]["claim_id"] == "claim-1"
    assert context["claim_inventory"][0]["claim_id"] == "claim-2"
    assert context["evidence_packet"][0]["evidence_id"] == "ev-2"
    assert context["unresolved_blockers"] == ["one novelty claim remains weak"]
    assert context["quality_state"][0]["surface"] == "citation_strength"


def test_member_context_includes_initial_research_brief_and_workspace_map() -> None:
    payload = build_team_member_context(
        brief=TaskBrief(
            capability_id="sci_literature_positioning",
            workspace_id="ws-1",
            raw_message="找联邦大模型创新点",
            brief={},
        ),
        capability_name="文献定位与创新点",
        template_id="research_planner.v1",
        display_role="研究规划师",
        blackboard=TeamBlackboard(mission_summary="文献定位与创新点"),
        research_brief={
            "schema_version": "wenjin.research_brief.v1",
            "brief_id": "brief-1",
            "research_topic": "FedLLM",
            "target_output": "文献图谱",
            "user_objective": "找联邦大模型创新点",
            "known_inputs": [{"kind": "user_objective", "summary": "FedLLM"}],
            "missing_inputs": [{"key": "dataset", "reason": "数据集未知"}],
            "perspectives": [{"perspective_id": "p1", "label": "通信效率"}],
            "search_plan": {"seed_queries": ["FedLLM LoRA"]},
            "quality_contract": {"unsupported_claim_policy": "mark_insufficient_evidence"},
        },
        workspace_map_summary={
            "schema_version": "wenjin.academic_workspace_map.summary.v1",
            "topic_hints": ["FedLLM"],
            "library": {"source_count": 2},
            "manuscript": {"sections": []},
            "experiments": {"datasets": []},
            "open_questions": ["是否已有 baseline？"],
        },
    )

    assert payload["research_brief"]["brief_id"] == "brief-1"
    assert payload["research_brief"]["missing_inputs"][0]["key"] == "dataset"
    assert payload["workspace_map_summary"]["topic_hints"] == ["FedLLM"]
    assert payload["workspace_map_summary"]["library"]["source_count"] == 2


def test_research_brief_and_workspace_map_projectors_bound_payloads() -> None:
    brief = project_research_brief_for_member_context(
        {
            "brief_id": "brief-1",
            "user_objective": "目标" * 3000,
            "perspectives": [{"perspective_id": str(idx), "label": "方向"} for idx in range(20)],
        }
    )
    workspace_map = project_workspace_map_for_member_context(
        {
            "topic_hints": [f"topic-{idx}" for idx in range(20)],
            "library": {"strong_sources": [{"title": "x" * 1000}]},
        }
    )

    assert brief is not None
    assert len(brief["user_objective"]) <= 4000
    assert len(brief["perspectives"]) == 8
    assert workspace_map is not None
    assert len(workspace_map["topic_hints"]) == 10
