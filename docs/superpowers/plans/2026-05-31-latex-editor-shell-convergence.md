# LaTeX Editor Shell Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans and superpowers:test-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Phase 5 first-stage convergence by extracting pure LaTeX editor helpers and leaf UI from `LatexEditorShell.tsx`, while keeping the Prism manuscript route and editing behavior unchanged.

**Architecture:** `LatexEditorShell.tsx` remains the public composition shell for `/workspaces/{workspace_id}/prism`. A local `latex-editor/` package owns pure file-kind helpers, feedback anchor/range matching, client error parsing, rewrite display helpers, Prism optimization job helpers, Monaco editor wiring, and rewrite diff preview rendering.

**Tech Stack:** Next.js 16, React 19, TypeScript, Vitest, Testing Library.

---

## File Structure

- Create `frontend/components/latex/latex-editor/fileKinds.ts`
  - Owns `languageForPath`, `isTextFile`, `isImageFile`.
- Create `frontend/components/latex/latex-editor/feedbackAnchors.ts`
  - Owns feedback id creation, line counting, LaTeX heading detection, anchor building, feedback range resolution, snippet resolution, PDF anchor parsing, and post-rewrite feedback shifting.
- Create `frontend/components/latex/latex-editor/clientErrors.ts`
  - Owns API error message/code/detail-field extraction.
- Create `frontend/components/latex/latex-editor/rewriteDisplay.ts`
  - Owns rewrite labels/classes, diff labels, whitespace-only diff detection, and rewrite error code sets.
- Create `frontend/components/latex/latex-editor/prismOptimizationJobs.ts`
  - Owns Prism optimization job types, job id creation, execution-to-job status mapping, status labels, node labels, and snippet trimming.
- Create `frontend/components/latex/latex-editor/PrismMonacoEditor.tsx`
  - Owns Monaco environment setup and text editor imperative handle.
- Create `frontend/components/latex/latex-editor/LatexRewritePreviewPanel.tsx`
  - Owns rewrite candidate selector, risk badges, hunk rendering, and apply/cancel/copy actions.
- Create `frontend/tests/unit/v2/latex-editor-utils.test.ts`
  - Covers pure helper behavior and job status projection.
- Modify `frontend/components/latex/LatexEditorShell.tsx`
  - Import focused modules and remove duplicated local helper/component definitions.
- Modify `backend/tests/architecture/test_dataservice_boundaries.py`
  - Add a guard keeping the shell below first-stage target and requiring local modules.

## Task 1: Red Tests And Architecture Guard

- [ ] **Step 1: Add failing architecture guard**

Add `test_latex_editor_shell_uses_focused_local_modules` requiring:

- `fileKinds.ts`
- `feedbackAnchors.ts`
- `clientErrors.ts`
- `rewriteDisplay.ts`
- `prismOptimizationJobs.ts`
- `PrismMonacoEditor.tsx`
- `LatexRewritePreviewPanel.tsx`

The guard also requires `LatexEditorShell.tsx` below 2400 lines and forbids local definitions of `buildFeedbackAnchor`, `resolveFeedbackRange`, and `PrismMonacoEditor`.

- [ ] **Step 2: Add failing utility tests**

Create `frontend/tests/unit/v2/latex-editor-utils.test.ts` covering:

- language/file-kind classification
- feedback anchor heading and line hints
- range/snippet resolution after content drift
- PDF anchor sanitization
- rewrite display labels and whitespace-only diff detection
- Prism optimization job status mapping from execution records

- [ ] **Step 3: Verify red**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_latex_editor_shell_uses_focused_local_modules -q
cd frontend && npx vitest run tests/unit/v2/latex-editor-utils.test.ts
```

Expected: architecture guard fails because modules are missing and shell is too large; Vitest fails because the modules do not exist yet.

## Task 2: Extract Pure Helpers And Editor Primitive

- [ ] **Step 1: Move file-kind helpers**

Move `languageForPath`, `isTextFile`, and `isImageFile` to `fileKinds.ts`.

- [ ] **Step 2: Move feedback anchor helpers**

Move:

- `createFeedbackId`
- `countLinesUntil`
- LaTeX heading/comment helpers
- `buildFeedbackAnchor`
- `resolveFeedbackRange`
- `resolveSnippetRange`
- `parsePdfAnchor`
- `shiftFeedbacksAfterRewrite`

- [ ] **Step 3: Move API error helpers**

Move:

- `readClientErrorMessage`
- `readClientErrorCode`
- `readClientErrorDetailField`

- [ ] **Step 4: Move rewrite display helpers**

Move:

- rewrite/risk/diff labels
- risk class helpers
- `isWhitespaceOnlyDiffOp`
- stale/structure rewrite error code sets

- [ ] **Step 5: Move Prism optimization job helpers**

Move:

- job status/type definitions
- job id creation
- `jobStatusFromExecution`
- `prismJobStatusLabel`
- `prismExecutionNodeLabel`
- `trimSnippet`

- [ ] **Step 6: Move Monaco editor primitive**

Move `PrismMonacoEditor` and related handle/props types to `PrismMonacoEditor.tsx`.

## Task 3: Extract Rewrite Preview Leaf Component

- [ ] **Step 1: Create `LatexRewritePreviewPanel.tsx`**

Move the rewrite diff preview renderer into a focused leaf component. It must receive all mutable actions as props and must not subscribe to stores.

- [ ] **Step 2: Replace shell local renderer**

Replace `renderRewritePreview()` call in the feedback inspector with `LatexRewritePreviewPanel`.

## Task 4: Verification

- [ ] **Step 1: Focused lint/type/test**

Run:

```bash
cd frontend && npx eslint frontend/components/latex/LatexEditorShell.tsx frontend/components/latex/latex-editor/*.{ts,tsx} frontend/tests/unit/v2/latex-editor-utils.test.ts
cd frontend && npm run typecheck
cd frontend && npx vitest run tests/unit/v2/latex-editor-utils.test.ts tests/unit/v2/prism-surface.test.tsx tests/unit/lib/prism-review-api.test.ts
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_latex_editor_shell_uses_focused_local_modules -q
```

- [ ] **Step 2: E2E/browser smoke**

Run Prism E2E if available:

```bash
cd frontend && npx playwright test tests/e2e/prism-surface.spec.ts
```

Also open the Prism route in the in-app browser when a local target is available and verify there is no Next error overlay.

- [ ] **Step 3: Graph review and diff hygiene**

Run code-review-graph incremental update/detect changes, `git diff --check`, and inspect status.

## Task 5: Commit And Push

- [ ] **Step 1: Commit**

Commit as:

```bash
git commit -m "refactor: split latex editor shell helpers"
```

- [ ] **Step 2: Push**

Push the current branch.

## Self-Review

- Scope: first-stage Phase 5 only; toolbar/panes and full shell target below 1200 remain future phases.
- Contract: does not change `/workspaces/{workspace_id}/prism`, `LatexPdfPreview` props, DataService contracts, or store contracts.
- Risk: mostly pure helper extraction and one leaf renderer move; covered by new helper tests, existing Prism page tests, typecheck, architecture guard, and Prism E2E/browser smoke.
