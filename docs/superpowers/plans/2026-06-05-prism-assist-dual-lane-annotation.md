# Prism Assist Manuscript Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Prism's Overleaf-like editing surface with a floating AI assist workflow for Word-like annotations, local section rewrite, document rewrite, and unified diff/apply/revert.

**Architecture:** Keep `LatexEditorShell` as orchestration owner and reuse `useLatexFeedbackWorkflow` for annotation/rewrite business logic. Replace the permanent Inspector-first UX with `PrismFloatingAssist` and `PrismAssistPanel`; local rewrites stay lightweight, while document rewrites call the existing `prism_selection_optimize` path with explicit context requirements.

**Tech Stack:** Next.js 16, React 19, TypeScript, Vitest, Playwright e2e, existing LaTeX/Prism API contracts.

**Implementation Result:** The fixed `LatexInspector` rail was removed. Prism now uses `PrismFloatingAssist` plus `PrismAssistPanel` as the single assist surface, including annotation composer/list, local rewrite preview, document rewrite entry, compile status, file protection, pending write review, apply, and revert. Verified with Vitest, Playwright e2e, production build, Docker Compose rebuild, and Chrome manual workflow.

---

## File Map

- Create `frontend/components/latex/latex-editor/prismAssistRouting.ts`  
  Deterministic quick/deep route selector.

- Create `frontend/components/latex/latex-editor/PrismFloatingAssist.tsx`  
  Floating AI pill and selection action bubble. Pure UI.

- Create `frontend/components/latex/latex-editor/PrismAnnotationComposer.tsx`  
  Draft comment + scope selector + save/quick/deep actions.

- Create `frontend/components/latex/latex-editor/PrismAnnotationList.tsx`  
  Current file annotation list with focus, quick rewrite, deep assist, delete.

- Create `frontend/components/latex/latex-editor/PrismAssistPanel.tsx`  
  Floating assist drawer/panel composed from composer, annotation list, rewrite preview, and job/compile status.

- Modify `frontend/components/latex/latex-editor/types.ts`  
  Narrow `PrismSurfaceMode` to `edit | compare`.

- Modify `frontend/components/latex/latex-editor/LatexEditorPanes.tsx`  
  Remove global four-mode switcher and expose editor/PDF only.

- Modify `frontend/components/latex/LatexEditorShell.tsx`  
  Wire floating assist, panel state, workflow actions, and no fixed Inspector by default.

- Modify `frontend/components/latex/latex-editor/useLatexFeedbackWorkflow.ts`  
  Add quick rewrite helper for draft selection and expose clearer action names without duplicating backend logic.

- Modify tests under `frontend/tests/unit/v2/` and `frontend/tests/e2e/` for the new UX.

---

## Task 1: Route Selector

**Files:**
- Create: `frontend/components/latex/latex-editor/prismAssistRouting.ts`
- Test: `frontend/tests/unit/v2/prism-assist-routing.test.ts`

- [ ] **Step 1: Write failing routing tests**

```ts
import { describe, expect, it } from "vitest";

import { choosePrismAssistRoute } from "@/components/latex/latex-editor/prismAssistRouting";

describe("choosePrismAssistRoute", () => {
  it("uses quick rewrite for local small selections", () => {
    expect(
      choosePrismAssistRoute({
        selectedTextLength: 320,
        comment: "更学术一点",
        scope: "selection",
      }),
    ).toBe("quick");
  });

  it("uses deep assist for large selections", () => {
    expect(
      choosePrismAssistRoute({
        selectedTextLength: 3000,
        comment: "整体优化",
        scope: "section",
      }),
    ).toBe("deep");
  });

  it("uses deep assist for manuscript-level intent", () => {
    expect(
      choosePrismAssistRoute({
        selectedTextLength: 500,
        comment: "检查贡献和审稿风险",
        scope: "selection",
      }),
    ).toBe("deep");
  });

  it("respects explicit route overrides", () => {
    expect(
      choosePrismAssistRoute({
        selectedTextLength: 4000,
        comment: "压缩一下",
        scope: "section",
        force: "quick",
      }),
    ).toBe("quick");
  });
});
```

- [ ] **Step 2: Run test and verify RED**

Run: `cd frontend && npm run test -- tests/unit/v2/prism-assist-routing.test.ts`

Expected: FAIL because `prismAssistRouting` does not exist.

- [ ] **Step 3: Implement route selector**

```ts
export type PrismAssistRoute = "quick" | "deep";

export function choosePrismAssistRoute(input: {
  selectedTextLength: number;
  comment: string;
  scope: "selection" | "section";
  force?: PrismAssistRoute;
}): PrismAssistRoute {
  if (input.force) {
    return input.force;
  }
  if (input.selectedTextLength > 2500) {
    return "deep";
  }
  if (input.scope === "section" && input.selectedTextLength > 1200) {
    return "deep";
  }
  if (/整体|全文|多节|文献|审稿|投稿|贡献|实验|证据|结构/.test(input.comment)) {
    return "deep";
  }
  return "quick";
}
```

- [ ] **Step 4: Run test and verify GREEN**

Run: `cd frontend && npm run test -- tests/unit/v2/prism-assist-routing.test.ts`

Expected: PASS.

---

## Task 2: Remove Four-Mode Switcher

**Files:**
- Modify: `frontend/components/latex/latex-editor/types.ts`
- Modify: `frontend/components/latex/latex-editor/LatexEditorPanes.tsx`
- Test: `frontend/tests/unit/v2/latex-editor-panes.test.tsx`

- [ ] **Step 1: Write failing pane tests**

Add assertions:

```ts
expect(screen.queryByRole("button", { name: "编辑" })).not.toBeInTheDocument();
expect(screen.queryByRole("button", { name: "对照" })).not.toBeInTheDocument();
expect(screen.queryByRole("button", { name: "审阅" })).not.toBeInTheDocument();
expect(screen.queryByRole("button", { name: "专注" })).not.toBeInTheDocument();
expect(screen.getByText("PDF 对照按需打开")).toBeInTheDocument();
```

- [ ] **Step 2: Run test and verify RED**

Run: `cd frontend && npm run test -- tests/unit/v2/latex-editor-panes.test.tsx`

Expected: FAIL because the four buttons still render.

- [ ] **Step 3: Narrow surface type**

Change `PrismSurfaceMode` to:

```ts
export type PrismSurfaceMode = "edit" | "compare";
```

- [ ] **Step 4: Remove `surfaceModeOptions` UI**

In `LatexEditorPanes.tsx`, remove imports and button map for `编辑 / 对照 / 审阅 / 专注`. Keep a simple status row:

```tsx
<div className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--wjn-line)] bg-white px-3">
  <p className="text-xs text-[var(--wjn-text-muted)]">
    {surfaceMode === "compare" ? "正在显示 PDF 对照" : "PDF 对照按需打开"}
  </p>
</div>
```

- [ ] **Step 5: Remove focus mode checks**

In `LatexEditorShell.tsx`, remove `surfaceMode !== "focus"` branches and always render `LatexResourceRail`.

- [ ] **Step 6: Run tests**

Run: `cd frontend && npm run test -- tests/unit/v2/latex-editor-panes.test.tsx tests/unit/v2/latex-editor-prism-shell.test.tsx`

Expected: PASS after updating affected mocks/assertions.

---

## Task 3: Floating Assist UI

**Files:**
- Create: `frontend/components/latex/latex-editor/PrismFloatingAssist.tsx`
- Test: `frontend/tests/unit/v2/prism-floating-assist.test.tsx`

- [ ] **Step 1: Write failing UI tests**

Test cases:

```ts
render(<PrismFloatingAssist selectedCharacterCount={0} pendingRewriteCount={0} runningJobCount={0} hasError={false} onOpen={vi.fn()} onAnnotate={vi.fn()} onQuickRewrite={vi.fn()} onDeepAssist={vi.fn()} />);
expect(screen.getByRole("button", { name: "AI 改稿" })).toBeInTheDocument();

render(<PrismFloatingAssist selectedCharacterCount={42} pendingRewriteCount={0} runningJobCount={0} hasError={false} onOpen={vi.fn()} onAnnotate={vi.fn()} onQuickRewrite={vi.fn()} onDeepAssist={vi.fn()} />);
expect(screen.getByText("已选 42 字")).toBeInTheDocument();
expect(screen.getByRole("button", { name: "批注" })).toBeInTheDocument();
expect(screen.getByRole("button", { name: "改这段" })).toBeInTheDocument();
expect(screen.getByRole("button", { name: "修改全文" })).toBeInTheDocument();
```

- [ ] **Step 2: Run test and verify RED**

Run: `cd frontend && npm run test -- tests/unit/v2/prism-floating-assist.test.tsx`

Expected: FAIL because component does not exist.

- [ ] **Step 3: Implement component**

Use `Sparkles`, `MessageSquareText`, and `Users` icons. Render:

- a fixed bottom-right pill button labeled by state;
- a compact action row when `selectedCharacterCount > 0`;
- no business logic inside the component.

- [ ] **Step 4: Run test and verify GREEN**

Run: `cd frontend && npm run test -- tests/unit/v2/prism-floating-assist.test.tsx`

Expected: PASS.

---

## Task 4: Assist Panel Components

**Files:**
- Create: `frontend/components/latex/latex-editor/PrismAnnotationComposer.tsx`
- Create: `frontend/components/latex/latex-editor/PrismAnnotationList.tsx`
- Create: `frontend/components/latex/latex-editor/PrismAssistPanel.tsx`
- Test: `frontend/tests/unit/v2/prism-assist-panel.test.tsx`

- [ ] **Step 1: Write failing panel tests**

Test behaviors:

- Closed panel renders nothing.
- Open panel has dialog name `AI 改稿`.
- Composer has textarea placeholder `写下批注或修改要求...`.
- Save action calls `onSaveComment`.
- Quick action calls `onQuickRewrite`.
- Deep action calls `onDeepAssist`.
- Annotation list shows saved comments and action buttons.
- Rewrite preview area renders when `rewritePreview` prop exists.

- [ ] **Step 2: Run test and verify RED**

Run: `cd frontend && npm run test -- tests/unit/v2/prism-assist-panel.test.tsx`

Expected: FAIL because components do not exist.

- [ ] **Step 3: Implement composer**

Props:

```ts
{
  contextText: string;
  draftComment: string;
  scope: "selection" | "section";
  canCreate: boolean;
  busy: boolean;
  onDraftChange(comment: string): void;
  onScopeChange(scope: "selection" | "section"): void;
  onSaveComment(): void;
  onQuickRewrite(): void;
  onDeepAssist(): void;
}
```

- [ ] **Step 4: Implement annotation list**

Props use `LatexFeedbackItem[]` and actions:

```ts
onFocus(item)
onQuickRewrite(item)
onDeepAssist(item)
onRemove(id)
```

Keep labels short:

- `定位`
- `改这段`
- `修改全文`
- `删除`

- [ ] **Step 5: Implement assist panel**

Render as fixed right drawer/panel over Prism content:

- `role="dialog" aria-label="AI 改稿"`
- close button `关闭 AI 改稿`
- composer section
- annotation list section
- rewrite preview section using existing `LatexRewritePreviewPanel`
- async job status summary via plain text props in first version

- [ ] **Step 6: Run test and verify GREEN**

Run: `cd frontend && npm run test -- tests/unit/v2/prism-assist-panel.test.tsx`

Expected: PASS.

---

## Task 5: Workflow Action Split

**Files:**
- Modify: `frontend/components/latex/latex-editor/useLatexFeedbackWorkflow.ts`
- Test: existing and new tests under `frontend/tests/unit/v2/`

- [ ] **Step 1: Add tests for quick vs deep actions**

In the shell/panel tests, verify:

- `改这段` uses local rewrite action.
- `修改全文` uses async launch action.
- `批注` only saves annotation.

- [ ] **Step 2: Implement `addFeedbackAndQuickRewrite`**

Add a callback:

```ts
const addFeedbackAndQuickRewrite = useCallback(async () => {
  const item = await createFeedbackFromSelection(true);
  if (!item) return;
  setFeedbackItems((prev) => [...prev, item]);
  setActiveFeedbackId(item.id);
  setFeedbackDraftComment("");
  setPdfDraftSelection(null);
  await rewriteFromFeedback(item);
}, [...]);
```

- [ ] **Step 3: Keep existing async action**

Rename UI-facing action only:

```ts
deepAssist: launchPrismOptimizationFromFeedback
```

Do not remove `launchPrismOptimization` until all callsites are updated.

- [ ] **Step 4: Run targeted tests**

Run: `cd frontend && npm run test -- tests/unit/v2/latex-editor-prism-shell.test.tsx tests/unit/v2/prism-assist-panel.test.tsx`

Expected: PASS.

---

## Task 6: Wire Prism Shell

**Files:**
- Modify: `frontend/components/latex/LatexEditorShell.tsx`
- Modify: `frontend/components/latex/latex-editor/LatexInspector.tsx` only if needed for removal compatibility.
- Test: `frontend/tests/unit/v2/latex-editor-prism-shell.test.tsx`

- [ ] **Step 1: Write shell tests**

Assert:

- fixed Inspector is not visible by default.
- floating `AI 改稿` is visible.
- selecting text state from mocked workflow shows `批注`, `改这段`, `修改全文`.
- compile still changes surface mode to `compare`.

- [ ] **Step 2: Run test and verify RED**

Run: `cd frontend && npm run test -- tests/unit/v2/latex-editor-prism-shell.test.tsx`

Expected: FAIL on missing floating assist or fixed Inspector still present.

- [ ] **Step 3: Add panel open state**

In `LatexEditorShell`:

```ts
const [isAssistOpen, setIsAssistOpen] = useState(false);
```

Open assist when:

- user clicks floating pill;
- selection bubble `批注` is clicked;
- quick/deep actions need to show status;
- compile failure should still open compile status, either in assist panel or current compile dialog.

- [ ] **Step 4: Stop rendering fixed Inspector by default**

Remove the always-rendered `LatexInspector` from the main flex row. Replace with `PrismAssistPanel` after `LatexEditorPanes` so it overlays.

- [ ] **Step 5: Keep compile clarity**

`compileWithVisibleFeedback` continues:

```ts
setSurfaceMode("compare");
setIsAssistOpen(true);
```

The assist panel should show compile status only when relevant.

- [ ] **Step 6: Run targeted tests**

Run: `cd frontend && npm run test -- tests/unit/v2/latex-editor-prism-shell.test.tsx frontend/tests/unit/v2/latex-editor-panes.test.tsx`

Expected: PASS.

---

## Task 7: E2E And Browser Coverage

**Files:**
- Modify: `frontend/tests/e2e/prism-surface.spec.ts`
- Possibly create: `frontend/tests/e2e/v2/prism-assist-flow.spec.ts`

- [ ] **Step 1: Update e2e assertions**

Assert:

- no `编辑 / 对照 / 审阅 / 专注` mode buttons.
- `AI 改稿` visible.
- compile opens PDF compare and compile status.
- resource rail still works.

- [ ] **Step 2: Run e2e**

Run: `cd frontend && npm run test:e2e -- --project=v2 tests/e2e/prism-surface.spec.ts`

Expected: PASS.

- [ ] **Step 3: Chrome walkthrough**

With docker compose local frontend build:

1. Open `http://localhost:2026/workspaces/<id>/prism`.
2. Confirm no four-mode switcher.
3. Confirm `AI 改稿` floating entry.
4. Select text in editor.
5. Confirm selection bubble.
6. Open assist panel.
7. Save annotation.
8. Trigger quick rewrite and inspect diff/apply controls if backend credentials are available.
9. Compile and confirm PDF opens.
10. Check browser console has no errors.

---

## Task 8: Final Verification

Run:

```bash
cd frontend && npm run typecheck
cd frontend && npm run build
cd frontend && npm run test
cd frontend && npm run test:e2e -- --project=v2 tests/e2e/prism-surface.spec.ts
```

Then rebuild frontend container:

```bash
docker compose -f docker-compose.yml -f docker-compose.local-build.yml build frontend
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --no-deps frontend
docker compose ps frontend nginx gateway dataservice
```

Expected:

- Typecheck exits 0.
- Build exits 0.
- Unit suite exits 0.
- E2E exits 0.
- Compose services are healthy.
- Chrome walkthrough passes without console error/warning.

---

## Self-Review

Spec coverage:

- Floating AI entry: Task 3 and Task 6.
- Word-like annotation: Task 4 and Task 5.
- Local rewrite path: Task 1, Task 5, Task 6.
- Document rewrite path: Task 1, Task 4, Task 5.
- Overleaf-like editor simplification: Task 2 and Task 7.
- Browser testing: Task 7 and Task 8.

Placeholder scan:

- No TBD/TODO placeholders.
- Each implementation task has exact files and commands.

Type consistency:

- `PrismAssistRoute` is defined in Task 1 and used only as `"quick" | "deep"`.
- `PrismSurfaceMode` is narrowed to `"edit" | "compare"` and focus/review modes are removed from shell rendering.

Risk:

- The largest risk is moving `LatexInspector` content without losing compile/review visibility. Mitigation: first implementation keeps business logic in `useLatexFeedbackWorkflow` and moves presentation only.
