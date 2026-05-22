# Workspace Execution Experience Convergence Plan

Date: 2026-05-22
Status: Draft for implementation
Scope: Workbench chat, LiveWorkflowPanel, Runs room, Prism handoff, execution UI projection

## Goal

把已经跑通的 chat -> Lead Agent -> worker -> DataService -> Runs/Prism 链路，收敛成用户可感知、可追踪、可继续操作的产品体验。

当前后端链路已经闭环，但前端仍像几套局部 UI 拼在一起：

- Chat stream 展示对话，但用户不容易确认“任务已经进入 Lead Agent 执行”。
- LiveWorkflowPanel 消费 `execution-store`，但它依赖 workspace event 触发，不是 chat dispatch 的第一视觉反馈。
- Runs drawer 通过 `/workspaces/{id}/runs` 单独拉历史，和 live execution card 不是同一个前端投影。
- Prism 是 canonical document surface，但完成态里“有 Prism 待审更新”还不够主动。

目标不是增加装饰，而是建立一个清晰事实：

> 用户发起一次 capability 后，整个 Workbench 只围绕同一个 execution/run 对象展示状态、进度、结果和下一步动作。

## Product Principle

1. **Chat 是发起和回执面**
   - 用户只需要在 chat 里发起任务。
   - Chat 立即显示启动回执、运行状态和完成入口。
   - Chat 不承载复杂节点详情，也不变成二级 dashboard。

2. **LiveWorkflowPanel 是执行过程面**
   - 右侧默认展示当前 execution 的节点进度、thinking 摘要、失败定位。
   - 当前任务优先于 idle suggestion。
   - 历史任务可折叠，但当前任务永远可见。

3. **Runs 是审计和历史面**
   - Runs drawer 展示可搜索、可复开的执行记录。
   - 它不重新定义状态，只消费共享 projection。
   - 从 Runs 可以定位到 live card、Prism、结果预览和失败详情。

4. **Prism 是产物落点**
   - capability 标记 `primary_surface=prism` 时，完成态必须主动提供 Prism review 入口。
   - Prism review item 是文档变更事实源，Runs 只负责过程审计。

5. **失败态产品化**
   - 不展示泛化 error。
   - 按启动失败、排队失败、执行节点失败、结果写回失败、结果提交失败分层。
   - 每一类失败都要给用户下一步：重试、查看节点、打开 Runs、继续提问。

## Current Architecture Audit

### Existing Useful Pieces

- `frontend/stores/chat-store.ts`
  - 负责 chat SSE block assembly。
  - 已支持 `status_line`、`tool_invocation`、`tool_result`、async `result_card`。
  - 已有 `execution.completed` handler，但它只把结果卡追加到 chat，缺少 launch/running projection。

- `frontend/stores/execution-store.ts`
  - 负责 live execution records。
  - 已支持 `execution.metadata`、`execution.graph_structure`、`execution.node`、`execution.node.delta`、`execution.completed`。

- `frontend/hooks/useWorkspaceEventStream.ts`
  - workspace event 触发后会 `getExecution()` 并 upsert 到 `execution-store`。
  - terminal execution 会转换成 chat `result_card`。

- `frontend/app/(workbench)/workspaces/[id]/components/ExecutionCardList.tsx`
  - 右侧 panel 已能展示 live execution cards。

- `frontend/app/(workbench)/workspaces/[id]/components/rooms/RunsDrawer.tsx`
  - Runs drawer 已能从 `/workspaces/{id}/runs` 拉历史。

- `frontend/app/(workbench)/workspaces/[id]/components/ResultCard.tsx`
  - Chat result card 已支持 staged output preview 和 commit。
  - 已能展示 Prism review items。

### Current Gaps

1. **Run projection 分裂**
   - `ExecutionRecord`、`RunRecord`、`ResultCardData` 各有自己的字段和状态解释。
   - UI 里出现三套 title/status/summary/duration 逻辑。

2. **Chat launch 态弱**
   - `tool_result` 有机会携带 `execution_id`，但没有被提升成清晰 run receipt。
   - 用户看到的是“回复结束”，不是“Lead Agent 正在执行”。

3. **右侧 panel 缺主动聚焦**
   - Workspace event 到达后 card 会出现，但 page 层没有“当前 run 已启动”的视觉协调。
   - Idle suggestion 和 active execution 的优先级关系不够明确。

4. **Runs drawer 与 live store 不互通**
   - Runs drawer 只在打开时 fetch。
   - 当前正在跑的 run 不一定立刻在 drawer 里高亮。

5. **Prism handoff 不够强**
   - result card 有 Prism review list，但 Workbench 顶层没有 “Prism 有待审变更” 的全局提示。
   - SurfaceSwitch 也没有 pending review badge。

6. **失败层级缺 contract**
   - Backend 能区分很多失败位置，但前端没有统一 failure category。
   - 节点失败、dispatch 失败、commit 失败没有统一文案和动作模型。

## Target Interaction Flow

### Happy Path

```text
User sends chat message
  -> Chat shows user message immediately
  -> Assistant shows thinking / status
  -> launch_feature returns execution_id
  -> Chat converts launched tool_result into RunReceipt
  -> Right panel focuses current ExecutionCard
  -> Workspace event stream hydrates ExecutionRecord
  -> Execution stream updates graph/node/thinking
  -> Execution completes
  -> Chat result card appears with summary + actions
  -> Right panel completed card shows result preview + Prism/commit actions
  -> Runs drawer history contains same run
  -> Prism badge appears if review_items exist
```

### Lead Busy Path

```text
User asks for another capability while active execution exists
  -> Chat Agent returns lead_busy advisory
  -> Chat renders status_line with current run link
  -> Right panel keeps current run focused
  -> No hidden queue, no second dispatch
```

### Failure Path

```text
Dispatch fails
  -> Chat shows launch failure card with retry
  -> No orphan "running" card

Node fails
  -> Right panel marks failed node
  -> Chat terminal card says partial/failed with "查看失败节点"

Result writeback fails
  -> Run is terminal but commit/review action shows recovery state
  -> User can reopen Runs detail and retry eligible action
```

## Canonical Frontend Projection

Create a shared projection:

`frontend/lib/execution-run-view.ts`

```ts
export type RunViewStatus =
  | "launching"
  | "queued"
  | "running"
  | "completed"
  | "failed_partial"
  | "failed"
  | "cancelled";

export type RunFailureCategory =
  | "launch_failed"
  | "queue_failed"
  | "node_failed"
  | "writeback_failed"
  | "commit_failed"
  | "unknown";

export type RunPrimaryAction =
  | "open_live"
  | "open_runs"
  | "open_prism"
  | "preview_results"
  | "retry"
  | "continue_chat";

export interface RunView {
  id: string;
  workspaceId: string;
  capabilityId?: string | null;
  title: string;
  status: RunViewStatus;
  summary: string;
  startedAt?: string | null;
  completedAt?: string | null;
  durationLabel?: string | null;
  progress?: number | null;
  nodeCount?: number;
  completedNodeCount?: number;
  failedNodeCount?: number;
  tokenUsage?: { input: number; output: number } | null;
  primarySurface?: "prism" | "rooms" | "sandbox" | "none";
  prismReviewCount?: number;
  hasPrismChanges: boolean;
  failureCategory?: RunFailureCategory | null;
  failureMessage?: string | null;
  actions: RunPrimaryAction[];
}
```

Projection builders:

- `runViewFromExecution(record: ExecutionRecord): RunView`
- `runViewFromRunRecord(record: RunRecord, workspaceId: string): RunView`
- `runViewFromResultCard(data: ResultCardData, workspaceId: string): RunView`
- `mergeRunViews(live: RunView | null, historical: RunView | null): RunView`

This becomes the only place that maps title/status/summary/duration/actions.

## Backend Contract Adjustments

The current `/workspaces/{id}/runs` projection is enough for basic history, but not enough for product navigation. Extend it cleanly, without compatibility branches:

`RunRecord` should include:

- `id`
- `workspace_id`
- `thread_id`
- `capability_id`
- `capability_name`
- `status`
- `started_at`
- `completed_at`
- `summary`
- `token_usage`
- `progress`
- `primary_surface`
- `review_items_count`
- `has_prism_changes`
- `failure_category`
- `failure_message`

Source of truth:

- execution status and timing: DataService execution domain
- capability name / surface: execution display/runtime metadata
- Prism review count: review item domain filtered by `execution_id` + `target_domain=prism`
- failure category: execution result/error projection, derived in backend service layer

No aliasing of old workflow ids. No fallback mapping.

## Frontend Implementation Plan

### Phase 1: Shared Run Projection

Files:

- Create `frontend/lib/execution-run-view.ts`
- Modify `frontend/lib/api/v2/runs.ts`
- Add tests under `frontend/tests/unit/lib/execution-run-view.test.ts`

Tasks:

- Add `RunView` model and projection builders.
- Move duration/status/title/action derivation out of `ExecutionCard`, `RunsDrawer`, `ResultCard`.
- Normalize terminal statuses and failure categories once.
- Add unit tests for:
  - live running execution
  - completed execution with Prism review items
  - failed_partial node failure
  - historical RunRecord with limited fields
  - result card conversion

Acceptance:

- No component manually derives run label/status/actions from raw payload.
- Current tests still pass.

### Phase 2: Execution UI Store

Files:

- Create `frontend/stores/run-ui-store.ts`
- Modify `frontend/hooks/useWorkspaceEventStream.ts`
- Modify `frontend/stores/chat-store.ts`

Store responsibilities:

- `activeRunId`
- `focusedRunId`
- `recentRunIds`
- `drawerHighlightedRunId`
- `lastLaunchReceiptByExecutionId`
- actions:
  - `markRunLaunching`
  - `markRunHydrated`
  - `focusRun`
  - `highlightRunInDrawer`
  - `clearTerminalFocusAfterDelay`

Important rule:

`execution-store` remains the raw live execution state. `run-ui-store` only owns UI focus/attention state.

Acceptance:

- Chat launch, workspace event, execution completion all update the same focused run id.
- No duplicated execution data in `run-ui-store`.

### Phase 3: Chat Launch Receipt

Files:

- Modify `frontend/stores/chat-store.ts`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/MessageBlock.tsx`
- Modify or create `frontend/app/(workbench)/workspaces/[id]/components/RunReceiptBlock.tsx`

Design:

- When `tool_result` has `{status: "launched", execution_id}`:
  - mark run as launching/focused
  - render a compact receipt block:
    - title: `已启动：{capability_name || feature_id}`
    - status: `Lead Agent 正在执行`
    - actions: `查看执行` / `打开 Runs`
- Keep block protocol unchanged by rendering launched `tool_result` as a first-class UI component. Do not add a new backend block type unless necessary.
- When `lead_busy` appears:
  - render status_line with current active run link.

Acceptance:

- User can see execution id or title immediately after dispatch.
- Chat completion no longer feels like the task silently moved elsewhere.

### Phase 4: LiveWorkflowPanel Focus And Empty State

Files:

- Modify `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/ExecutionCardList.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/ExecutionCard.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/InProgressView.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx`

Design:

- Active execution card is always pinned above suggestions.
- ProductIntro only appears when there is no active/recent execution or appears below run cards.
- Add compact panel header:
  - current run title
  - status
  - elapsed time
  - `Runs` and `Prism` quick actions when relevant
- Current run auto-expands.
- Terminal run stays expanded for a short time after completion.
- Failed nodes get explicit row-level affordance.

Acceptance:

- After chat dispatch, right panel immediately indicates the active run.
- Node progress is visible without opening Runs.

### Phase 5: Runs Drawer As History And Detail

Files:

- Modify `frontend/app/(workbench)/workspaces/[id]/components/rooms/RunsDrawer.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/RoomsTopbar.tsx`
- Add tests under `frontend/tests/unit/v2/rooms/RunsDrawer.test.tsx`

Design:

- Runs drawer consumes `RunView`, not raw `RunRecord`.
- Merge fetched historical runs with live `execution-store` runs.
- Highlight current/focused run.
- Add per-run actions:
  - `查看执行详情`
  - `打开 Prism`
  - `预览结果`
  - `继续基于本次结果提问`
- Topbar Runs icon shows:
  - running dot when active execution exists
  - count badge when new terminal run arrives

Acceptance:

- Opening Runs during execution shows the active run.
- Opening Runs after completion shows the completed run without manual refresh.

### Phase 6: Prism Handoff

Files:

- Modify `frontend/app/(workbench)/workspaces/[id]/components/SurfaceSwitch.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/ResultCard.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx`
- Verify `frontend/app/(workbench)/workspaces/[id]/prism/page.tsx`

Design:

- If `RunView.hasPrismChanges`:
  - Chat result card primary action is `预览 Prism 修改`
  - CompletedView shows `Prism 有待确认变更`
  - SurfaceSwitch Prism tab shows a small pending badge
- Prism URLs should focus specific review item when available:
  - `/workspaces/{id}/prism?focus=file_changes&review_item_id=...`

Acceptance:

- Prism is visibly the document result surface for manuscript/document changes.
- User does not need to infer from Runs summary.

### Phase 7: Failure UX

Files:

- Modify `frontend/lib/execution-run-view.ts`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/ExecutionCard.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/ResultCard.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/rooms/RunsDrawer.tsx`

Design:

- Introduce failure display matrix:

| Category | User-facing summary | Primary action |
| --- | --- | --- |
| `launch_failed` | 未能启动执行 | retry |
| `queue_failed` | 后台队列不可用 | retry later |
| `node_failed` | 某个执行节点失败 | open failed node |
| `writeback_failed` | 结果已生成但写回失败 | open Runs detail |
| `commit_failed` | 保存到工作区失败 | retry commit |
| `unknown` | 执行失败 | open detail |

Acceptance:

- No raw exception-first UI.
- Every failure card has a concrete next action.

### Phase 8: Browser Verification

Use Playwright/browser verification against local Docker stack.

Scenarios:

1. Launch `sci_literature_positioning` from chat.
2. Confirm chat launch receipt appears.
3. Confirm right panel active execution card appears and expands.
4. Confirm Runs topbar indicates running.
5. Wait for completion.
6. Confirm chat result card appears.
7. Confirm Runs drawer shows same run, completed.
8. Confirm Prism CTA appears when review items exist.
9. Simulate/fixture queue failure.
10. Simulate/fixture node failure.

Backend checks:

- `cd backend && .venv/bin/python -m pytest tests/ -v`

Frontend checks:

- `cd frontend && npm run typecheck`
- `cd frontend && npx vitest run`
- `cd frontend && npm run build`

## Data And Contract Tests

Add tests for:

- Backend `/workspaces/{id}/runs` projection includes extended fields.
- Frontend `RunView` projection from `ExecutionRecord`.
- Frontend `RunView` projection from `RunRecord`.
- Chat store handles launched `tool_result`.
- Workspace event stream focuses active execution.
- Runs drawer merges live and historical runs.
- Prism badge appears only when review count > 0.

## Non-goals

- No new legacy compatibility layer.
- No old workflow id alias.
- No second execution queue in frontend.
- No new backend block type unless `tool_result` rendering is insufficient.
- No visual redesign unrelated to execution state.
- No change to DataService ownership model.

## Suggested Execution Order

1. Implement shared `RunView` projection and tests.
2. Extend backend Runs projection only as needed by `RunView`.
3. Add `run-ui-store` and hook it into workspace events.
4. Convert chat launched `tool_result` into visible run receipt.
5. Refactor LiveWorkflowPanel to pin/focus active run.
6. Refactor RunsDrawer to consume `RunView` and merge live/history.
7. Add Prism pending handoff/badge.
8. Add failure category display.
9. Browser-test full chat chain again.

## Definition Of Done

- Starting a capability from chat visibly creates a run receipt within one second.
- Right panel focuses the same execution id.
- Runs drawer shows the same execution id while running and after completion.
- Completion shows result summary and correct next actions in chat and right panel.
- Prism handoff is visible when review items exist.
- Failure states are classified and actionable.
- Backend and frontend tests pass.
- Browser smoke confirms the full chain without manual refresh.

