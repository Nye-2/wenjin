# Workspace Execution Pipeline

更新时间: 2026-03-20

本文档描述 workspace 功能执行的统一链路（从 API 请求到 LangGraph 执行到 artifact 落库）。

## 1. Entry Points

- 主入口: `POST /api/workspaces/{workspace_id}/features/{feature_id}/execute`

## 2. End-to-End Flow

1. Router 接收请求并注入当前用户。
2. `FeatureExecutionHandler` 执行编排:
   - 校验 workspace 所有权
   - 根据 `workspace_type + feature_id` 从 registry 解析 feature
   - 执行文献阈值/积分/幂等/并发保护
   - 提交任务到 `TaskService`
3. `task/handlers/workspace_feature_handler.py` 执行任务:
   - 调用 `workspace_lead_agent.execute_feature_graph(...)`
   - 统一封装结果 payload
   - 按 feature 映射写入 artifacts
   - 异步触发 memory extraction（非阻塞）
4. 任务终态通过 `TaskService` 对外可见，前端按 `refresh_targets` 刷新数据。

## 3. Canonical Result Contract

workspace feature 任务结果遵循统一结构（关键字段）:

- `success: bool`
- `feature_id: str`
- `feature_name: str`
- `workspace_type: str`
- `handler_key: str`
- `message: str`
- `data: dict`
- `artifacts: list`
- `refresh_targets: list`（当前值: `artifacts` / `papers` / `workspace`）

## 4. Canonical Task Payload Contract

workspace feature 提交到 `TaskService` 的 payload 采用单一事实源约束:

- 顶层仅保留编排元数据:
  `workspace_id` / `workspace_type` / `workspace_name` / `workspace_description` /
  `workspace_discipline` / `workspace_config` / `feature_id` / `feature_name` /
  `agent` / `agent_label` / `handler_key` / `thread_id`
- 所有业务输入统一放在 `params`
- 不再把 `params` 里的业务字段平铺复制到顶层，避免双事实源
graph / service 读取业务参数时，应优先读取 `payload["params"]`，仅对 workspace 元数据读取顶层字段。

## 5. Registry Is Source of Truth

文件: `backend/src/workspace_features/registry.py`

registry 决定:

- canonical workspace types
- feature 元信息（id/name/description/icon/agent/panel/stages）
- `handler_key`
- `task_type`

任何新增/修改 feature，必须先更新 registry，再更新 handler/graph 和前端展示。

## 6. Key Files

- `backend/src/gateway/routers/features.py`
- `backend/src/application/handlers/feature_execution_handler.py`
- `backend/src/task/handlers/workspace_feature_handler.py`
- `backend/src/workspace_features/registry.py`
- `frontend/hooks/useFeatureTaskRunner.ts`
- `frontend/lib/taskPolling.ts`
