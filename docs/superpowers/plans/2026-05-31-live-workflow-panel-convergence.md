# Live Workflow Panel Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `LiveWorkflowPanel.tsx` into a smaller execution UX shell with a tested view model and focused local modules, while keeping the current workbench UI behavior stable.

**Architecture:** Keep `frontend/lib/execution-run-view.ts` as the canonical run projection. Add a `live-workflow/` component-local package for display types, pure helpers, derived view model, and styles so the shell can focus on store wiring, side effects, and high-level tab composition.

**Tech Stack:** Next.js 16, React 19, TypeScript, Zustand, Vitest, Testing Library.

---

## File Structure

- Create `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/types.ts`
  - Owns `EvidenceFilter`, `EvidenceItem`, and panel-local state/output types.
- Create `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/utils.ts`
  - Owns pure helpers currently embedded in `LiveWorkflowPanel.tsx`: evidence item construction, review item extraction, sandbox summaries, status/kind labels, JSON/date formatting, checked-set toggle, commit link label overrides.
- Create `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/useLiveWorkflowViewModel.ts`
  - Owns derived display state from records, selected ids, draft edits, and workspace id.
  - Must call `runViewFromExecution` only through existing projection contracts and must not duplicate `execution-run-view.ts` logic.
- Create `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/styles.ts`
  - Owns the existing `styles` object.
  - This is a mechanical extraction to stop visual style constants from dominating the shell file.
- Create `frontend/tests/unit/v2/live-workflow-view-model.test.ts`
  - Covers record selection, active/pending run preference, pending review counts, sandbox evidence counts, and terminal run auto-tab decision.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
  - Keep public props and export name unchanged.
  - Use `useLiveWorkflowViewModel` for derived values.
  - Import panel-local helpers and styles from `live-workflow/`.
- Modify `frontend/tests/unit/v2/LiveWorkflowPanel.test.tsx`
  - Keep existing smoke/behavior coverage green; update only if import paths or labels require it.
- Modify `backend/tests/architecture/test_dataservice_boundaries.py`
  - Add a repo-level architecture guard for this frontend hotspot.

## Task 1: Architecture And View-Model Tests

**Files:**
- Modify: `backend/tests/architecture/test_dataservice_boundaries.py`
- Create: `frontend/tests/unit/v2/live-workflow-view-model.test.ts`

- [ ] **Step 1: Add failing architecture guard**

Add a test named `test_live_workflow_panel_uses_focused_local_modules`:

```python
def test_live_workflow_panel_uses_focused_local_modules() -> None:
    panel_path = REPO_ROOT / "frontend" / "app" / "(workbench)" / "workspaces" / "[id]" / "components" / "LiveWorkflowPanel.tsx"
    module_root = panel_path.parent / "live-workflow"
    expected_files = {
        "types.ts",
        "utils.ts",
        "useLiveWorkflowViewModel.ts",
        "styles.ts",
    }
    missing = [name for name in sorted(expected_files) if not (module_root / name).exists()]
    assert not missing, f"Missing LiveWorkflowPanel focused modules: {missing}"

    source = panel_path.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 1800
    assert "useLiveWorkflowViewModel" in source
    assert "const styles:" not in source
    assert "function buildEvidenceItems(" not in source
```

- [ ] **Step 2: Verify architecture red**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_live_workflow_panel_uses_focused_local_modules -q
```

Expected: FAIL because the local modules do not exist and the shell is still over 1800 lines.

- [ ] **Step 3: Add failing view-model tests**

Create `frontend/tests/unit/v2/live-workflow-view-model.test.ts` with tests for:

```ts
import { describe, expect, it } from "vitest";
import type { ExecutionRecord } from "@/lib/api/types";
import {
  buildLiveWorkflowViewModel,
  resolveAutoWorkbenchTab,
  selectLiveWorkflowRecords,
} from "@/app/(workbench)/workspaces/[id]/components/live-workflow/useLiveWorkflowViewModel";

// Use small record factories:
// - running record in workspace
// - completed record with one task_report output
// - completed record with sandbox node output

describe("live workflow view model", () => {
  it("orders active workspace records before terminal history", () => {
    const records = selectLiveWorkflowRecords({
      records: [completedRecord, runningRecord],
      workspaceId: "ws-1",
      activeRunId: null,
    });
    expect(records.map((record) => record.id)).toEqual(["run-1", "done-1"]);
  });

  it("derives review and sandbox counts without duplicating run projection", () => {
    const model = buildLiveWorkflowViewModel({
      records: [completedRecord, sandboxRecord],
      workspaceId: "ws-1",
      selectedRunId: "sandbox-1",
      focusedRunId: null,
      activeRunId: null,
      selectedPreviewId: null,
      draftEdits: {},
    });
    expect(model.pendingReviewCount).toBe(1);
    expect(model.sandboxCount).toBe(1);
    expect(model.selectedRecord?.id).toBe("sandbox-1");
  });

  it("moves completed runs with outputs to review and running runs to run tab", () => {
    expect(resolveAutoWorkbenchTab({ selectedRecord: runningRecord, previews: [], reviewItems: [], evidenceItems: [] })).toBe("run");
    expect(resolveAutoWorkbenchTab({ selectedRecord: completedRecord, previews: [preview], reviewItems: [], evidenceItems: [] })).toBe("review");
  });
});
```

- [ ] **Step 4: Verify view-model red**

Run:

```bash
cd frontend && npx vitest run tests/unit/v2/live-workflow-view-model.test.ts
```

Expected: FAIL because `useLiveWorkflowViewModel.ts` does not exist.

## Task 2: Extract View Model, Utils, And Styles

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/types.ts`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/utils.ts`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/useLiveWorkflowViewModel.ts`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/styles.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`

- [ ] **Step 1: Move panel-local types**

Move `EvidenceFilter` and `EvidenceItem` into `types.ts`. Re-export any panel-local model types needed by tests.

- [ ] **Step 2: Move pure helpers**

Move these pure helpers into `utils.ts`:

```ts
buildEvidenceItems
readReviewItems
buildSandboxSummary
isTerminalStatus
toggleChecked
applyDraftLabelsToCommitLinks
generateUUID
statusLabel
qualityGateLabel
qualityGateTone
statusTone
kindLabel
fieldLabel
readString
truncate
formatJsonPreview
formatDateTime
```

Keep behavior byte-for-byte where possible and import the same canonical helpers from existing shared libs.

- [ ] **Step 3: Extract view model**

Implement:

```ts
export function selectLiveWorkflowRecords(...)
export function resolveSelectedLiveWorkflowRecord(...)
export function resolveAutoWorkbenchTab(...)
export function buildLiveWorkflowViewModel(...)
export function useLiveWorkflowViewModel(...)
```

The hook may use `useMemo`, but the pure functions must be directly unit-testable.

- [ ] **Step 4: Move styles**

Move `const styles: Record<string, CSSProperties>` to `styles.ts` and export it.

- [ ] **Step 5: Update shell**

Update `LiveWorkflowPanel.tsx` to import:

```ts
import { styles } from "./live-workflow/styles";
import { useLiveWorkflowViewModel } from "./live-workflow/useLiveWorkflowViewModel";
import { ...helpers } from "./live-workflow/utils";
```

Keep public `LiveWorkflowPanel` props unchanged.

- [ ] **Step 6: Verify green**

Run:

```bash
cd frontend && npx vitest run tests/unit/v2/live-workflow-view-model.test.ts tests/unit/v2/LiveWorkflowPanel.test.tsx
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_live_workflow_panel_uses_focused_local_modules -q
```

Expected: PASS.

## Task 3: Frontend Verification

**Files:**
- Verify touched frontend files.

- [ ] **Step 1: Typecheck**

Run:

```bash
cd frontend && npm run typecheck
```

Expected: PASS.

- [ ] **Step 2: Focused frontend tests**

Run:

```bash
cd frontend && npx vitest run tests/unit/lib/execution-run-view.test.ts tests/unit/v2/live-workflow-view-model.test.ts tests/unit/v2/LiveWorkflowPanel.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Browser verification**

Run the frontend dev server and open the workspace route in the in-app browser when a working local target is available. Verify the workbench panel renders and the main tabs do not crash.

## Task 4: Review, Commit, Push

**Files:**
- All Phase 4 changed files.

- [ ] **Step 1: Graph review**

Run code-review-graph incremental update and change detection. Confirm `LiveWorkflowPanel.tsx` is no longer over the first-stage threshold and no new local module exceeds the same threshold.

- [ ] **Step 2: Diff hygiene**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors and only intended files changed.

- [ ] **Step 3: Commit and push**

Run:

```bash
git add frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx frontend/app/(workbench)/workspaces/[id]/components/live-workflow frontend/tests/unit/v2/live-workflow-view-model.test.ts backend/tests/architecture/test_dataservice_boundaries.py docs/superpowers/plans/2026-05-31-live-workflow-panel-convergence.md
git commit -m "refactor: split live workflow panel view model"
git push
```

Expected: current branch contains the Phase 4 first-stage commit.

## Self-Review

- Spec coverage: implements Phase 4 first-stage `useLiveWorkflowViewModel`, local types, helper extraction, and shell size target below 1800 lines.
- Placeholder scan: no TODO/TBD/fill-later markers.
- Contract check: public `LiveWorkflowPanel` props and `execution-run-view.ts` projection contract remain unchanged.
- Risk: moving the `styles` object is mechanical but large; typecheck plus existing panel smoke tests must verify no import/runtime breakage.

---

## Task 5: Second-Stage Component Split

**Goal:** Finish the Phase 4 architecture-hotspot target for `LiveWorkflowPanel.tsx` by making it a composition shell below 900 lines.

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/WorkbenchHeader.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/InterventionBar.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/OverviewView.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/RunView.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/EvidenceView.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/ReviewView.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/ResultEditor.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/NodeInspector.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/shared.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- Modify: `backend/tests/architecture/test_dataservice_boundaries.py`

- [x] **Step 1: Add second-stage architecture guard**

Add `test_live_workflow_panel_composes_focused_views` requiring focused view modules and `LiveWorkflowPanel.tsx` below 900 lines.

- [x] **Step 2: Verify red**

The guard fails before modules exist, proving it catches the unresolved hotspot.

- [x] **Step 3: Extract focused view modules**

Move current local JSX sections without behavior changes:

- `WorkbenchHeader`
- `InterventionBar`
- `OverviewView`
- `RunView` and team roster
- `EvidenceView`
- `ReviewView`
- `ResultEditor`
- `NodeInspector`
- shared small display primitives

- [x] **Step 4: Keep shell responsibilities narrow**

`LiveWorkflowPanel.tsx` now owns store subscriptions, local state, effects, commit handling, intervention handling, and high-level tab composition only.

- [x] **Step 5: Verify focused behavior**

Run:

```bash
cd frontend && npx eslint 'app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx' 'app/(workbench)/workspaces/[id]/components/live-workflow/'*.tsx
cd frontend && npm run typecheck
cd frontend && npx vitest run tests/unit/lib/execution-run-view.test.ts tests/unit/v2/live-workflow-view-model.test.ts tests/unit/v2/LiveWorkflowPanel.test.tsx
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_live_workflow_panel_composes_focused_views tests/architecture/test_dataservice_boundaries.py::test_live_workflow_panel_uses_focused_local_modules -q
cd frontend && npx playwright test tests/e2e/v2/deep-research-flow.spec.ts --project=v2
```

Expected: all pass.

## Second-Stage Self-Review

- `LiveWorkflowPanel.tsx` target: below 900 lines; actual shell is about 530 lines after extraction.
- Contract check: public props and store contracts remain unchanged.
- Projection check: no duplicated `execution-run-view.ts` logic was added; view model remains the only derived-data layer.
- Risk: mostly mechanical JSX moves; covered by existing panel interaction tests, typecheck, architecture guard, and workspace E2E.
