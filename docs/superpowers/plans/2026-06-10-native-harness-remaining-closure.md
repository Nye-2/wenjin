# Native Harness Remaining Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the current Wenjin native harness goal efficiently: close the remaining quality-gate loop, prove the sandbox/team workflow still works end to end, and leave the architecture clean without Codex SDK, cc-switch, deer-flow runtime, or a second execution system.

**Architecture:** Keep the single Wenjin execution chain as the only source of truth: `ChatAgent -> LeadAgent -> TeamKernel/static graph -> ReactSubagent -> Wenjin Harness -> DataService/Sandbox/Review`. External projects are pattern references only; useful ideas must collapse into existing capability policy, harness metadata, research-task evaluation, sandbox layout, review-first artifacts, and current run projection. Every slice must be TDD-first and small enough to commit independently.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Pydantic v2, LangGraph, pytest, Ruff, existing DataService sandbox domain, existing Wenjin harness tools.

---

## Current Ground Truth

- Branch: `codex/wenjin-native-harness`
- Worktree expectation before starting: clean `git status --short`.
- Current native harness regression gate: `349 passed` at the last verified commit.
- Already closed:
  - output refs under `/workspace/tmp/tasks/.harness/outputs/**`
  - explicit `sandbox.read_output_ref`
  - bounded context allowlists for `sandbox_execution_summary` and `member_execution_transcript`
  - capability-derived research eval surfaces for mock SCI E2E
  - read/write scheduler with concurrent reads and exclusive writes/run_python
  - output budget head/tail preview already exists in `backend/src/agents/harness/output_budget.py`

## Execution Status

2026-06-10 update:

- Task 2 is implemented: TeamKernel quality gates now receive `capability_policy`, and `research_evidence_required` reuses the deterministic research-task evaluator for runtime-verifiable required surfaces.
- Task 3 is implemented: mock SCI sandbox E2E now asserts the runtime `execution.team.quality_gate` event contains `research_evidence_required` with `status=pass`.
- Task 4 verification passed:
  - `tests/integration/test_harness_mock_sandbox_e2e.py tests/agents/lead_agent/v2/test_team_quality_gates.py tests/agents/harness/test_research_task_eval.py -q` -> 43 passed.
  - Native harness gate including `tests/sandbox/test_docker_provider.py` -> 350 passed.
  - Ruff over harness/Lead/subagent/test targets -> passed.
  - Drift scan found no production runtime dependency on Codex SDK, cc-switch, deer-flow runtime, `/mnt/user-data`, or generic `sandbox.run_command`; documentation and negative/historical tests were the only expected hits.
  - `git diff --check` -> passed.
- Task 5 docs are updated; commit remains pending until final diff review.

2026-06-10 continuation update:

- Current branch is `codex/wenjin-native-harness`; `git status --short` is clean.
- Latest completed commits:
  - `a151807a feat: surface research evidence contract to team members`
  - `5c6b0082 fix: align sandbox script names with workspace layout`
  - `51ff3532 fix: filter protected sandbox artifacts`
- Current verified native harness gate: `365 passed` after the Prism academic-style delta contract slice.
- The current continuation has added bounded Prism `academic_style_contract` payload propagation plus optional `style_delta(schema=wenjin.prism.academic_style_delta.v1)` projection/eval coverage. The next work must remain a convergence pass: calibrate the new surface on real rewrite tasks, improve prompts/tools from failures, and avoid feature expansion or external runtime drift.

## Current Continuation Plan

### Slice A: Re-baseline the Harness Surface Before More Edits

**Purpose:** Start from facts, not memory, and prevent duplicate plan/doc drift.

**Files:**
- Read: `docs/current/native-harness-convergence-audit.md`
- Read: `docs/current/native-harness-external-gap-matrix.md`
- Read: `docs/current/release-gate-checklist.md`
- Read: `backend/src/sandbox/workspace_layout.py`
- Read: `backend/src/sandbox/providers/local.py`
- Read: `backend/src/agents/lead_agent/v2/sandbox_artifact_discovery.py`
- Read: `backend/src/agents/harness/context_assembly.py`
- Read: `backend/src/agents/lead_agent/v2/team/quality_gates.py`

- [x] **Step 1: Verify clean state**

Run:

```bash
git status --short
```

Expected:

```text

```

- [x] **Step 2: Re-run focused drift scan**

Run:

```bash
rg -n "from .*codex|import .*codex|cc-switch|ccswitch|deerflow|deer-flow|sandbox\\.run_command|/mnt/user-data|codex sdk|Codex SDK" \
  backend/src/agents/harness \
  backend/src/agents/lead_agent/v2 \
  backend/src/subagents/v2 \
  backend/src/sandbox \
  backend/tests/architecture \
  backend/tests/agents \
  docs/current -S
```

Expected:

- No production runtime import/use of Codex SDK, cc-switch, deer-flow runtime, generic `sandbox.run_command`, or `/mnt/user-data`.
- Allowed hits are documentation or negative boundary tests that explicitly reject those paths.

- [x] **Step 3: Rebuild code-review graph after latest commits**

Use the configured `code-review-graph` tool to refresh the graph for `/Users/ze/wenjin`.

Expected:

- Graph build completes.
- Review starts from changed harness/sandbox/Lead files instead of scanning the whole repository manually first.

### Slice B: Close Sandbox Artifact Discovery Target Safety

**Purpose:** Make sure generated artifact discovery cannot turn protected, internal, guidance, symlink-escaped, or host-path targets into user-reviewable artifacts.

**Files:**
- Test: `backend/tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py`
- Test: `backend/tests/sandbox/test_workspace_layout.py`
- Test if provider behavior is involved: `backend/tests/sandbox/test_docker_provider.py`
- Modify if needed: `backend/src/agents/lead_agent/v2/sandbox_artifact_discovery.py`
- Modify if needed: `backend/src/sandbox/workspace_layout.py`
- Modify if needed: `backend/src/sandbox/providers/local.py`

- [x] **Step 1: Write RED coverage for discovery target classification**

Add tests that prove these paths never enter `generated_artifacts[]`:

```text
/workspace/outputs/.env
/workspace/reports/.env
/workspace/outputs/README.md
/workspace/reports/manifest.json
/workspace/tmp/tasks/.harness/outputs/exec/node/invocation/stdout.txt
```

Also add one provider-level fixture where a listed `/workspace/outputs/leaked.csv` entry resolves to a target outside `/workspace` or to a protected target. Expected candidate list:

```python
assert [item["path"] for item in artifacts] == ["/workspace/outputs/result.csv"]
```

- [x] **Step 2: Run RED tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py \
  tests/sandbox/test_workspace_layout.py -q
```

Expected before any fix: at least one newly added test fails if the suspected boundary is not already covered.

- [x] **Step 3: Implement the smallest central fix**

Implementation rules:

- Reuse `is_user_reviewable_workspace_artifact_path()` for virtual path classification.
- Reuse existing provider/path resolver behavior for physical target checks.
- Do not add a second artifact allowlist in `sandbox_artifact_discovery.py`.
- Do not expose internal output-ref paths to list/search/artifact review.

- [x] **Step 4: Run GREEN and related tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py \
  tests/sandbox/test_workspace_layout.py \
  tests/agents/harness/test_sandbox_file_tools.py -q
```

Expected: all selected tests pass.

### Slice C: Tighten Team Quality Failure to Replan Context

**Purpose:** When a required research evidence surface fails, the next member should receive a concise repair brief with missing surfaces and safe evidence refs, not raw tool payloads or vague retry text.

**Files:**
- Test: `backend/tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py`
- Test: `backend/tests/agents/lead_agent/v2/test_team_quality_gates.py`
- Modify if needed: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Modify if needed: `backend/src/agents/lead_agent/v2/team/quality_gates.py`
- Modify if needed: `backend/src/agents/lead_agent/v2/team/member_context.py`

- [x] **Step 1: Write RED coverage for missing-surface repair brief**

Construct a state where `capability_policy.research_evidence.required_surfaces` contains `output_ref_reuse`, `sandbox_execution_summary.output_refs` has one recoverable ref, and `member_execution_transcript.output_refs_read` is empty.

Expected assertions:

```python
assert gate.status == "fail"
assert "output_ref_reuse" in repair_context["missing_research_surfaces"]
assert "/workspace/tmp/tasks/.harness/outputs/" in repair_context["safe_output_refs"][0]
assert "stdout" not in str(repair_context).lower()
assert "traceback" not in str(repair_context).lower()
```

- [x] **Step 2: Run RED test**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py::test_replan_context_includes_missing_research_surfaces_without_raw_payload -q
```

Expected: failure until the repair context is projected cleanly.

- [x] **Step 3: Implement bounded repair projection**

Implementation rules:

- Use existing quality-gate result/finding data.
- Project only surface names, short reasons, safe output refs, and allowed sandbox/reproducibility summaries.
- Do not include raw stdout/stderr/tool args/provider payloads/scripts.
- Keep this inside TeamKernel/member-context projection, not in ReactSubagent or frontend code.

- [x] **Step 4: Run GREEN and context tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py \
  tests/agents/lead_agent/v2/test_team_quality_gates.py \
  tests/agents/harness/test_context_assembly.py -q
```

Expected: all selected tests pass.

### Slice D: Prove Mock Sandbox Harness Still Runs as a Product Chain

**Purpose:** Test the actual chain users care about: capability task -> team member -> sandbox job -> output ref reuse -> reviewable artifact -> DataService review item.

**Files:**
- Test: `backend/tests/integration/test_harness_mock_sandbox_e2e.py`
- Modify only if test reveals a real bug: Lead/team/harness files touched by the failing assertion.

- [x] **Step 1: Run current mock sandbox E2E**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/integration/test_harness_mock_sandbox_e2e.py -q
```

Expected: all tests pass.

- [x] **Step 2: Tighten assertions only where they prove user-facing value**

The E2E must prove:

```python
assert any(item["target_kind"] == "sandbox_artifact" for item in review_items)
assert any(item["target_kind"] == "prism_file_change" for item in review_items)
assert evaluation.coverage["workflow_trace"] == "pass"
assert evaluation.coverage["output_ref_reuse"] == "pass"
assert quality_gate["name"] == "research_evidence_required"
assert quality_gate["status"] == "pass"
```

- [x] **Step 3: Re-run E2E after any assertion/fix**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/integration/test_harness_mock_sandbox_e2e.py -q
```

Expected: all integration tests pass without new runtime tables, frontend stores, or compatibility branches.

### Slice E: Full Native Harness Gate, Ruff, and Browser Smoke

**Purpose:** Verify the implementation as a system, including the browser-observable team/run UX, without expanding into unrelated UI redesign.

**Files:**
- No expected code changes unless verification reveals a bug.

- [x] **Step 1: Run native harness regression gate**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/agents/harness/test_scheduler_and_python_tool.py \
  tests/agents/harness/test_sandbox_file_tools.py \
  tests/agents/harness/test_command_audit.py \
  tests/agents/harness/test_policy_and_registry.py \
  tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py \
  tests/agents/harness/test_research_task_eval.py \
  tests/agents/harness/test_langchain_adapter.py \
  tests/agents/harness/test_context_assembly.py \
  tests/unit/subagents/test_react.py \
  tests/subagents/v2/test_registry.py \
  tests/agents/lead_agent/v2/test_team_policy.py \
  tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py \
  tests/agents/lead_agent/v2/test_sandbox_runtime.py \
  tests/agents/lead_agent/v2/test_workspace_sandbox_manager.py \
  tests/agents/lead_agent/v2/test_runtime.py::test_run_session_prism_review_items_satisfy_writing_evidence_eval \
  tests/architecture/test_native_harness_boundaries.py \
  tests/dataservice/test_sandbox_domain.py \
  tests/sandbox/test_docker_provider.py \
  tests/sandbox/test_workspace_layout.py \
  tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py \
  tests/agents/lead_agent/v2/test_citation_source_audit.py \
  tests/agents/lead_agent/v2/test_team_quality_gates.py \
  tests/services/test_workspace_prism_service.py::test_surface_projection_includes_review_provenance_and_protection \
  tests/services/test_prism_review_projection.py \
  tests/integration/test_harness_mock_sandbox_e2e.py -q
```

Expected: all selected tests pass; record the exact count in docs.

- [x] **Step 2: Run Ruff**

Run:

```bash
cd backend && .venv/bin/ruff check \
  src/agents/harness \
  src/agents/lead_agent/v2 \
  src/subagents/v2 \
  src/sandbox \
  tests/agents/harness \
  tests/agents/lead_agent/v2 \
  tests/sandbox \
  tests/integration/test_harness_mock_sandbox_e2e.py
```

Expected:

```text
All checks passed!
```

- [x] **Step 3: Browser smoke via existing local stack**

Use the browser automation tool against the running local Wenjin app.

Expected user-observable checks:

- Workspace opens without auth regression.
- Launching a research task shows one current run, not duplicate run surfaces.
- Team/member labels are readable and not exposing raw template ids as the main UI text.
- Acceptable review items include sandbox artifact / Prism file change surfaces when produced.
- No raw stdout/stderr/tool args appear in user-facing panels.

### Slice F: Documentation, Graph, Commit Boundary

**Purpose:** Leave the branch easy to merge and easy to review.

**Files:**
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/workspace-current-state.md`
- Modify: `docs/current/native-harness-convergence-audit.md`
- Modify: `docs/current/native-harness-external-gap-matrix.md`
- Modify: `docs/current/release-gate-checklist.md`
- Modify: `docs/superpowers/plans/2026-06-10-native-harness-remaining-closure.md`

- [x] **Step 1: Update docs with exact verification evidence**

Required doc facts:

- latest native harness gate count
- any new sandbox artifact / symlink / protected-path behavior
- any new quality-gate repair-context behavior
- browser smoke result
- explicit statement that Codex SDK/cc-switch/deer-flow runtime were not imported

- [x] **Step 2: Rebuild code-review graph after final edits**

Use the configured `code-review-graph` tool for `/Users/ze/wenjin`.

Expected: graph build completes after final code/doc changes.

- [ ] **Step 3: Final diff review**

Run:

```bash
git diff --stat
git diff --check
git diff -- backend/src/agents backend/src/sandbox backend/tests docs/current docs/superpowers/plans/2026-06-10-native-harness-remaining-closure.md
```

Expected:

- No whitespace errors.
- Diffs are limited to native harness/sandbox/team quality/docs.
- No unrelated UI, billing, model-routing, SDK, or provider bridge changes.

- [ ] **Step 4: Commit focused changes**

Stage only files changed by the current pass and commit with one message that describes the closed slice, for example:

```bash
git commit -m "fix: harden native harness sandbox review loop"
```

Expected:

- Commit succeeds.
- `git status --short` is clean after commit.

## Non-Negotiable Boundaries

Do:

- Use `backend/src/sandbox/workspace_layout.py` as the only workspace filesystem source of truth.
- Use `backend/src/agents/harness/research_task_eval.py` for deterministic output-quality checks.
- Use `backend/src/agents/harness/context_assembly.py` for bounded agent context.
- Use `ExecutionNodeRecord.node_metadata.harness` and existing DataService events for execution evidence.
- Keep result writes review-first through existing review/result-card flow.

Do not:

- Do not reintroduce Codex SDK, cc-switch, Kimi/MiMo protocol conversion, deer-flow runtime/factory/run store, ACP workspace, `/mnt/user-data`, generic `sandbox.run_command`, a second run table, or a second frontend execution stream/store.
- Do not add compatibility/fallback layers for old harness behavior.
- Do not widen agent permissions by exposing raw stdout/stderr/scripts/tool args in prompt context.
- Do not turn this into frontend redesign, billing, model routing, or generic terminal-agent work.

## File Structure

- Read: `/Users/ze/codex/codex-rs/core/src/unified_exec/head_tail_buffer.rs`
- Read: `/Users/ze/codex/codex-rs/core/src/turn_diff_tracker.rs`
- Read: `/Users/ze/codex/codex-rs/execpolicy/src/policy.rs`
- Read: `/Users/ze/deer-flow/backend/packages/harness/deerflow/agents/middlewares/tool_output_budget_middleware.py`
- Read: `/Users/ze/deer-flow/backend/packages/harness/deerflow/sandbox/file_operation_lock.py`
- Read: `/Users/ze/deer-flow/backend/packages/harness/deerflow/agents/lead_agent/prompt.py`
- Modify if needed: `backend/src/agents/harness/research_task_eval.py`
- Modify if needed: `backend/src/agents/lead_agent/v2/team/quality_gates.py`
- Modify if needed: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Modify if needed: `backend/src/agents/harness/context_assembly.py`
- Modify if needed: `backend/tests/agents/harness/test_research_task_eval.py`
- Modify if needed: `backend/tests/agents/lead_agent/v2/test_team_quality_gates.py`
- Modify if needed: `backend/tests/integration/test_harness_mock_sandbox_e2e.py`
- Modify after verification: `docs/current/native-harness-external-gap-matrix.md`
- Modify after verification: `docs/current/native-harness-convergence-audit.md`
- Modify after verification: `docs/current/release-gate-checklist.md`
- Modify after verification: `docs/current/architecture.md`

---

### Task 1: Reconfirm Remaining Gap From Evidence

**Files:**
- Read: `docs/current/native-harness-external-gap-matrix.md`
- Read: `docs/current/native-harness-convergence-audit.md`
- Read: `backend/src/agents/harness/output_budget.py`
- Read: selected Codex/deer-flow files above

- [ ] **Step 1: Verify clean state**

Run:

```bash
git status --short
```

Expected:

```text

```

- [ ] **Step 2: Confirm no duplicate output-budget work is needed**

Run:

```bash
sed -n '1,220p' backend/src/agents/harness/output_budget.py
```

Expected:

- `DEFAULT_PREVIEW_HEAD_CHARS`
- `DEFAULT_PREVIEW_TAIL_CHARS`
- `externalized_preview(...)`
- `bounded_externalized_preview_budget(...)`

If these exist, do not add another head/tail truncation slice.

- [ ] **Step 3: Re-sample only the external patterns relevant to the remaining gap**

Run:

```bash
sed -n '1,220p' /Users/ze/codex/codex-rs/core/src/turn_diff_tracker.rs
sed -n '1,180p' /Users/ze/codex/codex-rs/execpolicy/src/policy.rs
sed -n '1,220p' /Users/ze/deer-flow/backend/packages/harness/deerflow/agents/lead_agent/prompt.py
```

Expected decision:

- Adopt only patterns that strengthen Wenjin's existing harness quality loop.
- Do not import runtime/provider/protocol code.

- [ ] **Step 4: Pick exactly one implementation slice**

The default slice is:

```text
Wire capability-declared research evidence surfaces into runtime/team quality enforcement so required surfaces are not only tested in mock E2E but also visible as a deterministic runtime gate.
```

Reject a different slice unless inspection finds a higher-severity bug in:

- context leakage
- sandbox path safety
- review artifact staging
- replan loop semantics

---

### Task 2: Add Runtime Quality-Gate Coverage for Capability Evidence Surfaces

**Files:**
- Modify: `backend/src/agents/lead_agent/v2/team/quality_gates.py`
- Modify if needed: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Modify: `backend/tests/agents/lead_agent/v2/test_team_quality_gates.py`
- Reuse: `backend/src/agents/harness/research_task_eval.py`

- [ ] **Step 1: Write the failing test**

Add a focused test to `backend/tests/agents/lead_agent/v2/test_team_quality_gates.py` that constructs a runtime state with capability policy requiring `workflow_trace` and `output_ref_reuse`, then gives it harness metadata where recoverable refs exist but no member read them.

Expected assertion shape:

```python
assert result.status == "fail"
assert any("output_ref_reuse" in finding.message for finding in result.findings)
```

- [ ] **Step 2: Run the RED test**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_quality_gates.py::test_quality_gate_enforces_capability_required_research_surfaces -q
```

Expected:

```text
FAILED
```

The failure should show that capability-required research surfaces are not yet enforced by the runtime quality gate.

- [ ] **Step 3: Implement the smallest runtime bridge**

Implementation rule:

- Import and call existing `required_surfaces_from_capability_policy()` and `evaluate_research_task_evidence()`.
- Do not duplicate evidence parsing in `quality_gates.py`.
- Do not add a new evaluator class unless the existing file becomes clearly overloaded.
- Return a `QualityGateResult` finding that references the failed surface and its reason, not raw harness payload.

Expected behavior:

```text
capability_policy.research_evidence.required_surfaces
  -> required_surfaces_from_capability_policy(...)
  -> evaluate_research_task_evidence(...)
  -> QualityGateResult findings
```

- [ ] **Step 4: Run GREEN verification**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_quality_gates.py::test_quality_gate_enforces_capability_required_research_surfaces -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Run surrounding gate tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_quality_gates.py tests/agents/harness/test_research_task_eval.py -q
```

Expected: all selected tests pass.

---

### Task 3: Prove the Gate in Mock SCI Sandbox E2E

**Files:**
- Modify: `backend/tests/integration/test_harness_mock_sandbox_e2e.py`
- Modify if needed: `backend/src/agents/lead_agent/v2/runtime.py`
- Modify if needed: `backend/src/agents/lead_agent/v2/team/kernel.py`

- [ ] **Step 1: Add or tighten the E2E assertion**

The mock SCI flow must prove:

- capability policy declares required research surfaces
- required surfaces are derived from capability data, not hard-coded in the test
- the two-member sandbox path produces `workflow_trace`
- `sandbox.run_python` produces a recoverable output ref
- `sandbox.read_output_ref` reads that ref
- final evaluation passes `output_ref_reuse`

Expected assertion shape:

```python
required_surfaces = required_surfaces_from_capability_policy(runtime._capability_policy(capability))
assert "workflow_trace" in required_surfaces
assert "output_ref_reuse" in required_surfaces
assert evaluation.coverage["workflow_trace"] == "pass"
assert evaluation.coverage["output_ref_reuse"] == "pass"
```

- [ ] **Step 2: Run focused E2E**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/integration/test_harness_mock_sandbox_e2e.py::test_team_harness_mock_sandbox_flow_stages_reviewable_artifact -q
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Fix only real breakage**

Allowed fixes:

- pass missing capability policy into the runtime quality-gate context
- preserve bounded harness metadata needed by `evaluate_research_task_evidence`
- adjust the mock flow so it reads existing output refs before rerunning expensive sandbox work

Rejected fixes:

- hard-code SCI surfaces in runtime
- expose hidden output refs through list/search
- weaken `output_ref_reuse` to pass without an actual `sandbox.read_output_ref`

---

### Task 4: Run Native Harness Gate and Drift Scan

**Files:**
- No implementation changes expected unless tests fail.

- [ ] **Step 1: Run the focused regression set**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/agents/harness/test_scheduler_and_python_tool.py \
  tests/agents/harness/test_sandbox_file_tools.py \
  tests/agents/harness/test_command_audit.py \
  tests/agents/harness/test_policy_and_registry.py \
  tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py \
  tests/agents/harness/test_research_task_eval.py \
  tests/agents/harness/test_langchain_adapter.py \
  tests/agents/harness/test_context_assembly.py \
  tests/unit/subagents/test_react.py \
  tests/subagents/v2/test_registry.py \
  tests/agents/lead_agent/v2/test_team_policy.py \
  tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py \
  tests/agents/lead_agent/v2/test_sandbox_runtime.py \
  tests/agents/lead_agent/v2/test_workspace_sandbox_manager.py \
  tests/agents/lead_agent/v2/test_runtime.py::test_run_session_prism_review_items_satisfy_writing_evidence_eval \
  tests/architecture/test_native_harness_boundaries.py \
  tests/dataservice/test_sandbox_domain.py \
  tests/sandbox/test_workspace_layout.py \
  tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py \
  tests/agents/lead_agent/v2/test_citation_source_audit.py \
  tests/agents/lead_agent/v2/test_team_quality_gates.py \
  tests/services/test_workspace_prism_service.py::test_surface_projection_includes_review_provenance_and_protection \
  tests/services/test_prism_review_projection.py \
  tests/integration/test_harness_mock_sandbox_e2e.py -q
```

Expected: all selected tests pass. The exact count should be recorded in docs after the run.

- [ ] **Step 2: Run Ruff**

Run:

```bash
cd backend && .venv/bin/ruff check \
  src/agents/harness \
  src/agents/lead_agent/v2 \
  src/subagents/v2 \
  tests/agents/harness \
  tests/agents/lead_agent/v2 \
  tests/integration/test_harness_mock_sandbox_e2e.py
```

Expected:

```text
All checks passed!
```

- [ ] **Step 3: Run drift scan**

Run:

```bash
rg -n "from .*codex|import .*codex|cc-switch|ccswitch|deerflow|deer-flow|sandbox\\.run_command|/mnt/user-data|codex sdk|Codex SDK" \
  backend/src/agents/harness \
  backend/src/agents/lead_agent/v2 \
  backend/src/subagents/v2 \
  backend/src/sandbox \
  backend/tests/architecture \
  backend/tests/agents \
  docs/current -S
```

Expected:

- no production runtime import/use of external harnesses
- no generic `sandbox.run_command`
- no `/mnt/user-data` in native sandbox provider/runtime code
- documentation references are allowed only when they explicitly say "do not migrate" or "pattern reference only"

- [ ] **Step 4: Run whitespace check**

Run:

```bash
git diff --check
```

Expected:

```text

```

---

### Task 5: Update Current Docs and Commit

**Files:**
- Modify: `docs/current/native-harness-external-gap-matrix.md`
- Modify: `docs/current/native-harness-convergence-audit.md`
- Modify: `docs/current/release-gate-checklist.md`
- Modify if needed: `docs/current/architecture.md`
- Modify: `docs/superpowers/plans/2026-06-10-native-harness-remaining-closure.md`

- [ ] **Step 1: Update audit with exact verification results**

Add a dated entry to `docs/current/native-harness-convergence-audit.md`:

```text
2026-06-10 capability-required research-surface runtime gate:
- Capability policy required surfaces are now enforced through the existing deterministic research-task evaluator.
- Mock SCI sandbox E2E proves workflow_trace and output_ref_reuse through sandbox.run_python + sandbox.read_output_ref.
- Verification: <exact commands> -> <exact counts>.
```

- [ ] **Step 2: Update gap matrix**

In `docs/current/native-harness-external-gap-matrix.md`, update the quality-gate gap:

```text
SCI capability seeds can declare required research surfaces; Lead/runtime quality gates now evaluate those surfaces through the shared deterministic evaluator instead of relying only on mock E2E assertions.
```

- [ ] **Step 3: Update release gate count**

In `docs/current/release-gate-checklist.md`, replace the native harness gate count with the exact new count from Task 4.

- [ ] **Step 4: Review the diff**

Run:

```bash
git diff --stat
git diff -- backend/src/agents/harness backend/src/agents/lead_agent/v2 backend/tests/agents backend/tests/integration docs/current docs/superpowers/plans/2026-06-10-native-harness-remaining-closure.md
```

Expected:

- changes are limited to the runtime quality gate, tests, and docs
- no SDK/protocol/runtime bridge
- no broad refactor

- [ ] **Step 5: Commit**

Run:

```bash
git add \
  backend/src/agents/harness/research_task_eval.py \
  backend/src/agents/lead_agent/v2/team/quality_gates.py \
  backend/src/agents/lead_agent/v2/team/kernel.py \
  backend/tests/agents/harness/test_research_task_eval.py \
  backend/tests/agents/lead_agent/v2/test_team_quality_gates.py \
  backend/tests/integration/test_harness_mock_sandbox_e2e.py \
  docs/current/native-harness-external-gap-matrix.md \
  docs/current/native-harness-convergence-audit.md \
  docs/current/release-gate-checklist.md \
  docs/current/architecture.md \
  docs/superpowers/plans/2026-06-10-native-harness-remaining-closure.md
git commit -m "feat: enforce capability research evidence surfaces"
```

If some listed files were not changed, remove them from `git add` rather than touching them just to satisfy the command.

---

## Stop Conditions

Stop and reassess before coding if any of these happen:

- The test requires a new runtime table, new frontend store, or new execution event stream.
- The implementation needs raw stdout/stderr/tool args in prompt context.
- Capability policy shape is ambiguous and cannot be read from existing runtime state.
- A failing test reveals unrelated DataService, billing, model routing, or Prism UI bugs.
- External project sampling suggests importing runtime code rather than borrowing a pattern.

## Self-Review

- Spec coverage: the plan covers remaining harness closure, capability quality enforcement, mock sandbox E2E, drift scan, docs, and commit boundary.
- Placeholder scan: no "TBD", "TODO", "later", or undefined fallback slice is required to execute the plan.
- Type consistency: the plan reuses existing `required_surfaces_from_capability_policy()`, `evaluate_research_task_evidence()`, `QualityGateResult`, and current harness metadata instead of defining a parallel evaluator.
