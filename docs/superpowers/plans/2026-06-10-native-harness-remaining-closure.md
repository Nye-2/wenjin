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
