# LaTeX Editor Shell Second-Stage Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Phase 5 second-stage convergence by moving Prism editor panes, inspector views, and review/job orchestration out of `LatexEditorShell.tsx`, reducing the shell below 1200 lines without changing the `/workspaces/{workspace_id}/prism` behavior.

**Architecture:** `LatexEditorShell.tsx` remains the route-facing composition shell and keeps the high-level store wiring plus feedback rewrite workflow. Local `latex-editor/` modules own view-only panes/dialogs and two focused hooks for Prism optimization job tracking and Prism review queue actions. Hooks receive dependencies from the shell and return stable view/action objects; UI components stay store-free and receive all data/actions as props.

**Tech Stack:** Next.js 16, React 19, TypeScript, Zustand, Vitest, Playwright, Pytest architecture guards.

---

## File Structure

- Create `frontend/components/latex/latex-editor/types.ts`
  - Owns `PdfDraftSelection`, `LastRewriteUndoState`, `PrismSurfaceMode`, and `PrismInspectorTab`.
- Create `frontend/components/latex/latex-editor/usePrismOptimizationJobs.ts`
  - Owns Prism optimization job state, active job selection, execution polling/hydration, execution-to-job status projection, completion sync, active execution record/phases, and optimizing feedback id set.
- Create `frontend/components/latex/latex-editor/usePrismReviewQueue.ts`
  - Owns Prism file-change preview state, busy/error state, focused review item URL parsing, focus scroll/open/preview effect, apply/discard/revert actions, and `PrismReviewList` view model projection.
- Create `frontend/components/latex/latex-editor/useLatexFeedbackPersistence.ts`
  - Owns feedback load/save state, autosave debounce, load errors, save errors, and status setters.
- Create `frontend/components/latex/latex-editor/useLatexPdfSelectionMapping.ts`
  - Owns PDF selection draft state, transient PDF anchors, SyncTeX/text fallback mapping, and TeX-selection-to-PDF-highlight mapping.
- Create `frontend/components/latex/latex-editor/useLatexFeedbackCreation.ts`
  - Owns converting current TeX/PDF selection plus comment into a persisted `LatexFeedbackItem`.
- Create `frontend/components/latex/latex-editor/LatexEditorProjectBar.tsx`
  - Owns the top project bar, engine selector, save/compile controls, dirty badge, back navigation button, and inspector toggle button.
- Create `frontend/components/latex/latex-editor/LatexResourceRail.tsx`
  - Owns the left resource rail, file tree, file operations details, upload/create controls, and delete project button.
- Create `frontend/components/latex/latex-editor/LatexEditorPanes.tsx`
  - Owns editor panel, PDF panel, surface mode segmented control, compare split layout, blob preview, Monaco editor, and `LatexPdfPreview` wiring.
- Create `frontend/components/latex/latex-editor/LatexInspector.tsx`
  - Owns the right inspector shell and four tabs: feedback assist, Prism review queue, compile status, and Agent task summary.
- Create `frontend/components/latex/latex-editor/LatexCompileLogDialog.tsx`
  - Owns the compile log dialog body.
- Modify `frontend/components/latex/LatexEditorShell.tsx`
  - Import the focused hooks/components.
  - Remove local `renderProjectBar`, `renderResourceRail`, `renderEditorPanel`, `renderPdfPanel`, `renderWritingSurface`, `renderFeedbackInspector`, `renderReviewInspector`, `renderCompileInspector`, `renderAgentInspector`, `renderInspector`, and `renderPrismWorkspace`.
  - Replace Prism optimization job local state/effects with `usePrismOptimizationJobs`.
  - Replace Prism review queue local state/effects/actions with `usePrismReviewQueue`.
- Modify `backend/tests/architecture/test_dataservice_boundaries.py`
  - Add a second-stage guard requiring the new modules and `LatexEditorShell.tsx` below 1200 lines.
- Modify `frontend/tests/unit/v2/latex-editor-utils.test.ts`
  - Add focused tests for the new pure review queue projection where useful.

## Task 1: Red Guard And Focused Hook Tests

- [ ] **Step 1: Add second-stage architecture guard**

In `backend/tests/architecture/test_dataservice_boundaries.py`, add `test_latex_editor_shell_composes_second_stage_views` requiring:

- `types.ts`
- `usePrismOptimizationJobs.ts`
- `usePrismReviewQueue.ts`
- `useLatexFeedbackPersistence.ts`
- `useLatexPdfSelectionMapping.ts`
- `useLatexFeedbackCreation.ts`
- `LatexEditorProjectBar.tsx`
- `LatexResourceRail.tsx`
- `LatexEditorPanes.tsx`
- `LatexInspector.tsx`
- `LatexCompileLogDialog.tsx`

The guard must assert:

```python
assert len(source.splitlines()) < 1200
assert 'from "@/components/latex/latex-editor/LatexEditorPanes"' in source
assert 'from "@/components/latex/latex-editor/LatexInspector"' in source
assert "const renderProjectBar =" not in source
assert "const renderFeedbackInspector =" not in source
assert "const renderPrismWorkspace =" not in source
```

- [ ] **Step 2: Verify guard red**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_latex_editor_shell_composes_second_stage_views -q
```

Expected: FAIL because the second-stage modules do not exist and the shell is still above 1200 lines.

## Task 2: Extract Shared Types And Prism Job Hook

- [ ] **Step 1: Create `types.ts`**

Move local shell-only types:

```ts
export interface PdfDraftSelection { ... }
export interface LastRewriteUndoState extends LatexFeedbackRewriteUndoPayload { ... }
export type PrismSurfaceMode = "edit" | "compare" | "review" | "focus";
export type PrismInspectorTab = "assist" | "review" | "compile" | "agent";
```

- [ ] **Step 2: Create `usePrismOptimizationJobs.ts`**

Move the local job state and effects that currently:

- track `prismOptimizationJobs`
- track `activePrismOptimizationJobId`
- track `isPrismOptimizationTraceOpen`
- hydrate `listExecutions`
- sync `ExecutionRecord` statuses to jobs
- reload project after completed Prism optimization executions
- compute `activePrismOptimizationJob`
- compute `activePrismOptimizationRecord`
- compute `activePrismOptimizationPhases`
- compute `optimizingFeedbackIds`

The hook signature should be:

```ts
export function usePrismOptimizationJobs({
  workspaceId,
  projectId,
  executions,
  upsertExecution,
  loadProject,
  onReviewStateChanged,
  onFeedbackStatus,
}: UsePrismOptimizationJobsOptions): UsePrismOptimizationJobsResult
```

The result should expose `addJob(job)`, `updateJob(jobId, updater)`, `setActiveJobId`, `setTraceOpen`, and all computed view state.

- [ ] **Step 3: Replace shell job state**

Update `LatexEditorShell.tsx` so `launchPrismOptimizationFromFeedback` uses:

```ts
prismOptimization.addJob(job);
prismOptimization.updateJob(jobId, (entry) => ({ ...entry, executionId, status: "running" }));
```

## Task 3: Extract Prism Review Queue Hook

- [ ] **Step 1: Create `usePrismReviewQueue.ts`**

Move local review queue state/actions:

- `fileChangesRef`
- `lastFileChangeFocusKey`
- `fileChangePreviews`
- `busyFileChangeKey`
- `fileChangeError`
- `pendingReviewItems`
- `appliedReviewItems`
- focused `review_item_id` / `logical_key` parsing
- focus scroll/open/preview effect
- `previewProjectFileChange`
- `applyPendingFileChange`
- `discardPendingFileChange`
- `revertAppliedFileChange`

The hook should accept store actions and `searchParams`, then return a single object consumed by `LatexInspector` and `PrismOptimizationTraceDialog`.

- [ ] **Step 2: Replace shell review queue state**

Update `LatexEditorShell.tsx` to use `reviewQueue.fileChangesRef`, `reviewQueue.previewProjectFileChange`, `reviewQueue.applyPendingFileChange`, `reviewQueue.scrollToReviewQueue`, and the view state returned by the hook.

## Task 4: Extract UI Composition Components

- [ ] **Step 1: Create `LatexEditorProjectBar.tsx`**

Move top bar JSX without subscribing to stores. Props include project name/main file, active file path, dirty, engine, loading flags, `onBack`, `onEngineChange`, `onSave`, `onCompile`, and `onToggleInspector`.

- [ ] **Step 2: Create `LatexResourceRail.tsx`**

Move file tree, file operations details, upload/create controls, and delete project button. Props include tree, selection, engine state, current folder, toolbar callbacks, delete state, and project name.

- [ ] **Step 3: Create `LatexEditorPanes.tsx`**

Move editor/PDF/writing surface composition. Props include surface mode, active file info, selection info, editor ref, compile state, PDF highlight state, and pane actions.

- [ ] **Step 4: Create `LatexInspector.tsx`**

Move inspector shell and four inspector tabs. Props include feedback draft state/actions, rewrite preview props, review queue view/actions, compile status, and active Prism optimization job.

- [ ] **Step 5: Create `LatexCompileLogDialog.tsx`**

Move compile dialog and replace the inline shell dialog with this component.

- [ ] **Step 6: Replace shell render functions**

Update `LatexEditorShell.tsx` return body to compose:

```tsx
<LatexEditorProjectBar ... />
<div className="flex min-h-0 flex-1 overflow-hidden">
  {surfaceMode !== "focus" ? <LatexResourceRail ... /> : null}
  <LatexEditorPanes ... />
  <LatexInspector ... />
</div>
<PrismOptimizationTraceDialog ... />
<LatexCompileLogDialog ... />
```

## Task 5: Verification And Review

- [ ] **Step 1: Focused lint/type/test**

Run:

```bash
cd frontend && npx eslint components/latex/LatexEditorShell.tsx 'components/latex/latex-editor/*.{ts,tsx}' tests/unit/v2/latex-editor-utils.test.ts
cd frontend && npm run typecheck
cd frontend && npx vitest run tests/unit/v2/latex-editor-utils.test.ts tests/unit/v2/prism-surface.test.tsx tests/unit/lib/prism-review-api.test.ts
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_latex_editor_shell_uses_focused_local_modules tests/architecture/test_dataservice_boundaries.py::test_latex_editor_shell_composes_second_stage_views -q
```

- [ ] **Step 2: Browser/E2E verification**

Run:

```bash
cd frontend && npx playwright test tests/e2e/prism-surface.spec.ts
```

If the in-app browser can reach the local dev server, open `/workspaces/ws-1/prism` and check that it reaches the expected login or mocked Prism surface without a Next error overlay. If the in-app browser cannot connect but `curl` and Playwright can, record that limitation.

- [ ] **Step 3: Graph review and hygiene**

Run code-review-graph incremental update and `detect_changes`; inspect the changed modules for new hotspots. Run:

```bash
git diff --check
git status --short --branch
wc -l frontend/components/latex/LatexEditorShell.tsx frontend/components/latex/latex-editor/*.{ts,tsx}
```

## Task 6: Commit And Push

- [ ] **Step 1: Commit**

Commit as:

```bash
git commit -m "refactor: split latex editor panes"
```

- [ ] **Step 2: Push**

Push the current branch.

## Self-Review

- Spec coverage: covers Phase 5 second-stage `toolbar/panes` plus hook extraction needed to reach the `<1200` shell target.
- Contract check: does not change route entry, stores, DataService contracts, `LatexPdfPreview` props, or Prism review API calls.
- Risk check: biggest risk is props drift across extracted UI components; mitigated by typecheck, focused lint, existing Prism E2E, and architecture guard.
- Follow-up: Phase 5 third-stage below 800 and Phase 6 dead-code cleanup remain after this plan.
