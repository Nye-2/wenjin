# Prism Assist Manuscript Rewrite Design

> 状态：已实现并通过验证  
> 日期：2026-06-05  
> 范围：WenjinPrism LaTeX editor, PDF preview, annotation/rewrite UX, local rewrite, document rewrite, Prism review queue  
> 目标：把 Prism 的“划线点评、批注、改这段、修改全文、diff/apply/revert”收敛为一套轻量、成熟、可追踪的编辑器内工作流。

## 1. Product Goal

Prism should feel like an Overleaf-style editor with Wenjin's research assistance layered on demand:

- The main surface stays quiet: file tree, source editor, optional PDF preview, compile.
- AI assistance is available without permanently occupying the right side.
- Text/PDF selection creates Word-like annotations that can later drive local rewrite suggestions.
- Small local edits use only the current manuscript selection, file content, and annotation.
- Whole-document edits use the Lead Agent path with bounded workspace, Library, and sandbox context, while Prism still feels like the active editor.
- Every rewrite still goes through diff preview, explicit apply, and revert.

## 2. UX Principles

1. **Editor first**  
   Prism should not show four global modes (`编辑 / 对照 / 审阅 / 专注`). The user edits source, optionally opens PDF, and summons assist only when needed.

2. **Selection creates intent**  
   When the user selects text in TeX or PDF, a compact selection bubble appears near the editor/PDF area with `批注`, `改这段`, and `修改全文`.

3. **Annotation is the common object**  
   A saved comment and a local rewrite request operate on the same annotation record.

4. **Context matches intent**  
   `改这段` stays lightweight. `修改全文` can use manuscript context, workspace history, related documents, pending review summary, and sandbox artifacts.

5. **Review before write**  
   No rewrite overwrites manuscript text without showing a diff and requiring the user to apply it.

6. **Mature floating entry**  
   The always-available entry is a restrained floating `AI 改稿` pill, not a large customer-service-style ball.

## 3. Current Architecture To Reuse

Existing frontend and backend already provide most primitives:

- `useLatexPdfSelectionMapping` maps TeX/PDF selections and syncs anchors.
- `useLatexFeedbackCreation` builds `LatexFeedbackItem` records.
- `useLatexFeedbackWorkflow` manages feedback state, local rewrite preview/apply/revert, document rewrite launch, and rewrite candidate state.
- `previewLatexFeedbackRewrite` calls `POST /feedback/rewrite/preview`.
- `applyLatexFeedbackRewrite` calls `POST /feedback/rewrite/apply`.
- `revertLatexFeedbackRewrite` calls `POST /feedback/rewrite/revert`.
- `launchPrismOptimizationFromFeedback` starts the existing `prism_selection_optimize` capability through chat/lead orchestration.
- `PrismSelectionOptimizerSubagent` already rewrites selected text and stages a reviewable file change.

This feature should reorganize and expose these primitives. It should not create another rewrite backend, a second annotation store, or a second Workbench execution model.

## 4. Rewrite Context Model

### 4.1 Local Rewrite

Purpose: local, low-latency editing help inside Prism.

Use when:

- Selection is small or moderate.
- User wants phrasing, concision, clarity, tone, or local logic improvement.
- Scope is `selection` or a small containing section.
- Expected result is available in seconds.

Implementation:

- Creates or reuses a `LatexFeedbackItem`.
- Calls `previewLatexFeedbackRewrite`.
- Shows `LatexRewritePreviewPanel` inside the floating assist panel.
- User explicitly applies via `applyLatexFeedbackRewrite`.
- User can revert via `revertLatexFeedbackRewrite`.

Rules:

- Do not create a Workbench run.
- Do not send a Chat Agent message.
- Do not show team progress.
- Keep all status local to Prism.
- If response exceeds the timeout threshold or returns a structural/complexity failure, ask the user to use `修改全文` or narrow the request.

### 4.2 Document Rewrite

Purpose: heavier manuscript work that benefits from the Lead Agent/team infrastructure and broader context.

Use when:

- User explicitly selects `修改全文`.
- Scope is large or cross-section.
- Multiple annotations should be handled together.
- The request requires literature/context/argument-level judgment.
- Quick rewrite fails or times out and user accepts escalation.

Implementation:

- Creates or reuses the same `LatexFeedbackItem`.
- Calls the existing launch path for `prism_selection_optimize`.
- Tracks a local `PrismOptimizationJob` in Prism.
- Workbench can still record the run, but Prism presents only a compact job state.
- Output is staged as Prism review queue changes, not applied directly.

Rules:

- Reuse the existing Workbench/Lead Agent execution path for document-level work.
- Do not expose the full Workbench UI inside Prism.
- Do not require the user to manually write a chat prompt.
- Keep the Prism status copy lightweight: `团队处理中`, `待确认写入`, `失败，可重试`.

## 5. Routing Policy

The UX exposes explicit commands, but the default route for `改这段` should be deterministic:

```ts
type PrismAssistRoute = "quick" | "deep";

function choosePrismAssistRoute(input: {
  selectedTextLength: number;
  comment: string;
  scope: "selection" | "section";
  force?: PrismAssistRoute;
}): PrismAssistRoute {
  if (input.force) return input.force;
  if (input.selectedTextLength > 2500) return "deep";
  if (input.scope === "section" && input.selectedTextLength > 1200) return "deep";
  if (/整体|全文|多节|文献|审稿|投稿|贡献|实验|证据|结构/.test(input.comment)) return "deep";
  return "quick";
}
```

In the first implementation, this can be a small frontend utility. It should be covered by unit tests. The user can override via explicit `改这段` or `修改全文`.

## 6. Interaction Design

### 6.1 Main Prism Surface

Remove the global mode switcher from `LatexEditorPanes`.

Main states:

- `Editor only`: file tree + source editor.
- `Editor + PDF`: file tree + source editor + PDF preview.

Controls:

- `打开 PDF` appears in the editor panel when PDF is closed.
- `收起 PDF` appears in the PDF panel when PDF is open.
- Compile still opens PDF preview and shows compile status.
- Review and Agent tasks move into floating assist.

### 6.2 Selection Bubble

Appears when `hasFeedbackSelection` is true.

Buttons:

- `批注`: opens the annotation composer.
- `改这段`: creates a temporary default annotation if needed and runs quick rewrite.
- `修改全文`: creates a temporary default annotation if needed and starts document rewrite.

Behavior:

- Bubble is positioned near the editor/PDF surface, not on top of selected text if exact positioning is too expensive.
- It may be fixed near the lower-right of the editor pane for the first version.
- It hides when selection is cleared and no draft is active.

### 6.3 Floating AI Pill

Always visible in Prism while a project is loaded.

States:

- Default: `AI 改稿`
- With selection: `已选 N 字`
- With pending diff: `待应用修改`
- With async job: `团队处理中`
- With error: `需要处理`

Click opens the assist panel.

### 6.4 Assist Panel

This replaces the always-open `LatexInspector` as the primary user-facing assist surface.

Sections:

- Annotation composer
- Current file annotations
- Rewrite preview
- Pending write review queue
- File protection and recent quick-rewrite undo
- Async job status
- Compile details if opened from compile failure/status

The panel is a floating drawer/popover over the editor, not a permanent right rail by default. It should be closable and should not alter editor/PDF layout width unless explicitly docked later.

Implemented state: the old fixed inspector content has been moved into `PrismAssistPanel`; Prism exposes one user-facing assist model.

## 7. Data Model

The canonical record remains `LatexFeedbackItem`.

Frontend view model:

```ts
type PrismAnnotationStatus =
  | "idle"
  | "commented"
  | "previewing"
  | "ready_to_apply"
  | "applied"
  | "team_running"
  | "failed";

interface PrismAnnotationView {
  id: string;
  filePath: string;
  selectedText: string;
  comment: string;
  source: "tex" | "pdf";
  scope: "selection" | "section";
  status: PrismAnnotationStatus;
  lastError?: string;
  hasRewritePreview: boolean;
  hasAppliedRewrite: boolean;
}
```

No database migration is required in the first implementation. Persisted feedback continues to use project metadata through existing feedback endpoints.

## 8. Component Architecture

Create or refactor toward these focused components:

- `PrismFloatingAssist.tsx`  
  Floating pill and selection bubble. No rewrite logic.

- `PrismAssistPanel.tsx`  
  Floating panel containing composer, annotation list, rewrite preview, async status. Receives state/actions from the hook.

- `PrismAnnotationList.tsx`  
  Current-file annotation list with focus, quick rewrite, deep assist, delete.

- `PrismAnnotationComposer.tsx`  
  Draft comment textarea, scope selector, save/quick/deep actions.

- `prismAssistRouting.ts`  
  Deterministic quick/deep routing utility.

The previous fixed inspector component was removed after review queue, file protection, quick rewrite, document rewrite, and compile status were all moved into `PrismAssistPanel`. Prism now has one assist surface instead of a fixed right rail plus floating controls.

## 9. State Ownership

`LatexEditorShell` remains the orchestrator for project state.

`useLatexFeedbackWorkflow` remains the business hook for:

- annotation creation
- quick rewrite
- async launch
- preview/apply/revert
- status/error

The hook should expose enough actions for the new UI:

- `addFeedbackOnly`
- `addFeedbackAndQuickRewrite`
- `quickRewriteFeedback`
- `launchPrismOptimization`
- `applyRewrite`
- `cancelRewritePreview`
- `removeFeedback`
- `focusFeedback`
- `setFeedbackDraftComment`
- `setFeedbackScope`

If names are changed, keep the implementation internally small and update tests. Avoid introducing a parallel `usePrismAssist` hook unless the existing hook becomes too large after extraction.

## 10. Error Handling

Quick rewrite:

- Mapping failure: show `选区尚未映射到 TeX，无法直接改写`.
- LLM failure: show `改这段失败` with retry.
- Timeout: show `改这段耗时较长，是否修改全文处理？`.
- Structural guard failure: show `改写未通过结构安全校验，请重生成或修改全文`.
- Stale candidate: clear preview and show `正文已变化，请重新生成`.

Deep assist:

- Missing workspace: show `当前项目尚未关联工作区`.
- Chat/lead busy: show `团队正在处理其他任务，请稍后`.
- Launch failure: keep annotation and allow retry.
- Job completion: surface review queue state, not raw execution internals.

Apply/revert:

- Preserve existing signature/hash validation.
- Preserve compile guard rollback behavior.
- Never apply hidden async output without explicit user confirmation.

## 11. Testing Plan

Unit tests:

- `prismAssistRouting.test.ts`
  - small selection routes quick.
  - large selection routes deep.
  - global-paper intent routes deep.
  - explicit force overrides.

- `prism-floating-assist.test.tsx`
  - default pill renders `AI 改稿`.
  - selection state renders `已选 N 字`.
  - buttons expose `批注`, `改这段`, `修改全文`.

- `prism-assist-panel.test.tsx`
  - composer saves annotation.
  - quick rewrite action calls quick workflow action.
  - deep assist action calls async workflow action.
  - annotation list shows status and does not expose raw agent ids.

- Existing Prism shell tests:
  - no `编辑 / 对照 / 审阅 / 专注` mode switcher.
  - compile opens PDF compare.
  - fixed Inspector no longer appears by default.

E2E/browser:

- Open Prism.
- Verify no four-mode switcher.
- Select TeX text.
- Verify floating assist appears.
- Save a comment.
- Trigger quick rewrite and see diff/apply controls.
- Compile and verify PDF opens.
- Select PDF text if a PDF is available, verify mapping status.
- Trigger deep assist only as a mocked/low-cost path in e2e unless real backend is required.

## 12. Non-Goals

- No new backend rewrite service.
- No new persisted annotation table.
- No full Workbench run board inside Prism.
- No large decorative floating ball.
- No direct write without diff/apply.
- No multi-user collaborative comment threads in this iteration.

## 13. Self-Review

Scope check:

- This is one feature area: Prism annotation and assist. It touches UI composition and state routing, but uses existing backend interfaces.

Architecture check:

- Quick lane and deep lane share the same `LatexFeedbackItem`.
- Sync rewrite remains direct and local to Prism.
- Async work reuses existing Workbench/Lead Agent infrastructure but is presented as a light Prism job.

Complexity check:

- First implementation avoids a new persistence layer and avoids a new backend service.
- Component extraction is limited to floating assist and panel UI.
- The fixed Inspector can be retired gradually by moving its content into the assist panel.

Ambiguity resolved:

- Default route is quick.
- Explicit `修改全文` always routes deep.
- Compile handling remains separate from annotation routing but can be surfaced inside the assist panel.
