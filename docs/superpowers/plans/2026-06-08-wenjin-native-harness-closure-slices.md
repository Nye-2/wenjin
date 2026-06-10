# Wenjin Native Harness Closure Slices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the current Wenjin-native harness goal through focused closure slices: make existing harness evidence visible to users, verify realistic research/experiment workflows, remove remaining architecture drift, and leave the branch merge-ready without adopting Codex SDK, cc-switch, or deer-flow runtime.

**Architecture:** Keep the existing path authoritative: Chat Agent -> Lead Agent -> TeamKernel/static graph -> ReactSubagent -> Wenjin Harness -> DataService sandbox/execution/review domains. Codex and deer-flow remain reference projects only; portable ideas are accepted only when they land inside existing execution records, node metadata, sandbox workspace layout, capability policy, and frontend RunView projection.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Pydantic v2, LangGraph/LangChain adapter edge, DataService sandbox domain, Next.js 16, React 19, TypeScript, Zustand, vitest, pytest, ruff.

---

## Current State

- Branch: `codex/wenjin-native-harness`.
- Worktree requirement before each slice: `git status --short` should be clean.
- Completed harness foundations include bounded file/search/Python tools, structured patching, dataset/artifact manifest tools, one-workspace sandbox layout, context bundle, tool failure recovery, file-change summaries, sandbox execution summaries, reproducibility summaries, experiment narrative, TeamKernel same-run evidence replay, and external reference audit.
- The most valuable remaining gap is not another backend tool. It is product closure: default UI and run evidence still do not fully expose the new `reproducibility_summary` / `experiment_narrative` as concise user-facing progress.

## Scope Guard

Do this:

- Improve the native harness by projecting existing evidence better, adding realistic eval/smoke coverage, and tightening queue/cancel/performance details where tests show gaps.
- Keep all user-facing run state derived from `frontend/lib/execution-run-view.ts` and `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/useLiveWorkflowViewModel.ts`.
- Keep all backend facts attached to existing `ExecutionRecord`, `ExecutionNodeRecord.node_metadata.harness`, DataService sandbox jobs/artifacts, and review items.
- Commit each behavior boundary separately.

Do not do this:

- Do not add Codex SDK, cc-switch, deer-flow runtime, or external agent compatibility bridges.
- Do not add generic `sandbox.run_command`.
- Do not create a second execution table, harness run table, execution stream, frontend harness store, or router bypass.
- Do not make raw args, stdout, stderr, manifests, host paths, protected paths, or internal `/workspace/outputs/harness/**` refs visible in the default UI.

---

### Task 34: Project Reproducibility Evidence into Default Run UI

**Goal:** make the evidence already produced by `sandbox.run_python` visible as concise team-member and progress labels, without showing raw tool JSON.

**Files:**

- Modify: `frontend/lib/execution-run-view.ts`
- Modify: `frontend/tests/unit/lib/execution-run-view.test.ts`
- Docs: `docs/current/frontend-feature-plugin-contract.md`
- Docs: `docs/current/native-harness-convergence-audit.md`

- [ ] **Step 1: Write failing RunView projection test**

Add a test in `frontend/tests/unit/lib/execution-run-view.test.ts` with one `agent_invocation` node:

```ts
const view = runViewFromExecution(
  makeExecution({
    graph_structure: {
      mode: "team_kernel",
      nodes: [],
      edges: [],
    } as ExecutionRecord["graph_structure"],
    node_states: {
      "experiment_engineer.v1__1": {
        status: "completed",
        node_type: "agent_invocation",
        label: "实验工程师",
        node_metadata: {
          team: true,
          template_id: "experiment_engineer.v1",
          display_name: "实验工程师",
          harness: {
            reproducibility_summary: {
              schema: "wenjin.harness.reproducibility_summary.v1",
              python_runs: 1,
              dataset_paths: ["/workspace/datasets/panel.csv"],
              artifact_paths: ["/workspace/outputs/result.json"],
              script_paths: ["/workspace/scripts/analysis.py"],
              next_actions: ["检查稳健性"],
            },
          },
        },
      },
    } as ExecutionRecord["node_states"],
  }),
);

expect(view.team?.members[0]?.activityLabel).toBe("已完成可复现实验：1 个脚本 · 1 个数据集 · 1 个产物");
expect(view.team?.members[0]?.artifactCount).toBe(1);
```

Run:

```bash
cd /Users/ze/wenjin/frontend
npx vitest run tests/unit/lib/execution-run-view.test.ts -t "reproducibility"
```

Expected before implementation: fail because `reproducibility_summary` is ignored.

- [ ] **Step 2: Implement minimal projection in `execution-run-view.ts`**

Update `harnessActivityFromNodeState()` ordering:

1. `tool_failure_summary` / failed Python still wins when there is a recoverable problem.
2. `run_journal_summary.summary` remains highest-quality human text when present.
3. `reproducibility_summary` produces labels from bounded counts:
   - running: `正在运行可复现实验`
   - completed with script/data/artifact counts: `已完成可复现实验：N 个脚本 · M 个数据集 · K 个产物`
   - completed with only next actions: `实验已完成，等待复核`
4. fallback to `sandbox_execution_summary` and `file_change_summary`.

Do not add new component parsing of `node_metadata`.

- [ ] **Step 3: Run projection tests**

Run:

```bash
cd /Users/ze/wenjin/frontend
npx vitest run tests/unit/lib/execution-run-view.test.ts
npm run typecheck
```

Expected: all selected tests pass, TypeScript has no errors.

- [ ] **Step 4: Update docs**

Update docs to state:

- `execution-run-view.ts` consumes `reproducibility_summary` as a user-facing activity label.
- Raw tool payloads remain hidden in default LiveWorkflowPanel and Runs drawer.

- [ ] **Step 5: Commit**

Run:

```bash
cd /Users/ze/wenjin
git status --short
git add frontend/lib/execution-run-view.ts frontend/tests/unit/lib/execution-run-view.test.ts docs/current/frontend-feature-plugin-contract.md docs/current/native-harness-convergence-audit.md
git commit -m "feat: project harness reproducibility evidence"
```

---

### Task 35: Add Harness Evidence Items Without Raw Sandbox Noise

**Goal:** make the Evidence tab show clean sandbox/reproducibility evidence even when an execution has no normal staged output preview.

**Files:**

- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/utils.ts`
- Modify: `frontend/tests/unit/v2/live-workflow-view-model.test.ts`
- Test if needed: `frontend/tests/unit/v2/LiveWorkflowPanel.test.tsx`
- Docs: `docs/current/frontend-feature-plugin-contract.md`

- [ ] **Step 1: Write failing evidence-item test**

Add a test in `frontend/tests/unit/v2/live-workflow-view-model.test.ts`:

```ts
const reproducibleRecord = baseRecord({
  id: "repro-1",
  status: "completed",
  node_states: {
    "experiment-node": {
      status: "completed",
      node_type: "agent_invocation",
      label: "实验工程师",
      node_metadata: {
        harness: {
          reproducibility_summary: {
            schema: "wenjin.harness.reproducibility_summary.v1",
            script_paths: ["/workspace/scripts/analysis.py"],
            dataset_paths: ["/workspace/datasets/panel.csv"],
            artifact_paths: ["/workspace/outputs/result.json"],
            next_actions: ["复核图表"],
          },
        },
      },
    },
  },
});

const model = buildLiveWorkflowViewModel({
  records: [reproducibleRecord],
  workspaceId: "ws-1",
  selectedRunId: "repro-1",
  focusedRunId: null,
  activeRunId: null,
  selectedPreviewId: null,
  draftEdits: {},
});

expect(model.evidenceItems[0]?.kind).toBe("sandbox");
expect(model.evidenceItems[0]?.summary).toContain("analysis.py");
expect(model.evidenceItems[0]?.summary).not.toContain("stdout");
```

Run:

```bash
cd /Users/ze/wenjin/frontend
npx vitest run tests/unit/v2/live-workflow-view-model.test.ts -t "reproducible"
```

Expected before implementation: fail because `buildEvidenceItems()` only uses raw `output`, `output_preview`, or tool calls.

- [ ] **Step 2: Implement evidence summary helper**

In `live-workflow/utils.ts`, keep the public function shape stable:

```ts
function buildHarnessEvidenceSummary(state: ExecutionNodeState): string[] | null {
  const harness = readObject(readObject(state.node_metadata)?.harness);
  const reproducibility = readObject(harness?.reproducibility_summary);
  // Return bounded human labels from script_paths, dataset_paths, artifact_paths, next_actions.
}
```

Rules:

- Only show basename/path summaries for `/workspace/scripts/**`, `/workspace/datasets/**`, `/workspace/outputs/**`, `/workspace/reports/**`.
- Never show `/workspace/outputs/harness/**`, `.wenjin`, `.env`, keys, stdout, stderr, raw args, or full JSON.
- If both harness evidence and old sandbox output exist, prefer harness evidence.

- [ ] **Step 3: Run UI model tests**

Run:

```bash
cd /Users/ze/wenjin/frontend
npx vitest run tests/unit/v2/live-workflow-view-model.test.ts
npx vitest run tests/unit/lib/execution-run-view.test.ts
npm run typecheck
```

Expected: all selected tests pass.

- [ ] **Step 4: Commit**

Run:

```bash
cd /Users/ze/wenjin
git status --short
git add "frontend/app/(workbench)/workspaces/[id]/components/live-workflow/utils.ts" frontend/tests/unit/v2/live-workflow-view-model.test.ts docs/current/frontend-feature-plugin-contract.md
git commit -m "feat: summarize harness evidence items"
```

---

### Task 36: Realistic Mock Research-Experiment Eval

**Goal:** verify the harness can complete one realistic vertical task, not just isolated tool unit tests.

**Files:**

- Modify: `backend/tests/integration/test_harness_mock_sandbox_e2e.py`
- Modify only if needed: `backend/tests/agents/lead_agent/v2/test_team_kernel.py`
- Docs: `docs/current/native-harness-convergence-audit.md`

- [ ] **Step 1: Add realistic E2E scenario**

Extend the mock sandbox integration test to simulate:

1. A `sci` workspace asks for a literature-backed experiment package.
2. TeamKernel recruits at least a literature/data role and an experiment/code role.
3. The experiment role receives `_harness_context(schema=wenjin.harness.context_bundle.v1)` with workspace profile and safe dataset provenance.
4. The role writes `/workspace/scripts/analysis.py`.
5. The role runs `sandbox.run_python`.
6. The run returns `execution_manifest`, `reproducibility_manifest`, `experiment_narrative`, and artifact candidates.
7. Same-run evidence is replayed to the quality step or a follow-up recruited member.
8. Final task report includes reviewable sandbox artifacts and no protected/internal refs.

- [ ] **Step 2: Run backend integration tests**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/integration/test_harness_mock_sandbox_e2e.py -q
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_kernel.py tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Commit**

Run:

```bash
cd /Users/ze/wenjin
git status --short
git add backend/tests/integration/test_harness_mock_sandbox_e2e.py backend/tests/agents/lead_agent/v2/test_team_kernel.py docs/current/native-harness-convergence-audit.md
git commit -m "test: cover realistic harness research workflow"
```

If `test_team_kernel.py` is not changed, do not stage it.

---

### Task 37: Queue, Cancel, and Long-Run Stability Review

**Goal:** close the main operational risk from Codex/deer-flow comparison: long-running sandbox work must have bounded state, clear cancellation, and no orphaned UI state.

**Files:**

- Inspect: `backend/src/agents/lead_agent/v2/sandbox_runtime.py`
- Inspect: `backend/src/agents/lead_agent/v2/sandbox_job_runner.py`
- Inspect: `backend/src/agents/harness/scheduler.py`
- Inspect: `backend/src/agents/harness/sandbox_execution_tools.py`
- Modify only if a bug is found.
- Test: existing sandbox runtime / harness scheduler tests, plus a focused regression test if needed.
- Docs: `docs/current/native-harness-convergence-audit.md`

- [ ] **Step 1: Audit the lifecycle**

Check these exact conditions:

- one workspace can acquire only one active sandbox environment.
- `sandbox.run_python` timeout creates recoverable evidence instead of hanging the agent.
- cancellation does not leave a fake completed node.
- dependency installation failure is free of credit billing but still visible as recoverable guidance.
- generated artifact discovery skips internal harness output refs.

- [ ] **Step 2: Add regression tests only where gaps exist**

If a gap is found, write a failing test first. Examples:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness/test_scheduler_and_python_tool.py -q
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_sandbox_runtime.py -q
```

- [ ] **Step 3: Implement minimal fix if needed**

Keep fixes inside the existing sandbox runtime/session/job-runner/harness scheduler path. Do not introduce another scheduler or provider abstraction.

- [ ] **Step 4: Commit only if code changed**

Run:

```bash
cd /Users/ze/wenjin
git status --short
git add backend/src/agents/lead_agent/v2/sandbox_runtime.py backend/src/agents/lead_agent/v2/sandbox_job_runner.py backend/src/agents/harness/scheduler.py backend/src/agents/harness/sandbox_execution_tools.py backend/tests/agents/harness/test_scheduler_and_python_tool.py backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py docs/current/native-harness-convergence-audit.md
git commit -m "fix: stabilize sandbox harness lifecycle"
```

If no code change is needed, write the audit result into `docs/current/native-harness-convergence-audit.md` and commit with:

```bash
git commit -m "docs: record sandbox lifecycle audit"
```

---

### Task 38: Browser/Docker Product Smoke

**Goal:** prove the integrated product experience is understandable and stable after harness UI projection changes.

**Files:**

- Modify only if bugs are found.
- Likely frontend files:
  - `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/RunView.tsx`
  - `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/utils.ts`
  - `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- Likely backend files:
  - only touch if smoke reveals execution/metadata defects.

- [ ] **Step 1: Start stack**

Use the documented local stack, preferably Docker Compose for the final smoke:

```bash
cd /Users/ze/wenjin
docker compose up --build
```

If the existing development process is already running, use it and record that in the final report.

- [ ] **Step 2: Browser-test required flows**

Use the Browser/Chrome tooling against `localhost:2026`:

- login/session remains valid when switching Wenjin/Prism.
- create/open a `sci` workspace.
- trigger a team-agent research/experiment task.
- LiveWorkflowPanel shows real-name team members and concise progress.
- Evidence tab shows clean reproducibility/sandbox evidence.
- Run detail keeps debug payload collapsed.
- Prism remains usable: editor visible, compile affordance clear, PDF contrast can be opened intentionally, AI 改稿 panel does not auto-open from compile.

- [ ] **Step 3: Fix only observed regressions**

For every bug:

1. write or update a unit test where feasible.
2. implement the minimal fix.
3. rerun the targeted test.

- [ ] **Step 4: Commit smoke fixes**

Use one commit per coherent issue:

```bash
git commit -m "fix: stabilize harness product smoke"
```

Do not commit logs, screenshots, generated artifacts, or transient Docker state.

---

### Task 39: Final Architecture Convergence Review

**Goal:** decide whether the harness can be considered branch-complete, and document remaining shortcomings honestly.

**Files:**

- Modify: `docs/current/architecture.md`
- Modify: `docs/current/workspace-current-state.md`
- Modify: `docs/current/frontend-feature-plugin-contract.md`
- Modify: `docs/current/native-harness-convergence-audit.md`
- Modify: `docs/current/documentation-map.md` only if a new doc link is needed.

- [ ] **Step 1: Run architecture drift scan**

Run:

```bash
cd /Users/ze/wenjin
rg -n "codex sdk|cc-switch|deer-flow runtime|run_command|harness store|harness_run|compat|fallback|router bypass|raw stdout|raw stderr" backend frontend docs -S
```

Expected:

- allowed mentions only in docs explaining rejected paths.
- no production dependency or runtime path for external systems.
- no generic command tool.

- [ ] **Step 2: Run final verification**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check src tests
cd /Users/ze/wenjin/frontend
npm run typecheck
npx vitest run
cd /Users/ze/wenjin
git diff --check
git status --short
```

Expected:

- backend tests pass.
- ruff passes.
- frontend typecheck passes.
- vitest passes.
- no whitespace errors.
- status is clean after final commit.

- [ ] **Step 3: Update final audit**

Write the conclusion in `docs/current/native-harness-convergence-audit.md`:

- what is now closed.
- what still does not match Codex/deer-flow and why that is acceptable for Wenjin.
- remaining non-blocking follow-ups, especially eval quality and future bounded command tool design.

- [ ] **Step 4: Commit docs**

Run:

```bash
cd /Users/ze/wenjin
git status --short
git add docs/current/architecture.md docs/current/workspace-current-state.md docs/current/frontend-feature-plugin-contract.md docs/current/native-harness-convergence-audit.md docs/current/documentation-map.md
git commit -m "docs: finalize native harness closure audit"
```

If `documentation-map.md` is not changed, do not stage it.

---

## Execution Order

1. Task 34: RunView reproducibility projection.
2. Task 35: Evidence tab harness summary projection.
3. Task 36: realistic mock research/experiment eval.
4. Task 37: queue/cancel/long-run stability review.
5. Task 38: browser/Docker product smoke and bug fixes.
6. Task 39: final architecture convergence review, docs, full verification.

This order is intentional: user-visible quality first, then realistic backend closure, then operational stability, then full product smoke, then final docs. It avoids spending another cycle on backend tool expansion before the current evidence becomes useful to users.

## Review Checklist After Each Commit

- The implementation stays inside the existing Chat Agent -> Lead Agent -> TeamKernel -> ReactSubagent -> Harness path.
- The frontend still uses `execution-run-view.ts` / LiveWorkflow view model as projection sources.
- No raw tool args/stdout/stderr/internal refs appear in default UI.
- Tests prove the behavior changed.
- Docs describe implemented behavior, not desired future behavior.
- `git diff --check` passes.

