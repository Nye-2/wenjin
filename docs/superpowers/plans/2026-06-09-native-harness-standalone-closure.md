# Native Harness Standalone Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Wenjin's native harness into a stable research/workspace execution layer that can run experiments, manage sandbox files, recover bounded evidence, and evaluate output quality without Codex SDK, cc-switch, deer-flow runtime, or a second execution system.

**Architecture:** Keep one source-of-truth chain: `ChatAgent -> LeadAgent -> TeamKernel/static graph -> ReactSubagent -> Wenjin Harness -> DataService/Sandbox/Review`. External projects are used only as pattern references; all migrated behavior must collapse into existing Wenjin DataService, sandbox layout, harness metadata, research-task eval, release gate, and frontend execution projection. No compatibility layer, fallback runtime, generic shell, second run table, second frontend store, or provider protocol bridge is allowed.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Pydantic v2, LangGraph, existing Wenjin sandbox providers, pytest, Ruff, Next.js 16, React 19, TypeScript, Vitest.

---

## Scope Boundary

Implement in this closure plan:

- Close and commit the current `experiment_interpretation` outcome-quality slice.
- Tune native harness behavior against a real or realistic SCI sandbox workflow.
- Add the remaining deterministic outcome-quality surfaces that improve research output quality:
  - paper relevance
  - statistical / robustness sufficiency
  - Prism semantic preservation
- Keep agent-facing evidence compact and recoverable through existing harness context and output refs.
- Add user-facing projection only for evidence that helps users understand progress or trust output.
- Update current docs and release gates so future work cannot regress into a parallel runtime.

Do not implement in this closure plan:

- No Codex SDK integration.
- No cc-switch or provider protocol conversion.
- No deer-flow agent factory, runtime journal table, ACP workspace, or `/mnt/user-data` alias.
- No generic `sandbox.run_command`.
- No direct room commits outside curated result-card / review flow.
- No frontend debug payload viewer for raw tool calls.

## File Structure

- `backend/src/agents/harness/diff_tracker.py`: converts tool-call evidence into bounded harness node metadata summaries.
- `backend/src/agents/harness/context_assembly.py`: injects compact harness evidence into subagent context.
- `backend/src/agents/harness/research_task_eval.py`: deterministic research-output quality checks.
- `backend/src/agents/harness/sandbox_tools.py`: bounded file/output-ref tools and internal path protection.
- `backend/src/agents/harness/output_budget.py`: head/tail output externalization.
- `backend/src/agents/harness/tool_names.py`: canonical tool names and companion tool expansion.
- `backend/src/agents/lead_agent/v2/team/quality_gates.py`: TeamKernel quality-gate evidence source.
- `backend/src/agents/lead_agent/v2/team/citation_source_audit.py`: citation/source audit normalization.
- `backend/src/agents/lead_agent/v2/sandbox_runtime.py`: sandbox runtime facade.
- `backend/src/agents/lead_agent/v2/sandbox_job_runner.py`: sandbox job orchestration only.
- `backend/src/agents/lead_agent/v2/sandbox_artifact_discovery.py`: reviewable artifact discovery.
- `backend/src/sandbox/workspace_layout.py`: canonical `/workspace` layout and path classes.
- `frontend/lib/execution-run-view.ts`: user-facing execution/team projection.
- `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`: team and progress UI.
- `backend/tests/agents/harness/test_research_task_eval.py`: outcome-quality tests.
- `backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py`: metadata summary tests.
- `backend/tests/agents/harness/test_context_assembly.py`: bounded context projection tests.
- `backend/tests/integration/test_harness_mock_sandbox_e2e.py`: realistic harness/team flow.
- `backend/tests/architecture/test_native_harness_boundaries.py`: no-drift architecture checks.
- `docs/current/architecture.md`: source-of-truth architecture.
- `docs/current/workspace-current-state.md`: workspace/sandbox/current behavior.
- `docs/current/native-harness-external-gap-matrix.md`: external reference decisions and remaining gaps.
- `docs/current/native-harness-convergence-audit.md`: implementation audit trail.
- `docs/current/release-gate-checklist.md`: release verification contract.

---

### Task 0: Close Current Experiment Interpretation Slice

**Files:**
- Modify: `backend/src/agents/harness/diff_tracker.py`
- Modify: `backend/src/agents/harness/context_assembly.py`
- Modify: `backend/src/agents/harness/research_task_eval.py`
- Modify: `backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py`
- Modify: `backend/tests/agents/harness/test_context_assembly.py`
- Modify: `backend/tests/agents/harness/test_research_task_eval.py`
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/native-harness-convergence-audit.md`
- Modify: `docs/current/native-harness-external-gap-matrix.md`
- Modify: `docs/current/release-gate-checklist.md`
- Modify: `docs/current/workspace-current-state.md`

- [ ] **Step 1: Review the current code diff**

Run:

```bash
git diff --stat
git diff -- backend/src/agents/harness/diff_tracker.py backend/src/agents/harness/context_assembly.py backend/src/agents/harness/research_task_eval.py
```

Expected:

- `diff_tracker.py` only adds bounded `experiment_interpretation_summary` metadata and safe path filtering.
- `context_assembly.py` only exposes the new summary in existing harness context.
- `research_task_eval.py` only adds the optional `experiment_interpretation` surface.

- [ ] **Step 2: Run focused tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py \
  tests/agents/harness/test_context_assembly.py \
  tests/agents/harness/test_research_task_eval.py -q
```

Expected:

```text
35 passed
```

- [ ] **Step 3: Run the native harness regression gate**

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

Expected:

```text
304 passed
```

- [ ] **Step 4: Run style and drift checks**

Run:

```bash
cd backend && .venv/bin/ruff check \
  src/agents/harness/diff_tracker.py \
  src/agents/harness/context_assembly.py \
  src/agents/harness/research_task_eval.py \
  tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py \
  tests/agents/harness/test_context_assembly.py \
  tests/agents/harness/test_research_task_eval.py
```

Run:

```bash
git diff --check
rg -n "from .*codex|import .*codex|cc-switch|ccswitch|deerflow|deer-flow|sandbox.run_command|/mnt/user-data" \
  backend/src/agents/harness backend/src/agents/lead_agent/v2 backend/src/subagents/v2 -g '*.py'
```

Expected:

- Ruff passes.
- `git diff --check` has no output.
- Drift scan has no production-code hits.

- [ ] **Step 5: Commit the slice**

Run:

```bash
git add backend/src/agents/harness/diff_tracker.py \
  backend/src/agents/harness/context_assembly.py \
  backend/src/agents/harness/research_task_eval.py \
  backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py \
  backend/tests/agents/harness/test_context_assembly.py \
  backend/tests/agents/harness/test_research_task_eval.py \
  docs/current/architecture.md \
  docs/current/native-harness-convergence-audit.md \
  docs/current/native-harness-external-gap-matrix.md \
  docs/current/release-gate-checklist.md \
  docs/current/workspace-current-state.md \
  docs/superpowers/plans/2026-06-09-native-harness-standalone-closure.md
git commit -m "feat: add experiment interpretation research eval"
```

Expected: commit succeeds with no unrelated files staged.

---

### Task 1: Tune Harness on a Realistic SCI Sandbox Workflow

**Files:**
- Modify: `backend/tests/integration/test_harness_mock_sandbox_e2e.py`
- Modify if needed: `backend/src/agents/harness/context_assembly.py`
- Modify if needed: `backend/src/agents/harness/sandbox_tools.py`
- Modify if needed: `backend/src/agents/harness/tool_names.py`
- Modify: `docs/current/native-harness-convergence-audit.md`

- [ ] **Step 1: Add or extend an integration test where later members must consume prior evidence**

Add a test scenario to `backend/tests/integration/test_harness_mock_sandbox_e2e.py` with three member phases:

1. a literature/data member writes a dataset or evidence file under `/workspace/datasets` and produces a bounded output ref;
2. an experiment member runs Python from `task_scratch_path`, writes `/workspace/outputs/result.json`, and externalizes large stdout;
3. a synthesis member uses `scratch_refs`, `reproducibility_summary`, and `experiment_interpretation_summary` instead of rerunning the experiment.

Expected assertions:

```python
assert "/workspace/tmp/tasks/" in harness_context["task_scratch_path"]
assert harness_context["scratch_refs"]
assert harness_context["reproducibility_summary"]["script_count"] >= 1
assert harness_context["experiment_interpretation_summary"]["interpretation_count"] >= 1
assert "sandbox.read_output_ref" in available_tool_names
```

- [ ] **Step 2: Run the new test and verify it fails for a real gap**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/integration/test_harness_mock_sandbox_e2e.py -q
```

Expected before implementation: failure should identify a missing or weak projection, not an unrelated fixture error.

- [ ] **Step 3: Fix only the missing projection or guidance**

Allowed fixes:

- add bounded context fields already produced by harness metadata;
- add canonical tool companion expansion through `tool_names.py`;
- tighten safe scratch/output-ref projection;
- improve agent-facing context labels so a synthesis member sees the correct evidence.

Disallowed fixes:

- create a new run store;
- add a second frontend stream;
- add a generic shell;
- make hidden internal paths listable/searchable.

- [ ] **Step 4: Run focused integration and harness tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/integration/test_harness_mock_sandbox_e2e.py \
  tests/agents/harness/test_context_assembly.py \
  tests/agents/harness/test_sandbox_file_tools.py \
  tests/unit/subagents/test_react.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Record what changed**

Update `docs/current/native-harness-convergence-audit.md` with:

- what the realistic workflow proved;
- whether agents used output refs instead of rerunning;
- any remaining prompt/tool behavior risk.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/tests/integration/test_harness_mock_sandbox_e2e.py \
  backend/src/agents/harness/context_assembly.py \
  backend/src/agents/harness/sandbox_tools.py \
  backend/src/agents/harness/tool_names.py \
  docs/current/native-harness-convergence-audit.md
git commit -m "test: tune native harness on sci workflow evidence"
```

Expected: commit contains only files actually touched.

---

### Task 2: Add Paper Relevance Outcome-Quality Surface

**Files:**
- Modify: `backend/src/agents/harness/research_task_eval.py`
- Modify: `backend/tests/agents/harness/test_research_task_eval.py`
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/native-harness-external-gap-matrix.md`
- Modify: `docs/current/release-gate-checklist.md`

- [ ] **Step 1: Add failing tests**

Add tests requiring `paper_relevance` to pass only when cited papers are aligned with the task topic or claim:

```python
def test_research_task_eval_passes_paper_relevance_with_topic_aligned_sources() -> None:
    evaluation = evaluate_research_task_evidence(
        _report(),
        node_events=[
            {
                "node_metadata": {
                    "harness": {
                        "paper_relevance_summary": {
                            "schema": "wenjin.harness.paper_relevance_summary.v1",
                            "aligned_count": 2,
                            "weak_count": 0,
                            "off_topic_count": 0,
                            "aligned_refs": [
                                {"source_id": "s1", "citation_key": "smith2026", "reason": "directly studies federated LLM fine-tuning"},
                                {"source_id": "s2", "citation_key": "lee2025", "reason": "reports privacy-preserving LLM training benchmark"},
                            ],
                        }
                    }
                }
            }
        ],
        required_surfaces=("paper_relevance",),
    )

    assert evaluation.status == "pass"
    assert evaluation.coverage == {"paper_relevance": "pass"}
```

Add a failing test where `off_topic_count > 0` and `aligned_count == 0`.

- [ ] **Step 2: Run the tests and confirm RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_research_task_eval.py -q
```

Expected: failure on missing `paper_relevance` surface or missing evidence extractor.

- [ ] **Step 3: Implement deterministic evaluator**

Update `ResearchSurface` to include `paper_relevance`.

Implement helper logic with these pass criteria:

- `aligned_count >= 1`;
- `off_topic_count == 0`;
- each aligned ref has `source_id` or `citation_key`;
- weak refs do not fail by themselves if at least one aligned ref exists and no off-topic refs exist;
- evidence payload reports `aligned_count`, `weak_count`, `off_topic_count`, and bounded `aligned_refs`.

- [ ] **Step 4: Run focused tests and Ruff**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_research_task_eval.py -q
cd backend && .venv/bin/ruff check src/agents/harness/research_task_eval.py tests/agents/harness/test_research_task_eval.py
```

Expected: tests and Ruff pass.

- [ ] **Step 5: Update docs**

Update:

- `docs/current/architecture.md`: document `paper_relevance` as deterministic metadata eval.
- `docs/current/native-harness-external-gap-matrix.md`: remove paper relevance from remaining gap list.
- `docs/current/release-gate-checklist.md`: include the new surface in focused gate expectations.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/src/agents/harness/research_task_eval.py \
  backend/tests/agents/harness/test_research_task_eval.py \
  docs/current/architecture.md \
  docs/current/native-harness-external-gap-matrix.md \
  docs/current/release-gate-checklist.md
git commit -m "feat: add paper relevance research eval"
```

Expected: commit succeeds.

---

### Task 3: Add Statistical and Robustness Sufficiency Surface

**Files:**
- Modify: `backend/src/agents/harness/diff_tracker.py`
- Modify: `backend/src/agents/harness/context_assembly.py`
- Modify: `backend/src/agents/harness/research_task_eval.py`
- Modify: `backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py`
- Modify: `backend/tests/agents/harness/test_context_assembly.py`
- Modify: `backend/tests/agents/harness/test_research_task_eval.py`
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/native-harness-external-gap-matrix.md`
- Modify: `docs/current/release-gate-checklist.md`

- [ ] **Step 1: Add summary extraction tests**

Add diff-tracker tests where a tool call contains:

```python
"statistical_check": {
    "method": "difference-in-differences",
    "sample_size": 1250,
    "metric_names": ["accuracy", "f1"],
    "robustness_checks": [
        {"name": "seed_sensitivity", "status": "passed"},
        {"name": "ablation_without_privacy_adapter", "status": "passed"},
    ],
    "limitations": ["single public benchmark"],
    "artifact_paths": ["/workspace/outputs/robustness.json"],
    "dataset_paths": ["/workspace/datasets/panel.csv"],
}
```

Expected summary:

```python
{
    "schema": "wenjin.harness.statistical_robustness_summary.v1",
    "check_count": 1,
    "method_count": 1,
    "metric_names": ["accuracy", "f1"],
    "robustness_check_count": 2,
    "passed_robustness_check_count": 2,
    "limitation_count": 1,
    "artifact_paths": ["/workspace/outputs/robustness.json"],
    "dataset_paths": ["/workspace/datasets/panel.csv"],
}
```

- [ ] **Step 2: Run summary tests and confirm RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py -q
```

Expected: missing `statistical_robustness_summary`.

- [ ] **Step 3: Implement bounded summary extraction**

Add `build_statistical_robustness_summary_from_tool_calls()` in `diff_tracker.py`.

Requirements:

- accept `statistical_check` from tool-call root or metadata;
- compact method text;
- dedupe metric names while preserving order;
- count robustness checks and passed robustness checks;
- copy only safe `/workspace/outputs/**`, `/workspace/reports/**`, `/workspace/datasets/**` paths;
- filter `/workspace/tmp/tasks/.harness/**`, `.env`, `.git`, `.wenjin`, `.pem`, `.key`, and traversal paths.

- [ ] **Step 4: Project summary into context**

Add `statistical_robustness_summary` to:

- top-level context bundle;
- `_harness_summary()` preserved keys;
- `_fit_budget()` droppable latest summaries.

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_context_assembly.py -q
```

Expected: all context tests pass.

- [ ] **Step 5: Add evaluator**

Add `statistical_robustness` to `ResearchSurface`.

Pass criteria:

- at least one method;
- at least one metric;
- `sample_size` or equivalent sample/observation count exists when available in summary;
- at least one robustness check;
- no failed critical robustness checks;
- at least one limitation;
- at least one artifact and dataset path;
- artifact/dataset paths align with `reproducibility_summary`.

- [ ] **Step 6: Run focused tests, Ruff, and commit**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py \
  tests/agents/harness/test_context_assembly.py \
  tests/agents/harness/test_research_task_eval.py -q
cd backend && .venv/bin/ruff check \
  src/agents/harness/diff_tracker.py \
  src/agents/harness/context_assembly.py \
  src/agents/harness/research_task_eval.py \
  tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py \
  tests/agents/harness/test_context_assembly.py \
  tests/agents/harness/test_research_task_eval.py
```

Expected: tests and Ruff pass.

Run:

```bash
git add backend/src/agents/harness/diff_tracker.py \
  backend/src/agents/harness/context_assembly.py \
  backend/src/agents/harness/research_task_eval.py \
  backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py \
  backend/tests/agents/harness/test_context_assembly.py \
  backend/tests/agents/harness/test_research_task_eval.py \
  docs/current/architecture.md \
  docs/current/native-harness-external-gap-matrix.md \
  docs/current/release-gate-checklist.md
git commit -m "feat: add statistical robustness research eval"
```

Expected: commit succeeds.

---

### Task 4: Add Prism Semantic Preservation Surface

**Files:**
- Modify: `backend/src/services/prism_review_projection.py`
- Modify: `backend/src/agents/harness/research_task_eval.py`
- Modify: `backend/tests/services/test_prism_review_projection.py`
- Modify: `backend/tests/agents/harness/test_research_task_eval.py`
- Modify if needed: `frontend/lib/execution-run-view.ts`
- Modify if needed: `frontend/tests/unit/lib/execution-run-view.test.ts`
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/native-harness-external-gap-matrix.md`
- Modify: `docs/current/release-gate-checklist.md`

- [ ] **Step 1: Add projection tests**

In `backend/tests/services/test_prism_review_projection.py`, assert each Prism review item includes a bounded semantic contract:

```python
assert item["preview"]["semantic_contract"] == {
    "target_path": "main.tex",
    "preserves_claims": True,
    "preserves_citations": True,
    "preserves_equations": True,
    "preserves_tables": True,
    "risk": "low",
}
```

For incomplete or risky edits, assert `risk` is `medium` or `high` and missing preservation flags are explicit.

- [ ] **Step 2: Add research eval tests**

Add passing/failing tests for `writing_semantic_preservation`.

Pass criteria:

- all main-text edits have `preserves_claims=True`;
- citation-bearing files have `preserves_citations=True`;
- equation/table-bearing files have the corresponding preservation flag;
- no item has `risk="high"`;
- each review item still has the existing LaTeX content contract.

- [ ] **Step 3: Run tests and confirm RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/services/test_prism_review_projection.py \
  tests/agents/harness/test_research_task_eval.py -q
```

Expected: missing `semantic_contract` or missing `writing_semantic_preservation`.

- [ ] **Step 4: Implement projection and evaluator**

Implementation boundary:

- derive flags from existing Prism preview/content-contract metadata where available;
- do not call a model judge inside the evaluator;
- do not inspect full user documents outside bounded Prism service contracts;
- keep `preview.semantic_contract` small and stable.

- [ ] **Step 5: Run backend and frontend focused tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/services/test_prism_review_projection.py \
  tests/agents/harness/test_research_task_eval.py \
  tests/services/test_workspace_prism_service.py::test_surface_projection_includes_review_provenance_and_protection -q
cd frontend && npm run typecheck
cd frontend && npx vitest run tests/unit/lib/execution-run-view.test.ts
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/src/services/prism_review_projection.py \
  backend/src/agents/harness/research_task_eval.py \
  backend/tests/services/test_prism_review_projection.py \
  backend/tests/agents/harness/test_research_task_eval.py \
  frontend/lib/execution-run-view.ts \
  frontend/tests/unit/lib/execution-run-view.test.ts \
  docs/current/architecture.md \
  docs/current/native-harness-external-gap-matrix.md \
  docs/current/release-gate-checklist.md
git commit -m "feat: add prism semantic preservation eval"
```

Expected: commit contains only files actually touched.

---

### Task 5: Improve User-Facing Quality Projection Without Debug Payload

**Files:**
- Modify: `frontend/lib/execution-run-view.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- Modify: `frontend/tests/unit/lib/execution-run-view.test.ts`
- Modify if needed: `frontend/tests/unit/v2/LiveWorkflowPanel.test.tsx`
- Modify: `docs/current/workspace-current-state.md`

- [ ] **Step 1: Add projection tests**

Add tests that convert backend quality findings into concise UI labels:

```ts
expect(view.qualityHighlights).toEqual([
  { label: "引用支撑", status: "pass", detail: "2 条强支撑" },
  { label: "实验解释", status: "pass", detail: "指标、限制与产物已对齐" },
  { label: "语义保持", status: "warning", detail: "1 处改写需要确认" },
])
```

Ensure no UI projection contains:

- raw tool args;
- raw stdout/stderr;
- `*.v1` schema names;
- `/workspace/tmp/tasks/.harness/outputs/**`.

- [ ] **Step 2: Run tests and confirm RED**

Run:

```bash
cd frontend && npx vitest run tests/unit/lib/execution-run-view.test.ts
```

Expected: missing `qualityHighlights` or missing sanitization.

- [ ] **Step 3: Implement projection**

Implementation boundary:

- only read existing hydrated node state / runtime state;
- keep `run-ui-store` as UI focus/badge only;
- do not add a second store or second stream;
- render concise, human-readable quality summary in `LiveWorkflowPanel`.

- [ ] **Step 4: Run frontend focused tests**

Run:

```bash
cd frontend && npm run typecheck
cd frontend && npx vitest run \
  tests/unit/lib/execution-run-view.test.ts \
  tests/unit/v2/LiveWorkflowPanel.test.tsx
```

Expected: typecheck and tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add frontend/lib/execution-run-view.ts \
  frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx \
  frontend/tests/unit/lib/execution-run-view.test.ts \
  frontend/tests/unit/v2/LiveWorkflowPanel.test.tsx \
  docs/current/workspace-current-state.md
git commit -m "feat: show concise harness quality highlights"
```

Expected: commit succeeds.

---

### Task 6: Final Release Gate, Docs, and Browser Smoke

**Files:**
- Modify if needed: `docs/current/architecture.md`
- Modify if needed: `docs/current/workspace-current-state.md`
- Modify if needed: `docs/current/native-harness-external-gap-matrix.md`
- Modify if needed: `docs/current/native-harness-convergence-audit.md`
- Modify if needed: `docs/current/release-gate-checklist.md`

- [ ] **Step 1: Run full backend tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
```

Expected: all backend tests pass.

- [ ] **Step 2: Run backend Ruff**

Run:

```bash
cd backend && .venv/bin/ruff check src tests
```

Expected: Ruff passes.

- [ ] **Step 3: Run frontend checks**

Run:

```bash
cd frontend && npm run typecheck
cd frontend && npx vitest run
```

Expected: typecheck passes and all frontend unit tests pass.

- [ ] **Step 4: Run architecture drift scan**

Run:

```bash
rg -n "from .*codex|import .*codex|cc-switch|ccswitch|deerflow|deer-flow|sandbox.run_command|/mnt/user-data|app-server|ACP workspace|harness store|run journal table" \
  backend/src frontend/app frontend/lib frontend/stores -g '*.py' -g '*.ts' -g '*.tsx'
```

Expected:

- no production-code imports or runtime usage of forbidden systems;
- documentation-only concepts are not scanned in this command;
- any remaining production hit must be an explicit negative guard or test name, not runtime behavior.

- [ ] **Step 5: Run browser smoke if frontend changed**

Start or reuse the local stack:

```bash
docker compose up --build
```

Use Browser/Chrome to verify:

- `/workspaces` loads without login regression when already authenticated;
- a SCI workspace can launch a team task;
- LiveWorkflowPanel shows concise team progress and quality highlights without raw tool payloads;
- Result review still uses checkboxes and one-click accept;
- Prism opens, compiles, and AI assist does not auto-open on compile;
- no browser console errors appear on the main flow.

- [ ] **Step 6: Update docs with final status**

Update:

- `docs/current/architecture.md`: final native harness architecture and allowed extension points.
- `docs/current/workspace-current-state.md`: current user-visible execution/team behavior.
- `docs/current/native-harness-external-gap-matrix.md`: remaining non-blocking gaps only.
- `docs/current/native-harness-convergence-audit.md`: exact test commands and results.
- `docs/current/release-gate-checklist.md`: final release gate command list.

- [ ] **Step 7: Commit final docs/checklist**

Run:

```bash
git add docs/current/architecture.md \
  docs/current/workspace-current-state.md \
  docs/current/native-harness-external-gap-matrix.md \
  docs/current/native-harness-convergence-audit.md \
  docs/current/release-gate-checklist.md
git commit -m "docs: finalize native harness closure status"
```

Expected: commit succeeds only if docs changed.

---

## Self-Review Checklist

- [ ] Every planned backend capability stays inside the existing execution chain.
- [ ] Every new quality check is deterministic over existing metadata; no model judge is required in release gates.
- [ ] Internal harness refs remain hidden from listing/search/artifact discovery.
- [ ] Output recovery happens through explicit bounded output refs.
- [ ] Reviewable outputs still go through result-card / Prism review flows.
- [ ] The frontend only shows concise user-facing projection, never raw tool payloads.
- [ ] Docs list Codex/deer-flow as pattern references only, not runtime dependencies.
- [ ] Each implementation slice has focused tests, Ruff/typecheck where relevant, and a commit.
