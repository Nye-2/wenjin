# Frontend Feature Plugin Contract

更新时间: 2026-05-20

本文档定义 workspace capability 入口兼容层的前后端契约，避免前端硬编码 capability 目录与执行入口逻辑。

当前产品行为总览见: `docs/current/workspace-current-state.md`

## 1. Backend Contract

### 1.1 拉取 capability 入口目录

- Endpoint: `GET /api/workspaces/{workspace_id}/features`
- 说明：这是当前工作台 capability entry catalog 的兼容 UI 接口，不是 capability schema 的 SSOT
- 返回字段（核心）:
  - `id`
  - `name`
  - `description`
  - `icon`
  - `agent` / `agentLabel`
  - `panel`
  - `stages[]`
  - `color`
  - `followUpPrompt`

### 1.2 解析 capability 入口 follow-up / rerun action

- Endpoint: `POST /api/workspaces/{workspace_id}/features/{feature_id}/resolve-action`
- Request:

```json
{
  "orchestration_params": {},
  "source_artifact_id": "optional-artifact-id"
}
```

- Response:

```json
{
  "source_artifact_id": "artifact-xxx",
  "follow_up_prompt": "继续深化框架",
  "route_params": {
    "topic": "LLM planning",
    "source_artifact_id": "artifact-xxx"
  },
  "rerun_params": {
    "topic": "LLM planning"
  },
  "rerun_unavailable_reason": null
}
```

说明:

- 这条接口只负责把 artifact / orchestration 上下文解析成 canonical rerun / follow-up route state。
- 真正的 launch / resume 统一通过 workspace workbench query seed 进入 ChatPanel，再由 chat agent 调用 `launch_feature` tool。

## 2. Frontend Integration Points

关键文件:

- `frontend/lib/api/workspace.ts`
- `frontend/lib/api/threads.ts`
- `frontend/lib/block-actions.ts`
- `frontend/lib/workspace-feature-routes.ts`
- `frontend/lib/workspace-thread-entry.ts`
- `frontend/stores/features.ts`
- `frontend/stores/compute.ts`
- `frontend/stores/execution-store.ts`
- `frontend/stores/latex.ts`
- `frontend/lib/execution-presenters.ts`
- `frontend/hooks/useWorkspaceEventStream.ts`
- `frontend/app/(workbench)/workspaces/[id]/page.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/ResultCard.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx`
- `frontend/app/(workbench)/workspaces/[id]/prism/page.tsx`
- `frontend/components/prism/PrismReviewList.tsx`

## 3. Workspace Workbench Entry Contract

当前 capability 入口导航采用 workspace workbench 单入口，不再依赖独立 feature slug 页面或独立 `/chat` 页面。

- Canonical entry: `/workspaces/{workspace_id}`
- 必带 query: `feature=<feature_id>`（当前兼容入口字段；语义上对应 capability id）
- 可选 query: `skill=<skill_id>` 以及 capability seed params（如 `topic`、`query`、`source_artifact_id`）
- 前端职责:
  - 解析 query seed
  - 生成首条可编辑 prompt
  - 在第一次 chat turn 中把 `metadata.orchestration.intent=launch + feature_id + params` 一并发给后端
- 后端职责:
  - 所有 chat turns 统一进入 lead-agent（`create_react_agent`）
  - lead-agent 根据 workspace skills 上下文判断是否调用 `launch_feature` tool
  - `launch_feature` tool 创建或复用 `ExecutionRecord`，并分发 `execute_execution(execution_id)`
  - 在 `metadata.orchestration.execution_id` 存在时，走 ingress resume 继续同一 execution
  - assistant thread message 会持久化 `metadata.orchestration.execution_id`，供前端在刷新/恢复后将 result card 锚定回对应消息

### 1.3 Launch / Resume Fact

- 当前没有独立的 `POST /workspaces/{workspace_id}/features/{feature_id}/execute` 公共入口作为主链事实源。
- capability 启动与恢复以 workspace thread orchestration + `launch_feature` 为准。
- 返回给前端用于订阅、恢复、提交的 canonical 标识始终是 `execution_id`。

## 4. 交互约束

1. capability entry 目录按后端下发动态渲染，不做 workspace 类型硬编码按钮列表。
2. capability 执行后统一汇聚到 `ExecutionRecord`，并由 `ComputeSession` 提供工作台 shell。
3. 前端不再单独维护 task/panel 两套运行态；长任务详情统一进入 LiveWorkflowPanel / compute projection UI。
4. workspace SSE 以 `execution.* / task.updated / subagent.updated / compute.updated` 驱动 execution/compute store 增量更新。
5. capability 入口卡片、artifact follow-up、activity retry 必须统一落到 `/workspaces/{workspace_id}?feature=...` query seed，并保留 `source_artifact_id/context_artifact_ids` 等 seed；不得重新引入中间 feature slug 页面。
6. Prism writing result action 必须统一落到 `/workspaces/{workspace_id}/prism?focus=file_changes&review_item_id=...&logical_key=...`，不得落到 standalone `/latex/{project_id}` 页面。

## 5. Refresh Targets Contract

任务成功后，前端按 execution / result card 提供的 `refresh_targets` 刷新资源:

- `artifacts` -> `fetchArtifacts(workspaceId)`
- `references` -> `fetchReferences(workspaceId)`
- `workspace` -> `loadWorkspace(workspaceId)`

实现位置: `frontend/hooks/useWorkspaceEventStream.ts` 与 `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`

## 6. Compute Runtime Notes

- 执行态 UI 以 Compute projection 为主展示面；`ExecutionRecord`、task、subagent、runtime blocks、sandbox files、logs、artifacts 和 canonical Prism review items 是 projection 的事实来源。
- Thread message 只承载发起、追问、完成摘要和 pointer metadata，不用于恢复当前执行状态。
- Thread message 的 `metadata.orchestration.execution_id` 只用作归属锚点，不替代 `ExecutionRecord` 的实时状态。
- LiveWorkflowPanel 必须能从 `/api/workspaces/{workspace_id}/compute/sessions` 和 `/api/compute/sessions/{compute_session_id}/projection` 恢复任务状态。
- WenjinPrism file changes 必须走 DB-backed review item 与 `preview -> apply/reject/revert`；前端不得直接把 capability 生成内容写入 Prism 文件。
- Prism protected sections 与 source links 由后端 canonical tables 投影；前端只做展示、聚焦导航和用户动作触发。
