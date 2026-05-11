# Workspace Feature 域当前架构

更新时间：2026-05-11
状态：Current
适用项目：`wenjin`

本文档定义 workspace v2 场景下 Two-Agent 拓扑、Capability 驱动执行、Output Mapping、SSE 桥接与 Commit 流程的关系与边界，作为实现与验收依据。

## 1. 目标与约束

### 1.1 目标

1. 用户侧严格单入口：Chat Agent（左面板）统一处理对话与能力触发。
2. 能力侧数据驱动：YAML seed + DB-backed capability 定义，Admin 可运行时编辑。
3. capability 执行完整生命周期：TaskBrief → LeadAgentRuntime v2 → TaskReport → SSE → ResultCard → Commit。
4. 结构化输出：5 种 ResultOutput kind（library_item, document, memory_fact, decision, task），通过 OutputMappingResolver 从 subagent 结果映射。
5. 用户确认后才落库：ResultCard 展示 → 用户勾选 → commit → room services 写入。
6. Two-Agent 拓扑：Chat Agent 负责对话入口，Lead Agent v2 负责执行编排，1:1 映射，lead-busy 阻塞新派发。

### 1.2 非目标

1. 不引入新的用户入口页面替代 chat 主路由。
2. 不把 capability 做成绕过 Chat Agent 的独立执行框架。
3. 不把 subagent 暴露为面向用户的单独产品主链。
4. 不让 thread message 承载 execution 当前状态。

## 2. 核心关系模型

```text
User/UI (Chat)
        │
        ▼
Chat Agent (左面板)
        │
        ├─ pure chat → 直接回复
        └─ 能力意图 → launch_feature tool
                          │
                          ▼
              ExecutionService.create_execution()
                          │
                          ▼
              Celery execute_execution task
                          │
                          ▼
              ExecutionEngineV2.run()
                          │
                          ▼
              LeadAgentRuntime.run_session()
               ├─ CapabilityResolver.load()
               ├─ compile_graph()
               ├─ LangGraph nodes (v2 subagents)
               ├─ OutputMappingResolver.resolve()
               └─ publish execution.completed
                          │
                          ▼
              TaskReport (status + outputs + errors)
                          │
                          ▼
              SSE → useChatStream → ResultCard
                          │
                          ▼
              用户 commit → POST /api/executions/{id}/commit
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
      Library       Documents     Memory ...
      RoomService   RoomService   RoomService
```

## 3. 组件职责边界

| 组件 | 应负责 | 不应负责 |
| --- | --- | --- |
| Chat Agent | 普通问答、意图识别、能力触发、追问交互、最终收口摘要 | 直接执行 graph、驱动 subagent 编排、持有 execution 状态 |
| launch_feature tool | lead-busy 检查、创建 ExecutionRecord、派发 Celery task | 业务执行细节 |
| ExecutionEngineV2 | 获取 ExecutionRecord、标记运行、调用 LeadAgentRuntime、持久化 TaskReport、记录运行历史 | capability 解析、graph 编译 |
| LeadAgentRuntime v2 | 加载 capability、编译 graph、执行 subagent graph、收集输出、发布事件 | 处理 chat 会话文本策略 |
| CapabilityResolver | 从 YAML seed + DB 加载 capability 定义、验证完整性 | 运行时编排 |
| compiler.py | 将 graph_template 编译为 LangGraph StateGraph | 业务逻辑 |
| OutputMappingResolver | 将 YAML outputs 声明映射为类型化 ResultOutput | 执行编排 |
| V2 Subagent Registry | 管理已注册 subagent 类的查找与实例化 | feature 入口分发、用户交互 |
| execution-store | 前端 execution 记录管理与 SSE 消费 | 后端状态持久化 |
| useChatStream | SSE 事件订阅、chat/execution 双路分发、execution.completed → ResultCard 桥接 | 业务逻辑 |
| Commit Endpoint | 接收用户选中的 outputs，按 kind 路由到 room services | 执行编排 |
| Room Services | 各自 room 的数据持久化（Library/Documents/Memory/Decisions/Tasks） | 执行过程管理 |

## 4. Capability / Lead Agent / Subagent 的关系

### 4.1 Capability（数据驱动）

1. capability 定义存储在 YAML seed 文件（`backend/seed/capabilities/{workspace_type}/`）和数据库中。
2. 每个 capability 包含 `display_name`、`graph_template`（phases/tasks/subagent_type/outputs）、`brief_schema`。
3. `CapabilityResolver` 根据 `capability_id` + `workspace_type` 加载和验证 capability。
4. graph_template 的 phases 声明 `depends_on` 形成执行依赖图，支持 fan-in/fan-out。
5. 每个 task 声明 `subagent_type`（必须已在 v2 registry 注册）和 `outputs`（映射规则）。

### 4.2 Chat Agent / Lead Agent v2

1. Chat Agent（`backend/src/agents/chat_agent/agent.py`）：处理 pure chat、建议、workspace read，通过内置 `launch_feature` tool 决定何时启动 capability。
2. Chat Agent 不直接执行 graph，仅通过 `ExecutionService` 创建 execution record 并派发。
3. Lead Agent v2（`backend/src/agents/lead_agent/v2/`）：独立负责 capability 的完整执行周期。
4. Lead Agent v2 通过 `compile_graph()` 将 graph_template 动态编译为 LangGraph StateGraph。

### 4.3 Subagents（v2 Registry）

1. subagent 通过 `@subagent("name")` 装饰器注册到 `REGISTRY`（`backend/src/subagents/v2/registry.py`）。
2. 当前注册的 subagent：`scholar_searcher`、`critical_writer`、`outliner`、`clusterer`、`web_searcher` 等。
3. compiler 编译 graph 时通过 `REGISTRY.get(subagent_type)` 查找，未知 type 抛出 `KeyError`。
4. 每个 subagent 接收 `SubagentContext`（workspace_id、execution_id、prompt、inputs、tools），返回 `SubagentResult`（output、thinking、tool_calls、token_usage）。
5. subagent 执行失败时写入 `{"error": "..."}` 而非 raise，允许 graph 继续运行。
6. 支持 `retry_on_failure` 策略，task spec 中配置重试次数。

## 5. 统一契约

### 5.1 TaskBrief（输入契约）

```json
{
  "capability_id": "paper_analysis",
  "brief": {
    "paper_title": "...",
    "query": "..."
  },
  "raw_message": "用户原始消息",
  "decisions": {},
  "workspace_id": "ws_xxx"
}
```

语义：

1. `capability_id` 必须与 YAML seed 中定义的 capability 匹配。
2. `brief` 必须符合 capability 的 `brief_schema`。
3. `decisions` 携带前置决策上下文。

### 5.2 TaskReport（输出契约）

```json
{
  "execution_id": "exec_xxx",
  "capability_id": "paper_analysis",
  "status": "completed | failed_partial | cancelled",
  "duration_seconds": 42,
  "token_usage": {"input": 5000, "output": 2000},
  "narrative": "完成论文分析，共执行 3 个节点。",
  "outputs": [
    {
      "id": "search-library_item-0",
      "kind": "library_item",
      "preview": "Attention Is All You Need — Vaswani et al., 2017",
      "default_checked": true,
      "data": {"title": "...", "authors": [...], "year": 2017}
    }
  ],
  "errors": []
}
```

约束：`outputs` 通过 `OutputMappingResolver` 从 subagent `node_results` 映射生成，非硬编码。

### 5.3 Execution Event（SSE 契约）

```json
{
  "type": "execution.updated | execution.completed | execution.failed | execution.graph_structure",
  "execution_id": "exec_xxx",
  "status": "running | completed | failed | cancelled",
  "data": {}
}
```

- `execution.graph_structure`：前端 LiveWorkflowPanel 消费，渲染节点和边。
- `execution.completed`：含完整 TaskReport，前端桥接为 ResultCard。

## 6. 前端桥接与 Commit 流程

### 6.1 SSE 事件消费

`useChatStream` hook 订阅 workspace SSE 事件：

1. `chat.*` 事件 → `chat-store.handleEvent()` 处理文本/状态 block。
2. `execution.updated/completed/failed` 事件：
   - 更新 `execution-store` 中的 execution 记录。
   - 当 `execution.completed` 且含 `task_report` 时，将 `outputs` 映射为 `result_card` 事件推入 chat-store。

### 6.2 ResultCard 与 Commit

1. ResultCard 渲染每个 ResultOutput，显示 preview 和 checkbox。
2. `default_checked` 控制初始勾选状态（默认全选）。
3. 用户点击"全部接受"或手动选择后，前端调用 `POST /api/executions/{id}/commit`。
4. commit endpoint 按 `kind` 分发到对应 room service 持久化。

### 6.3 Lead-Busy 语义

1. `launch_feature` tool 查询当前 workspace 是否有 pending/running execution。
2. 如果有，返回 advisory 状态，不创建新 execution。
3. 前端 Chat Agent 收到 advisory 后告知用户当前正在执行。

## 7. Capability Graph 编译与执行

### 7.1 编译（compiler.py）

1. 遍历 `graph_template.phases`，每个 phase 的每个 task 生成一个 LangGraph node。
2. Node name 格式：`{phase_name}__{task_name}`。
3. 无 `depends_on` 的 phase 为 root phase，连接 `START`。
4. 有 `depends_on` 的 phase 建立边：src phase 的每个 node → dst phase 的每个 node（fan-in/fan-out）。
5. 无后继的 phase 连接 `END`。

### 7.2 执行（runtime.py）

1. `LeadAgentRuntime.run_session()` 是 capability 执行的完整生命周期入口。
2. 构建 `ExecutionState`（workspace_id、execution_id、inputs_for_tasks、workspace_data、node_results）。
3. 调用 `compile_graph()` 编译后 `graph.ainvoke(initial_state)` 执行。
4. 每个 node 执行前检查 Redis abort signal。
5. 执行完成后：
   - 收集 node_errors（`failed_partial` 判断）。
   - 通过 `OutputMappingResolver` 收集 outputs。
   - 构建 narrative 和 token usage。
   - 发布 `execution.completed` event。
   - 返回 `TaskReport`。

## 8. Workspace Feature Registry 与 Runtime Profile

### 8.1 Registry

文件：`backend/src/workspace_features/registry.py`

- 5 种 workspace type：thesis、sci、proposal、software_copyright、patent。
- 每个 feature 定义：id、name、description、icon、agent、handler_key、panel、stages、color、follow_up_prompt。
- 提供 `list_workspace_features()`、`get_workspace_feature()`、`get_workspace_feature_by_handler()` 查询接口。

### 8.2 Runtime Profile

文件：`backend/src/workspace_features/runtime_profiles.py`

每个 feature 的 runtime profile 定义：

- `runtime_mode`：chat_only / deterministic / compute_workflow / compute_agentic。
- `requires_compute`、`requires_sandbox`。
- `allowed_subagents`、`max_subagents`。
- `output_contract`、`review_gate`。

任何 feature 增删改都必须先更新 registry 和 runtime profile，再更新 capability YAML 和前端。

## 9. 现有代码映射到目标边界

| 现有位置 | 目标角色 |
| --- | --- |
| `backend/src/agents/chat_agent/agent.py` | Chat Agent，对话入口与意图识别 |
| `backend/src/tools/builtins/launch_feature.py` | launch_feature tool，创建 execution 并派发 |
| `backend/src/execution/engine.py` | ExecutionEngineV2，统一执行引擎 |
| `backend/src/services/execution_service.py` | ExecutionRecord CRUD 与状态管理 |
| `backend/src/services/capability_resolver.py` | CapabilityResolver，加载和验证 capability |
| `backend/src/agents/lead_agent/v2/runtime.py` | LeadAgentRuntime v2，capability 执行编排 |
| `backend/src/agents/lead_agent/v2/compiler.py` | graph_template → LangGraph 编译 |
| `backend/src/agents/lead_agent/v2/output_mapping.py` | OutputMappingResolver，outputs 映射 |
| `backend/src/subagents/v2/registry.py` | v2 subagent 注册表 |
| `backend/src/agents/contracts/task_brief.py` | TaskBrief 输入契约 |
| `backend/src/agents/contracts/task_report.py` | TaskReport 输出契约（含 5 种 ResultOutput） |
| `backend/src/workspace_features/registry.py` | workspace feature 目录 |
| `backend/src/workspace_features/runtime_profiles.py` | runtime profile 策略 |
| `backend/src/runtime/runs/manager.py` | run 管理 |
| `backend/src/runtime/stream_bridge/redis.py` | SSE 流桥接 |
| `frontend/hooks/useChatStream.ts` | SSE 事件订阅与 execution → ResultCard 桥接 |
| `frontend/stores/chat-store.ts` | chat 状态管理（7 种 block type） |
| `frontend/stores/execution-store.ts` | execution 状态管理 |

## 10. 架构守卫（必须满足）

1. 不允许任何入口绕过 Chat Agent 直调 ExecutionEngine 或 LeadAgentRuntime。
2. 不允许 Chat Agent 直接承担 graph 执行逻辑。
3. graph_template 中的 `subagent_type` 必须在 v2 REGISTRY 中注册，否则编译失败。
4. ExecutionRecord 是 execution 运行态与恢复态唯一聚合对象。
5. ResultOutput 必须通过 OutputMappingResolver 从 node_results 映射，不允许硬编码。
6. 用户 commit 前数据不写入 room，commit 后按 kind 路由到对应 room service。
7. WenjinPrism 文件写入必须走 preview/apply/discard/revert，不允许 capability 直接覆盖已有主稿。
