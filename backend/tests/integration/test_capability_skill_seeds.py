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
    required = {"id", "workspace_type", "display_name", "intent_description",
                "brief_schema", "graph_template", "ui_meta"}
    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        missing = required - set(data.keys())
        assert not missing, f"{cap_path}: missing fields {missing}"


def test_capability_count_matches_spec():
    files = _collect_capability_files()
    by_ws: dict[str, int] = {}
    for f in files:
        data = yaml.safe_load(f.read_text())
        by_ws[data["workspace_type"]] = by_ws.get(data["workspace_type"], 0) + 1
    assert by_ws.get("thesis") == 7, f"thesis: expected 7, got {by_ws.get('thesis', 0)}"
    assert by_ws.get("sci") == 8, f"sci: expected 8, got {by_ws.get('sci', 0)}"
    assert by_ws.get("proposal") == 4, f"proposal: expected 4, got {by_ws.get('proposal', 0)}"
    assert by_ws.get("patent") == 3, f"patent: expected 3, got {by_ws.get('patent', 0)}"
    assert by_ws.get("software_copyright") == 3, f"software_copyright: expected 3, got {by_ws.get('software_copyright', 0)}"
