from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

FIRST_WAVE = [
    "seed/capabilities/sci/sci_literature_positioning.yaml",
    "seed/capabilities/sci/research_question_to_paper.yaml",
    "seed/capabilities/sci/sci_empirical_package.yaml",
    "seed/capabilities/sci/reproducibility_audit.yaml",
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
