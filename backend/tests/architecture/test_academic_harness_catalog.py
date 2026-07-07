from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

FIRST_WAVE = [
    "seed/capabilities/sci/sci_literature_positioning.yaml",
    "seed/capabilities/sci/research_question_to_paper.yaml",
    "seed/capabilities/sci/sci_empirical_package.yaml",
    "seed/capabilities/sci/reproducibility_audit.yaml",
]

REPRESENTATIVE_WORKSPACE_HARNESS = {
    "seed/capabilities/thesis/thesis_research_pack.yaml": {
        "literature",
        "citation_strength",
        "paper_relevance",
        "writing_semantic_preservation",
        "argument_chain",
        "protected_section_safety",
    },
    "seed/capabilities/proposal/idea_to_proposal_package.yaml": {
        "writing_semantic_preservation",
        "writing_academic_style",
        "feasibility_evidence",
        "risk_evidence",
        "milestone_realism",
    },
    "seed/capabilities/patent/invention_to_patent_draft.yaml": {
        "citation_strength",
        "writing_semantic_preservation",
        "prior_art_provenance",
        "claim_support",
        "enablement_support",
        "drawing_consistency",
    },
    "seed/capabilities/software_copyright/software_copyright_application_pack.yaml": {
        "output_ref_reuse",
        "figure_data_consistency",
        "source_provenance",
        "screenshot_provenance",
        "non_fabrication_evidence",
    },
    "seed/capabilities/math_modeling/math_modeling_paper_pack.yaml": {
        "experiment_reproducibility",
        "figure_data_consistency",
        "statistical_robustness",
        "ai_use_disclosure",
    },
}

METHODOLOGY_REPRESENTATIVES = {
    "seed/capabilities/sci/research_question_to_paper.yaml": {
        "stages": {
            "scope",
            "literature_facets",
            "reason",
            "methodology",
            "execute_or_draft",
            "analyze",
            "synthesize",
            "write_review",
        },
        "gates": {
            "workflow_trace",
            "review_packet_completeness",
            "claim_evidence_alignment",
        },
    },
    "seed/capabilities/sci/sci_literature_positioning.yaml": {
        "stages": {
            "scope",
            "literature_facets",
            "gap_reasoning",
            "positioning_synthesis",
            "review",
        },
        "gates": {
            "workflow_trace",
            "review_packet_completeness",
            "claim_evidence_alignment",
        },
    },
    "seed/capabilities/thesis/thesis_research_pack.yaml": {
        "stages": {
            "scope",
            "literature_facets",
            "framework_reasoning",
            "outline_methodology",
            "synthesize",
            "review",
        },
        "gates": {
            "workflow_trace",
            "review_packet_completeness",
            "claim_evidence_alignment",
        },
    },
}

SCI_FIRST_WAVE_SKILLS = [
    "seed/skills/query-planner.yaml",
    "seed/skills/research-scout.yaml",
    "seed/skills/source-screener.yaml",
    "seed/skills/literature-synthesizer.yaml",
    "seed/skills/citation-auditor.yaml",
    "seed/skills/method-design.yaml",
    "seed/skills/evidence-analyst.yaml",
    "seed/skills/reproducibility-auditor.yaml",
    "seed/skills/manuscript-architect.yaml",
    "seed/skills/manuscript-writer.yaml",
    "seed/skills/review-critic.yaml",
]

CROSS_WORKSPACE_CRITICAL_SKILLS = [
    "seed/skills/claim-verifier.yaml",
    "seed/skills/figure-engineer.yaml",
    "seed/skills/format-compliance-checker.yaml",
    "seed/skills/grant-planner.yaml",
    "seed/skills/patent-drafter.yaml",
    "seed/skills/patent-strategist.yaml",
    "seed/skills/proposal-writer.yaml",
    "seed/skills/software-doc-drafter.yaml",
    "seed/skills/software-structure-planner.yaml",
    "seed/skills/source-quality-auditor.yaml",
    "seed/skills/task-scope-planner.yaml",
    "seed/skills/thesis-school-rules.yaml",
]


def _read_yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text()) or {}


def test_first_wave_capabilities_declare_academic_harness_policy() -> None:
    for path in FIRST_WAVE:
        capability = _read_yaml(path)
        policy = capability.get("research_evidence")
        assert isinstance(policy, dict), path
        assert policy.get("review_packet") == "required", path
        assert isinstance(policy.get("required_surfaces"), list) and policy["required_surfaces"], path
        assert isinstance(policy.get("surface_enforcement"), dict), path
        assert "review_packet_completeness" in policy["required_surfaces"], path
        assert "claim_evidence_alignment" in policy["required_surfaces"], path


def test_representative_workspace_capabilities_declare_research_evidence_surfaces() -> None:
    for path, domain_surfaces in REPRESENTATIVE_WORKSPACE_HARNESS.items():
        capability = _read_yaml(path)
        policy = capability.get("research_evidence")
        assert isinstance(policy, dict), path
        assert policy.get("review_packet") == "required", path

        required_surfaces = set(policy.get("required_surfaces") or [])
        assert {"workflow_trace", "review_packet_completeness", "claim_evidence_alignment"}.issubset(
            required_surfaces
        ), path
        assert domain_surfaces.issubset(required_surfaces), path

        enforcement = policy.get("surface_enforcement")
        assert isinstance(enforcement, dict), path
        missing_enforcement = required_surfaces - set(enforcement)
        assert not missing_enforcement, f"{path} missing enforcement for {sorted(missing_enforcement)}"


def test_representative_research_capabilities_expose_research_loop_methodology() -> None:
    for path, expected in METHODOLOGY_REPRESENTATIVES.items():
        capability = _read_yaml(path)
        methodology = capability.get("methodology") or {}
        stages = methodology.get("stages") or []
        stage_ids = {stage.get("id") for stage in stages}
        assert stage_ids == expected["stages"], path
        assert "literature_facets" in stage_ids, path

        completion_gates = set(methodology.get("completion_gates") or [])
        assert expected["gates"].issubset(completion_gates), path


def test_first_wave_team_kernel_capabilities_have_ordered_phases_or_team_policy() -> None:
    for path in FIRST_WAVE:
        capability = _read_yaml(path)
        runtime_mode = capability.get("runtime", {}).get("mode")
        if runtime_mode is not None:
            assert runtime_mode in {"team_kernel", "graph"}, path
        has_team = bool(capability.get("team_policy", {}).get("core_templates"))
        has_graph = bool(capability.get("graph_template", {}).get("phases"))
        assert has_team or has_graph, path


def test_sci_first_wave_skills_declare_prompt_pack_v3_contract() -> None:
    for path in SCI_FIRST_WAVE_SKILLS:
        _assert_prompt_pack_v3_skill(path)


def test_cross_workspace_critical_skills_declare_prompt_pack_v3_contract() -> None:
    for path in CROSS_WORKSPACE_CRITICAL_SKILLS:
        _assert_prompt_pack_v3_skill(path)


def _assert_prompt_pack_v3_skill(path: str) -> None:
    skill = _read_yaml(path)
    role_prompt = skill.get("worker", {}).get("role_prompt") or ""
    assert "Prompt Pack v2" not in role_prompt, path
    assert "Prompt Pack v3" in role_prompt, path
    assert "`methodology_contract`" in role_prompt, path
    assert "`required_artifacts`" in role_prompt, path
    assert "`retrieval_policy.escalation`" in role_prompt, path
    assert "insufficient_evidence" in role_prompt, path
    assert "expert_report.claim_inventory" in role_prompt, path
    assert "expert_report.evidence_packet" in role_prompt, path
    output_schema = skill.get("io_contract", {}).get("output_schema", {})
    assert "expert_report" in set(output_schema.get("required") or []), path
    expert_report_schema = output_schema.get("properties", {}).get("expert_report", {})
    assert expert_report_schema.get("type") == "object", path
    required = set(expert_report_schema.get("required") or [])
    assert {"claim_inventory", "evidence_packet"}.issubset(required), path
    properties = expert_report_schema.get("properties") or {}
    assert "research_brief_delta" in properties, path
    assert "claim_inventory" in properties, path
    assert "evidence_packet" in properties, path
