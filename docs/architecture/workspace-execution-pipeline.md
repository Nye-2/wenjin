# Workspace Execution Pipeline

更新时间：2026-04-10

本文档描述 workspace 当前的执行主链，覆盖 chat、skills、features、tasks、subagents 和最终 writeback。

## 1. Canonical Entry Points

### 1.1 Chat 主入口

- `POST /api/chat`
- `POST /api/chat/stream`

chat 是用户侧统一入口。若用户或 UI seed 触发 workspace 功能，lead-agent 会通过 `run_workspace_feature` 进入 feature 执行链。

### 1.2 Feature 显式入口

- `POST /api/workspaces/{workspace_id}/features/{feature_id}/execute`

这是所有 workspace feature 的 canonical 执行入口。任何新增功能都应接入这条链，而不是额外发明平行执行面。

## 2. Chat -> Feature 协作链

1. Chat router 接收消息，解析 thread/workspace/user 运行时上下文。
2. `ChatTurnHandler` 调用 lead-agent。
3. lead-agent 根据用户消息、当前 thread、selected skill、workspace context 决定：
   - 直接回答
   - 或调用 `run_workspace_feature`
4. `run_workspace_feature` 只接受业务参数与 `skill_id`，运行时 ids 由上下文自动注入。
5. tool bridge 进入 `FeatureExecutionHandler.execute(...)`。

约束：

- skill 只作为 feature 入口语义，不再是独立执行框架。
- `run_workspace_feature` 是 chat 到 feature 的唯一显式执行入口。
- feature 所需业务输入统一放在 `params`，不再平铺到顶层形成双事实源。

## 3. Feature Execution Chain

1. Gateway router 接收 feature execute 请求。
2. `FeatureExecutionHandler`：
   - 校验 workspace owner
   - 根据 `workspace_type + feature_id` 查 registry
   - 执行 credit / policy / lock / idempotency 检查
   - 生成 canonical task payload
   - 提交给 `TaskService`
3. Celery worker 拉取任务并交给 `task/handlers/workspace_feature_handler.py`
4. handler 调用 `workspace_lead_agent.execute_feature_graph(...)`
5. feature graph 协调 service 层、subagents、LaTeX sync、runtime blocks
6. 结果统一写回：
   - task status / result
   - artifacts
   - workspace activities
   - thread/task/subagent status events

## 4. Feature Graph 和 Service 边界

### Graph 层

- 位置：`backend/src/agents/graphs/`
- 负责：
  - orchestration
  - feature runtime progress / blocks
  - 结果结构整形
  - 与 task runtime / latex sync 的连接

### Service 层

- 位置：`backend/src/workspace_features/services/`
- 负责：
  - 模型调用
  - payload 规范化
  - schema 化输出
  - generation mode / fallback 逻辑

规则：

- graph 保持轻量，不吸收大块 LLM 业务逻辑
- service 统一通过共享 JSON helper 约束结构化生成

## 5. Registry Is Source of Truth

文件：`backend/src/workspace_features/registry.py`

registry 决定：

- workspace type 列表
- feature 元信息（id/name/description/icon/agent/panel/stages）
- `handler_key`
- `task_type`
- `follow_up_prompt`

任何 feature 增删改都必须先更新 registry，再更新 graph/service/frontend。

## 6. Subagents in the Pipeline

subagents 当前是 worker 能力，而不是独立主执行平面。

- spawn 入口：lead-agent `task` tool 或 subagent API
- 运行时：`backend/src/subagents/`
- 上下文：通过 context snapshot 注入
- 状态：统一回写 thread/task/subagent status

当前策略：

- feature/workflow 主导 orchestration
- subagent 不抢占 feature 分发语义
- subagent prompt 与上下文使用裁剪快照，而不是整套主 agent middleware

## 7. Result Contract

workspace feature 结果的关键字段：

- `success`
- `feature_id`
- `feature_name`
- `workspace_type`
- `handler_key`
- `message`
- `data`
- `artifacts`
- `refresh_targets`

当前 `refresh_targets` 主要包括：

- `artifacts`
- `papers`
- `workspace`

## 8. Key Files

- `backend/src/gateway/routers/chat.py`
- `backend/src/application/handlers/chat_turn_handler.py`
- `backend/src/tools/builtins/workspace.py`
- `backend/src/application/handlers/feature_execution_handler.py`
- `backend/src/task/handlers/workspace_feature_handler.py`
- `backend/src/agents/workspace_lead_agent.py`
- `backend/src/workspace_features/registry.py`
- `backend/src/subagents/context_snapshot.py`
- `frontend/lib/workspace-chat-entry.ts`
- `frontend/lib/workspace-feature-routes.ts`
- `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
