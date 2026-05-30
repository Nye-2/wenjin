# Research Writing Agent Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the reusable research/writing team foundation: stable agent templates, method-oriented skills, workspace overlays, stronger quality contracts/gates, and sample team capabilities.

**Architecture:** Keep the existing Chat Agent -> Lead Agent -> Team Kernel -> result_card path unchanged. Expand DataService catalog seeds and runtime-derived `ResolvedQualityContract` so roles, skills, workspace overlays, and quality gates compose without creating another workflow engine.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, ruff, YAML seed catalogs, existing Lead Agent v2 Team Kernel.

---

## File Structure

- Modify: `backend/src/agents/lead_agent/v2/team/quality_contract.py`
  - Add workspace overlay resolution and optional family schema merge.
  - Keep the contract a runtime-derived model, not a new DataService catalog.
- Modify: `backend/src/agents/lead_agent/v2/team/quality_gates.py`
  - Add reusable deterministic gates for foundation outputs.
  - Keep LLM judging out of this phase.
- Modify: `backend/tests/agents/lead_agent/v2/test_team_quality_contract.py`
  - Prove overlay skills merge into `ResolvedQualityContract`.
- Modify: `backend/tests/agents/lead_agent/v2/test_team_quality_gates.py`
  - Prove missing family fields trigger revise/recruit paths.
- Modify: `backend/tests/integration/test_capability_skill_seeds.py`
  - Prove seed catalog consistency for foundation templates, skills, overlays, and sample capabilities.
- Create/modify: `backend/seed/agent_templates/*.yaml`
  - Replace the 4-role prototype pool with the 11 stable template pool.
- Create/modify: `backend/seed/skills/*.yaml`
  - Add method-oriented foundation skills and workspace overlays.
  - Preserve current skill IDs where existing capabilities already reference them.
- Modify: `backend/seed/capabilities/sci/sci_literature_positioning.yaml`
- Modify: `backend/seed/capabilities/thesis/thesis_research_pack.yaml`
- Modify: `backend/seed/capabilities/proposal/proposal_background_pack.yaml`
  - Convert sample policies to foundation team patterns.

## Task 1: Lock Foundation Seed Expectations

**Files:**
- Modify: `backend/tests/integration/test_capability_skill_seeds.py`

- [ ] **Step 1: Add failing tests for the stable template pool**

Add constants near the top:

```python
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

FOUNDATION_OVERLAY_SKILLS = {
    "sci-journal-rules",
    "thesis-school-rules",
    "proposal-panel-rules",
    "patent-examiner-rules",
    "software-copyright-rules",
}
```

Add tests:

```python
def test_foundation_agent_templates_are_seeded():
    template_ids = _collect_agent_template_ids()
    missing = FOUNDATION_AGENT_TEMPLATES - template_ids
    assert not missing, f"missing foundation agent templates {sorted(missing)}"


def test_foundation_template_default_skills_exist():
    skill_ids = _collect_skill_ids()
    for f in (SEED_ROOT / "agent_templates").glob("*.yaml"):
        data = yaml.safe_load(f.read_text())
        if data["id"] not in FOUNDATION_AGENT_TEMPLATES:
            continue
        assert data.get("schema_version") == "agent_template.v1"
        assert data.get("enabled") is True
        assert data.get("display_role")
        assert data.get("persona_prompt")
        default_skills = set(data.get("default_skills") or [])
        assert default_skills, f"{f}: foundation template must declare default_skills"
        missing = default_skills - skill_ids
        assert not missing, f"{f}: unknown default skills {sorted(missing)}"
        assert (data.get("risk_profile") or {}).get("room_write") == "staged_only"
```

- [ ] **Step 2: Add failing tests for overlay and skill output contracts**

Add:

```python
def test_workspace_overlay_skills_are_seeded():
    skill_ids = _collect_skill_ids()
    missing = FOUNDATION_OVERLAY_SKILLS - skill_ids
    assert not missing, f"missing workspace overlay skills {sorted(missing)}"


def test_foundation_skills_have_quality_contract_shape():
    for f in (SEED_ROOT / "skills").glob("*.yaml"):
        data = yaml.safe_load(f.read_text())
        if data["id"] not in _collect_skill_ids():
            continue
        worker = data.get("worker") or {}
        io_contract = data.get("io_contract") or {}
        output_schema = io_contract.get("output_schema") or {}
        properties = output_schema.get("properties") or {}
        required = set(output_schema.get("required") or [])
        assert worker.get("role_prompt"), f"{f}: missing worker.role_prompt"
        assert output_schema.get("type") == "object", f"{f}: output_schema must be object"
        assert "text" in properties, f"{f}: output_schema.properties.text required"
        assert "quality_gates_checked" in properties, (
            f"{f}: output_schema.properties.quality_gates_checked required"
        )
        assert {"text", "quality_gates_checked"} <= required, (
            f"{f}: text and quality_gates_checked must be required"
        )
        assert data.get("quality_gates"), f"{f}: quality_gates must not be empty"
```

- [ ] **Step 3: Add failing tests for sample capabilities using foundation patterns**

Add:

```python
def test_sample_capabilities_use_foundation_team_patterns():
    expected = {
        "sci_literature_positioning": {
            "core": {"research_planner.v1", "research_scout.v1", "literature_synthesizer.v1"},
            "optional": {"citation_auditor.v1", "document_architect.v1", "critical_reviewer.v1", "generalist_assistant.v1"},
        },
        "thesis_research_pack": {
            "core": {"research_planner.v1", "research_scout.v1", "literature_synthesizer.v1"},
            "optional": {"citation_auditor.v1", "document_architect.v1", "critical_reviewer.v1", "generalist_assistant.v1"},
        },
        "proposal_background_pack": {
            "core": {"research_planner.v1", "research_scout.v1", "literature_synthesizer.v1"},
            "optional": {"citation_auditor.v1", "document_architect.v1", "critical_reviewer.v1", "generalist_assistant.v1"},
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
        assert policy.get("recruitment_triggers", {}).get("missing_sources")
        assert policy.get("recruitment_triggers", {}).get("unsupported_claims")
```

- [ ] **Step 4: Run tests to verify they fail**

Run:

```bash
cd backend
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy -u NO_PROXY -u no_proxy /Users/ze/wenjin/backend/.venv/bin/python -m pytest tests/integration/test_capability_skill_seeds.py -v
```

Expected: FAIL because the new foundation templates and overlay skills are not seeded yet.

## Task 2: Seed Stable Agent Templates

**Files:**
- Modify/delete old prototype seeds in `backend/seed/agent_templates/`
- Create: `backend/seed/agent_templates/research_planner.yaml`
- Create: `backend/seed/agent_templates/research_scout.yaml`
- Create: `backend/seed/agent_templates/literature_synthesizer.yaml`
- Create: `backend/seed/agent_templates/methodologist.yaml`
- Create: `backend/seed/agent_templates/evidence_analyst.yaml`
- Create: `backend/seed/agent_templates/figure_table_engineer.yaml`
- Create: `backend/seed/agent_templates/document_architect.yaml`
- Create: `backend/seed/agent_templates/manuscript_writer.yaml`
- Create: `backend/seed/agent_templates/citation_auditor.yaml`
- Keep/modify: `backend/seed/agent_templates/critical_reviewer.yaml`
- Keep/modify: `backend/seed/agent_templates/generalist_assistant.yaml`

- [ ] **Step 1: Replace prototype role IDs with foundation IDs**

Each foundation template must follow this exact shape:

```yaml
schema_version: agent_template.v1
id: research_planner.v1
enabled: true
display_role: 研究规划师
category: planning
description: 澄清科研写作目标，拆解检索、处理、写作和审查步骤。
persona_prompt: |
  You are Wenjin's research planner. Turn an underspecified academic or regulated writing request into a concrete, reviewable execution plan.

  Operating rules:
  - Separate information collection steps from analysis, drafting, and review steps.
  - Identify missing user decisions without blocking progress when a conservative plan is possible.
  - Preserve workspace safety boundaries: propose staged outputs only and never claim to commit canonical state.
default_skills:
  - task-scope-planner
  - query-planner
tool_affinity:
  preferred:
    - document_read
    - memory_read
  can_request:
    - library_read
    - artifact_create
risk_profile:
  network: limited
  filesystem: no_direct_write
  code_execution: not_needed
  room_write: staged_only
output_contracts:
  - research_execution_plan.v1
quality_expectations:
  - separate collection, analysis, drafting, and review steps
  - list missing decisions and safe assumptions explicitly
runtime_defaults:
  max_turns: 6
  timeout_seconds: 240
```

Use the same field set for every template. Change `id`, `display_role`, `category`, `description`, `persona_prompt`, `default_skills`, `tool_affinity`, `output_contracts`, and `quality_expectations` according to the spec table.

- [ ] **Step 2: Keep compatibility aliases out of this phase**

Do not preserve old template IDs like `research_scholar.v1` or `writing_editor.v1` in team policies. Existing static graph capabilities do not depend on agent templates. Team-kernel sample capabilities will be updated in Task 6.

- [ ] **Step 3: Run template seed tests**

Run:

```bash
cd backend
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy -u NO_PROXY -u no_proxy /Users/ze/wenjin/backend/.venv/bin/python -m pytest tests/integration/test_capability_skill_seeds.py::test_foundation_agent_templates_are_seeded tests/integration/test_capability_skill_seeds.py::test_foundation_template_default_skills_exist -v
```

Expected: PASS after Task 3 adds all referenced skills, or fail only for missing skill IDs until Task 3 is complete.

## Task 3: Seed Method-Oriented Skills And Overlays

**Files:**
- Create/modify under `backend/seed/skills/`

- [ ] **Step 1: Add common output schema to every foundation skill**

Every foundation skill uses this baseline:

```yaml
io_contract:
  input_schema:
    type: object
  output_schema:
    type: object
    required:
      - text
      - quality_gates_checked
    properties:
      text:
        type: string
      quality_gates_checked:
        type: array
        items:
          type: string
      open_questions:
        type: array
        items:
          type: string
      decision_candidates:
        type: array
        items:
          type: object
```

- [ ] **Step 2: Add foundation skills referenced by templates**

At minimum seed these IDs:

```text
task-scope-planner
query-planner
source-screener
research-scout
literature-synthesizer
novelty-mapper
method-design
reporting-guideline-checker
evidence-analyst
reproducibility-auditor
figure-engineer
table-builder
manuscript-architect
document-outline-builder
manuscript-writer
style-polisher
citation-auditor
source-quality-auditor
review-critic
claim-verifier
structured-summary
format-compliance-checker
```

Existing seed IDs should be upgraded in place when present. New skill files should use lowercase kebab-case filenames matching the ID, such as `backend/seed/skills/query-planner.yaml`.

- [ ] **Step 3: Add overlay skills**

Create:

```text
sci-journal-rules
thesis-school-rules
proposal-panel-rules
patent-examiner-rules
software-copyright-rules
```

Each overlay must use `worker.category: domain_overlay`, `subagent_type: react`, no direct write tools, and quality gates that match the workspace-specific gates already tested in `test_workspace_specific_quality_gates_present`.

- [ ] **Step 4: Run skill seed tests**

Run:

```bash
cd backend
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy -u NO_PROXY -u no_proxy /Users/ze/wenjin/backend/.venv/bin/python -m pytest tests/integration/test_capability_skill_seeds.py::test_workspace_overlay_skills_are_seeded tests/integration/test_capability_skill_seeds.py::test_foundation_skills_have_quality_contract_shape tests/integration/test_capability_skill_seeds.py::test_every_skill_required_fields_present -v
```

Expected: PASS.

## Task 4: Extend ResolvedQualityContract With Workspace Overlays

**Files:**
- Modify: `backend/src/agents/lead_agent/v2/team/quality_contract.py`
- Modify: `backend/tests/agents/lead_agent/v2/test_team_quality_contract.py`

- [ ] **Step 1: Write failing overlay merge test**

Add:

```python
def test_quality_contract_resolver_auto_merges_workspace_overlay_skill() -> None:
    cap = _capability()
    cap.definition_json["workspace_type"] = "sci"
    cap.definition_json["team_policy"] = {}
    overlay = _skill(
        "sci-journal-rules",
        required=["text", "quality_gates_checked", "checked_requirements"],
        quality_gates=["reporting_guideline_checked"],
    )

    contract = QualityContractResolver.resolve(
        capability=cap,
        template=_template(),
        team_policy=_team_policy(),
        effective_skill_ids=["research-scout"],
        skill_records={
            "research-scout": _skill(
                "research-scout",
                required=["text", "quality_gates_checked"],
                quality_gates=["source_log_required"],
            ),
            "sci-journal-rules": overlay,
        },
    )

    assert "sci-journal-rules" in contract.skill_ids
    assert "reporting_guideline_checked" in contract.quality_gates
    assert "checked_requirements" in contract.output_schema["required"]
    assert "workspace_overlay.sci" in contract.source_refs["skill_ids"]
```

- [ ] **Step 2: Implement overlay mapping**

Add near the top of `quality_contract.py`:

```python
WORKSPACE_OVERLAY_SKILLS = {
    "sci": "sci-journal-rules",
    "thesis": "thesis-school-rules",
    "proposal": "proposal-panel-rules",
    "patent": "patent-examiner-rules",
    "software_copyright": "software-copyright-rules",
}
```

In `resolve()`, compute:

```python
skill_ids = _effective_skill_ids_with_overlay(capability, definition, effective_skill_ids, skill_records, source_refs)
```

Iterate over `skill_ids` instead of `effective_skill_ids`, and return `skill_ids=list(skill_ids)`.

Implement helper:

```python
def _effective_skill_ids_with_overlay(
    capability: Any,
    definition: dict[str, Any],
    effective_skill_ids: list[str],
    skill_records: dict[str, Any | None],
    source_refs: dict[str, list[str]],
) -> list[str]:
    result = list(effective_skill_ids)
    workspace_type = str(
        getattr(capability, "workspace_type", "")
        or definition.get("workspace_type")
        or ""
    )
    overlay_id = WORKSPACE_OVERLAY_SKILLS.get(workspace_type)
    if overlay_id and overlay_id in skill_records and overlay_id not in result:
        result.append(overlay_id)
        _add_source_ref(source_refs, "skill_ids", f"workspace_overlay.{workspace_type}")
    return result
```

- [ ] **Step 3: Run quality contract tests**

Run:

```bash
cd backend
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy -u NO_PROXY -u no_proxy /Users/ze/wenjin/backend/.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_quality_contract.py -v
```

Expected: PASS.

## Task 5: Add Foundation Quality Gates

**Files:**
- Modify: `backend/src/agents/lead_agent/v2/team/quality_gates.py`
- Modify: `backend/tests/agents/lead_agent/v2/test_team_quality_gates.py`

- [ ] **Step 1: Write failing tests for family-field gates**

Add tests for missing research and review fields:

```python
def test_quality_gates_request_research_revision_for_missing_query_log() -> None:
    contract = {
        "schema_version": "resolved_quality_contract.v1",
        "template_id": "research_scout.v1",
        "output_schema": {"type": "object", "properties": {}, "required": []},
        "quality_gates": ["query_strategy_recorded"],
        "acknowledgement_required_gates": [],
        "recruitment_hints": {"missing_sources": ["research_scout.v1"]},
    }
    gates = evaluate_quality_gates(
        ["query_strategy_recorded"],
        [_invocation(template_id="research_scout.v1", output_report={"text": "searched"}, quality_contract=contract)],
        team_policy=CapabilityTeamPolicy(
            core_templates=["research_scout.v1"],
            optional_templates=["citation_auditor.v1"],
            recruitment_triggers={"missing_sources": ["research_scout.v1"]},
        ),
        counts=Counter({"research_scout.v1": 1}),
        latest_invocations=[],
    )
    gate = next(item for item in gates if item.gate_id == "query_strategy_recorded")
    assert gate.status == "fail"
    assert gate.next_action == "revise_existing"


def test_quality_gates_request_reviewer_revision_for_vague_findings() -> None:
    contract = {
        "schema_version": "resolved_quality_contract.v1",
        "template_id": "critical_reviewer.v1",
        "output_schema": {"type": "object", "properties": {}, "required": []},
        "quality_gates": ["review_findings_actionable"],
        "acknowledgement_required_gates": [],
        "recruitment_hints": {},
    }
    gates = evaluate_quality_gates(
        ["review_findings_actionable"],
        [_invocation(template_id="critical_reviewer.v1", output_report={"text": "looks weak"}, quality_contract=contract)],
        team_policy=CapabilityTeamPolicy(core_templates=["critical_reviewer.v1"]),
        counts=Counter({"critical_reviewer.v1": 1}),
        latest_invocations=[],
    )
    gate = next(item for item in gates if item.gate_id == "review_findings_actionable")
    assert gate.status == "fail"
    assert gate.next_action == "revise_existing"
```

- [ ] **Step 2: Implement deterministic gate helper**

Add `_foundation_field_gates()` and call it from `evaluate_quality_gates()` after `_quality_gates_acknowledged()`.

```python
FOUNDATION_GATE_REQUIRED_FIELDS = {
    "query_strategy_recorded": ["query_log"],
    "source_screening_complete": ["included_sources", "borderline_sources", "rejected_sources"],
    "claim_evidence_map_required": ["claim_evidence_map"],
    "upstream_outputs_used": ["upstream_outputs_used"],
    "unsupported_claims_marked": ["unsupported_claims"],
    "method_assumptions_logged": ["assumptions"],
    "reproducibility_status_declared": ["verified_results", "artifact_refs"],
    "review_findings_actionable": ["findings_by_severity", "required_fixes"],
    "format_requirements_checked": ["checked_requirements"],
}
```

The helper should inspect each succeeded invocation's `quality_contract.quality_gates`, require listed fields when the gate appears, and use `_revision_recruit()` to suggest revising the same template.

- [ ] **Step 3: Run quality gate tests**

Run:

```bash
cd backend
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy -u NO_PROXY -u no_proxy /Users/ze/wenjin/backend/.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_quality_gates.py -v
```

Expected: PASS.

## Task 6: Adapt Sample Capabilities To Foundation Team Patterns

**Files:**
- Modify: `backend/seed/capabilities/sci/sci_literature_positioning.yaml`
- Modify: `backend/seed/capabilities/thesis/thesis_research_pack.yaml`
- Modify: `backend/seed/capabilities/proposal/proposal_background_pack.yaml`

- [ ] **Step 1: Update `team_policy` for the three sample capabilities**

For research-first writing capabilities, use:

```yaml
team_policy:
  core_templates:
    - research_planner.v1
    - research_scout.v1
    - literature_synthesizer.v1
  optional_templates:
    - citation_auditor.v1
    - document_architect.v1
    - critical_reviewer.v1
    - generalist_assistant.v1
  recruitment_triggers:
    missing_sources:
      - research_scout.v1
    unsupported_claims:
      - citation_auditor.v1
      - critical_reviewer.v1
    writing_needed:
      - document_architect.v1
    overloaded_or_missing_specialist:
      - generalist_assistant.v1
```

Keep each capability's existing `capability_tools`, `limits`, and `budget` unless they reference obsolete template IDs.

- [ ] **Step 2: Update `capability_skills`**

Use this shared research-first skill superset for all three sample capabilities:

```yaml
capability_skills:
  - task-scope-planner
  - query-planner
  - research-scout
  - source-screener
  - literature-synthesizer
  - novelty-mapper
  - citation-auditor
  - source-quality-auditor
  - manuscript-architect
  - review-critic
  - claim-verifier
```

Add `sci-journal-rules`, `thesis-school-rules`, or `proposal-panel-rules` only if explicit capability-level inclusion is simpler than auto-injection. Preferred implementation is auto-injection from Task 4, so explicit inclusion is optional.

- [ ] **Step 3: Run sample policy tests**

Run:

```bash
cd backend
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy -u NO_PROXY -u no_proxy /Users/ze/wenjin/backend/.venv/bin/python -m pytest tests/integration/test_capability_skill_seeds.py::test_team_kernel_capability_declares_recruitable_team_policy tests/integration/test_capability_skill_seeds.py::test_sample_capabilities_use_foundation_team_patterns -v
```

Expected: PASS.

## Task 7: Verify End-To-End Team Kernel Behavior

**Files:**
- Modify tests only if Task 4/5 require assertions in `backend/tests/agents/lead_agent/v2/test_team_kernel.py`

- [ ] **Step 1: Run focused backend verification**

Run:

```bash
cd backend
/Users/ze/wenjin/backend/.venv/bin/ruff check src tests
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy -u NO_PROXY -u no_proxy /Users/ze/wenjin/backend/.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_policy.py tests/agents/lead_agent/v2/test_team_quality_contract.py tests/agents/lead_agent/v2/test_team_quality_gates.py tests/agents/lead_agent/v2/test_team_kernel.py tests/integration/test_capability_skill_seeds.py -v
```

Expected: ruff passes and focused tests pass.

- [ ] **Step 2: Run full backend suite**

Run:

```bash
cd backend
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy -u NO_PROXY -u no_proxy /Users/ze/wenjin/backend/.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit implementation**

Run:

```bash
git status --short
git add backend/src/agents/lead_agent/v2/team/quality_contract.py backend/src/agents/lead_agent/v2/team/quality_gates.py backend/tests/agents/lead_agent/v2/test_team_quality_contract.py backend/tests/agents/lead_agent/v2/test_team_quality_gates.py backend/tests/integration/test_capability_skill_seeds.py backend/seed/agent_templates backend/seed/skills backend/seed/capabilities/sci/sci_literature_positioning.yaml backend/seed/capabilities/thesis/thesis_research_pack.yaml backend/seed/capabilities/proposal/proposal_background_pack.yaml
git commit -m "feat: add research writing agent foundation"
```

Expected: one implementation commit on `codex/research-writing-agent-foundation`.

## Self-Review

- Spec coverage: Tasks cover stable templates, method skills, workspace overlays, quality contract merge, deterministic quality gates, sample capability adaptation, and verification.
- Placeholder scan: no unresolved implementation placeholders.
- Type consistency: role IDs use `.v1`; skill IDs use kebab-case; workspace overlay IDs match the spec.
- Scope check: no frontend, router, execution SSOT, commit service, or DataService schema changes are planned.
