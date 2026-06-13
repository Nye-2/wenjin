from types import SimpleNamespace

import pytest

from src.agents.lead_agent.v2.team.contracts import (
    AgentTemplate,
    CapabilityTeamPolicy,
)
from src.agents.lead_agent.v2.team.policy import (
    TeamPolicyError,
    build_capability_team_policy,
    build_invocation_assignment,
    resolve_effective_skills,
    resolve_effective_tools,
)


def _template(template_id: str = "research_scout.v1") -> AgentTemplate:
    return AgentTemplate(
        id=template_id,
        display_role="文献检索员",
        category="research",
        description="Research role",
        persona_prompt="research",
        default_skills=["research-scout", "citation-auditor"],
        tool_affinity={
            "preferred": ["web_search", "library_read"],
            "can_request": ["citation_parser", "artifact_create"],
        },
        risk_profile={"room_write": "staged_only"},
        output_contracts=["literature_evidence_report.v1"],
        quality_expectations=["claims map to sources"],
        runtime_defaults={"max_turns": 8},
    )


def test_build_capability_team_policy_rejects_unknown_template() -> None:
    cap = SimpleNamespace(
        definition_json={
            "team_policy": {
                "core_templates": ["missing.v1"],
                "optional_templates": [],
                "limits": {"max_iterations": 3},
            }
        },
        runtime={"mode": "team_kernel"},
    )

    with pytest.raises(TeamPolicyError, match="unknown agent template"):
        build_capability_team_policy(cap, templates={"research_scout.v1": _template()})


def test_build_capability_team_policy_applies_platform_caps() -> None:
    cap = SimpleNamespace(
        definition_json={
            "team_policy": {
                "core_templates": ["research_scout.v1"],
                "optional_templates": [],
                "limits": {
                    "max_iterations": 99,
                    "max_parallel_invocations": 99,
                    "max_invocations_total": 99,
                    "max_invocations_per_template": 99,
                    "no_progress_rounds_before_stop": 9,
                },
                "budget": {"max_tokens_soft": 1000, "max_tokens_hard": 2000},
            }
        },
        runtime={"mode": "team_kernel"},
    )

    policy = build_capability_team_policy(
        cap,
        templates={"research_scout.v1": _template()},
    )

    assert policy.limits.max_iterations == 8
    assert policy.limits.max_parallel_invocations == 5
    assert policy.limits.max_invocations_total == 24
    assert policy.limits.max_invocations_per_template == 6


def test_build_capability_team_policy_rejects_unknown_trigger_template() -> None:
    cap = SimpleNamespace(
        definition_json={
            "team_policy": {
                "core_templates": ["research_scout.v1"],
                "optional_templates": [],
                "recruitment_triggers": {"member_failed": ["missing.v1"]},
            }
        },
        runtime={"mode": "team_kernel"},
    )

    with pytest.raises(TeamPolicyError, match="unknown recruitment trigger template"):
        build_capability_team_policy(cap, templates={"research_scout.v1": _template()})


def test_effective_tools_keep_high_ceiling_but_block_direct_commit() -> None:
    policy = CapabilityTeamPolicy(
        core_templates=["research_scout.v1"],
        optional_templates=[],
        capability_tools=["web_search", "library_read", "citation_parser", "room_commit"],
        workspace_tools=["web_search", "library_read", "citation_parser", "artifact_create"],
        user_tools=["web_search", "library_read", "citation_parser", "artifact_create", "room_commit"],
    )
    effective = resolve_effective_tools(_template(), policy)

    assert effective == ["web_search", "library_read", "citation_parser"]
    assert "room_commit" not in effective


def test_effective_tools_canonicalize_sandbox_tool_aliases() -> None:
    template = AgentTemplate(
        id="code_engineer.v1",
        display_role="码农一号",
        category="engineering",
        description="Runs code experiments",
        persona_prompt="code",
        default_skills=[],
        tool_affinity={
            "preferred": ["sandbox_python"],
            "can_request": ["sandbox.read_file"],
        },
        risk_profile={},
        output_contracts=[],
        quality_expectations=[],
        runtime_defaults={},
    )
    policy = CapabilityTeamPolicy(
        core_templates=["code_engineer.v1"],
        optional_templates=[],
        capability_tools=["sandbox.run_python", "sandbox.read_file"],
        workspace_tools=["sandbox.run_python", "sandbox.read_file"],
        user_tools=["sandbox.run_python", "sandbox.read_file"],
    )

    assert resolve_effective_tools(template, policy) == [
        "sandbox.run_python",
        "sandbox.read_file",
    ]


def test_capability_team_policy_respects_empty_user_tool_allowlist() -> None:
    cap = SimpleNamespace(
        definition_json={
            "team_policy": {
                "core_templates": ["research_scout.v1"],
                "capability_tools": ["web_search", "library_read", "citation_parser"],
            }
        },
        runtime={"mode": "team_kernel"},
    )

    policy = build_capability_team_policy(
        cap,
        templates={"research_scout.v1": _template()},
        user_tools=[],
    )

    assert policy.user_tools == []
    assert resolve_effective_tools(_template(), policy) == []


def test_invocation_assignment_uses_expert_profile_public_identity() -> None:
    template = AgentTemplate(
        id="research_scout.v1",
        display_role="文献检索员",
        category="research",
        expert_profile={
            "public_name": "文献猎手 Nora",
            "role_title": "文献检索专家",
            "avatar_label": "文",
            "status_phrases": {"running": "扫文献雷达中"},
        },
    )

    assignment = build_invocation_assignment(
        template=template,
        iteration=1,
        template_invocation_count=1,
        reason="core",
        input_brief={},
        effective_tools=[],
        effective_skills=[],
    )

    assert assignment.display_name == "文献猎手 Nora"
    assert assignment.assigned_role == "文献检索专家"
    assert assignment.expert_profile["public_name"] == "文献猎手 Nora"


def test_invocation_assignment_applies_capability_profile_override() -> None:
    template = AgentTemplate(
        id="literature_synthesizer.v1",
        display_role="文献综合专家",
        category="research",
        expert_profile={
            "public_name": "文献专家",
            "role_title": "文献综合专家",
            "status_phrases": {"running": "整理文献中"},
        },
    )

    assignment = build_invocation_assignment(
        template=template,
        iteration=1,
        template_invocation_count=1,
        reason="core",
        input_brief={},
        effective_tools=[],
        effective_skills=[],
        profile_override={
            "public_name": "综述姐 Athena",
            "status_phrases": {"running": "织主题矩阵中"},
        },
    )

    assert assignment.display_name == "综述姐 Athena"
    assert assignment.assigned_role == "文献综合专家"
    assert assignment.expert_profile["status_phrases"]["running"] == "织主题矩阵中"


def test_build_capability_team_policy_materializes_template_profile_overrides() -> None:
    cap = SimpleNamespace(
        definition_json={
            "team_policy": {
                "core_templates": ["literature_synthesizer.v1"],
                "optional_templates": [],
            },
            "extensions": {
                "team_presentation": {
                    "template_overrides": {
                        "literature_synthesizer.v1": {
                            "public_name": "综述姐 Athena",
                            "status_phrases": {"running": "织主题矩阵中"},
                        }
                    }
                }
            },
        },
        runtime={"mode": "team_kernel"},
    )

    policy = build_capability_team_policy(
        cap,
        templates={"literature_synthesizer.v1": _template("literature_synthesizer.v1")},
    )

    override = policy.template_profile_overrides["literature_synthesizer.v1"]
    assert override["public_name"] == "综述姐 Athena"
    assert override["status_phrases"]["running"] == "织主题矩阵中"


def test_build_capability_team_policy_rejects_override_outside_team_policy() -> None:
    cap = SimpleNamespace(
        definition_json={
            "team_policy": {
                "core_templates": ["research_scout.v1"],
                "optional_templates": [],
            },
            "extensions": {
                "team_presentation": {
                    "template_overrides": {
                        "literature_synthesizer.v1": {
                            "public_name": "综述姐 Athena",
                        }
                    }
                }
            },
        },
        runtime={"mode": "team_kernel"},
    )

    with pytest.raises(TeamPolicyError, match="override outside team_policy"):
        build_capability_team_policy(
            cap,
            templates={
                "research_scout.v1": _template("research_scout.v1"),
                "literature_synthesizer.v1": _template("literature_synthesizer.v1"),
            },
        )


def test_build_capability_team_policy_reads_contract_overlays() -> None:
    cap = SimpleNamespace(
        definition_json={
            "team_policy": {
                "core_templates": ["research_scout.v1"],
                "contract_overlay_skills": ["sci-journal-rules", "sci-journal-rules"],
                "contract_overlay_categories": ["review", "writing", "review"],
            }
        },
        runtime={"mode": "team_kernel"},
    )

    policy = build_capability_team_policy(
        cap,
        templates={"research_scout.v1": _template()},
    )

    assert policy.contract_overlay_skills == ["sci-journal-rules"]
    assert policy.contract_overlay_categories == ["review", "writing"]


def test_invocation_assignment_names_duplicate_templates() -> None:
    assignment_a = build_invocation_assignment(
        template=_template("code_engineer.v1"),
        iteration=1,
        template_invocation_count=1,
        reason="code required",
        input_brief={"task": "patch"},
        effective_tools=["sandbox_exec"],
        effective_skills=["code-patch-planning"],
    )
    assignment_b = build_invocation_assignment(
        template=_template("code_engineer.v1"),
        iteration=1,
        template_invocation_count=2,
        reason="parallel code review",
        input_brief={"task": "review"},
        effective_tools=["sandbox_exec"],
        effective_skills=["code-patch-planning"],
    )

    assert assignment_a.display_name.endswith("A")
    assert assignment_b.display_name.endswith("B")
    assert assignment_b.template_id == "code_engineer.v1"


def test_effective_skills_include_template_defaults_and_task_requested() -> None:
    effective = resolve_effective_skills(
        _template(),
        requested_skills=["evidence_traceability.v1"],
        capability_skills=["research-scout", "citation-auditor", "evidence_traceability.v1"],
    )

    assert effective == ["research-scout", "citation-auditor", "evidence_traceability.v1"]
