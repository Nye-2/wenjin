"""Integration test: all capability seeds reference existing skills."""

from pathlib import Path

import yaml

SEED_ROOT = Path(__file__).resolve().parent.parent.parent / "seed"
SKILLLESS_SUBAGENTS = {"sandbox_python", "prism_selection_optimizer"}


def _collect_skill_ids() -> set[str]:
    out: set[str] = set()
    for f in (SEED_ROOT / "skills").glob("*.yaml"):
        data = yaml.safe_load(f.read_text())
        out.add(data["id"])
    return out


def _collect_capability_files() -> list[Path]:
    return list((SEED_ROOT / "capabilities").glob("*/*.yaml"))


def _is_hidden_capability(data: dict) -> bool:
    return (data.get("display") or {}).get("entry_tier") == "hidden"


def test_every_capability_skill_id_exists():
    skill_ids = _collect_skill_ids()
    assert skill_ids, "no skills found"

    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        for phase in data["graph_template"]["phases"]:
            for task in phase["tasks"]:
                if task.get("subagent_type") in SKILLLESS_SUBAGENTS:
                    continue
                sid = task.get("skill_id")
                assert sid is not None, f"{cap_path}: task {task.get('name')} missing skill_id"
                assert sid in skill_ids, (
                    f"{cap_path}: task {task['name']} references unknown skill_id '{sid}'. "
                    f"Available: {sorted(skill_ids)}"
                )


def test_every_capability_subagent_type_is_registered():
    from src.subagents.v2 import types as _types  # noqa: F401
    from src.subagents.v2.registry import REGISTRY

    valid = set(REGISTRY.all_names())
    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        for phase in data["graph_template"]["phases"]:
            for task in phase["tasks"]:
                st = task.get("subagent_type")
                assert st in valid, (
                    f"{cap_path}: task {task['name']} has invalid subagent_type '{st}'. "
                    f"Must be one of {valid}"
                )


def test_searcher_capabilities_query_uses_runtime_request_fields():
    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        for phase in data["graph_template"]["phases"]:
            for task in phase["tasks"]:
                if task.get("subagent_type") != "searcher":
                    continue
                query_template = (task.get("inputs") or {}).get("query")
                assert query_template == "{{topic}} {{query}} {{goal}} {{raw_message}}", (
                    f"{cap_path}: searcher task {task['name']} must query the "
                    "runtime request fields, not a single brittle launch shape"
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
        if _is_hidden_capability(data):
            assert data["mission"]["primary_surface"] in {"prism", "sandbox", "none"}
        else:
            assert data["mission"]["primary_surface"] == "prism"
        assert "requires_sandbox" not in data
        assert "runtime" not in data


def test_every_capability_declares_result_exit():
    valid_kinds = {
        "document",
        "library_item",
        "memory_fact",
        "decision",
        "task",
        "prism_file_change",
    }
    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        outputs: list[dict] = []
        for phase in data["graph_template"]["phases"]:
            for task in phase["tasks"]:
                outputs.extend(task.get("outputs") or [])

        assert outputs, f"{cap_path}: capability has no declared result exit"
        for output in outputs:
            kind = output.get("kind")
            assert kind in valid_kinds, (
                f"{cap_path}: output kind '{kind}' is not supported by TaskReport "
                "or Prism review staging"
            )
            assert isinstance(output.get("mapping"), dict), (
                f"{cap_path}: output '{kind}' must declare an explicit mapping"
            )


def test_visible_multistep_capabilities_are_sequential():
    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        if _is_hidden_capability(data):
            continue

        phases = data["graph_template"]["phases"]
        tasks = [task for phase in phases for task in phase["tasks"]]
        if len(tasks) <= 1:
            continue

        assert len(phases) == len(tasks), (
            f"{cap_path}: multistep capabilities must use one task per phase so "
            "downstream agents receive upstream outputs instead of running in parallel"
        )
        for index, phase in enumerate(phases):
            assert len(phase["tasks"]) == 1, (
                f"{cap_path}: phase {phase['name']} should contain exactly one task"
            )
            if index == 0:
                assert "depends_on" not in phase, (
                    f"{cap_path}: first phase should not declare depends_on"
                )
                continue

            expected = [phases[index - 1]["name"]]
            assert phase.get("depends_on") == expected, (
                f"{cap_path}: phase {phase['name']} should depend on {expected}"
            )
            task_inputs = phase["tasks"][0].get("inputs") or {}
            assert task_inputs.get("upstream_outputs") == "{{phases}}", (
                f"{cap_path}: downstream task {phase['tasks'][0]['name']} must receive "
                "the rendered upstream phase outputs"
            )


def test_workspace_specific_quality_gates_present():
    expected_by_workspace = {
        "thesis": {
            "thesis_structure_matches_school_template",
            "chapter_claims_have_evidence",
            "references_follow_target_style",
        },
        "sci": {
            "reporting_guideline_checked",
            "imrad_or_journal_structure_respected",
            "data_code_availability_considered",
        },
        "proposal": {
            "objective_method_metric_alignment",
            "review_criteria_explicitly_addressed",
            "feasibility_risk_mitigation_included",
        },
        "software_copyright": {
            "application_form_source_manual_consistency",
            "software_name_version_consistent",
            "source_and_document_deposit_rules_checked",
            "no_claims_about_unimplemented_features",
        },
        "patent": {
            "claim_terms_supported_by_description",
            "independent_claim_scope_not_overbroad",
            "embodiments_enable_claim_features",
            "drawings_reference_numerals_consistent",
        },
    }

    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        if _is_hidden_capability(data):
            continue

        gates = set(data.get("quality_gates") or [])
        expected = expected_by_workspace[data["workspace_type"]]
        missing = expected - gates
        assert not missing, f"{cap_path}: missing workspace-specific gates {sorted(missing)}"


def test_china_jurisdiction_defaults_for_software_copyright_and_patent():
    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        if _is_hidden_capability(data):
            continue

        workspace_type = data["workspace_type"]
        if workspace_type not in {"software_copyright", "patent"}:
            continue

        strategy = (
            (data.get("extensions") or {})
            .get("content_strategy", {})
            .get("strategy", "")
        )
        if workspace_type == "software_copyright":
            assert "China software copyright" in strategy, (
                f"{cap_path}: software copyright capabilities must default to "
                "China registration practice"
            )
            continue

        assert "China/CNIPA-first" in strategy, (
            f"{cap_path}: patent capabilities must default to China/CNIPA practice"
        )
        jurisdiction = (
            data.get("inputs", {})
            .get("brief_schema", {})
            .get("properties", {})
            .get("jurisdiction", {})
            .get("description", "")
        )
        assert "默认中国专利申请语境" in jurisdiction, (
            f"{cap_path}: patent jurisdiction field must make China the default"
        )


def test_china_jurisdiction_defaults_for_software_and_patent_skills():
    prompts_by_id = {
        yaml.safe_load(path.read_text())["id"]: yaml.safe_load(path.read_text())["worker"]["role_prompt"]
        for path in (SEED_ROOT / "skills").glob("*.yaml")
    }

    for skill_id in {"software-structure-planner", "software-doc-drafter"}:
        assert "China software copyright registration" in prompts_by_id[skill_id], (
            f"{skill_id}: software copyright skills must default to China registration"
        )

    for skill_id in {"patent-strategist", "patent-drafter"}:
        assert "China/CNIPA patent application practice" in prompts_by_id[skill_id], (
            f"{skill_id}: patent skills must default to China/CNIPA practice"
        )


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
        role_prompt = data["worker"]["role_prompt"]
        assert "Operating rules:" in role_prompt, (
            f"{skill_path}: skill prompt must define executable operating rules"
        )
        assert "Output contract:" in role_prompt, (
            f"{skill_path}: skill prompt must define an output contract"
        )


def test_capability_count_matches_spec():
    files = _collect_capability_files()
    by_ws: dict[str, int] = {}
    for f in files:
        data = yaml.safe_load(f.read_text())
        if _is_hidden_capability(data):
            continue
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
