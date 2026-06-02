# Frontend Feature Plugin Contract

更新时间: 2026-06-02

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
- `frontend/stores/run-ui-store.ts`
- `frontend/lib/execution-run-view.ts`
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
  - 在第一次 chat turn 中把 `metadata.orchestration.feature_id + entry + params` 一并发给后端
- 后端职责:
  - 所有 chat turns 统一进入 Chat Agent（`create_react_agent`）
  - Chat Agent 根据 workspace mission catalog / skills 上下文判断是否调用 `launch_feature` tool
  - `launch_feature` tool 先执行 context gate；上下文足够时创建或复用 `ExecutionRecord`，并分发 `execute_execution(execution_id)`
  - sandbox-backed work 不允许在 Chat Agent tool/middleware 中执行；它必须在 `execute_execution` 后进入 LeadAgentRuntime / subagent graph，根据 capability `sandbox_policy` 执行
  - thread run stream 必须把 `launch_feature` 的 `tool_invocation` / `tool_result` 发回前端
  - `tool_result.status == "launched"` 时必须携带 `execution_id`、`feature_id`，并尽量携带 `capability_name`
  - `tool_result.status == "advisory"` 且 `code == "missing_params"` 时不得携带新的 `execution_id`，也不得触发 credit reservation、Celery dispatch 或外部检索
  - 在 `metadata.orchestration.execution_id` 存在时，走 ingress resume 继续同一 execution
  - assistant thread message 会持久化 `metadata.orchestration.execution_id`，供前端在刷新/恢复后将 result card 锚定回对应消息

### 3.1 Capability Launch Context Gate

Workbench capability 卡片、feature query seed 和 frontend-generated prompt 只负责把用户意图路由到对应 capability。它们不能代替具体任务上下文。

后端必须按以下规则处理：

- `metadata.orchestration.feature_id` 选择 capability；它不是 mission goal。
- frontend 生成的通用 launch prompt 只作为意图触发文本；不得被解析成 `goal` / `query` / `topic`。
- 需要具体上下文的 capability 必须从用户显式输入、query seed、route params、source artifact 或已提交 room context 中读取参数。
- 缺少必要上下文时返回 advisory：

```json
{
  "status": "advisory",
  "code": "missing_params",
  "feature_id": "sci_literature_positioning",
  "required_context": ["topic", "query"]
}
```

前端必须按以下规则处理：

- advisory 只渲染为 chat 提示，不建立 run receipt。
- advisory 不写入 `run-ui-store.activeRunId`，不打开 Current run，不订阅 execution stream。
- 用户补充上下文后，以新的 chat turn 重新进入 Chat Agent / `launch_feature`。

### 3.2 Launch / Resume Fact

- 当前没有独立的 `POST /workspaces/{workspace_id}/features/{feature_id}/execute` 公共入口作为主链事实源。
- capability 启动与恢复以 workspace thread orchestration + `launch_feature` 为准。
- 返回给前端用于订阅、恢复、提交的 canonical 标识始终是 `execution_id`。
- 用户可见启动确认来自标准 `tool_result` block，而不是模型自然语言承诺。

### 3.3 RunView Projection Contract

前端所有 execution UX 展示必须先投影为 `RunView`：

- live execution：`runViewFromExecution(record)`
- Runs history：`runViewFromRunRecord(record, workspaceId)`
- chat result card：`runViewFromResultCard(data, workspaceId)`
- live/history 合并：`mergeRunViews(live, historical)`

`RunView` 负责统一 title、status、duration、node counts、token usage、Prism review handoff、failure category 和 primary actions。

`run-ui-store` 只允许保存：

- `activeRunId`
- `focusedRunId`
- `highlightedRunId`
- `completedRunIds`

不得把 execution lifecycle、node state 或 backend result 复制进 `run-ui-store`。

## 4. 交互约束

1. capability entry 目录按后端下发动态渲染，不做 workspace 类型硬编码按钮列表。
2. capability 执行后统一汇聚到 `ExecutionRecord`，并由 `ComputeSession` 提供工作台 shell。
3. 前端不再单独维护 task/panel 两套运行态；长任务详情统一进入 LiveWorkflowPanel / compute projection UI，并通过 `RunView` 呈现。
4. workspace SSE 以 `execution.* / task.updated / subagent.updated / compute.updated` 驱动 execution/compute store 增量更新。
5. capability 入口卡片、artifact follow-up、activity retry 必须统一落到 `/workspaces/{workspace_id}?feature=...` query seed，并保留 `source_artifact_id/context_artifact_ids` 等 seed；不得重新引入中间 feature slug 页面。
6. Prism writing result action 必须统一落到 `/workspaces/{workspace_id}/prism?focus=file_changes&review_item_id=...&logical_key=...`，不得落到 standalone `/latex/{project_id}` 页面。
7. Runs drawer 必须合并 live execution store 与 `/api/workspaces/{workspace_id}/runs`，不得成为第二套执行状态系统。
8. LiveWorkflowPanel 必须 pin 当前 active/focused run；从 running 到 completed 的状态切换必须来自 execution store / Runs projection，不来自本地计时假设。
9. Prism editor API client 可以继续位于 `frontend/lib/api/latex.ts`，但它是 Prism LaTeX adapter client；所有 HTTP 调用必须走 `/prism/latex-adapter/*` 或 `/api/prism/latex-adapter/*`，不得调用 `/latex/*` 或 `/api/latex/*`。

### 4.1 全站 UIUX 收敛约束

这些约束适用于 Workbench、Prism、room drawers、admin 和 settings：

1. 自动适配是默认行为。viewport、运行状态、选中项和完成态应驱动布局与焦点；不得把 `manual lock`、`focused id`、hydration 等内部状态暴露成用户必须点击的恢复按钮。
2. 信息密度必须分层处理。主界面展示摘要、当前状态和下一步决策；详情、编辑、trace、diff、BibTeX、日志进入二级导航、detail pane、drawer、fullscreen 或 Prism。
3. 当横向空间不足时，导航和次级操作先折叠为 icon-only + tooltip；内容区不能被重复文字按钮挤压。
4. 列表项必须约束长文本宽度。标题、作者、文件名、URL 和 run 名称在列表中 ellipsis / line-clamp，完整内容只在详情区展示。
5. 列表与详情不能在窄面板中硬挤两栏。窄面板默认 list-first；点击条目后进入更宽详情面或 fullscreen split view。
6. 用户可见文案必须是产品语言：运行中、待审阅、已保存、已完成、需要补充。不得出现 projection、hydration、focus lock、retry internals 等工程语言。

## 5. Refresh Targets Contract

任务成功后，前端按 execution / result card 提供的 `refresh_targets` 刷新资源:

- `artifacts` -> `fetchArtifacts(workspaceId)`
- `references` -> `fetchReferences(workspaceId)`
- `workspace` -> `loadWorkspace(workspaceId)`

实现位置: `frontend/hooks/useWorkspaceEventStream.ts` 与 `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`

## 6. Compute Runtime Notes

- 执行态 UI 以 Compute projection 为主展示面；`ExecutionRecord`、task、subagent、runtime blocks、sandbox files、logs、artifacts 和 canonical Prism review items 是 projection 的事实来源。
- Sandbox files/logs/artifacts 在前端只能作为 execution/run detail 的只读 trace 展示，不提供用户侧代码 console 或公开任意执行入口。
- 公共 capability 目录接口（`/api/capabilities` 与 workspace-scoped capability list）必须过滤 `entry_tier: hidden` / hidden tier capability；这类 capability 只用于内部诊断或自动化验证，不作为用户卡片展示。
- Thread message 只承载发起、追问、完成摘要和 pointer metadata，不用于恢复当前执行状态。
- Thread message 的 `metadata.orchestration.execution_id` 只用作归属锚点，不替代 `ExecutionRecord` 的实时状态。
- LiveWorkflowPanel 必须能从 `/api/workspaces/{workspace_id}/compute/sessions` 和 `/api/compute/sessions/{compute_session_id}/projection` 恢复任务状态。
- WenjinPrism file changes 必须走 DB-backed review item 与 `preview -> apply/reject/revert`；前端不得直接把 capability 生成内容写入 Prism 文件。
- Prism protected sections 与 source links 由后端 canonical tables 投影；前端只做展示、聚焦导航和用户动作触发。
- Prism adapter route 是后端 manuscript editing 的唯一 API 面；前端不得恢复 standalone LaTeX page/action，也不得为旧 route 增加兼容跳转。
