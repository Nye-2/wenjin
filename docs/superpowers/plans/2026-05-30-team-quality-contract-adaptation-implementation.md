# Team Quality Contract Adaptation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Implement runtime quality contracts for Team Kernel invocations and use them to drive lightweight quality gates and dynamic recruitment/revision decisions.

**Architecture:** Keep Chat Agent and Lead Agent topology unchanged. Add a runtime-only `QualityContractResolver` that derives member-level contracts from existing capability, agent template, and capability skill catalog records, then inject those contracts into `AgentInvocation.input_brief`. Keep quality evaluation as Team Kernel runtime behavior, with deterministic checks producing `QualityGateResult` facts.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, existing Wenjin DataService catalog contracts, Team Kernel runtime.

---

## File Structure

- Create `backend/src/agents/lead_agent/v2/team/quality_contract.py`
  - Owns `ResolvedQualityContract`, skill catalog extraction, deterministic merge and dedupe.
- Create `backend/src/agents/lead_agent/v2/team/quality_gates.py`
  - Owns pure quality gate evaluation helpers for invocation output availability, schema minimum shape, quality gate acknowledgement, direct commit intent, and recruitment/revision mapping.
- Modify `backend/src/agents/lead_agent/v2/team/kernel.py`
  - Inject quality contracts after skill catalog prefetch and before member execution.
  - Delegate gate evaluation to `quality_gates.py`.
  - Treat hard quality failures as report errors.
  - Allow `revise_existing` gate actions to schedule a same-template follow-up invocation when policy limits allow it.
- Modify `backend/src/services/capability_schema.py`
  - Add pure-data validation for non-empty `quality_pipeline` on `team_kernel` capabilities.
  - Validate quality gate ids are non-empty strings.
  - Validate skill output schema is object-shaped and supports `quality_gates_checked` when skill gates exist.
- Modify tests:
  - `backend/tests/agents/lead_agent/v2/test_team_quality_contract.py`
  - `backend/tests/agents/lead_agent/v2/test_team_quality_gates.py`
  - `backend/tests/agents/lead_agent/v2/test_team_kernel.py`
  - `backend/tests/services/test_capability_schema.py`

## Task 1: Quality Contract Resolver

**Files:**
- Create: `backend/tests/agents/lead_agent/v2/test_team_quality_contract.py`
- Create: `backend/src/agents/lead_agent/v2/team/quality_contract.py`

- [x] **Step 1: Write failing resolver tests**

Create tests that construct:

```python
AgentTemplate(
    id="research_scholar.v1",
    display_role="文献专家",
    category="research",
    default_skills=["research-scout", "citation-auditor"],
    output_contracts=["literature_evidence_report.v1"],
    quality_expectations=["claims map to source ids"],
    risk_profile={"room_write": "staged_only"},
)
```

and skill payloads where `skill_json.io_contract.output_schema.required == ["text", "quality_gates_checked"]`.

Assert:

```python
contract.schema_version == "resolved_quality_contract.v1"
contract.capability_id == "team_research"
contract.template_id == "research_scholar.v1"
contract.role == "文献专家"
contract.skill_ids == ["research-scout", "citation-auditor"]
contract.output_contracts == ["literature_evidence_report.v1"]
contract.output_schema["required"] == ["text", "quality_gates_checked"]
contract.quality_gates == [
    "evidence_traceability",
    "no_fabricated_sources",
    "source_log_required",
]
contract.recruitment_hints["missing_sources"] == ["research_scholar.v1"]
contract.source_refs["quality_gates"] == [
    "team_policy.quality_pipeline",
    "skill.research-scout.quality_gates",
    "skill.citation-auditor.quality_gates",
]
```

- [x] **Step 2: Verify resolver tests fail**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_quality_contract.py -v
```

Expected: fail because `quality_contract.py` does not exist.

- [x] **Step 3: Implement resolver**

Implement:

```python
class ResolvedQualityContract(BaseModel):
    schema_version: Literal["resolved_quality_contract.v1"] = "resolved_quality_contract.v1"
    capability_id: str
    template_id: str
    skill_ids: list[str] = Field(default_factory=list)
    role: str
    output_contracts: list[str] = Field(default_factory=list)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    quality_gates: list[str] = Field(default_factory=list)
    acknowledgement_required_gates: list[str] = Field(default_factory=list)
    quality_expectations: list[str] = Field(default_factory=list)
    must_rules: list[str] = Field(default_factory=list)
    should_rules: list[str] = Field(default_factory=list)
    may_rules: list[str] = Field(default_factory=list)
    recruitment_hints: dict[str, list[str]] = Field(default_factory=dict)
    source_refs: dict[str, list[str]] = Field(default_factory=dict)
```

Implement `QualityContractResolver.resolve(...)` as a pure function that:

- Reads `capability.id`, `capability.definition_json`, `team_policy`.
- Reads skill data from `skill.skill_json` first and `skill.config` second.
- Merges object output schemas with ordered `required` and `properties`.
- Adds direct-write and citation rules to `must_rules`.
- Adds template quality expectations to `should_rules`.
- Converts recruitment triggers to `recruitment_hints`.
- Dedupes list fields while preserving order.

- [x] **Step 4: Verify resolver tests pass**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_quality_contract.py -v
```

Expected: pass.

## Task 2: Team Kernel Brief Integration

**Files:**
- Modify: `backend/tests/agents/lead_agent/v2/test_team_kernel.py`
- Modify: `backend/src/agents/lead_agent/v2/team/kernel.py`

- [x] **Step 1: Write failing integration test**

Add a test that runs `LeadAgentRuntime.run_session(...)` with `FakeTeamCatalogClient`, captures `record_node_event` input data, and asserts every successful team node has:

```python
contract = event["input_data"]["quality_contract"]
assert contract["schema_version"] == "resolved_quality_contract.v1"
assert contract["template_id"] in {"research_scholar.v1", "critical_reviewer.v1"}
assert "quality_gates" in contract
```

- [x] **Step 2: Verify integration test fails**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_kernel.py::test_team_kernel_runtime_injects_quality_contract_into_member_brief -v
```

Expected: fail because `quality_contract` is not in `input_brief`.

- [x] **Step 3: Inject quality contract**

Modify `_run_invocation_batch` to call `_inject_quality_contracts(...)` after `_ensure_skill_cache(...)` and before `asyncio.gather(...)`.

Implement `_inject_quality_contracts(...)` to mutate each invocation:

```python
invocation.input_brief["quality_contract"] = QualityContractResolver.resolve(
    capability=capability,
    template=templates[invocation.template_id],
    team_policy=team_policy,
    effective_skill_ids=invocation.effective_skills,
    skill_records=skill_cache.records,
).model_dump(mode="json")
```

- [x] **Step 4: Verify integration test passes**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_kernel.py::test_team_kernel_runtime_injects_quality_contract_into_member_brief -v
```

Expected: pass.

## Task 3: Quality Gate Evaluator And Dynamic Revision

**Files:**
- Create: `backend/tests/agents/lead_agent/v2/test_team_quality_gates.py`
- Create: `backend/src/agents/lead_agent/v2/team/quality_gates.py`
- Modify: `backend/src/agents/lead_agent/v2/team/kernel.py`

- [x] **Step 1: Write failing gate tests**

Cover these cases:

```python
def test_quality_gates_request_revision_for_schema_violation():
    # succeeded invocation with output_report={"summary": "ok"}
    # quality_contract.output_schema.required == ["text"]
    # expects gate_id "output_schema_min_shape", status "fail",
    # next_action "revise_existing", required_fixes non-empty,
    # suggested_recruits contains same template id.

def test_quality_gates_request_recruit_for_missing_sources():
    # output_report.open_questions includes "missing_sources"
    # quality_contract.recruitment_hints maps missing_sources to ["research_scholar.v1"]
    # expects next_action "recruit_more".

def test_quality_gates_fail_direct_commit_tool_call():
    # tool_calls include {"name": "room_commit"}
    # expects gate_id "no_direct_commit_intent", status "fail",
    # next_action "stop_with_warning".
```

- [x] **Step 2: Verify gate tests fail**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_quality_gates.py -v
```

Expected: fail because `quality_gates.py` does not exist.

- [x] **Step 3: Implement gate evaluator**

Implement a pure `evaluate_quality_gates(...)` function that returns `list[QualityGateResult]` and supports:

- Existing member failed/cancelled behavior.
- `member_output_available`.
- `output_schema_min_shape`.
- `quality_gates_acknowledged`.
- `no_direct_commit_intent`.
- `citation_and_evidence_required`.

Use only policy-allowed templates for `suggested_recruits`.

- [x] **Step 4: Route Team Kernel through evaluator**

Modify `_run_quality_gates` to call `evaluate_quality_gates(...)`.

Modify `_next_recruits_from_gates` so `next_action in {"recruit_more", "revise_existing"}` can schedule a follow-up invocation from `suggested_recruits`, while keeping all existing team policy limits.

Add `_errors_from_quality_gates(...)` and include hard fail gate errors in the final report.

- [x] **Step 5: Verify gate and team kernel tests pass**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_quality_gates.py tests/agents/lead_agent/v2/test_team_kernel.py -v
```

Expected: pass.

## Task 4: Schema Validation Convergence

**Files:**
- Modify: `backend/tests/services/test_capability_schema.py`
- Modify: `backend/src/services/capability_schema.py`

- [x] **Step 1: Write failing schema tests**

Add tests:

```python
def test_team_kernel_requires_quality_pipeline():
    payload = valid_v2_payload_with_runtime_team_policy()
    payload["team_policy"]["quality_pipeline"] = []
    with pytest.raises(ValidationError, match="quality_pipeline"):
        CapabilityV2YamlModel(**payload)

def test_quality_gate_ids_must_not_be_blank():
    payload = valid_v2_payload()
    payload["quality_gates"] = [" "]
    with pytest.raises(ValidationError, match="quality_gates"):
        CapabilityV2YamlModel(**payload)

def test_skill_with_quality_gates_requires_checked_output_field():
    payload = valid_skill_payload()
    payload["quality_gates"] = ["source_log_required"]
    payload["io_contract"]["output_schema"] = {"type": "object", "properties": {"text": {"type": "string"}}}
    with pytest.raises(ValidationError, match="quality_gates_checked"):
        CapabilitySkillV2YamlModel(**payload)
```

- [x] **Step 2: Verify schema tests fail**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/services/test_capability_schema.py -v
```

Expected: fail on the newly added tests.

- [x] **Step 3: Implement validators**

Add Pydantic validators:

- `CapabilityV2YamlModel.validate_team_kernel_contract` enforces non-empty quality pipeline and non-blank quality gate ids for `team_kernel`.
- `CapabilitySkillV2YamlModel` validates `io_contract.output_schema.type == "object"` when schema exists.
- `CapabilitySkillV2YamlModel` requires `quality_gates_checked` in output schema properties or required list when `quality_gates` is non-empty.

- [x] **Step 4: Verify schema tests pass**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/services/test_capability_schema.py -v
```

Expected: pass.

## Task 5: Verification, Review, Browser Test, Commit

**Files:**
- All modified implementation and test files.

- [x] **Step 1: Run targeted backend tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_quality_contract.py tests/agents/lead_agent/v2/test_team_quality_gates.py tests/agents/lead_agent/v2/test_team_kernel.py tests/agents/lead_agent/v2/test_team_policy.py tests/services/test_capability_schema.py tests/integration/test_capability_skill_seeds.py -v
```

Expected: pass.

- [x] **Step 2: Run full backend tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/ -v
```

Expected: pass.

- [x] **Step 3: Run frontend typecheck**

Run:

```bash
cd frontend && npm run typecheck
```

Expected: pass.

- [x] **Step 4: Browser verification**

Start the frontend dev server:

```bash
cd frontend && npm run dev -- --port 3099
```

Use the in-app Browser against `http://localhost:3099` and verify:

- The app loads without a runtime error overlay.
- The page has visible Wenjin/workbench UI shell text.
- Browser console has no app-breaking error after load.

- [x] **Step 5: Self-review**

Review:

- `git diff --check`
- new runtime files for over-broad abstractions
- no direct commit tools reintroduced
- quality contract is runtime-only and does not create a new catalog
- gate evaluator only suggests policy-allowed templates

- [x] **Step 6: Commit**

Run:

```bash
git status --short
git add docs/superpowers/plans/2026-05-30-team-quality-contract-adaptation-implementation.md backend/src/agents/lead_agent/v2/team/quality_contract.py backend/src/agents/lead_agent/v2/team/quality_gates.py backend/src/agents/lead_agent/v2/team/kernel.py backend/src/services/capability_schema.py backend/tests/agents/lead_agent/v2/test_team_quality_contract.py backend/tests/agents/lead_agent/v2/test_team_quality_gates.py backend/tests/agents/lead_agent/v2/test_team_kernel.py backend/tests/services/test_capability_schema.py
git commit -m "feat: add team quality contract loop"
```

Expected: commit succeeds and worktree is clean.

## Self-Review Checklist

- Spec coverage: resolver, member brief injection, gate evaluation, dynamic recruit/revise mapping, schema validation, tests, browser verification.
- Scope control: no new DataService catalog, no frontend state rewrite, no Chat Agent change.
- Architecture convergence: quality contract is runtime-only and team kernel remains the single dynamic loop owner.
- Safety: direct commit tools remain blocked; staged result flow remains intact.
