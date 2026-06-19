# Wenjin Global UIUX Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first production slice of the global UIUX redesign by polishing the workspace shell and making Prism's expandable PDF preview stage a first-class Overleaf-like editing mode.

**Architecture:** Keep the current Workbench and Prism architecture. Reuse `--wjn-*` tokens, `WorkspaceChrome`, `LatexEditorShell`, `LatexEditorPanes`, `LatexPdfPreview`, and existing Prism review stores. Add small UI state and props around the existing PDF compare mode instead of rewriting the LaTeX editor or API contracts.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind, Zustand, Vitest, Testing Library, pdfjs-dist.

---

## File Structure

- Modify `frontend/app/globals.css`: add reusable quiet panel, stage button, PDF toolbar, and Prism studio classes using `--wjn-*`.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/shell/WorkspaceChrome.tsx`: polish the surface switch and add Lucide icons.
- Modify `frontend/app/(workbench)/workspaces/[id]/prism/page.tsx`: wrap Prism in a studio shell and preserve loading/error/empty state behavior.
- Modify `frontend/app/(workbench)/workspaces/[id]/prism/PrismContextRail.tsx`: restyle the context rail with tokenized review/evidence chips.
- Modify `frontend/components/latex/LatexEditorShell.tsx`: pass a user-facing stage label into the panes and keep compile opening compare mode.
- Modify `frontend/components/latex/latex-editor/LatexEditorPanes.tsx`: add PDF stage toolbar controls for compile, sync, fit, page, zoom, focus, and collapse.
- Modify tests in `frontend/tests/unit/v2/prism-surface.test.tsx`, `frontend/tests/unit/v2/latex-editor-panes.test.tsx`, and `frontend/tests/unit/v2/latex-editor-prism-shell.test.tsx`.

## Task 1: Stabilize Existing Prism Surface Tests

**Files:**
- Modify: `frontend/tests/unit/v2/prism-surface.test.tsx`

- [ ] **Step 1: Update loading assertion**

Replace the stale English loading assertion with:

```ts
expect(screen.getByTestId("workspace-surface-state")).toHaveTextContent(
  "正在打开论文写作台",
);
expect(screen.getByTestId("workspace-surface-state")).toHaveTextContent(
  "正在加载工作区主稿和待确认修改。",
);
```

- [ ] **Step 2: Update empty-state assertion**

Replace the stale English empty assertion with:

```ts
expect(await screen.findByText("还没有绑定写作项目")).toBeInTheDocument();
expect(
  screen.getByText("从 Workbench 启动论文写作任务后，这里会自动打开主稿。"),
).toBeInTheDocument();
```

- [ ] **Step 3: Scope duplicate review text assertion**

Use:

```ts
expect(screen.getAllByText("待确认").length).toBeGreaterThan(0);
```

- [ ] **Step 4: Verify**

Run:

```bash
cd frontend && npx vitest run tests/unit/v2/prism-surface.test.tsx
```

Expected: existing Prism page tests pass before adding new stage assertions.

## Task 2: Add Failing Tests For Prism PDF Preview Stage

**Files:**
- Modify: `frontend/tests/unit/v2/latex-editor-panes.test.tsx`
- Modify: `frontend/tests/unit/v2/latex-editor-prism-shell.test.tsx`

- [ ] **Step 1: Add PDF stage control test**

In `latex-editor-panes.test.tsx`, import `fireEvent` and add:

```tsx
it("renders an Overleaf-like PDF preview stage with compile, view, page, zoom, sync, and collapse controls", () => {
  renderPanes("compare");

  expect(screen.getByRole("toolbar", { name: "PDF 预览台" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重新编译 PDF" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "同步滚动" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("button", { name: "适合宽度" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("button", { name: "整页" })).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByLabelText("PDF 页码")).toHaveValue(1);
  expect(screen.getByText("/ 1")).toBeInTheDocument();
  expect(screen.getByLabelText("PDF 缩放")).toHaveValue(100);
  expect(screen.getByRole("button", { name: "展开 PDF 预览" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "收起 PDF" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Add compile callback test**

Add:

```tsx
it("recompiles from the PDF preview stage toolbar", () => {
  handlers.onCompile.mockClear();
  renderPanes("compare");

  fireEvent.click(screen.getByRole("button", { name: "重新编译 PDF" }));

  expect(handlers.onCompile).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 3: Add shell stage label coverage**

Update the `LatexEditorPanes` mock in `latex-editor-prism-shell.test.tsx` to render `stageLabel`, then extend the compile test with:

```ts
expect(screen.getByTestId("stage-label")).toHaveTextContent("PDF 预览台");
```

- [ ] **Step 4: Verify RED**

Run:

```bash
cd frontend && npx vitest run tests/unit/v2/latex-editor-panes.test.tsx tests/unit/v2/latex-editor-prism-shell.test.tsx
```

Expected: fail because production code does not yet expose the PDF stage toolbar or `stageLabel`.

## Task 3: Implement Prism PDF Stage Controls

**Files:**
- Modify: `frontend/components/latex/LatexEditorShell.tsx`
- Modify: `frontend/components/latex/latex-editor/LatexEditorPanes.tsx`
- Modify: `frontend/app/globals.css`

- [ ] **Step 1: Pass `stageLabel` from `LatexEditorShell`**

Add:

```ts
const stageLabel = surfaceMode === "compare" ? "PDF 预览台" : "编辑台";
```

Pass `stageLabel={stageLabel}` to `LatexEditorPanes`.

- [ ] **Step 2: Add local PDF stage state and controls**

In `LatexEditorPanes`, add state for `pdfFitMode`, `pdfPage`, `pdfZoom`, `syncScroll`, and `pdfFocused`. Replace the PDF header with a `role="toolbar" aria-label="PDF 预览台"` toolbar exposing buttons and inputs for `重新编译 PDF`, `同步滚动`, `适合宽度`, `整页`, `PDF 页码`, `PDF 缩放`, `展开 PDF 预览`, and `收起 PDF`.

- [ ] **Step 3: Rebalance expanded panel sizes**

Use `pdfFocused` to shift compare mode from roughly `54/46` editor/PDF to `34/66`.

- [ ] **Step 4: Add global classes**

Add `.wjn-icon-button`, `.wjn-stage-button`, `.wjn-stage-field`, and `.wjn-prism-pdf-toolbar` to `globals.css`, using only `--wjn-*` tokens.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
cd frontend && npx vitest run tests/unit/v2/latex-editor-panes.test.tsx tests/unit/v2/latex-editor-prism-shell.test.tsx
```

Expected: pass.

## Task 4: Polish Workspace Chrome And Prism Studio Composition

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/shell/WorkspaceChrome.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/prism/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/prism/PrismContextRail.tsx`
- Modify: `frontend/app/globals.css`
- Modify: `frontend/tests/unit/v2/prism-surface.test.tsx`

- [ ] **Step 1: Add icons to surface tabs**

Use `PanelsTopLeft` for Workbench and `BookOpenText` for Prism. Keep existing href, `aria-selected`, and count badge behavior.

- [ ] **Step 2: Add Prism studio shell**

Wrap the loaded Prism branch with:

```tsx
<div data-testid="prism-studio-shell" className="wjn-prism-studio flex h-full min-h-0 flex-col">
  <PrismContextRail surface={surface} />
  <LatexEditorShell ... />
</div>
```

- [ ] **Step 3: Tokenize `PrismContextRail` chips**

Use `--wjn-review`, `--wjn-review-soft`, `--wjn-evidence`, `--wjn-evidence-soft`, and `--wjn-line`.

- [ ] **Step 4: Add shell classes**

Add `.wjn-prism-studio` and `.wjn-prism-context-rail` to `globals.css`.

- [ ] **Step 5: Add page test assertion**

In `prism-surface.test.tsx`, assert:

```ts
expect(await screen.findByTestId("prism-studio-shell")).toBeInTheDocument();
```

- [ ] **Step 6: Verify**

Run:

```bash
cd frontend && npx vitest run tests/unit/v2/prism-surface.test.tsx
```

Expected: pass.

## Task 5: Verification And Visual QA

**Files:**
- No source edits unless checks expose issues.

- [ ] **Step 1: Focused checks**

Run:

```bash
cd frontend && npm run typecheck
cd frontend && npx vitest run tests/unit/v2/prism-surface.test.tsx tests/unit/v2/latex-editor-panes.test.tsx tests/unit/v2/latex-editor-prism-shell.test.tsx tests/unit/v2/WorkspaceChromeAuth.test.tsx
```

- [ ] **Step 2: Broader unit check**

Run:

```bash
cd frontend && npm run test:unit
```

- [ ] **Step 3: Visual QA**

Start:

```bash
cd frontend && npm run dev -- --hostname 127.0.0.1 --port 3001
```

Inspect `/workspaces/ws-1/prism` and `/workspaces/ws-1` at desktop and mobile widths. Confirm no text overlap, no cramped PDF/editor columns, visible top chrome, visible Prism PDF controls, and no decorative orb/purple/ancient-style regression.

- [ ] **Step 4: Commit**

Stage only files from this plan and commit:

```bash
git commit -m "feat: polish prism pdf preview stage"
```

## Self-Review

- Spec coverage: This plan covers the first implementable slice: global shell polish, Prism Editorial Studio, Overleaf-like expandable PDF preview stage, token discipline, and self-check. Rooms and LiveWorkflow deep redesign remain separate follow-up slices.
- Placeholder scan: No placeholders or undefined future tasks are present.
- Type consistency: `surfaceMode` keeps existing `"edit"` and `"compare"` behavior; new `stageLabel` and PDF stage controls are consistently named across tests and code.
