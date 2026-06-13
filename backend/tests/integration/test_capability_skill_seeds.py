"""Integration test: all capability seeds reference existing skills."""

from pathlib import Path

import yaml

SEED_ROOT = Path(__file__).resolve().parent.parent.parent / "seed"
SKILLLESS_SUBAGENTS = {"sandbox_python", "prism_selection_optimizer"}
DIRECT_COMMIT_TOOLS = {"room_commit", "workspace_room_write", "prism_apply"}
FOUNDATION_AGENT_TEMPLATES = {
    "research_planner.v1",
    "research_scout.v1",
    "literature_synthesizer.v1",
    "methodologist.v1",
    "evidence_analyst.v1",
    "figure_table_engineer.v1",
    "document_architect.v1",
    "manuscript_writer.v1",
    "citation_auditor.v1",
    "critical_reviewer.v1",
    "generalist_assistant.v1",
}
FOUNDATION_SKILLS = {
    "task-scope-planner",
    "query-planner",
    "source-screener",
    "research-scout",
    "literature-synthesizer",
    "novelty-mapper",
    "method-design",
    "reporting-guideline-checker",
    "evidence-analyst",
    "reproducibility-auditor",
    "figure-engineer",
    "table-builder",
    "manuscript-architect",
    "document-outline-builder",
    "manuscript-writer",
    "style-polisher",
    "citation-auditor",
    "source-quality-auditor",
    "review-critic",
    "claim-verifier",
    "structured-summary",
    "format-compliance-checker",
}
FOUNDATION_OVERLAY_SKILLS = {
    "sci-journal-rules",
    "thesis-school-rules",
    "proposal-panel-rules",
    "patent-examiner-rules",
    "software-copyright-rules",
}


def _collect_skill_ids() -> set[str]:
    out: set[str] = set()
    for f in (SEED_ROOT / "skills").glob("*.yaml"):
        data = yaml.safe_load(f.read_text())
        out.add(data["id"])
    return out


def _collect_capability_files() -> list[Path]:
    return list((SEED_ROOT / "capabilities").glob("*/*.yaml"))


def _collect_agent_template_ids() -> set[str]:
    out: set[str] = set()
    for f in (SEED_ROOT / "agent_templates").glob("*.yaml"):
        data = yaml.safe_load(f.read_text())
        out.add(data["id"])
    return out


def _collect_skill_records() -> dict[str, dict]:
    records: dict[str, dict] = {}
    for f in (SEED_ROOT / "skills").glob("*.yaml"):
        data = yaml.safe_load(f.read_text())
        records[data["id"]] = data
    return records


def _collect_agent_template_records() -> dict[str, dict]:
    records: dict[str, dict] = {}
    for f in (SEED_ROOT / "agent_templates").glob("*.yaml"):
        data = yaml.safe_load(f.read_text())
        records[data["id"]] = data
    return records


def _is_hidden_capability(data: dict) -> bool:
    return (data.get("display") or {}).get("entry_tier") == "hidden"


def test_foundation_agent_templates_are_seeded():
    template_ids = _collect_agent_template_ids()
    missing = FOUNDATION_AGENT_TEMPLATES - template_ids
    assert not missing, f"missing foundation agent templates {sorted(missing)}"


def test_foundation_template_default_skills_exist():
    skill_ids = _collect_skill_ids()
    records = _collect_agent_template_records()
    for template_id in sorted(FOUNDATION_AGENT_TEMPLATES):
        data = records[template_id]
        assert data.get("schema_version") == "agent_template.v1"
        assert data.get("enabled") is True
        assert data.get("display_role")
        assert data.get("persona_prompt")
        default_skills = set(data.get("default_skills") or [])
        assert default_skills, f"{template_id}: foundation template must declare default_skills"
        missing = default_skills - skill_ids
        assert not missing, f"{template_id}: unknown default skills {sorted(missing)}"
        assert (data.get("risk_profile") or {}).get("room_write") == "staged_only"


def test_foundation_template_tool_contracts_match_team_registry():
    from src.subagents.v2.registry import validate_agent_template_contract

    records = _collect_agent_template_records()
    for template_id in sorted(FOUNDATION_AGENT_TEMPLATES):
        errors = validate_agent_template_contract(records[template_id])
        assert not errors, f"{template_id}: invalid tool contract {errors}"


def test_foundation_templates_declare_expert_profiles():
    from src.contracts.team_presentation import ExpertProfileV1

    records = _collect_agent_template_records()
    for template_id in sorted(FOUNDATION_AGENT_TEMPLATES):
        profile = records[template_id].get("expert_profile")
        assert isinstance(profile, dict), f"{template_id}: missing expert_profile"
        parsed = ExpertProfileV1.model_validate(profile)
        assert parsed.public_name, f"{template_id}: public_name required"
        assert parsed.role_title, f"{template_id}: role_title required"
        assert parsed.avatar_label, f"{template_id}: avatar_label required"


def test_workspace_overlay_skills_are_seeded():
    skill_ids = _collect_skill_ids()
    missing = FOUNDATION_OVERLAY_SKILLS - skill_ids
    assert not missing, f"missing workspace overlay skills {sorted(missing)}"


def test_foundation_skills_have_quality_contract_shape():
    records = _collect_skill_records()
    expected_ids = FOUNDATION_SKILLS | FOUNDATION_OVERLAY_SKILLS
    missing_ids = expected_ids - set(records)
    assert not missing_ids, f"missing foundation skills {sorted(missing_ids)}"
    for skill_id in sorted(expected_ids):
        data = records[skill_id]
        worker = data.get("worker") or {}
        io_contract = data.get("io_contract") or {}
        output_schema = io_contract.get("output_schema") or {}
        properties = output_schema.get("properties") or {}
        required = set(output_schema.get("required") or [])
        assert worker.get("role_prompt"), f"{skill_id}: missing worker.role_prompt"
        assert output_schema.get("type") == "object", (
            f"{skill_id}: output_schema must be object"
        )
        assert "text" in properties, f"{skill_id}: output_schema.properties.text required"
        assert "quality_gates_checked" in properties, (
            f"{skill_id}: output_schema.properties.quality_gates_checked required"
        )
        assert {"text", "quality_gates_checked"} <= required, (
            f"{skill_id}: text and quality_gates_checked must be required"
        )
        assert data.get("quality_gates"), f"{skill_id}: quality_gates must not be empty"


def test_foundation_skill_required_fields_cover_quality_gate_contracts():
    from src.agents.lead_agent.v2.team.quality_gates import FOUNDATION_GATE_REQUIRED_FIELDS

    records = _collect_skill_records()
    expected_ids = FOUNDATION_SKILLS | FOUNDATION_OVERLAY_SKILLS
    for skill_id in sorted(expected_ids):
        data = records[skill_id]
        output_schema = ((data.get("io_contract") or {}).get("output_schema") or {})
        properties = output_schema.get("properties") or {}
        required = set(output_schema.get("required") or [])
        for gate_id in data.get("quality_gates") or []:
            for field in FOUNDATION_GATE_REQUIRED_FIELDS.get(gate_id, []):
                assert field in required, (
                    f"{skill_id}: quality gate {gate_id} requires {field}, "
                    "but output_schema.required does not"
                )
                assert field in properties, (
                    f"{skill_id}: quality gate {gate_id} requires {field}, "
                    "but output_schema.properties does not define it"
                )


def test_sample_capabilities_use_foundation_team_patterns():
    expected = {
        "sci_literature_positioning": {
            "core": {
                "research_planner.v1",
                "research_scout.v1",
                "literature_synthesizer.v1",
            },
            "optional": {
                "citation_auditor.v1",
                "document_architect.v1",
                "critical_reviewer.v1",
                "generalist_assistant.v1",
            },
            "overlay": {"sci-journal-rules"},
        },
    }
    by_id = {
        yaml.safe_load(path.read_text())["id"]: path
        for path in _collect_capability_files()
    }
    for capability_id, expected_policy in expected.items():
        data = yaml.safe_load(by_id[capability_id].read_text())
        policy = data.get("team_policy") or {}
        assert set(policy.get("core_templates") or []) == expected_policy["core"]
        assert expected_policy["optional"] <= set(policy.get("optional_templates") or [])
        assert set(policy.get("contract_overlay_skills") or []) == expected_policy["overlay"]
        assert "research" not in set(policy.get("contract_overlay_categories") or [])
        triggers = policy.get("recruitment_triggers") or {}
        assert triggers.get("missing_sources")
        assert triggers.get("unsupported_claims")


def test_existing_graph_output_capabilities_stay_on_graph_runtime():
    by_id = {
        yaml.safe_load(path.read_text())["id"]: path
        for path in _collect_capability_files()
    }
    for capability_id in {"thesis_research_pack", "proposal_background_pack"}:
        data = yaml.safe_load(by_id[capability_id].read_text())
        outputs = [
            output
            for phase in data["graph_template"]["phases"]
            for task in phase["tasks"]
            for output in task.get("outputs") or []
        ]
        assert any(output.get("kind") in {"library_item", "document"} for output in outputs)
        assert (data.get("runtime") or {}).get("mode") != "team_kernel"
        assert data.get("team_policy") is None


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
        runtime = data.get("runtime")
        if runtime is not None:
            assert runtime.get("mode") == "team_kernel", (
                f"{cap_path}: runtime is only allowed for team_kernel capabilities"
            )
            assert isinstance(data.get("team_policy"), dict), (
                f"{cap_path}: team_kernel capabilities must declare team_policy"
            )


def test_team_kernel_capability_declares_recruitable_team_policy():
    template_ids = _collect_agent_template_ids()
    skill_ids = _collect_skill_ids()
    template_records = _collect_agent_template_records()
    assert template_ids, "no agent templates found"
    team_kernel_capabilities: list[str] = []

    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        if (data.get("runtime") or {}).get("mode") != "team_kernel":
            continue
        team_kernel_capabilities.append(data["id"])
        policy = data.get("team_policy") or {}
        template_refs = [
            *list(policy.get("core_templates") or []),
            *list(policy.get("optional_templates") or []),
        ]
        assert template_refs, f"{cap_path}: team_policy must recruit at least one template"
        assert set(template_refs) <= template_ids, (
            f"{cap_path}: unknown agent templates {sorted(set(template_refs) - template_ids)}"
        )
        capability_tools = set(policy.get("capability_tools") or [])
        assert capability_tools, f"{cap_path}: team_policy.capability_tools must not be empty"
        assert not capability_tools.intersection(DIRECT_COMMIT_TOOLS), (
            f"{cap_path}: direct commit tools must stay behind staged result_card flow"
        )
        assert policy.get("quality_pipeline"), (
            f"{cap_path}: team_policy.quality_pipeline must close the loop"
        )
        capability_skills = set(policy.get("capability_skills") or [])
        assert capability_skills, f"{cap_path}: team_policy.capability_skills must not be empty"
        for template_id in template_refs:
            default_skills = set(template_records[template_id].get("default_skills") or [])
            missing_defaults = default_skills - capability_skills
            assert not missing_defaults, (
                f"{cap_path}: capability_skills filters out default skills for "
                f"{template_id}: {sorted(missing_defaults)}"
            )
        overlay_skills = set(policy.get("contract_overlay_skills") or [])
        assert overlay_skills <= skill_ids, (
            f"{cap_path}: unknown contract overlay skills {sorted(overlay_skills - skill_ids)}"
        )
        if overlay_skills:
            assert policy.get("contract_overlay_categories"), (
                f"{cap_path}: contract overlays must declare applicable template categories"
            )

    assert "sci_literature_positioning" in team_kernel_capabilities


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


def test_sci_sandbox_research_capabilities_declare_evidence_surfaces():
    required = {
        "sci_empirical_package": {
            "literature",
            "experiment",
            "writing",
            "workflow_trace",
            "experiment_interpretation",
            "output_ref_reuse",
        },
        "reproducibility_audit": {
            "experiment",
            "workflow_trace",
            "experiment_interpretation",
            "output_ref_reuse",
        },
    }
    by_id = {
        yaml.safe_load(path.read_text())["id"]: path
        for path in _collect_capability_files()
    }
    for capability_id, required_surfaces in required.items():
        data = yaml.safe_load(by_id[capability_id].read_text())
        research_evidence = data.get("research_evidence") or {}
        surfaces = set(research_evidence.get("required_surfaces") or [])
        assert required_surfaces <= surfaces, (
            f"{capability_id}: missing research evidence surfaces "
            f"{sorted(required_surfaces - surfaces)}"
        )


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
