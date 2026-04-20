# Frontend Feature Plugin Contract

更新时间: 2026-04-14

本文档定义 workspace 功能插件化渲染的前后端契约，避免前端硬编码 feature 逻辑。

当前产品行为总览见: `docs/product/workspace-current-state.md`

## 1. Backend Contract

### 1.1 拉取 feature 列表

- Endpoint: `GET /api/workspaces/{workspace_id}/features`
- 返回字段（核心）:
  - `id`
  - `name`
  - `description`
  - `icon`
  - `agent` / `agentLabel`
  - `taskType`
  - `handlerKey`
  - `panel`
  - `stages[]`

### 1.2 执行 feature

- Endpoint: `POST /api/workspaces/{workspace_id}/features/{feature_id}/execute`
- Request:

```json
{
  "params": {},
  "thread_id": "optional-thread-id",
  "execution_session_id": "optional-resume-session-id"
}
```

- Response:

```json
{
  "task_id": "task-xxx",
  "execution_session_id": "exec-xxx",
  "status": "pending",
  "feature_id": "proposal_outline",
  "message": "任务已提交"
}
```

说明:

- `execution_session_id` 为空时表示 launch；传入时表示 resume 同一 feature 事务。
  - `status` 可能返回 `awaiting_user_input`（缺参追问状态），此时前端应回到 thread 路由（`/chat`）继续追问并在下一轮携带该 `execution_session_id`。

## 2. Frontend Integration Points

关键文件:

- `frontend/lib/api/workspace.ts`
- `frontend/lib/api/threads.ts`
- `frontend/lib/workspace-feature-routes.ts`
- `frontend/lib/workspace-thread-entry.ts`
- `frontend/stores/features.ts`
- `frontend/stores/execution.ts`
- `frontend/lib/execution-presenters.ts`
- `frontend/hooks/useWorkspaceEventStream.ts`
- `frontend/app/(workbench)/workspaces/[id]/components/ThreadPanel.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/KnowledgePanel.tsx`

## 3. Thread Route Entry Contract

当前 feature 导航采用 thread route 单入口（URL 为 `/chat`），不再依赖独立 feature slug 页面。

- Canonical entry: `/workspaces/{workspace_id}/chat`
- 必带 query: `feature=<feature_id>`
- 可选 query: `skill=<skill_id>` 以及 feature seed params（如 `topic`、`query`、`source_artifact_id`）
- 前端职责:
  - 解析 query seed
  - 生成首条可编辑 prompt
  - 在第一次 chat turn 中把 `metadata.orchestration.feature_id + params` 一并发给后端
- 后端职责:
  - 优先消费显式 `metadata.orchestration`
  - 由 lead-agent / `run_workspace_feature` 接回 canonical feature execution
  - 在 `metadata.orchestration.execution_session_id` 存在时，走 ingress resume 继续同一 execution session

## 4. 交互约束

1. Feature 按后端下发动态渲染，不做 workspace 类型硬编码按钮列表。
2. 功能执行后统一汇聚到 `ExecutionSession`，前端不再单独维护 task/panel 两套运行态。
3. workspace SSE 以 `execution.* / task.updated / subagent.updated` 驱动 execution store 增量更新。
4. feature 卡片、artifact follow-up、activity retry 必须统一落到 `/chat`，不得重新引入中间 feature slug 页面。

## 5. Refresh Targets Contract

任务成功后，前端按 `task.result.refresh_targets` 刷新资源:

- `artifacts` -> `fetchArtifacts(workspaceId)`
- `papers` -> `fetchPapers(workspaceId)`
- `workspace` -> `loadWorkspace(workspaceId)`

实现位置: `frontend/hooks/useWorkspaceEventStream.ts` 与 `frontend/app/(workbench)/workspaces/[id]/components/ThreadPanel.tsx`

## 6. Runtime Notes

- 执行态 UI 只消费 `ExecutionSession`；task/subagent 事件只作为 execution store 的增量补丁，不再直接驱动独立 task/panel store。
