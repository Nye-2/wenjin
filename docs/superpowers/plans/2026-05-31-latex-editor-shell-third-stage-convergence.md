# LaTeX Editor Shell Third-Stage Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development when available, otherwise superpowers:executing-plans. Track tasks with the checklist below.

**Goal:** Finish Phase 5 third-stage convergence by moving feedback, rewrite, protection, and Prism selection optimization orchestration out of `LatexEditorShell.tsx`, reducing the shell below 800 lines without changing `/workspaces/{workspace_id}/prism` behavior.

**Architecture:** `LatexEditorShell.tsx` stays the route-facing composition shell. It wires stores, PDF selection mapping, Prism job tracking, review queue tracking, and view components. A focused `useLatexFeedbackWorkflow` hook owns user feedback lifecycle actions and exposes a typed view/action object to the shell.

**Tech Stack:** Next.js 16, React 19, TypeScript, Zustand, Vitest, Playwright, Pytest architecture guards.

---

## File Structure

- Create `frontend/components/latex/latex-editor/useLatexFeedbackWorkflow.ts`
  - Owns feedback draft state, scope, active feedback id, busy id, rewrite preview state, rewrite candidate state, diff controls, undo payload, protection state, and all feedback/rewrite/protection actions.
  - Internally uses `useLatexFeedbackCreation`, `previewLatexFeedbackRewrite`, `applyLatexFeedbackRewrite`, `revertLatexFeedbackRewrite`, `protectLatexSection`, feedback anchor helpers, rewrite error helpers, and client error helpers.
  - Receives project/file/store dependencies from the shell; does not subscribe to global stores.
  - Returns derived view state for `LatexEditorPanes` and `LatexInspector`.
- Modify `frontend/components/latex/LatexEditorShell.tsx`
  - Import `useLatexFeedbackWorkflow`.
  - Remove local feedback/rewrite/protection state and local action callbacks.
  - Keep only shell-level route auth/load, project selection state, compile log state, PDF mapping, Prism optimization tracking, review queue tracking, and component composition.
- Modify `backend/tests/architecture/test_dataservice_boundaries.py`
  - Add third-stage guard requiring `useLatexFeedbackWorkflow.ts`, `LatexEditorShell.tsx` below 800 lines, and no local rewrite/protection orchestration symbols in the shell.

## Task 1: Red Guard

- [x] **Step 1: Add third-stage architecture guard**

Add `test_latex_editor_shell_delegates_feedback_workflow` requiring:

```python
assert (module_root / "useLatexFeedbackWorkflow.ts").exists()
assert len(source.splitlines()) < 800
assert 'from "@/components/latex/latex-editor/useLatexFeedbackWorkflow"' in source
assert "launchPrismOptimizationFromFeedback" not in source
assert "rewriteFromFeedback" not in source
assert "applyRewriteCandidate" not in source
assert "undoLastRewrite" not in source
assert "protectActiveFile" not in source
```

- [x] **Step 2: Verify guard red**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_latex_editor_shell_delegates_feedback_workflow -q
```

Expected: FAIL because the hook does not exist and the shell remains above 800 lines.

## Task 2: Extract Feedback Workflow Hook

- [x] **Step 1: Create `useLatexFeedbackWorkflow.ts`**

Move local shell state and callbacks for:

- feedback draft comment/scope
- active feedback id and busy feedback id
- rewrite preview file/feedback ids
- rewrite candidates, selected candidate, diff mode, whitespace-only toggle, collapsed hunks
- applying state and last rewrite undo state
- protect-active-file state
- `clearRewritePreview`
- `addFeedbackOnly`
- `focusFeedback`
- `removeFeedback`
- `launchPrismOptimizationFromFeedback`
- `rewriteFromFeedback`
- `applyRewriteCandidate`
- `regenerateRewritePreview`
- `copySelectedRewrite`
- `toggleDiffHunkCollapsed`
- `setAllDiffHunksCollapsed`
- `undoLastRewrite`
- rewrite keyboard shortcut effect
- `addFeedbackAndRewrite`
- `protectActiveFile`

The hook should expose a stable object:

```ts
export function useLatexFeedbackWorkflow(options: UseLatexFeedbackWorkflowOptions): UseLatexFeedbackWorkflowResult
```

`UseLatexFeedbackWorkflowResult` must include `view`, `actions`, and the derived pane values `selectionText`, `hasFeedbackSelection`, and `pdfHighlightFeedbacks`.

- [x] **Step 2: Replace shell local orchestration**

Update `LatexEditorShell.tsx` so the shell reads values from `feedbackWorkflow.view` and calls `feedbackWorkflow.actions.*`.

## Task 3: Verify And Review

- [x] **Step 1: Focused verification**

Run:

```bash
cd frontend && npx eslint components/latex/LatexEditorShell.tsx 'components/latex/latex-editor/*.{ts,tsx}' tests/unit/v2/latex-editor-utils.test.ts
cd frontend && npm run typecheck
cd frontend && npx vitest run tests/unit/v2/latex-editor-utils.test.ts tests/unit/v2/prism-surface.test.tsx tests/unit/lib/prism-review-api.test.ts
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_latex_editor_shell_uses_focused_local_modules tests/architecture/test_dataservice_boundaries.py::test_latex_editor_shell_composes_second_stage_views tests/architecture/test_dataservice_boundaries.py::test_latex_editor_shell_delegates_feedback_workflow -q
```

- [x] **Step 2: Browser/E2E verification**

Run:

```bash
cd frontend && npx playwright test tests/e2e/prism-surface.spec.ts
```

- [x] **Step 3: Hygiene**

Run:

```bash
git diff --check
git status --short --branch
wc -l frontend/components/latex/LatexEditorShell.tsx frontend/components/latex/latex-editor/*.{ts,tsx}
```

## Task 4: Commit And Push

- [x] Commit the third-stage split separately from dead-code cleanup.
- [ ] Push the current branch.

## Self-Review

- Spec coverage: covers Phase 5 third-stage `<800` shell target. Phase 6 dead-code cleanup remains separate by spec and must not be mixed into this functional split.
- Contract check: no route, store, DataService, Prism review API, or `LatexPdfPreview` prop contract changes.
- Risk check: main risk is callback dependency drift inside the extracted hook; mitigated by typecheck, lint, existing Prism unit/E2E checks, and architecture guard.
