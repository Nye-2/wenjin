# Super Agent Capability Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use engineering-context:subagent-driven-development (recommended) or engineering-context:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut Wenjin capability/skill/sandbox from workflow-era entries to mission-level Super Agent Harness contracts.

**Architecture:** DataService Catalog remains the capability/skill SSOT. Runtime launches only mission-level `capability.v2` records, skills are worker instruction packs, sandbox execution is controlled by explicit policy, and reviewable outputs converge through ReviewBatch/ReviewItem and Prism. The cutover is a clean migration: no alias layer, no runtime fallback to old capability ids, no dual-read catalog.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, SQLAlchemy async inside DataService only, LangGraph lead runtime, Next.js 16/React 19 frontend, pytest/vitest/typecheck.

---

## Source Context

- Spec: `docs/superpowers/specs/2026-05-20-super-agent-capability-system-design.md`
- Current workspace facts: `docs/current/workspace-current-state.md`
- Current old catalog facts: `docs/current/workspace-feature-catalog.md`
- DataService SSOT overview: `docs/superpowers/specs/2026-05-21-dataservice-full-migration-overview.md`
- Catalog domain: `backend/src/dataservice/domains/catalog/`
- Seed roots: `backend/seed/capabilities/`, `backend/seed/skills/`

## Current Audit

The design was paused after DataService work started. The remaining mismatch is explicit:

- Capability seed files still have no `schema_version` and still expose workflow-step ids such as `outline_generate`, `section_write`, `framework_outline`, `proposal_outline`, `patent_outline`.
- Skill seed files still have no `schema_version` and still use old role names such as `framework-designer`, `section-writer`, `literature-reviewer`.
- `backend/src/services/capability_schema.py` validates the old schema and still models `runtime.requires_sandbox`.
- `backend/src/services/capability_loader.py` only checks required top-level keys and does not validate v2 mission contracts.
- `backend/src/compute/projection_service.py` still derives sandbox requirement from `runtime.requires_sandbox`.
- `backend/src/subagents/v2/registry.py` currently has only `react` and `searcher`.
- `backend/src/services/feature_action_resolution_service.py`, dashboard services, frontend feature stage mapping, and docs still contain old capability ids.

## Cutover Rules

1. New capability records must declare `schema_version: capability.v2`.
2. New skill records must declare `schema_version: capability_skill.v2`.
3. Runtime code must reject unknown schema versions instead of silently defaulting.
4. `runtime.requires_sandbox` is removed from runtime semantics; `sandbox_policy.mode` is the only capability-level sandbox signal.
5. Old workflow ids are deleted from seeds and docs, not mapped through aliases.
6. `feature_id` remains only as the transport parameter name in `launch_feature`; its value must be a canonical capability id.
7. Workbench cards show mission cards. Workflow-step actions move to Prism contextual actions or capability params.
8. Sandbox policy must reject host/container/server control and default away from arbitrary web browsing.

## Target Mission Catalog

### Thesis

- `idea_to_thesis_manuscript`
- `thesis_research_pack`
- `thesis_empirical_analysis`
- `thesis_revision_pass`
- `thesis_defense_pack`
- `thesis_reference_curation`

### SCI

- `research_question_to_paper`
- `sci_literature_positioning`
- `sci_empirical_package`
- `sci_revision_for_journal`
- `journal_submission_strategy`
- `response_to_reviewers`
- `reproducibility_audit`

### Proposal

- `idea_to_proposal_package`
- `proposal_background_pack`
- `technical_route_package`
- `feasibility_and_risk_review`
- `proposal_polish_for_review`

### Software Copyright

- `software_copyright_application_pack`
- `software_technical_manual`
- `software_evidence_pack`
- `software_architecture_diagrams`

### Patent

- `invention_to_patent_draft`
- `prior_art_and_novelty_pack`
- `claims_strategy`
- `embodiment_and_drawings`
- `office_action_response`

## File Map

### Schema And Loader

- Modify: `backend/src/services/capability_schema.py`
  - Add strict `CapabilityV2YamlModel` and `CapabilitySkillV2YamlModel`.
  - Keep old model names only if tests still need them during the same commit; the runtime loader must instantiate v2 models.
- Modify: `backend/src/services/capability_loader.py`
  - Validate every seed through `CapabilityV2YamlModel`.
  - Require `schema_version: capability.v2`.
  - Persist normalized v2 fields into DataService Catalog.
- Modify: `backend/src/dataservice/domains/catalog/service.py`
  - Preserve `mission`, `display`, `intent`, `inputs`, `context_policy`, `sandbox_policy`, `review_policy`, `quality_gates` inside `definition_json`.
  - Derive legacy projection fields (`display_name`, `trigger_phrases`, `brief_schema`, `graph_template`, `ui_meta`) from v2 fields only for read-model continuity.
- Modify: `backend/src/dataservice/domains/catalog/contracts.py`
  - Keep projections stable, but document `definition_json` as the canonical full v2 contract.
- Tests:
  - `backend/tests/services/test_capability_schema.py`
  - `backend/tests/services/test_capability_loader.py`
  - `backend/tests/dataservice/test_catalog_domain.py`

### Skill System

- Modify: `backend/src/services/admin_skill_service.py`
- Modify: `backend/src/agents/middlewares/capability_skill_preload.py`
- Modify: `backend/src/services/skill_resolver.py`
- Modify: `backend/src/dataservice/domains/catalog/service.py`
- Replace files under `backend/seed/skills/`
- Tests:
  - `backend/tests/services/test_cross_ref_validator.py`
  - `backend/tests/integration/test_capability_skill_seeds.py`
  - `backend/tests/services/test_admin_skill_service.py`

### Runtime And Compute

- Modify: `backend/src/tools/builtins/launch_feature.py`
  - Update docstring/examples from old ids to mission ids.
  - Reject non-v2 capability records.
- Modify: `backend/src/agents/chat_agent/agent.py`
  - Prompt should describe missions, not workflows.
  - Render `mission.user_promise`, `display.entry_tier`, and trigger phrases from v2 definition.
- Modify: `backend/src/agents/lead_agent/v2/runtime.py`
  - Pass `mission`, `context_policy`, `sandbox_policy`, `review_policy`, and `quality_gates` into task distribution.
- Modify: `backend/src/compute/projection_service.py`
  - Derive sandbox required/optional state from `sandbox_policy.mode`.
- Tests:
  - `backend/tests/tools/test_launch_feature_tool.py`
  - `backend/tests/agents/lead_agent/v2/test_runtime.py`
  - `backend/tests/compute/test_projection_service.py`

### Seeds And Docs

- Delete old capability seed files under `backend/seed/capabilities/*/*.yaml`.
- Add new mission seed files under the same workspace directories.
- Update: `docs/current/workspace-feature-catalog.md`
- Update: `docs/current/workspace-current-state.md`
- Update: `docs/current/architecture.md`
- Tests:
  - `backend/tests/seed/test_capability_seeds_load.py`
  - `backend/tests/integration/test_capability_skill_seeds.py`

### Frontend

- Modify: `frontend/lib/workspace-feature-stages.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
- Modify old tests referencing workflow ids:
  - `frontend/tests/unit/lib/workspace-feature-action-context.test.ts`
  - `frontend/tests/unit/lib/workspace-feature-actions.test.ts`
  - `frontend/tests/unit/v2/CompletedView.test.tsx`
  - `frontend/tests/unit/v2/ExecutionCard.test.tsx`
- Verification:
  - `cd frontend && npm run typecheck`
  - `cd frontend && npx vitest run`

## Task 1: Strict Capability v2 Schema Foundation

**Files:**

- Modify: `backend/src/services/capability_schema.py`
- Modify: `backend/tests/services/test_capability_schema.py`

- [x] **Step 1: Add failing tests for required v2 schema fields**

Add tests that assert:

```python
def test_capability_v2_requires_schema_version():
    with pytest.raises(ValidationError):
        CapabilityV2YamlModel(
            id="idea_to_thesis_manuscript",
            workspace_type="thesis",
            enabled=True,
            display={"name": "Idea 到论文全文", "description": "x", "icon": "file-pen", "color": "blue", "order": 10, "entry_tier": "primary"},
            intent={"description": "x", "trigger_phrases": ["写全文"]},
            mission={"goal": "produce_or_update_primary_document", "primary_surface": "prism", "document_role": "primary_manuscript", "user_promise": "x", "allowed_deliverables": ["full_document_update"]},
            inputs={"brief_schema": {"type": "object"}},
            context_policy={"room_reads": {}, "prism_context": {}},
            sandbox_policy={"mode": "conditional", "profiles": ["analysis"], "allowed_operations": ["run_python"]},
            review_policy={"default_targets": ["prism_file_change"], "require_user_acceptance": True, "allow_bulk_accept": True},
            quality_gates=["no_direct_primary_document_write"],
            graph_template={"phases": []},
        )
```

Expected: fails because `schema_version` is required.

- [x] **Step 2: Add `CapabilityV2YamlModel`**

Implement strict Pydantic v2 models with `extra="forbid"`:

- `CapabilitySchemaVersion = Literal["capability.v2"]`
- `CapabilityDisplayModel`
- `CapabilityIntentModel`
- `CapabilityMissionModel`
- `CapabilityInputsModel`
- `CapabilityContextPolicyModel`
- `CapabilitySandboxPolicyModel`
- `CapabilityReviewPolicyModel`
- `CapabilityV2YamlModel`

Keep graph template task fields `extra="allow"` for runtime graph extensibility only.

- [x] **Step 3: Add sandbox policy validation**

Reject:

- `mode` outside `none | optional | conditional | required`
- `isolation.allow_docker_socket: true`
- `isolation.allow_privileged: true`
- `isolation.allow_host_network: true`
- `isolation.allow_host_paths: true`
- `isolation.allow_sibling_containers: true`

- [x] **Step 4: Run targeted schema tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/services/test_capability_schema.py -q
```

Expected: pass.

## Task 2: Strict Skill v2 Schema Foundation

**Files:**

- Modify: `backend/src/services/capability_schema.py`
- Modify: `backend/tests/services/test_capability_schema.py`

- [x] **Step 1: Add failing tests for skill v2**

Assert `schema_version: capability_skill.v2`, `worker.category`, `worker.subagent_type`, `io_contract`, `context_access`, `tool_policy`, `sandbox_access`, and `quality_gates` are validated.

- [x] **Step 2: Add `CapabilitySkillV2YamlModel`**

Implement:

- `SkillWorkerModel`
- `SkillIOContractModel`
- `SkillContextAccessModel`
- `SkillToolPolicyModel`
- `SkillSandboxAccessModel`
- `CapabilitySkillV2YamlModel`

- [x] **Step 3: Keep cross-reference validation pointed at subagent types**

Update `CrossRefValidator.validate_skill` to read `skill.worker.subagent_type` for v2.

- [x] **Step 4: Run tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/services/test_capability_schema.py tests/services/test_cross_ref_validator.py -q
```

Expected: pass.

## Task 3: Loader Cutover To v2

**Files:**

- Modify: `backend/src/services/capability_loader.py`
- Modify: `backend/src/dataservice/domains/catalog/service.py`
- Modify: `backend/tests/services/test_capability_loader.py`

- [x] **Step 1: Make old seed fail in loader test**

Use a seed without `schema_version` and assert:

```python
with pytest.raises(ValueError, match="schema_version"):
    await loader.load_seeds_if_empty()
```

- [x] **Step 2: Validate seed text through `CapabilityV2YamlModel`**

`CapabilityLoader._validate_yaml_text()` should instantiate `CapabilityV2YamlModel` and return `model.to_catalog_data()`.

- [x] **Step 3: Normalize catalog values from v2**

In `DataServiceCatalogService.capability_values()`:

- `display_name = data["display"]["name"]`
- `description = data["display"]["description"]`
- `trigger_phrases = data["intent"]["trigger_phrases"]`
- `brief_schema = data["inputs"]["brief_schema"]`
- `ui_meta` derives from `display`
- `runtime = {"mode": "compute_agentic", "sandbox_policy": data["sandbox_policy"]}`
- `definition_json` stores the full v2 document.

- [x] **Step 4: Run loader/catalog tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/services/test_capability_loader.py tests/dataservice/test_catalog_domain.py -q
```

Expected: pass.

## Task 4: Mission Seed Cutover

**Files:**

- Delete: old files under `backend/seed/capabilities/*/*.yaml`
- Add: new mission files under `backend/seed/capabilities/{workspace_type}/`
- Modify: `backend/tests/seed/test_capability_seeds_load.py`
- Modify: `docs/current/workspace-feature-catalog.md`

- [x] **Step 1: Replace thesis seeds**

Create six thesis mission YAMLs listed in Target Mission Catalog. Each must include:

- `schema_version: capability.v2`
- `display.entry_tier`
- `mission.primary_surface: prism`
- `context_policy.room_reads`
- `sandbox_policy.mode`
- `review_policy.default_targets`
- `quality_gates`
- executable `graph_template.phases[*].tasks[*].skill_id`

- [x] **Step 2: Replace SCI/proposal/software/patent seeds**

Use the same schema and target catalog. Do not keep old ids.

- [x] **Step 3: Update seed tests**

Assert that no old ids exist:

```python
old_ids = {"outline_generate", "section_write", "section_revise", "framework_outline", "section_writing", "proposal_outline", "patent_outline", "writing", "thesis_writing"}
assert old_ids.isdisjoint({record.id for record in records})
```

- [x] **Step 4: Run seed tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/seed/test_capability_seeds_load.py tests/integration/test_capability_skill_seeds.py -q
```

Expected: pass.

## Task 5: Skill Seed Cutover

**Files:**

- Delete: old files under `backend/seed/skills/*.yaml`
- Add: v2 worker skill files under `backend/seed/skills/*.yaml`
- Modify: `backend/tests/integration/test_capability_skill_seeds.py`

- [x] **Step 1: Add core worker skills**

Add:

- `research-scout`
- `literature-synthesizer`
- `source-quality-auditor`
- `manuscript-architect`
- `evidence-analyst`
- `figure-engineer`
- `manuscript-writer`
- `citation-auditor`
- `review-critic`
- `grant-planner`
- `proposal-writer`
- `patent-strategist`
- `patent-drafter`
- `software-structure-planner`
- `software-doc-drafter`

- [x] **Step 2: Update skill loader/service path**

Persist full v2 skill under `skill_json`, derive existing projection fields from v2.

- [x] **Step 3: Run skill seed tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/integration/test_capability_skill_seeds.py tests/services/test_admin_skill_service.py -q
```

Expected: pass.

## Task 6: Runtime Policy Cutover

**Files:**

- Modify: `backend/src/tools/builtins/launch_feature.py`
- Modify: `backend/src/agents/chat_agent/agent.py`
- Modify: `backend/src/agents/lead_agent/v2/runtime.py`
- Modify: `backend/src/compute/projection_service.py`

- [x] **Step 1: Reject non-v2 capability at launch**

If `cap.schema_version != "capability.v2"`, return an error with `code="unsupported_capability_schema"`.

- [x] **Step 2: Render mission catalog in Chat Agent**

`_render_workspace_available_skills()` should prefer `cap["definition_json"]["mission"]["user_promise"]` and `cap["definition_json"]["display"]["entry_tier"]`.

- [x] **Step 3: Pass policies into Lead Agent task state**

Add `capability_policy` to initial `ExecutionState`:

```python
"capability_policy": {
    "mission": cap.definition_json.get("mission", {}),
    "context_policy": cap.definition_json.get("context_policy", {}),
    "sandbox_policy": cap.definition_json.get("sandbox_policy", {}),
    "review_policy": cap.definition_json.get("review_policy", {}),
    "quality_gates": cap.definition_json.get("quality_gates", []),
}
```

- [x] **Step 4: Replace compute sandbox signal**

`_build_runtime_profile_projection()` should return:

```python
"sandbox_policy": definition_json.get("sandbox_policy", {}),
"requires_sandbox": definition_json.get("sandbox_policy", {}).get("mode") == "required",
```

- [x] **Step 5: Run runtime tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/tools/test_launch_feature_tool.py tests/agents/lead_agent/v2/test_runtime.py tests/compute/test_projection_service.py -q
```

Expected: pass.

## Task 7: Frontend Mission Catalog Cutover

**Files:**

- Modify: `frontend/lib/workspace-feature-stages.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- Modify: affected frontend tests

- [x] **Step 1: Replace stage mapping ids**

Use mission ids from Target Mission Catalog.

- [x] **Step 2: Update tests away from workflow ids**

Replace old ids in tests with canonical mission ids.

- [x] **Step 3: Run frontend verification**

Run:

```bash
cd frontend && npm run typecheck
cd frontend && npx vitest run
```

Expected: pass.

## Task 8: Remove Old Resolver/Dashboard Workflow Assumptions

**Files:**

- Modify: `backend/src/services/feature_action_resolution_service.py`
- Modify: `backend/src/services/workspace_summary_service.py`
- Modify: `backend/src/services/dashboard/*.py`
- Modify: tests covering these services

- [x] **Step 1: Remove old id resolver dispatch**

Delete resolver branches for old workflow ids and add mission id handlers only.

- [x] **Step 2: Update dashboard module ids**

Dashboard summaries must report mission-level progress.

- [x] **Step 3: Add architecture guard**

Add a test that scans runtime and frontend source for old capability ids, allowing only historical docs.

- [x] **Step 4: Run backend verification**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/services tests/gateway tests/architecture -q
```

Expected: pass.

## Task 9: Release Gate And Docs

**Files:**

- Modify: `docs/current/workspace-feature-catalog.md`
- Modify: `docs/current/workspace-current-state.md`
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/release-gate-checklist.md`

- [x] **Step 1: Update current docs**

State that mission-level capability v2 is current and old workflow ids are removed.

- [x] **Step 2: Run full release gate subset**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/seed tests/services/test_capability_schema.py tests/services/test_capability_loader.py tests/integration/test_capability_skill_seeds.py -q
cd frontend && npm run typecheck
```

Expected: pass.

- [ ] **Step 3: Commit**

Commit message:

```bash
git commit -m "feat: cut capability catalog to super agent missions"
```

## Self-Review

- Spec coverage: the plan covers mission-first capability, worker skill contracts, sandbox policy, review policy, Prism as primary surface, DataService Catalog as SSOT, clean cutover, and frontend mission entry catalog.
- Known deliberate sequencing: ReviewBatch v2 storage is not first because DataService review v1 already supports user-reviewable batches; runtime can use it while schema v2 establishes capability and skill policy.
- No runtime fallback: every task either rejects non-v2 or deletes old ids. Any compatibility terms in frontend docs are treated as historical and must not be runtime logic.
- First safe implementation slice: Task 1 and Task 2 can land without rewriting all seeds; Task 3 is the point where old seed loading intentionally starts failing until Task 4 lands in the same working branch.
