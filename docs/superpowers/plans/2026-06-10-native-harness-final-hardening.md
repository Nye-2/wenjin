# Native Harness Final Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the current Wenjin native harness hardening pass so sandbox execution evidence, workspace filesystem contracts, replan signals, and external-project learnings converge into one stable Wenjin-native architecture.

**Architecture:** Keep the single execution chain `ChatAgent -> LeadAgent -> TeamKernel/static graph -> ReactSubagent -> Wenjin Harness -> DataService/Sandbox/Review`. Borrow only mechanisms from Codex and deer-flow: structured tool evidence, explicit safety policy, bounded execution transcript, and plan/replan discipline. Do not migrate their runtimes, provider adapters, workspace roots, or frontend streams.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Pydantic v2, LangGraph, pytest, Ruff, existing DataService sandbox domain, existing Wenjin harness tools.

---

## Current State

Current branch:

```bash
git status --short --branch
```

Expected:

```text
## codex/wenjin-native-harness
```

Recent completed commits:

- `40314164 feat: record sandbox task contract`
- `f55c5fd7 feat: define task workspace contract`
- `cfb3d683 feat: surface recoverable sandbox outputs`

The next pass must stay narrow. The known concrete issue is that `build_sandbox_execution_summary_from_tool_calls()` can count the same generated artifact twice when a sandbox tool record carries `generated_artifacts` both at the top level and under `metadata`, which happens naturally after adapter metadata extraction.

## Non-Negotiable Boundaries

Do this:

- Keep `backend/src/sandbox/workspace_layout.py` as the only `/workspace` filesystem source of truth.
- Keep `backend/src/agents/harness/diff_tracker.py` as the harness metadata summarizer.
- Keep TeamKernel replan as a bounded quality-gate signal, not as a second scheduler.
- Keep all sandbox execution evidence bounded, path-safe, and recoverable through output refs.
- Prefer small tests and small commits.

Do not do this:

- Do not reintroduce Codex SDK, cc-switch, Kimi/MiMo protocol bridges, or provider conversion code.
- Do not import or wrap deer-flow runtime/factory/run store.
- Do not add ACP workspace, `/mnt/user-data`, or another workspace root.
- Do not add generic `sandbox.run_command`.
- Do not create a second execution/run table or a second frontend stream/store.
- Do not add compatibility/fallback layers for old harness behavior.

## File Structure

- Modify `backend/src/agents/harness/diff_tracker.py`: dedupe generated artifact paths, keep sandbox summaries bounded, preserve replan signal schema.
- Modify `backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py`: regression tests for artifact dedupe and summary shape.
- Modify `backend/tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py`: regression tests for replan signal dedupe/loop semantics if current audit reveals a gap.
- Modify `backend/src/agents/lead_agent/v2/team/kernel.py`: only if `_sync_harness_replan_signals()` needs key semantics tightened.
- Modify `backend/src/agents/lead_agent/v2/team/quality_gates.py`: only if replan quality gates suggest repeated work beyond signal limits.
- Modify `backend/src/agents/harness/context_assembly.py`: only if final audit finds missing bounded context projection for the already-added task contract/output-ref recovery.
- Modify `docs/current/architecture.md`: document final native harness source-of-truth boundaries.
- Modify `docs/current/workspace-current-state.md`: document sandbox task contract metadata and agent-safe projection.
- Modify `docs/current/native-harness-external-gap-matrix.md`: record final Codex/deer-flow borrow list and remaining intentional gaps.
- Modify `docs/current/native-harness-convergence-audit.md`: record verification results.
- Modify `docs/current/release-gate-checklist.md`: keep the release gate aligned with the final test set.

---

### Task 1: Deduplicate Reviewable Generated Artifact Counts

**Files:**
- Modify: `backend/src/agents/harness/diff_tracker.py`
- Test: `backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py`

- [x] **Step 1: Write the failing regression test**

Add this test near `test_harness_node_metadata_includes_sandbox_execution_summary` in `backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py`:

```python
def test_sandbox_execution_summary_dedupes_generated_artifacts_across_record_and_metadata() -> None:
    metadata = build_harness_node_metadata_from_tool_calls(
        [
            {
                "name": "sandbox.run_python",
                "status": "completed",
                "generated_artifacts": [
                    {"path": "/workspace/outputs/result.json"},
                    {"path": "/workspace/reports/analysis.md"},
                ],
                "metadata": {
                    "generated_artifacts": [
                        {"path": "/workspace/outputs/result.json"},
                        {"path": "/workspace/reports/analysis.md"},
                        {"path": "/workspace/tmp/tasks/.harness/outputs/exec/node/internal.txt"},
                        {"path": "/workspace/.env"},
                    ]
                },
            }
        ]
    )

    summary = metadata["harness"]["sandbox_execution_summary"]
    assert summary["generated_artifact_count"] == 2
```

- [x] **Step 2: Run the focused RED test**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py::test_sandbox_execution_summary_dedupes_generated_artifacts_across_record_and_metadata -q
```

Expected before the fix:

```text
FAILED
```

The failure should show `generated_artifact_count` is `4` instead of `2`.

- [x] **Step 3: Implement path-level dedupe in the sandbox execution summary**

In `backend/src/agents/harness/diff_tracker.py`, replace the integer-only count accumulation with a list of unique reviewable artifact paths.

Use this helper:

```python
def _append_reviewable_artifact_paths(result: list[str], artifacts: Any) -> None:
    for artifact in _list_of_dicts(artifacts):
        path = str(artifact.get("path") or "").strip()
        if not path or not is_user_reviewable_workspace_artifact_path(path):
            continue
        _append_unique(result, path)
```

Then inside `build_sandbox_execution_summary_from_tool_calls()`:

```python
generated_artifact_paths: list[str] = []
```

Replace both existing count increments:

```python
generated_artifact_count += _reviewable_artifact_count(tool_call.get("generated_artifacts"))
generated_artifact_count += _reviewable_artifact_count(metadata.get("generated_artifacts"))
```

with:

```python
_append_reviewable_artifact_paths(generated_artifact_paths, tool_call.get("generated_artifacts"))
_append_reviewable_artifact_paths(generated_artifact_paths, metadata.get("generated_artifacts"))
```

And set the result field:

```python
"generated_artifact_count": len(generated_artifact_paths),
```

Keep the existing `_reviewable_artifact_count()` helper because other summaries may still use it.

- [x] **Step 4: Run GREEN verification**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py -q
```

Expected: all selected tests pass.

- [x] **Step 5: Run targeted style check**

Run:

```bash
cd backend && .venv/bin/ruff check src/agents/harness/diff_tracker.py tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py
```

Expected: Ruff passes.

- [x] **Step 6: Commit**

Run:

```bash
git add backend/src/agents/harness/diff_tracker.py backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py docs/superpowers/plans/2026-06-10-native-harness-final-hardening.md
git commit -m "fix: dedupe sandbox generated artifact summary"
```

---

### Task 2: Freeze Replan Signal Loop Semantics

**Files:**
- Test: `backend/tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py`
- Modify if needed: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Modify if needed: `backend/src/agents/lead_agent/v2/team/quality_gates.py`

- [x] **Step 1: Add a regression test for duplicate signals from the same invocation**

Add this test to `backend/tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py`:

```python
def test_harness_node_metadata_dedupes_replan_signals_from_duplicate_failures() -> None:
    metadata = build_harness_node_metadata_from_tool_calls(
        [
            _run_python_tool_call("python_exit_nonzero"),
            _run_python_tool_call("python_exit_nonzero"),
        ]
    )

    signals = metadata["harness"]["replan_signals"]
    assert len(signals) == 1
    assert signals[0]["failure_codes"] == ["python_exit_nonzero"]
    assert signals[0]["max_extra_iterations"] == 1
```

- [x] **Step 2: Run the focused test**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py::test_harness_node_metadata_dedupes_replan_signals_from_duplicate_failures -q
```

Expected: pass if existing `_dedupe_replan_signals()` is sufficient. If it fails, fix `backend/src/agents/harness/diff_tracker.py` by preserving the first signal for each `_replan_signal_key()`.

- [x] **Step 3: Add a regression test that queue timeout does not suggest extra work**

Add this pure metadata test:

```python
def test_harness_node_metadata_marks_queue_timeout_non_iterative() -> None:
    metadata = build_harness_node_metadata_from_tool_calls(
        [_run_python_tool_call("sandbox_queue_timeout")]
    )

    signal = metadata["harness"]["replan_signals"][0]
    assert signal["recommended_action"] == "wait_or_stop"
    assert signal["max_extra_iterations"] == 0
```

- [x] **Step 4: Run the full replan test file**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py -q
```

Expected: all selected tests pass. The runtime tests must continue to show:

- `python_exit_nonzero` revises the code agent once.
- `tool_input_validation` revises the same agent once.
- `sandbox_queue_timeout` stops with warning.
- `tool_forbidden` stops with warning.

- [x] **Step 5: Commit only if code or tests changed**

Run:

```bash
git add backend/tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py backend/src/agents/harness/diff_tracker.py backend/src/agents/lead_agent/v2/team/kernel.py backend/src/agents/lead_agent/v2/team/quality_gates.py docs/superpowers/plans/2026-06-10-native-harness-final-hardening.md
git commit -m "test: freeze harness replan loop semantics"
```

If only the plan file is changed because existing tests already cover the behavior, skip this commit and include the result in the final review note.

---

### Task 3: Update Current Docs To Match the Converged Runtime

**Files:**
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/workspace-current-state.md`
- Modify: `docs/current/native-harness-external-gap-matrix.md`
- Modify: `docs/current/native-harness-convergence-audit.md`
- Modify: `docs/current/release-gate-checklist.md`

- [x] **Step 1: Update the architecture source of truth**

Ensure `docs/current/architecture.md` states:

```markdown
- Native harness sandbox execution is Wenjin-owned. The supported chain is ChatAgent -> LeadAgent -> TeamKernel/static graph -> ReactSubagent -> Wenjin Harness -> DataService/Sandbox/Review.
- `/workspace` path semantics are centralized in `backend/src/sandbox/workspace_layout.py`.
- Agent-visible task contracts come from `build_agent_workspace_task_contract()`.
- Internal output refs stay under `/workspace/tmp/tasks/.harness/outputs` and are recoverable only through explicit output-ref tools.
- Codex and deer-flow are reference projects only; their runtimes, protocol bridges, workspace roots, and stream stores are not part of Wenjin.
```

- [x] **Step 2: Update workspace current behavior**

Ensure `docs/current/workspace-current-state.md` includes:

```markdown
- Sandbox job metadata records the same agent-safe task contract used in harness context.
- Agent context exposes `sandbox.task_contract` without raw `output_ref_root`.
- Full task-contract internals remain in `workspace_layout.py` and runtime code, not in model-facing prompts.
```

- [x] **Step 3: Update the external gap matrix**

Ensure `docs/current/native-harness-external-gap-matrix.md` has this final decision table:

```markdown
| External pattern | Bring into Wenjin | Do not bring |
| --- | --- | --- |
| Codex structured tool evidence | Bounded harness tool-call metadata, file diffs, output refs, command audits | Codex SDK runtime, provider bridge, generic terminal agent |
| Codex sandbox/file discipline | Explicit path policy and protected/internal path masking | `/mnt/user-data` or ACP workspace root |
| deer-flow planner/reporter discipline | TeamKernel quality gates, replan signals, final report checks | deer-flow graph runtime, message bus, run store |
| deer-flow regression density | Small deterministic tests for path, truncation, tool evidence, and replan semantics | Broad compatibility layer |
```

- [x] **Step 4: Update release gate**

Ensure `docs/current/release-gate-checklist.md` includes the final native harness gate command from Task 4.

- [x] **Step 5: Commit docs**

Run:

```bash
git add docs/current/architecture.md docs/current/workspace-current-state.md docs/current/native-harness-external-gap-matrix.md docs/current/native-harness-convergence-audit.md docs/current/release-gate-checklist.md docs/superpowers/plans/2026-06-10-native-harness-final-hardening.md
git commit -m "docs: record native harness final boundaries"
```

---

### Task 4: Final Verification Gate

**Files:**
- No expected code changes.

- [x] **Step 1: Run focused harness and sandbox tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py \
  tests/agents/harness/test_context_assembly.py \
  tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py \
  tests/agents/lead_agent/v2/test_sandbox_runtime.py \
  tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py \
  tests/sandbox/test_workspace_layout.py \
  tests/integration/test_harness_mock_sandbox_e2e.py -q
```

Expected: all selected tests pass.

- [x] **Step 2: Run backend architecture drift scan**

Run:

```bash
rg -n "from .*codex|import .*codex|cc-switch|ccswitch|deerflow|deer-flow|sandbox\\.run_command|/mnt/user-data" backend/src/agents/harness backend/src/agents/lead_agent/v2 backend/src/subagents/v2 -g '*.py'
```

Expected: no output and exit code `1`.

- [x] **Step 3: Run Ruff**

Run:

```bash
cd backend && .venv/bin/ruff check \
  src/agents/harness/diff_tracker.py \
  src/agents/harness/context_assembly.py \
  src/agents/lead_agent/v2/team/kernel.py \
  src/agents/lead_agent/v2/team/quality_gates.py \
  tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py \
  tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py
```

Expected: Ruff passes.

- [x] **Step 4: Run full native harness gate**

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
  tests/agents/lead_agent/v2/test_sandbox_runtime.py \
  tests/agents/lead_agent/v2/test_workspace_sandbox_manager.py \
  tests/agents/lead_agent/v2/test_runtime.py::test_run_session_prism_review_items_satisfy_writing_evidence_eval \
  tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py \
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

Expected: all selected tests pass.

- [x] **Step 5: Run whitespace diff check**

Run:

```bash
git diff --check
```

Expected: no output.

- [x] **Step 6: Final commit if verification documentation changed**

Run:

```bash
git add docs/current/native-harness-convergence-audit.md docs/current/release-gate-checklist.md docs/superpowers/plans/2026-06-10-native-harness-final-hardening.md
git commit -m "docs: close native harness hardening verification"
```

Skip this commit if no files changed.

---

## Final Review Criteria

The pass is complete only when all are true:

- `build_sandbox_execution_summary_from_tool_calls()` does not double-count the same reviewable artifact path.
- Replan signals remain bounded and do not create an open-ended loop.
- Agent-facing context exposes enough sandbox/task information to use the workspace, but not internal roots or protected paths.
- Docs say Codex and deer-flow are reference projects, not runtime dependencies.
- Drift scan has no Codex SDK, cc-switch, deer-flow runtime, `/mnt/user-data`, or `sandbox.run_command` hits in native harness production paths.
- Full native harness gate passes.
- Every code change is covered by a focused test.

## Execution Order

1. Task 1 first because it fixes a concrete bug with low blast radius.
2. Task 2 second because it confirms dynamic replan remains bounded.
3. Task 3 third because docs should reflect verified behavior, not intended behavior.
4. Task 4 last because it is the release gate.
