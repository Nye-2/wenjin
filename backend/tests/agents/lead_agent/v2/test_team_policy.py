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


def _template(template_id: str = "research_scholar.v1") -> AgentTemplate:
    return AgentTemplate(
        id=template_id,
        display_role="文献专家",
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
        build_capability_team_policy(cap, templates={"research_scholar.v1": _template()})


def test_build_capability_team_policy_applies_platform_caps() -> None:
    cap = SimpleNamespace(
        definition_json={
            "team_policy": {
                "core_templates": ["research_scholar.v1"],
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
        templates={"research_scholar.v1": _template()},
    )

    assert policy.limits.max_iterations == 8
    assert policy.limits.max_parallel_invocations == 5
    assert policy.limits.max_invocations_total == 24
    assert policy.limits.max_invocations_per_template == 6


def test_effective_tools_keep_high_ceiling_but_block_direct_commit() -> None:
    policy = CapabilityTeamPolicy(
        core_templates=["research_scholar.v1"],
        optional_templates=[],
        capability_tools=["web_search", "library_read", "citation_parser", "room_commit"],
        workspace_tools=["web_search", "library_read", "citation_parser", "artifact_create"],
        user_tools=["web_search", "library_read", "citation_parser", "artifact_create", "room_commit"],
    )
    effective = resolve_effective_tools(_template(), policy)

    assert effective == ["web_search", "library_read", "citation_parser"]
    assert "room_commit" not in effective


def test_capability_team_policy_respects_empty_user_tool_allowlist() -> None:
    cap = SimpleNamespace(
        definition_json={
            "team_policy": {
                "core_templates": ["research_scholar.v1"],
                "capability_tools": ["web_search", "library_read", "citation_parser"],
            }
        },
        runtime={"mode": "team_kernel"},
    )

    policy = build_capability_team_policy(
        cap,
        templates={"research_scholar.v1": _template()},
        user_tools=[],
    )

    assert policy.user_tools == []
    assert resolve_effective_tools(_template(), policy) == []


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
