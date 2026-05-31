# Unified Execution Architecture — Review Issues (2026-05-08)

> 来源：代码架构审查（非产品反馈，故不填 Feedback Date）
> 关联仓库：wenjin (frontend + backend)

---

## ✅ 已修复（本轮已合入，无需再开 issue）

### 1. `[FIXED]` Feature task 幂等检查因 TaskRecord 不更新而失效

- **Issue type**: Bug
- **Labels**: `backend`, `execution`, `task-system`
- **描述**: `TaskStore.mark_task_started/completed` 对 `WORKSPACE_FEATURE_TASK` 直接 `return`，导致 feature task 的 `TaskRecord` 永远停留在 `"pending"`。用户重复提交同一 feature 时，`find_active_task` 永远命中旧记录，新任务被静默拒绝。
- **修复**: `task/store.py` + `task/tasks/base.py` — 对 feature task 做最小化 status 更新（running/completed/failed），保留并发控制和幂等检查。

### 2. `[FIXED]` TaskService 对 feature task 发布 stale `task.updated` workspace event

- **Issue type**: Bug
- **Labels**: `backend`, `execution`, `events`
- **描述**: `TaskService.submit_task()` 对所有 task type 发布 `task.updated` event。feature task 的 worker 已跳过 legacy 更新，但初始 event 仍会触发前端在 `workflowStore` 中创建永远不会更新的 pending task。
- **修复**: `task/service.py` — 添加 `if task_type != WORKSPACE_FEATURE_TASK:` 跳过 feature task 的 event 发布。

### 3. `[FIXED]` FeatureLaunchService 幂等命中返回错误的 execution_id

- **Issue type**: Bug
- **Labels**: `backend`, `execution`, `gateway`
- **描述**: 当 `reused_existing_task=True`（已有进行中的任务），gateway 仍预先创建新的 `ExecutionRecord` E1，但 worker 处理的是旧 task。前端拿到 E1 的 ID 订阅 stream，E1 永远不会被启动，用户看到卡住的进度条。
- **修复**: `application/services/feature_launch_service.py` — 当幂等命中时，取消新创建的 `ExecutionRecord`，并从旧 task payload 中解析真正的 `execution_id` 返回。

### 4. `[FIXED]` SubagentTaskRecord ORM 模型与 migration schema 不一致

- **Issue type**: Bug
- **Labels**: `backend`, `database`, `migration`
- **描述**: Migration 030 在 `subagent_task_records` 表添加了 `execution_id` 列，但 `SubagentTaskRecord` 模型未定义该字段，导致 ORM 与 schema 不一致。
- **修复**: `database/models/subagent_task.py` — 添加 `execution_id: Mapped[str | None]` 字段。

### 5. `[FIXED]` SubagentTaskStore 未写入 execution_id

- **Issue type**: Task
- **Labels**: `backend`, `subagent`, `execution`
- **描述**: `SubagentTaskStore.upsert_task_record()` 未从 `task.metadata` 中提取 `execution_id` 写入记录，导致新添加的 `execution_id` 列始终为 null。
- **修复**: `subagents/store.py` — 在 `upsert_task_record` 中解析并写入 `execution_id`。

### 6. `[FIXED]` 前端 execution stream 不支持断线重连

- **Issue type**: Task
- **Labels**: `frontend`, `execution`, `sse`
- **描述**: `subscribeExecutionStream` 在连接断开后直接调用 `onError`，不会自动恢复。网络抖动时用户会丢失后续执行进度。
- **修复**: `lib/api/executions.ts` — 添加自动重连逻辑（最多 3 次，指数退避），并支持 `Last-Event-ID` header 从断点恢复。

### 7. `[FIXED]` Execution SSE `Content-Location` header 指向错误 URL

- **Issue type**: Bug
- **Labels**: `backend`, `gateway`, `execution`, `sse`
- **描述**: `gateway/routers/executions.py` 的 `stream_execution` 使用了 `build_run_stream_headers(execution_id)`，返回的 `Content-Location` 为 `/api/runs/{id}/stream`（run stream 的 URL），但 execution stream 的实际 URL 是 `/api/executions/{id}/stream`。虽然前端当前不消费该 header，但会破坏未来依赖 `Content-Location` 的客户端（如断线重连时解析 resume URL）。
- **修复**: `gateway/routers/executions.py` — 不再复用 `build_run_stream_headers`，改为显式设置正确的 `Content-Location: /api/executions/{execution_id}/stream`。

---

## ✅ 后续复查已收敛

### 8. `[FIXED]` `ExecutionNodeRecord` 已成为节点级事实源

- **Issue type**: Task
- **Labels**: `backend`, `execution`, `database`, `tech-debt`
- **原问题**: `execution_nodes` 表存在，但执行链路只读取 `ExecutionRecord.node_states` JSONB，导致节点级表闲置并形成双事实源。
- **当前状态**: `LeadAgentRuntime` 通过 `ExecutionService.upsert_node_event()` 写入 `execution_nodes`；`GET /executions/{execution_id}/nodes/{node_id}` 通过 `ExecutionService.find_node_by_node_id()` 读取节点详情。`graph_structure` 只负责静态节点拓扑与 label/phase 默认值。
- **防回归**: `tests/architecture/test_dataservice_boundaries.py::test_execution_node_detail_router_uses_execution_node_records` 禁止 router 重新读取 `record.node_states`。

### 9. `[FIXED]` feature launch 并发控制已迁到 ExecutionRecord

- **Issue type**: Task
- **Labels**: `backend`, `execution`, `task-system`, `refactor`
- **原问题**: feature task 依赖 `TaskRecord` guarded create 做并发限制，产品执行事实源与后台任务记录耦合。
- **当前状态**: `launch_feature` 通过 active `ExecutionRecord` 判断 lead-busy；`TaskRecord` 仅保留为 Celery / upload / generic background task 的 durable task history，不再作为 feature execution 并发事实源。
- **边界**: 后续新增 feature execution 入口必须复用 `ExecutionRecord` lead-busy 语义，不得回退到 `TaskRecord.find_active_task()`。
