# Frontend Feature Plugin Contract

更新时间: 2026-03-19

本文档定义 workspace 功能插件化渲染的前后端契约，避免前端硬编码 feature 逻辑。

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
  "thread_id": "optional-thread-id"
}
```

- Response:

```json
{
  "task_id": "task-xxx",
  "status": "pending",
  "feature_id": "proposal_outline",
  "message": "任务已提交"
}
```

## 2. Frontend Integration Points

关键文件:

- `frontend/lib/api.ts`
- `frontend/stores/features.ts`
- `frontend/hooks/useFeatureTaskRunner.ts`
- `frontend/components/workspace/QuickActions.tsx`
- `frontend/components/workspace/TaskFeedbackBanner.tsx`
- `frontend/components/workspace/WorkspaceResultPanel.tsx`

## 3. 交互约束

1. Feature 按后端下发动态渲染，不做 workspace 类型硬编码按钮列表。
2. 功能执行后统一进入任务轮询，直到终态。
3. `TaskFeedbackBanner` 只展示执行状态和错误，不承载最终结果正文。
4. `WorkspaceResultPanel` 消费标准 view model，容忍结果字段缺失。

## 4. Refresh Targets Contract

任务成功后，前端按 `task.result.refresh_targets` 刷新资源:

- `artifacts` -> `fetchArtifacts(workspaceId)`
- `papers` -> `fetchPapers(workspaceId)`
- `workspace` -> `loadWorkspace(workspaceId)`

实现位置: `frontend/hooks/useFeatureTaskRunner.ts`

## 5. Compatibility Notes

- 兼容老任务: 如果缺少 `refresh_targets`，默认刷新 `artifacts`。
- 兼容 warning 场景: `status=warning` 且无 `task_id` 时，前端应直接提示，不进入轮询。
