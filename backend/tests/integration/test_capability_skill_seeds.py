"""Integration test: all capability seeds reference existing skills."""

from pathlib import Path

import yaml

SEED_ROOT = Path(__file__).resolve().parent.parent.parent / "seed"


def _collect_skill_ids() -> set[str]:
    out: set[str] = set()
    for f in (SEED_ROOT / "skills").glob("*.yaml"):
        data = yaml.safe_load(f.read_text())
        out.add(data["id"])
    return out


def _collect_capability_files() -> list[Path]:
    return list((SEED_ROOT / "capabilities").glob("*/*.yaml"))


def test_every_capability_skill_id_exists():
    skill_ids = _collect_skill_ids()
    assert skill_ids, "no skills found"

    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        for phase in data["graph_template"]["phases"]:
            for task in phase["tasks"]:
                sid = task.get("skill_id")
                assert sid is not None, f"{cap_path}: task {task.get('name')} missing skill_id"
                assert sid in skill_ids, (
                    f"{cap_path}: task {task['name']} references unknown skill_id '{sid}'. "
                    f"Available: {sorted(skill_ids)}"
                )


def test_every_capability_subagent_type_is_searcher_or_react():
    valid = {"searcher", "react"}
    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        for phase in data["graph_template"]["phases"]:
            for task in phase["tasks"]:
                st = task.get("subagent_type")
                assert st in valid, (
                    f"{cap_path}: task {task['name']} has invalid subagent_type '{st}'. "
                    f"Must be one of {valid}"
                )


def test_every_capability_required_fields_present():
    required = {
        "schema_version",
        "id",
        "workspace_type",
        "display",
        "intent",
        "mission",
        "inputs",
        "context_policy",
        "sandbox_policy",
        "review_policy",
        "quality_gates",
        "graph_template",
    }
    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        missing = required - set(data.keys())
        assert not missing, f"{cap_path}: missing fields {missing}"
        assert data["schema_version"] == "capability.v2"
        assert data["mission"]["primary_surface"] == "prism"
        assert "requires_sandbox" not in data
        assert "runtime" not in data


def test_every_skill_required_fields_present():
    required = {
        "schema_version",
        "id",
        "display_name",
        "worker",
        "io_contract",
        "context_access",
        "tool_policy",
        "sandbox_access",
        "quality_gates",
    }
    for skill_path in (SEED_ROOT / "skills").glob("*.yaml"):
        data = yaml.safe_load(skill_path.read_text())
        missing = required - set(data.keys())
        assert not missing, f"{skill_path}: missing fields {missing}"
        assert data["schema_version"] == "capability_skill.v2"
        assert "config" not in data
        assert "subagent_type" not in data


def test_capability_count_matches_spec():
    files = _collect_capability_files()
    by_ws: dict[str, int] = {}
    for f in files:
        data = yaml.safe_load(f.read_text())
        by_ws[data["workspace_type"]] = by_ws.get(data["workspace_type"], 0) + 1
    assert by_ws.get("thesis") == 6, f"thesis: expected 6, got {by_ws.get('thesis', 0)}"
    assert by_ws.get("sci") == 7, f"sci: expected 7, got {by_ws.get('sci', 0)}"
    assert by_ws.get("proposal") == 5, f"proposal: expected 5, got {by_ws.get('proposal', 0)}"
    assert by_ws.get("patent") == 5, f"patent: expected 5, got {by_ws.get('patent', 0)}"
    assert by_ws.get("software_copyright") == 4, f"software_copyright: expected 4, got {by_ws.get('software_copyright', 0)}"


def test_old_workflow_capability_ids_are_removed():
    old_ids = {
        "outline_generate",
        "section_write",
        "section_revise",
        "opening_research",
        "framework_outline",
        "section_writing",
        "literature_search",
        "literature_review",
        "paper_analysis",
        "peer_review",
        "proposal_outline",
        "experiment_design",
        "patent_outline",
        "prior_art_search",
        "copyright_materials",
        "technical_description",
        "figure_generation",
        "writing",
        "thesis_writing",
    }
    current_ids = {
        yaml.safe_load(path.read_text())["id"]
        for path in _collect_capability_files()
    }
    assert old_ids.isdisjoint(current_ids)
