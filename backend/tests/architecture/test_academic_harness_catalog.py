from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

FIRST_WAVE = [
    "seed/capabilities/sci/sci_literature_positioning.yaml",
    "seed/capabilities/sci/research_question_to_paper.yaml",
    "seed/capabilities/sci/sci_empirical_package.yaml",
    "seed/capabilities/sci/reproducibility_audit.yaml",
]

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


def test_first_wave_team_kernel_capabilities_have_ordered_phases_or_team_policy() -> None:
    for path in FIRST_WAVE:
        capability = _read_yaml(path)
        runtime_mode = capability.get("runtime", {}).get("mode")
        if runtime_mode is not None:
            assert runtime_mode in {"team_kernel", "graph"}, path
        has_team = bool(capability.get("team_policy", {}).get("core_templates"))
        has_graph = bool(capability.get("graph_template", {}).get("phases"))
        assert has_team or has_graph, path


def test_sci_first_wave_skills_declare_prompt_pack_v2_contract() -> None:
    for path in SCI_FIRST_WAVE_SKILLS:
        skill = _read_yaml(path)
        role_prompt = skill.get("worker", {}).get("role_prompt") or ""
        assert "Prompt Pack v2" in role_prompt, path
        assert "insufficient_evidence" in role_prompt, path
        assert "expert_report.claim_inventory" in role_prompt, path
        assert "expert_report.evidence_packet" in role_prompt, path
        expert_report_schema = (
            skill.get("io_contract", {})
            .get("output_schema", {})
            .get("properties", {})
            .get("expert_report", {})
        )
        assert expert_report_schema.get("type") == "object", path
        required = set(expert_report_schema.get("required") or [])
        assert {"claim_inventory", "evidence_packet"}.issubset(required), path
        properties = expert_report_schema.get("properties") or {}
        assert "research_brief_delta" in properties, path
        assert "claim_inventory" in properties, path
        assert "evidence_packet" in properties, path
