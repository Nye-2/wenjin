# Native Harness Standalone Next Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the current Wenjin native harness slice, prove output-ref reuse through a realistic SCI sandbox workflow, update the architecture record, and leave the branch in a tested commit-ready state without drifting toward Codex SDK, cc-switch, deer-flow runtime, or a second execution system.

**Architecture:** Keep the single source-of-truth chain `ChatAgent -> LeadAgent -> TeamKernel/static graph -> ReactSubagent -> Wenjin Harness -> DataService/Sandbox/Review`. External projects remain pattern references only; every useful idea must collapse into existing Wenjin harness metadata, sandbox layout, deterministic research eval, release gates, docs, and review-first UX. This pass is intentionally narrow: finish the partially implemented `output_ref_reuse` quality surface, run the native gate, then decide the next concrete gap from evidence rather than adding abstractions speculatively.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Pydantic v2, LangGraph, pytest, Ruff, existing DataService sandbox domain, existing Wenjin harness tools.

---

## Non-Negotiable Scope

Do:

- Finish the uncommitted `output_ref_reuse` slice already present in `research_task_eval.py` and the mock SCI E2E test.
- Keep output refs internal, bounded, explicit, and readable only through `sandbox.read_output_ref`.
- Keep all new checks deterministic over existing harness metadata.
- Update current docs and release-gate records after tests pass.
- Commit only focused, verified changes.

Do not:

- Do not reintroduce Codex SDK, cc-switch, Kimi/MiMo protocol bridges, deer-flow runtime/factory/run store, ACP workspace, `/mnt/user-data`, generic `sandbox.run_command`, second execution table, second frontend stream/store, or compatibility fallback layers.
- Do not expand this pass into frontend redesign, billing, model routing, or another agent-planning layer.
- Do not make hidden `/workspace/tmp/tasks/.harness/outputs/**` refs listable, searchable, writable, or reviewable artifacts.

## Current Modified Files

- Modify: `backend/src/agents/harness/research_task_eval.py`
  - Owns deterministic research-task evidence surfaces.
  - Current slice adds optional `output_ref_reuse`.
- Modify: `backend/tests/agents/harness/test_research_task_eval.py`
  - Unit coverage for pass/fail behavior of `output_ref_reuse`.
- Modify: `backend/tests/integration/test_harness_mock_sandbox_e2e.py`
  - Realistic SCI flow proving a member can run Python, receive an output ref, then read that ref through the actual companion tool path.
- Modify after tests pass: `docs/current/native-harness-external-gap-matrix.md`
- Modify after tests pass: `docs/current/native-harness-convergence-audit.md`
- Modify after tests pass: `docs/current/release-gate-checklist.md`
- Modify if needed: `docs/current/architecture.md`
- Modify if needed: `docs/current/workspace-current-state.md`

---

### Task 1: Close `output_ref_reuse` Unit Behavior

**Files:**
- Modify: `backend/src/agents/harness/research_task_eval.py`
- Test: `backend/tests/agents/harness/test_research_task_eval.py`

- [x] **Step 1: Review the current diff**

Run:

```bash
git diff -- backend/src/agents/harness/research_task_eval.py backend/tests/agents/harness/test_research_task_eval.py
```

Expected:

- `ResearchSurface` includes `"output_ref_reuse"`.
- `evaluate_research_task_evidence()` routes `"output_ref_reuse"` to `_evaluate_output_ref_reuse`.
- Unit tests cover:
  - pass when a recoverable ref is actually read;
  - fail when a recoverable ref exists but no member read it;
  - filtering excludes non-harness refs and protected refs.

- [x] **Step 2: Run focused unit tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/agents/harness/test_research_task_eval.py::test_research_task_eval_passes_output_ref_reuse_when_member_reads_recoverable_ref \
  tests/agents/harness/test_research_task_eval.py::test_research_task_eval_fails_output_ref_reuse_when_recoverable_refs_are_ignored -q
```

Expected:

```text
2 passed
```

- [x] **Step 3: Tighten implementation if review finds a small issue**

If `_output_ref_reuse_evidence()` repeatedly builds `set(output_refs_read)` inside a list comprehension, replace it with one local set:

```python
read_ref_set = set(output_refs_read)
reused_output_refs = [ref for ref in recoverable_output_refs if ref in read_ref_set][:50]
```

Do not change the schema shape:

```python
{
    "recoverable_output_refs": recoverable_output_refs,
    "output_refs_read": output_refs_read,
    "reused_output_refs": reused_output_refs,
    "recoverable_output_ref_count": len(recoverable_output_refs),
    "output_ref_read_count": len(output_refs_read),
    "reused_output_ref_count": len(reused_output_refs),
}
```

- [x] **Step 4: Run full research eval file**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_research_task_eval.py -q
```

Expected: all tests in the file pass.

---

### Task 2: Prove Output Ref Reuse in the Mock SCI E2E Flow

**Files:**
- Modify: `backend/tests/integration/test_harness_mock_sandbox_e2e.py`

- [x] **Step 1: Run the focused E2E test**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/integration/test_harness_mock_sandbox_e2e.py::test_team_harness_mock_sandbox_flow_stages_reviewable_artifact -q
```

Expected:

```text
1 passed
```

If it fails, only fix the exact break:

- If `SubagentContext` has no `context_bundle`, inject fake sandbox state through `harness_context.workspace_data["_harness_sandbox"]`.
- If tool names differ, use canonical resolved tool names already returned by `_resolve_tools(["sandbox.run_python"], harness_context)`.
- If refs differ, assert the canonical `/workspace/tmp/tasks/.harness/outputs/{execution_id}/{node_id}/sandbox.run_python.stdout.txt` path generated by the current harness.

- [x] **Step 2: Confirm the E2E exercises the actual tool path**

The analyst branch must do this:

```python
tools = _resolve_tools(["sandbox.run_python"], harness_context)
assert [tool.name for tool in tools] == ["sandbox_run_python", "sandbox_read_output_ref"]
```

Then it must call `sandbox_run_python`, capture the first returned `output_refs` item, and call `sandbox_read_output_ref` with:

```python
{
    "output_ref": captured["tool_payload"]["output_refs"][0],
    "start_line": 1,
    "end_line": 1,
}
```

Expected assertions:

```python
assert harness["member_execution_transcript"]["tool_names"] == [
    "sandbox.run_python",
    "sandbox.read_output_ref",
]
assert harness["member_execution_transcript"]["output_ref_read_count"] == 1
assert evaluation.coverage["output_ref_reuse"] == "pass"
```

- [x] **Step 3: Run the full integration file**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/integration/test_harness_mock_sandbox_e2e.py -q
```

Expected: all tests in the file pass.

---

### Task 3: Run Focused Harness Gate and Style Checks

**Files:**
- No expected implementation changes unless tests fail.

- [x] **Step 1: Run focused backend tests for this slice**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/agents/harness/test_research_task_eval.py \
  tests/integration/test_harness_mock_sandbox_e2e.py -q
```

Expected: both files pass.

- [x] **Step 2: Run Ruff on touched code**

Run:

```bash
cd backend && .venv/bin/ruff check \
  src/agents/harness/research_task_eval.py \
  tests/agents/harness/test_research_task_eval.py \
  tests/integration/test_harness_mock_sandbox_e2e.py
```

Expected: Ruff passes.

- [x] **Step 3: Run full native harness gate**

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

Expected: all selected tests pass.

- [x] **Step 4: Run architecture drift and whitespace checks**

Run:

```bash
rg -n "from .*codex|import .*codex|cc-switch|ccswitch|deerflow|deer-flow|sandbox\.run_command|/mnt/user-data" \
  backend/src/agents/harness \
  backend/src/agents/lead_agent/v2 \
  backend/src/subagents/v2 \
  backend/src/sandbox/providers \
  backend/src/services/release_gate_service.py \
  backend/src/quality/release_gate.py -g '*.py'
```

Expected: no output and exit code `1`.

Run:

```bash
git diff --check
```

Expected: no output.

---

### Task 4: Update Current Docs and Release Gate Records

**Files:**
- Modify: `docs/current/native-harness-external-gap-matrix.md`
- Modify: `docs/current/native-harness-convergence-audit.md`
- Modify: `docs/current/release-gate-checklist.md`
- Modify if needed: `docs/current/architecture.md`
- Modify if needed: `docs/current/workspace-current-state.md`
- Modify: `docs/superpowers/plans/2026-06-10-native-harness-standalone-next-pass.md`

- [x] **Step 1: Update external gap matrix**

Record that `output_ref_reuse` closes the structural observability gap for expensive sandbox output recovery:

```markdown
The optional `output_ref_reuse` research-task surface now fails when recoverable `/workspace/tmp/tasks/.harness/outputs/**` refs exist but no member reads them through `sandbox.read_output_ref`. This gives real SCI workflows a deterministic gate for "inspect prior expensive output before rerunning" without exposing hidden refs to list/search/artifact discovery.
```

- [x] **Step 2: Update convergence audit**

Add a dated entry with the exact commands and results from Tasks 1-3:

```markdown
- 2026-06-10 output-ref reuse eval slice:
  - `backend`: `.venv/bin/python -m pytest tests/agents/harness/test_research_task_eval.py ...` -> passed
  - `backend`: `.venv/bin/python -m pytest tests/integration/test_harness_mock_sandbox_e2e.py ...` -> passed
  - `backend`: full native harness gate -> passed
  - drift scan and `git diff --check` -> passed
```

- [x] **Step 3: Update release gate checklist**

Ensure the native harness gate command includes:

```text
tests/sandbox/test_docker_provider.py
tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py
tests/integration/test_harness_mock_sandbox_e2e.py
```

Also mention that `research_task_eval` now includes the optional `output_ref_reuse` surface.

- [x] **Step 4: Mark this plan's completed steps**

Change completed checkboxes from `[ ]` to `[x]` only after the corresponding command passed.

---

### Task 5: Review With Code Graph, Commit, and Decide Next Slice

**Files:**
- No expected implementation changes unless review finds a concrete bug.

- [x] **Step 1: Rebuild/update code-review graph**

Use code-review-graph for the changed files:

```text
repo_root=/Users/ze/wenjin
changed_files=[
  "backend/src/agents/harness/research_task_eval.py",
  "backend/tests/agents/harness/test_research_task_eval.py",
  "backend/tests/integration/test_harness_mock_sandbox_e2e.py",
  "docs/current/native-harness-external-gap-matrix.md",
  "docs/current/native-harness-convergence-audit.md",
  "docs/current/release-gate-checklist.md"
]
```

Expected review focus:

- no runtime dependency drift;
- no hidden path leakage;
- no duplicate quality surface with `workflow_trace`;
- E2E uses the real companion tool path, not a fake shortcut;
- docs match verified behavior.

- [x] **Step 2: Fix only concrete review findings**

Acceptable fixes:

- minor schema/evidence naming cleanup;
- bounded evidence shape correction;
- missing test assertion;
- documentation mismatch.

Unacceptable fixes in this pass:

- adding new runtime services;
- adding frontend debug surfaces;
- widening sandbox permissions;
- adding compatibility fallbacks.

- [x] **Step 3: Commit the slice**

Run:

```bash
git add \
  backend/src/agents/harness/research_task_eval.py \
  backend/tests/agents/harness/test_research_task_eval.py \
  backend/tests/integration/test_harness_mock_sandbox_e2e.py \
  docs/current/native-harness-external-gap-matrix.md \
  docs/current/native-harness-convergence-audit.md \
  docs/current/release-gate-checklist.md \
  docs/current/architecture.md \
  docs/current/workspace-current-state.md \
  docs/superpowers/plans/2026-06-10-native-harness-standalone-next-pass.md
git commit -m "feat: evaluate sandbox output-ref reuse"
```

Before staging, run:

```bash
git status --short
```

Expected: only intended files are staged/committed.

- [x] **Step 4: Decide the next harness slice from evidence**

After commit, choose exactly one next slice based on test/review evidence:

1. If E2E still shows repeated sandbox work despite available refs, tune team/member prompts and capability guidance to prefer `sandbox.read_output_ref` before rerun.
2. If context is sufficient but output quality is weak, add a deterministic reviewer-facing academic style/content-quality surface.
3. If real sandbox filesystem behavior is still confusing, harden `workspace_layout.py` docs/manifests and agent-visible `operation_policy`.
4. If all harness backend gates are stable, stop backend work and run browser/product smoke on the real workflow UI.

Selected next slice: run a real or realistic SCI workflow smoke with `workflow_trace` and optional `output_ref_reuse` required, then tune member prompt/tool guidance only from observed failures. This follows the current evidence: mock E2E is now closed, while real-task behavior remains the next unproven layer.

Do not start more than one next slice without a new short plan.

---

## Completion Criteria

- `output_ref_reuse` exists as an optional deterministic research eval surface.
- Unit tests prove pass/fail behavior and safe ref filtering.
- Mock SCI E2E proves real companion tool reuse: `sandbox.run_python` -> output ref -> `sandbox.read_output_ref` -> transcript -> eval evidence.
- Full native harness gate passes.
- Ruff, drift scan, and `git diff --check` pass.
- Current docs match verified behavior.
- The final commit contains no Codex SDK, cc-switch, deer-flow runtime, generic shell, hidden ref exposure, or compatibility layer.
- Next work is chosen from evidence, not from broad architectural speculation.
