# Workspace Execution Pipeline

更新时间：2026-04-28

本文档描述 workspace 当前执行主链，覆盖 chat、features、execution sessions、compute sessions、tasks、subagents、WenjinPrism 和最终 writeback。

## 1. Canonical Entry Points

### 1.1 Chat Control Plane

- `POST /api/threads/{thread_id}/runs/stream`
- `POST /api/runs/stream`
- `POST /api/threads/{thread_id}/runs/wait`
- `POST /api/runs/wait`

chat 统一通过 runs API 入口。所有 chat turns 进入 lead-agent（`create_react_agent`），lead-agent 通过内置 `launch_feature` tool 直接调用 `FeatureIngressService.launch()` 来启动 feature，无需上游 router。

补充：

- run 元数据通过 Redis 持久化（`runtime:runs:*`），网关重启后可恢复最近 run 记录。
- run 流事件通过 Redis Stream（`runtime:runs:stream:{run_id}`）支持 `Last-Event-ID` 回放。
- 网关启动会自动水合最近 run，并把重启前 `pending/running` run 标记为 `interrupted`。
- runs 主执行固定在 worker 内通过 `src.task.tasks.execute_run` 执行（`CELERY_ENABLED=true` 且 `REDIS_ENABLED=true` 为硬前置条件），gateway 仅负责 run 创建、SSE 汇聚与状态查询。

### 1.2 Feature API

- `POST /api/workspaces/{workspace_id}/features/{feature_id}/execute`

这是 workspace feature 的 canonical API 入口。它不直接执行 graph，而是构造 `FeatureLaunchCommand` 并调用 `FeatureIngressService.launch(command)` 创建或恢复 feature 事务。

### 1.3 Compute Read Surface

- `GET /api/workspaces/{workspace_id}/compute/sessions`
- `GET /api/compute/sessions/{compute_session_id}`
- `GET /api/compute/sessions/{compute_session_id}/projection`

Compute 只提供用户可见工作台投影，不成为业务事实源。projection 从 `ExecutionSession`、`TaskRecord`、runtime snapshot、subagent records、artifacts、sandbox file references 和 WenjinPrism metadata 聚合。

### 1.4 Domain Ingress

- `FeatureLaunchCommand`（launch/resume 输入）
- `FeatureIngressService.launch(command)`

chat、feature API、activity retry 和 automation 只能作为 adapter 调用 domain ingress，不允许绕过 ingress 直调 `FeatureSubmissionService`、task handler 或 graph。

## 2. Chat -> Feature 协作链

1. Runs router 接收消息，解析 thread/workspace/user 运行时上下文。
2. `ThreadTurnHandler.prepare_turn()` 写入 user message 并设置 thread running。
3. 所有 chat turns 统一进入 lead-agent（`create_react_agent`）。
4. lead-agent 处理 pure chat（普通问答、建议、workspace read tools）。
5. 当用户意在启动 feature 时，lead-agent 调用内置 `launch_feature` tool（`backend/src/tools/builtins/launch_feature.py`），该 tool 直接构造 `FeatureLaunchCommand` 并调用 `FeatureIngressService.launch()`。

约束：

- skill 只作为 feature 入口语义，不是独立执行框架。
- pure chat 不创建 task、execution session 或 compute session。
- feature 所需业务输入统一放在 `params`，不再平铺到顶层形成双事实源。
- thread message 只保存发起、追问、完成摘要和 pointer metadata，不作为 feature 当前状态来源。

## 3. Feature Execution Chain

1. 入口 adapter 构造 `FeatureLaunchCommand`：
   - 统一承载 `workspace_id/feature_id/params/thread_id/skill_id/execution_session_id/launch_source`。
   - launch 与 resume 使用同一命令对象，`execution_session_id` 非空时表示 resume。
2. `FeatureIngressService.launch(command)`：
   - 校验 workspace/thread/user 绑定。
   - 根据 `workspace_type + feature_id` 查 registry。
   - 创建或恢复 `ExecutionSession`。
   - 创建或复用唯一 `ComputeSession`。
   - 缺参时将 session 置为 `awaiting_user_input` 并返回结构化追问。
3. `FeatureSubmissionService.execute(...)`：
   - 校验 workspace owner。
   - 执行 policy / lock / idempotency 检查。
   - 生成 canonical task payload。
   - 提交给 `TaskService`。
4. Celery worker 拉取任务并交给 workspace feature runtime。
4. `FeatureLeaderRuntime.execute_feature(...)` 根据 runtime profile 选择 deterministic workflow、`feature_leader.graph_registry` 注册的 LangGraph graph 或 AgentHarness。
5. feature graph/service 产出 runtime blocks、draft/review/file-change packs、artifacts、activity 和 token usage。
6. worker 根据 `services/billing_policy.py` 的 feature token policy 在成功后结算积分。
7. 结果统一写回：
   - `task_records`
   - `execution_sessions`
   - `compute_sessions` projection 依赖的源数据
   - artifacts
   - workspace activities
   - subagent records
   - workspace events

补充：

- feature resume 必须复用同一 execution session 和 compute session。
- subagent 缺少 `execution_session_id` 时拒绝执行。
- AgentHarness 只能作为 Compute 内部能力，不能接管 workspace/thread/billing/artifact/task lifecycle。

## 4. Compute Projection Chain

Compute Stage 是长任务工作面，展示但不拥有业务状态。

projection 来源：

- `ComputeSessionRecord`：工作台 shell、active view、sandbox session 指针。
- `ExecutionSessionRecord`：feature lifecycle、params、task ids、artifact ids、next actions。
- `TaskRecord`：worker 状态、progress、runtime_state、result。
- `SubagentTaskRecord`：子任务状态、metadata、输出摘要。
- runtime snapshot：phases、blocks、activity。
- artifacts / file refs：sandbox files、linked files、artifact ids。
- WenjinPrism metadata：`file_changes`、`applied_file_changes`、compile info、target files。

前端 `ComputeStage` 通过 compute store 和 workspace events 恢复当前任务，不从 thread message 反推状态。

## 5. WenjinPrism Write Gate

写作/LaTeX 类 feature 的关系：

```text
生成在 Feature
过程在 Compute
确认在 Review Gate
落稿在 WenjinPrism
精修在 WenjinPrism
摘要回 Chat
```

当前约束：

1. 新建 Prism 项目允许初始化 seed。
2. 对已有 Prism 文件，feature 生成内容不自动覆盖；变化进入 metadata 的 `file_changes`。
3. `POST /api/latex/projects/{project_id}/file-changes/preview` 生成 diff 与 `change_signature`。
4. `POST /api/latex/projects/{project_id}/file-changes/apply` 必须携带 preview 签名。
5. apply 后写入 metadata 的 `applied_file_changes`，其中包含 undo hash 和 `revert_signature`。
6. `POST /api/latex/projects/{project_id}/file-changes/revert` 必须携带 revert 签名，并校验当前文件 hash。
7. 有待确认写入时，compile 返回 `blocked_by_review`，避免把旧稿 PDF 当作新结果。

ComputeStage 和 WenjinPrism 均可触发 preview / apply / discard / revert；处理后以 Prism metadata 刷新 Compute projection。

## 6. Feature Graph 和 Service 边界

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
  - generation mode

规则：

- graph 保持轻量，不吸收大块 LLM 业务逻辑。
- service 统一通过共享 JSON helper 约束结构化生成。
- fallback 只允许作为领域内部策略，不允许作为旧主链兼容设施。

## 7. Runtime Profile Is Source of Truth

文件：

- `backend/src/workspace_features/registry.py`
- `backend/src/workspace_features/runtime_profiles.py`

registry 决定：

- workspace type 列表
- feature 元信息（id/name/description/icon/agent/panel/stages）
- `handler_key`
- `task_type`
- `follow_up_prompt`

runtime profile 决定：

- runtime mode
- 是否需要 Compute
- sandbox policy
- subagent policy
- AgentHarness provider
- output contract
- review gate

任何 feature 增删改都必须先更新 registry 和 runtime profile，再更新 graph/service/frontend。

## 8. Subagents in the Pipeline

subagents 当前是 Compute 内部 worker 能力，不是独立 public API 或产品主链。

- 创建入口：feature leader runtime / AgentHarness。
- 运行时：`backend/src/subagents/`
- 上下文：通过 execution-bound context snapshot 注入。
- 状态：写入 `subagent_task_records`，并通过 workspace events / compute projection 展示。

当前策略：

- feature/runtime profile 主导 orchestration。
- subagent 不抢占 feature 分发语义。
- subagent prompt 与上下文使用裁剪快照。
- public subagent router 已移除。

## 9. Result Contract

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
- `references`
- `workspace`

写作类结果还可能包含：

- `latex_project_id`
- `prism_url`
- `file_changes`
- `applied_file_changes`
- `compile_status`

## 10. Key Files

- `backend/src/gateway/routers/thread_runs.py`
- `backend/src/gateway/routers/runs.py`
- `backend/src/runtime/runs/manager.py`
- `backend/src/runtime/stream_bridge/redis.py`
- `backend/src/application/handlers/thread_turn_handler.py`
- `backend/src/tools/builtins/launch_feature.py`
- `backend/src/application/commands.py`
- `backend/src/application/services/feature_launch_service.py`
- `backend/src/application/services/feature_submission_service.py`
- `backend/src/compute/session_service.py`
- `backend/src/compute/projection_service.py`
- `backend/src/gateway/routers/compute.py`
- `backend/src/task/tasks/base.py`
- `backend/src/agents/feature_leader/runtime.py`
- `backend/src/agents/harness/`
- `backend/src/workspace_features/registry.py`
- `backend/src/workspace_features/runtime_profiles.py`
- `backend/src/workspace_features/latex_sync.py`
- `frontend/lib/workspace-thread-entry.ts`
- `frontend/components/compute/ComputeStage.tsx`
- `frontend/stores/compute.ts`
- `frontend/stores/latex.ts`
- `frontend/app/(workbench)/workspaces/[id]/components/ThreadPanel.tsx`
