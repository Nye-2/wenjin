# Workspace Execution Pipeline

更新时间：2026-05-11

本文档描述 workspace v2 执行主链，覆盖 two-agent 拓扑、capability 驱动执行、LeadAgentRuntime v2、OutputMappingResolver、task contracts、SSE 事件桥接和 commit 流程。

## 1. 架构概览

v2 采用 Two-Agent 拓扑：

- **Chat Agent**（左面板）：对话入口，负责意图识别、追问澄清、日常问答。通过 `dispatch_capability` tool 触发能力执行。
- **Lead Agent v2**（右面板）：执行编排面，运行 LangGraph subagent graph，产出结构化 `TaskReport`。

执行主链：

```text
用户消息 → Chat Agent
                │
                ├─ 普通问答 → 直接回复
                └─ 能力触发 → dispatch_capability tool
                                      │
                                      ▼
                          ExecutionEngineV2
                          (ExecutionService + Celery execute_execution task)
                                      │
                                      ▼
                          LeadAgentRuntime.run_session()
                          (CapabilityResolver → compile_graph → v2 subagents)
                                      │
                                      ▼
                          OutputMappingResolver → TaskReport
                                      │
                                      ▼
                          SSE event (execution.completed)
                                      │
                                      ▼
                          前端 ResultCard → 用户 commit
                                      │
                                      ▼
                          POST /api/executions/{id}/commit → room services
```

## 2. Canonical Entry Points

### 2.1 Chat Control Plane

- `POST /api/threads/{thread_id}/runs/stream`
- `POST /api/runs/stream`
- `POST /api/threads/{thread_id}/runs/wait`
- `POST /api/runs/wait`

chat 统一通过 runs API 入口。所有 chat turns 进入 Chat Agent（`backend/src/agents/chat_agent/agent.py`），Chat Agent 通过内置 `launch_feature` tool 创建 ExecutionRecord 并派发到 v2 执行引擎。

补充：

- run 元数据通过 Redis 持久化（`runtime:runs:*`），网关重启后可恢复最近 run 记录。
- run 流事件通过 Redis Stream（`runtime:runs:stream:{run_id}`）支持 `Last-Event-ID` 回放。
- 网关启动会自动水合最近 run，并把重启前 `pending/running` run 标记为 `interrupted`。
- runs 主执行固定在 worker 内通过 Celery task 执行（`CELERY_ENABLED=true` 且 `REDIS_ENABLED=true` 为硬前置条件），gateway 仅负责 run 创建、SSE 汇聚与状态查询。

### 2.2 Execution API

- `POST /api/executions/{id}/commit` — 用户确认 commit，按 kind 路由到 room services

commit endpoint 接收用户选中的 ResultOutput 列表，按 `kind` 分发：

| kind | 目标 room service |
|------|-------------------|
| `library_item` | LibraryRoomService |
| `document` | DocumentsRoomService |
| `memory_fact` | MemoryRoomService |
| `decision` | DecisionsRoomService |
| `task` | TasksRoomService |

### 2.3 Compute Read Surface

- `GET /api/workspaces/{workspace_id}/compute/sessions`
- `GET /api/compute/sessions/{compute_session_id}`
- `GET /api/compute/sessions/{compute_session_id}/projection`

Compute 只提供用户可见工作台投影，不成为业务事实源。

## 3. Chat → Capability 协作链

1. Runs router 接收消息，解析 thread/workspace/user 运行时上下文。
2. Chat Agent 处理 pure chat（普通问答、建议、workspace read tools）。
3. 当用户意在启动 capability 时，Chat Agent 调用内置 `launch_feature` tool（`backend/src/tools/builtins/launch_feature.py`）。
4. `launch_feature` tool 执行：
   - Lead-busy check：查询当前 workspace 是否有 pending/running execution。
   - 创建 ExecutionRecord（via `ExecutionService.create_execution()`）。
   - 发布 `execution.updated` workspace event。
   - 派发 Celery `execute_execution` task 到 `long_running` queue。
5. Chat Agent 返回 `{"status": "launched", "execution_id": "...", "feature_id": "..."}` 给前端。

约束：

- pure chat 不创建 execution、task 或 compute session。
- lead-busy 时返回 advisory 状态，不排队。
- thread message 只保存发起、追问、完成摘要，不作为执行状态来源。

## 4. V2 Execution Chain

1. Celery worker 拉取 `execute_execution` task，交给 `ExecutionEngineV2.run(execution_id)`。
2. `ExecutionEngineV2`：
   - 通过 `ExecutionService.get_by_id()` 获取 ExecutionRecord。
   - 调用 `ExecutionService.start_execution()` 标记为 running。
   - 从 ExecutionRecord.params 中构造 `TaskBrief`。
   - 调用 `LeadAgentRuntime.run_session(execution_id, brief)`。
   - 完成后通过 `ExecutionService.complete_execution()` 持久化 `TaskReport`。
   - 通过 `RunHistoryService.record()` 写入运行历史。
   - 失败时标记 execution 为 failed 并 re-raise。
3. `LeadAgentRuntime.run_session()`：
   - 通过 `CapabilityResolver` 加载 capability 定义（YAML seed + DB）。
   - 发布 `execution.graph_structure` event（前端 workflow panel 消费）。
   - 调用 `compile_graph()` 将 capability 的 `graph_template` 编译为 LangGraph `StateGraph`。
   - 执行 graph（subagents 在各 node 中运行，支持 abort check）。
   - 通过 `OutputMappingResolver` 将 node_results 映射为 `ResultOutput` 列表（5 种 kind）。
   - 聚合 token usage、构建 narrative。
   - 发布 `execution.completed` event（含完整 `TaskReport`）。
   - 返回 `TaskReport`。

补充：

- graph 编译由 `compiler.py` 完成，每个 phase task 对应一个 node，node name 格式 `{phase}__{task}`。
- subagent 通过 `REGISTRY.get(subagent_type)` 查找，支持 retry_on_failure。
- node 执行失败时写入 `{"error": "..."}` 而非 raise，允许 graph 继续运行（`failed_partial` 状态）。
- 支持 Redis abort signal，check 在每个 node 执行前进行。

## 5. Task Contracts

### 5.1 TaskBrief（输入）

```python
class TaskBrief(BaseModel):
    capability_id: str      # 能力标识
    brief: dict             # 能力输入数据
    raw_message: str        # 用户原始消息
    decisions: dict[str, str]  # 前置决策
    workspace_id: str       # workspace 标识
```

### 5.2 TaskReport（输出）

```python
class TaskReport(BaseModel):
    execution_id: str
    capability_id: str
    status: Literal["completed", "failed_partial", "cancelled"]
    duration_seconds: int
    token_usage: dict[str, int] | None
    narrative: str                          # 人读摘要
    outputs: list[ResultOutput]             # 结构化输出（5 种 kind）
    errors: list[ResultError]               # 错误记录
```

### 5.3 ResultOutput（5 种 kind）

| kind | 数据模型 | 说明 |
|------|----------|------|
| `library_item` | LibraryItemData | 文献条目（论文、书籍等） |
| `document` | DocumentData | 存储文档 |
| `memory_fact` | MemoryFactData | 记忆事实 |
| `decision` | DecisionData | 记录的决策 |
| `task` | TaskData | 跟进任务 |

每个 ResultOutput 携带 `id`、`preview`、`default_checked` 和对应 `data`。前端 ResultCard 使用 `default_checked` 初始化 checkbox 状态。

## 6. OutputMappingResolver

`OutputMappingResolver` 将 capability YAML 中声明的 `outputs` 映射规则应用于 subagent 的 `node_results`，产出类型化的 `ResultOutput` 对象。

工作流程：

1. 遍历 `graph_template.phases[].tasks[].outputs[]` 声明。
2. 每个声明指定 `kind`（如 `library_item`）和 `mapping`（字段到模板表达式的映射）。
3. 支持 `iterate_on`：当输出是数组时，为每个元素生成独立 ResultOutput。
4. 模板表达式支持 `{{output.field}}` 和 `{{item.field}}` 占位符。
5. 构造对应的 Pydantic data model，生成 preview 文本。

## 7. Capability 数据驱动

### 7.1 Capability YAML Seed

capability 定义通过 YAML seed 文件管理：

- 位置：`backend/seed/capabilities/{workspace_type}/`
- 包含：display_name、description、graph_template（phases/tasks/subagent_type/outputs）、brief_schema。
- DB-backed：Admin 可在运行时编辑，无需重新部署。

### 7.2 CapabilityResolver

`CapabilityResolver` 负责加载和验证 capability：

- 根据 `capability_id` 和 `workspace_type` 查找。
- 验证 graph_template 中引用的 `subagent_type` 是否已在 v2 registry 注册。
- 返回包含完整执行上下文的 capability 对象。

### 7.3 Workspace Feature Registry

`workspace_features/registry.py` 维护各 workspace type 的 feature 目录：

- 5 种 workspace type：thesis、sci、proposal、software_copyright、patent。
- 每个 feature 定义包含 id、name、description、icon、agent、handler_key、stages 等。
- `runtime_profiles.py` 定义每个 feature 的 runtime profile（mode、sandbox policy、subagent policy 等）。

## 8. V2 Subagent Registry

subagent 通过类型化注册表管理（`backend/src/subagents/v2/registry.py`）：

- 使用 `@subagent("name")` 装饰器注册 `SubagentBase` 子类。
- `REGISTRY.get(name)` 查找，未知 name 抛出 `KeyError`。
- 已注册 subagent：`scholar_searcher`、`critical_writer`、`outliner`、`clusterer`、`web_searcher` 等。
- 每个 subagent 接收 `SubagentContext`，返回 `SubagentResult`（output、thinking、tool_calls、token_usage）。

## 9. SSE 事件桥接与前端消费

### 9.1 useChatStream Hook

`frontend/hooks/useChatStream.ts` 订阅 workspace SSE 事件，双路分发：

- `chat.*` 事件 → `chat-store.handleEvent()`（文本/状态更新）。
- `execution.updated/completed/failed` 事件 → `execution-store`（执行状态）+ 桥接为 ResultCard 事件进入 chat-store。

### 9.2 执行完成桥接

当 `execution.completed` 事件到达：

1. 从 `TaskReport` 提取 `outputs` 列表。
2. 将每个 output 映射为 `result_card` 事件，推入 chat-store。
3. 前端 ChatPanel 渲染 ResultCard（带 checkbox），默认全选。
4. 用户点击"全部接受"或手动选择后，调用 `POST /api/executions/{id}/commit`。

### 9.3 前端 Store

- `chat-store.ts`：管理 chat blocks（7 种 block type），处理 SSE 事件。
- `execution-store.ts`：管理 execution 记录，支持 upsert 和 currentExecution 跟踪。

## 10. Compute Projection Chain

Compute Stage 是长任务工作面，展示但不拥有业务状态。

projection 来源：

- `ExecutionRecord`：capability lifecycle、params、status、result（TaskReport）。
- Run History：执行记录、duration、token usage。
- WenjinPrism metadata：`file_changes`、`applied_file_changes`、compile info、target files。

前端通过 execution-store 和 workspace events 恢复当前执行状态，不从 thread message 反推。

## 11. WenjinPrism Write Gate

写作/LaTeX 类 capability 的关系：

```text
生成在 Capability Execution
过程在 Compute
确认在 Review Gate
落稿在 WenjinPrism
精修在 WenjinPrism
摘要回 Chat
```

当前约束：

1. 新建 Prism 项目允许初始化 seed。
2. 对已有 Prism 文件，capability 生成内容不自动覆盖；变化进入 metadata 的 `file_changes`。
3. `POST /api/latex/projects/{project_id}/file-changes/preview` 生成 diff 与 `change_signature`。
4. `POST /api/latex/projects/{project_id}/file-changes/apply` 必须携带 preview 签名。
5. apply 后写入 metadata 的 `applied_file_changes`，其中包含 undo hash 和 `revert_signature`。
6. `POST /api/latex/projects/{project_id}/file-changes/revert` 必须携带 revert 签名，并校验当前文件 hash。
7. 有待确认写入时，compile 返回 `blocked_by_review`，避免把旧稿 PDF 当作新结果。

## 12. Key Files

### V2 Core

- `backend/src/agents/chat_agent/agent.py` — Chat Agent
- `backend/src/agents/lead_agent/v2/agent.py` — Lead Agent v2 入口
- `backend/src/agents/lead_agent/v2/runtime.py` — LeadAgentRuntime
- `backend/src/agents/lead_agent/v2/compiler.py` — capability graph 编译器
- `backend/src/agents/lead_agent/v2/output_mapping.py` — OutputMappingResolver
- `backend/src/execution/engine.py` — ExecutionEngineV2
- `backend/src/subagents/v2/registry.py` — v2 subagent 注册表
- `backend/src/agents/contracts/task_brief.py` — TaskBrief 输入契约
- `backend/src/agents/contracts/task_report.py` — TaskReport 输出契约

### Services & Tools

- `backend/src/tools/builtins/launch_feature.py` — launch_feature tool
- `backend/src/services/execution_service.py` — ExecutionService
- `backend/src/services/capability_resolver.py` — CapabilityResolver
- `backend/src/workspace_features/registry.py` — workspace feature 目录
- `backend/src/workspace_features/runtime_profiles.py` — runtime profile 策略

### Gateway

- `backend/src/gateway/routers/thread_runs.py` — runs API
- `backend/src/gateway/routers/runs.py` — runs API
- `backend/src/runtime/runs/manager.py` — run 管理
- `backend/src/runtime/stream_bridge/redis.py` — SSE 流桥接

### Frontend

- `frontend/hooks/useChatStream.ts` — SSE 事件桥接 hook
- `frontend/stores/chat-store.ts` — chat 状态管理
- `frontend/stores/execution-store.ts` — execution 状态管理
- `frontend/app/(workbench)/workspaces/[id]/v2/page.tsx` — v2 workspace 页
- `frontend/app/(workbench)/workspaces/[id]/v2/components/ChatPanel.tsx` — chat 面板
- `frontend/app/(workbench)/workspaces/[id]/v2/components/LiveWorkflowPanel.tsx` — workflow 面板
