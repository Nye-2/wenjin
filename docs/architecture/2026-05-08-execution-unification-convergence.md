# Wenjin 执行架构统一收敛 — 完整设计文档

> 状态：已冻结，进入实施阶段  
> 作者：Kimi Code CLI (AI Agent)  
> 日期：2026-05-08  
> 关联文档：
> - [workflow-panel-redesign.md](../superpowers/specs/2026-05-08-workflow-panel-redesign.md)
> - [system-architecture.md](./system-architecture.md)
> - [workspace-execution-pipeline.md](./workspace-execution-pipeline.md)

---

## 目录

- [0. 心路历程](#0-心路历程)
- [1. 参考项目：deer-flow 架构深度解析](#1-参考项目deer-flow-架构深度解析)
- [2. 现状调研：wenjin 的"飘逸"架构](#2-现状调研wenjin-的飘逸架构)
- [3. 问题诊断：五大根因](#3-问题诊断五大根因)
- [4. 统一方案：Execution 模型](#4-统一方案execution-模型)
- [5. 数据流全景](#5-数据流全景)
- [6. API 设计](#6-api-设计)
- [7. deer-flow 迁移清单](#7-deer-flow-迁移清单)
- [8. 数据库迁移](#8-数据库迁移)
- [9. 实施路线图](#9-实施路线图)
- [10. 风险与缓解](#10-风险与缓解)
- [11. 开放问题](#11-开放问题)
- [12. 深度补充：监控与可观测性](#12-深度补充监控与可观测性)
- [13. 深度补充：降级策略](#13-深度补充降级策略)
- [14. 深度补充：数据回填幂等性策略](#14-深度补充数据回填幂等性策略)
- [15. 深度补充：Feature graph_structure 发射点](#15-深度补充feature-graph_structure-发射点)
- [16. 深度补充：前端 Store 集成细节](#16-深度补充前端-store-集成细节)
- [附录：核实修正记录](#附录核实修正记录)

---

## 0. 心路历程

### 0.1 用户最初的诉求

用户在 2026-05-08 提出了一个复合需求：

1. **迁移 deer-flow 基础设施**： deer-flow（`/Users/ze/deer-flow`）是一套基于 LangGraph 的 super agent harness 系统，用户的 wenjin 项目最初是从 deer-flow 迁移过来的，但迁移从未完成（`deerflow_adapter.py` 里直接 `raise NotImplementedError`）。用户希望把 deer-flow 最新的基础设施（Stream Bridge、Run Worker、Run Journal、中间件链等）完整迁移到 wenjin 中。

2. **重新设计 LiveWorkflowPanel**：当前的 Panel 使用 `Run → Phase → Subagent` 的三层树形模型，存在严重的信息层级扁平化问题——task 节点和 subagent 节点难以区分，phase `-1` 的 task 伪节点显示为 `0`，run title 不稳定。用户希望每个 task card 内部显示一个**LangGraph node flow**，节点完成时变绿，可点击展示 input/output/thinking/tools。

3. **重新收敛 chat ↔ execution ↔ panel 链路**：随着多次迭代，chat 消息触发执行、执行流式输出到 panel、panel 状态反馈到 chat 这三条链路已经"飘逸"（走样、不收敛），需要重新设计为一套干净的架构。

### 0.2 第一轮理解：修 bug 还是重构架构？

我的第一反应是：先修当前系统的 bug，让现有架构能工作，再谈重构。因此我先修复了四个关键 bug：

1. **Double SSE**：`useWorkflowSubscription.ts` 和 `useWorkspaceEventStream.ts` 同时订阅 workspace events，导致事件重复处理。
2. **Run ID 分裂**：task 事件用 `task_id` 作为 run key，subagent 事件用 `execution_session_id` 作为 run key，同一 execution 被拆成两个 run。
3. **Race condition**：`ensureWorkspaceThread` 在 API 调用期间如果本地插入了新消息，返回后会覆盖本地状态。
4. **Stream error 删除用户消息**：流式请求失败时 fallback 逻辑会删除用户已发送的消息。

修复后 135 个测试全部通过。但这只是**治标**。用户明确指出："项目中的基础设施是飘逸的，架构随着多次修改变得不收敛。"

### 0.3 第二轮理解：深挖架构漂移

我启动了四个并行的 explore agent，分别调研：

1. **deer-flow 架构**：理解 StreamBridge、RunWorker、RunJournal、TaskTool、中间件链的完整实现。
2. **wenjin 后端执行路径**：理解 Feature Execution Path 和 Chat Execution Path 的完整链路。
3. **wenjin 前端状态管理**：理解 workflow-store、thread-store、workspace-store 的事件消费方式。
4. **数据库模型**：理解 TaskRecord、ExecutionSessionRecord、RunRecord、SubagentTaskRecord 的 schema 和关系。

调研结果揭示了一个惊人的事实：**wenjin 的两条执行路径（Feature vs Chat）共享零基础设施**——不同的状态机、不同的事件系统、不同的持久化层、不同的前端消费方式。这不是"部分迁移 deer-flow"能解决的问题，而是需要**根本性的架构统一**。

### 0.4 第三轮理解：提出关键架构问题

基于调研，我提出了五个必须用户拍板的架构决策：

| # | 问题 | 选项 | 用户选择 |
|---|------|------|---------|
| 1 | Feature Execution 的入口模型 | A. 统一到 Thread Run / B. 保留独立路径但统一状态机 / C. 保持现状只做事件层收敛 | **A** |
| 2 | 事件系统收敛策略 | A. Workspace Events + 统一 Execution Stream / B. 所有事件走 Workspace Events / C. 完全采用 deer-flow 模型 | **A** |
| 3 | 数据模型收敛 | A. 引入 Execution 统一根实体 / B. 保留现有表但统一枚举 / C. 完全迁移到 deer-flow 模型 | **A** |
| 4 | deer-flow 中间件迁移范围 | A. 选择性迁移缺失功能 / B. 完全替换 / C. 不迁移只迁基础设施 | **A** |
| 5 | LiveWorkflowPanel 数据契约 | A. Execution Stream 嵌入 graph 结构 / B. API + 事件更新 / C. 前端自行推断 | **A** |

用户全部选择了 **A 选项**（最彻底的收敛方案）。这意味着：
- Feature execution 也将通过 Thread Run 启动（在 thread 中插入系统消息后统一走 execution）
- 保留 Workspace Events 但大幅精简，所有执行流数据走统一的 Execution Stream
- 引入 `ExecutionRecord` 作为统一根实体，取代 TaskRecord + ExecutionSessionRecord
- 选择性迁移 deer-flow 缺失的中间件（LoopDetection、Clarification 等）
- Panel 通过 Execution Stream 收 graph 结构事件，一次性拿到拓扑，后续只收状态更新

### 0.5 第四轮：深度设计

基于用户确认的方向，我进入了 Plan Mode，完成了以下设计：

1. **统一执行层**：`ExecutionService` + `ExecutionRecord` + `ExecutionNodeRecord`
2. **统一事件流**：`ExecutionStream`（基于 Redis Streams，借鉴 deer-flow StreamBridge）
3. **执行引擎**：`ChatExecutionEngine` + `FeatureExecutionEngine` 共享 `ExecutionEngine` 接口
4. **前端状态层**：`execution-store` + `useExecutionStream` + 兼容性适配层
5. **API 设计**：`/executions/*` 新端点 + 旧端点兼容层
6. **数据库迁移**：`executions` + `execution_nodes` 表 + 历史数据回填
7. **实施路线图**：5 个 phase，共 7 周

### 0.6 核心洞察

整个设计过程中，最关键的三个洞察：

**洞察 1：deer-flow 的"单一假设"是解药**
deer's 核心假设是**所有执行都是 thread 中的 message turn**。wenjin 的 Feature Execution 走独立路径（Panel 直接触发）打破了这一假设，导致了整个架构的分裂。统一回 thread-based 模型是收敛的根本。

**洞察 2：事件系统比数据模型更重要**
即使数据模型统一了，如果事件系统不统一（三个独立事件流），前端仍然被迫做大量适配。因此 Execution Stream 的设计优先级高于 ExecutionRecord 的表设计。

**洞察 3：兼容性层是迁移的关键**
不要试图一次性重写所有代码。通过 `executionToRun` 兼容性适配层，可以让 `LiveWorkflowPanel` 在 Phase 1-3 **零改动**地继续工作，同时新系统逐步接管。这大大降低了迁移风险。

---

## 1. 参考项目：deer-flow 架构深度解析

### 1.1 什么是 deer-flow

deep-flow（Deep Exploration and Efficient Research Flow）是一个开源的 **super agent harness**，基于 LangGraph 构建。它的核心定位是：为单一会话式 AI 和复杂自主工作流之间架起桥梁。

关键组件：
- **Lead Agent Factory**：`make_lead_agent()` 创建主 agent graph
- **Subagent Executor**：通过 `task` tool 在后台线程 spawn subagent
- **Stream Bridge**：解耦事件生产者（worker）和消费者（SSE）
- **Run Journal**：LangChain callback handler，捕获 LLM/tool/lifecycle 事件到 DB
- **中间件链**：14 个中间件注入行为（guardrails、loop detection、clarification 等）

### 1.2 StreamBridge 机制

deer's StreamBridge 是一个**纯内存的 per-run 事件日志**，位于 `backend/packages/harness/deerflow/runtime/stream_bridge/`：

```python
# backend/packages/harness/deerflow/runtime/stream_bridge/memory.py
class MemoryStreamBridge(StreamBridge):
    def __init__(self, *, queue_maxsize: int = 256):
        self._streams: dict[str, _RunStream] = {}  # run_id → event list
        self._counters: dict[str, int] = {}

    async def publish(self, run_id: str, event: str, data: Any) -> None:
        stream = self._get_or_create_stream(run_id)
        entry = StreamEvent(id=self._next_id(run_id), event=event, data=data)
        stream.events.append(entry)
        if len(stream.events) > self._maxsize:
            # 丢弃最旧的事件
            overflow = len(stream.events) - self._maxsize
            del stream.events[:overflow]
            stream.start_offset += overflow
        stream.condition.notify_all()

    async def subscribe(self, run_id: str, *, last_event_id: str | None = None):
        # 支持 Last-Event-ID 重放
        # 支持 heartbeat（15s 超时）
        # 支持 END_SENTINEL 终止
```

**wenjin 已有等价实现**：`backend/src/runtime/stream_bridge/memory.py`（bounded buffer 512），但**仅用于 chat runs**。Feature execution 完全不使用流式抽象。

**关键设计**：
- **Bounded buffer**：默认 256 条事件，旧事件被丢弃
- **Replay**：通过 `last_event_id` 线性扫描数组重放
- **Pub/sub**：`asyncio.Condition` 通知所有等待的 subscriber
- **Heartbeat**： subscriber 超时未收到事件时收到心跳帧

**wenjin 的适配**：

wenjin 已有 **两级 StreamBridge 实现**：
1. **`MemoryStreamBridge`**（`runtime/stream_bridge/memory.py`，bounded buffer 512）— 纯内存，仅用于 gateway 进程的 chat run SSE
2. **`RedisStreamBridge`**（`runtime/stream_bridge/redis.py`，bounded buffer 512，TTL 86400s）— **Redis Streams 后端**，支持 `XADD`/`XREAD`，**已用于跨 worker 的 chat run 流**

Feature execution **完全不使用流式抽象** — subagent 进度通过 `workspace_events.publish_workspace_event("subagent.updated", ...)` 发布。

统一方案需要：
1. **扩展 `RedisStreamBridge`** 使其同时覆盖 feature execution（目前 feature 路径完全缺失流式抽象）
2. **统一 key prefix**：chat runs 用 `runtime:runs:stream:{run_id}`，executions 用 `execution:stream:{execution_id}`
3. **保留接口语义**：publish/subscribe/replay/heartbeat（`RedisStreamBridge` 已完整实现）

### 1.3 RunWorker 执行模型

文件：`backend/packages/harness/deerflow/runtime/runs/worker.py`

```python
async def run_agent(bridge, run_manager, record, *, ctx, agent_factory, graph_input, config):
    # 1. Mark running
    await run_manager.set_status(run_id, RunStatus.running)

    # 2. Capture pre-run checkpoint（用于 rollback）
    if checkpointer is not None:
        ckpt_tuple = await checkpointer.aget_tuple(config_for_check)
        pre_run_checkpoint_id = ckpt_tuple.config["configurable"]["checkpoint_id"]

    # 3. Publish metadata
    await bridge.publish(run_id, "metadata", {"run_id": run_id, "thread_id": thread_id})

    # 4. Build agent
    agent = agent_factory(config=runnable_config)
    agent.checkpointer = checkpointer
    agent.store = store

    # 5. Stream via graph.astream()
    async for chunk in agent.astream(graph_input, config=runnable_config, stream_mode=single_mode):
        if record.abort_event.is_set():
            break
        sse_event = _lg_mode_to_sse_event(single_mode)
        await bridge.publish(run_id, sse_event, serialize(chunk))

    # 6. Final status + rollback support
    if record.abort_event.is_set():
        if action == "rollback":
            await _rollback_to_pre_run_checkpoint(...)
        else:
            await run_manager.set_status(run_id, RunStatus.interrupted)
    else:
        await run_manager.set_status(run_id, RunStatus.success)

    # 7. Cleanup
    await bridge.publish_end(run_id)
    asyncio.create_task(bridge.cleanup(run_id, delay=60))
```

**关键设计**：
- **Checkpointer snapshot**：运行前 capture checkpoint，支持 `multitask_strategy=rollback`
- **Abort event**：`asyncio.Event` 用于 cooperative cancellation
- **Stream modes**：支持 `values`, `updates`, `messages`, `custom` 等
- **Journal integration**：RunJournal 作为 LangChain callback handler 注入

### 1.4 RunJournal 事件捕获

文件：`backend/packages/harness/deerflow/runtime/journal.py`

RunJournal 是 deer 的**审计日志系统**，通过 LangChain callbacks 捕获 9 类事件：

| Event Type | Category | Trigger |
|-----------|----------|---------|
| `run.start` | trace | `on_chain_start` (root invocation) |
| `run.end` | outputs | `on_chain_end` |
| `run.error` | error | `on_chain_error` |
| `llm.human.input` | message | `on_chat_model_start` (first human msg) |
| `llm.ai.response` | message | `on_llm_end` (with token usage, latency) |
| `llm.tool.result` | message | `on_tool_end` |
| `llm.error` | trace | `on_llm_error` |
| `middleware:{tag}` | middleware | 中间件显式调用 |

**Buffer + Flush**：
- 内存 buffer，阈值 20 条时触发 flush
- flush 是 best-effort 异步任务
- worker finally block 中强制 flush 剩余 buffer

**Token accumulation**：
- `on_llm_end` 时从 `usage_metadata` 提取 token 数
- 累加到 `_total_input_tokens`, `_total_output_tokens`
- run completion 时写入 RunStore

### 1.5 TaskTool 子代理机制

文件：`backend/packages/harness/deerflow/tools/builtins/task_tool.py`

当 lead agent 调用 `task` tool 时：

1. **解析 subagent config**：根据名称找到配置（built-in 或自定义）
2. **创建 SubagentExecutor**：在 `ThreadPoolExecutor` 中运行
3. **隔离 event loop**：每个 subagent 在持久化的独立 event loop 中运行
4. **Polling loop**：task tool 每 5 秒 poll 一次 subagent 状态
5. **Custom events**：通过 `get_stream_writer()` 发射 `task_started`, `task_running`, `task_completed` 等事件
6. **返回结果**：subagent 完成后返回 `ToolMessage`

### 1.6 中间件链

文件：`backend/packages/harness/deerflow/agents/lead_agent/agent.py`

deer's lead agent 有 **14 个中间件**（`backend/packages/harness/deerflow/agents/middlewares/`），按顺序执行：

| Order | Middleware | Hook | Purpose |
|-------|-----------|------|---------|
| 0 | ThreadDataMiddleware | `before_agent` | 创建 thread 目录 |
| 1 | UploadsMiddleware | `before_agent` | 扫描注入上传文件 |
| 2 | SandboxMiddleware | `before/after_agent` | 获取/释放 sandbox |
| 3 | DanglingToolCallMiddleware | `after_model` | 补全缺失的 ToolMessage |
| 4 | GuardrailMiddleware | `wrap_tool_call` | 安全护栏 |
| 5 | ToolErrorHandlingMiddleware | `wrap_tool_call` | 异常转 ToolMessage |
| 6 | SummarizationMiddleware | `after_model` | 上下文压缩 |
| 7 | TodoMiddleware | `after_model` | 计划模式任务列表 |
| 8 | TitleMiddleware | `after_model` | 自动生成对话标题 |
| 9 | MemoryMiddleware | `after_agent` | 记忆更新队列 |
| 10 | ViewImageMiddleware | `before_model` | 注入图像 base64 |
| 11 | SubagentLimitMiddleware | `after_model` | 截断过量并行 task call |
| 12 | LoopDetectionMiddleware | `after_model` | 检测并打破工具调用循环 |
| 13 | ClarificationMiddleware | `after_model` | 拦截 `ask_clarification` tool |

**关键规则**：`before_*` 按 0→N 顺序执行，`after_*` 按 N→0 逆序执行。ClarificationMiddleware 是最后一个，所以它的 `after_model` **最先执行**，可以短路后续中间件。

### 1.7 deer-flow 的 SSE Wire Format

```
event: metadata
data: {"run_id": "...", "thread_id": "..."}

event: values
data: {...}

event: messages
data: [...]

event: custom
data: {"type": "task_running", ...}

event: error
data: {"message": "...", "name": "..."}

event: end
data: null

: heartbeat

```

**特性**：
- `Content-Location` header 用于 SDK 元数据提取
- Heartbeat 是 SSE comment（`: heartbeat\n\n`）
- `Last-Event-ID` header 支持断线重连重放

---

## 2. 现状调研：wenjin 的"飘逸"架构

### 2.1 两条独立执行路径

#### Path A: Feature Execution（Panel 触发）

```
HTTP POST /workspaces/{id}/features/{feature_id}/launch
  → FeatureIngressService.launch()
    → ExecutionSessionService.create_session()
    → TaskService.submit_task()
      → DB: TaskRecord
      → Celery: execute_task()
        → execute_workspace_feature()
          → FeatureLeaderRuntime.execute_feature()
            → ParallelExecutor.execute_plan()
              → GlobalSubagentManager.spawn()
                → workspace_event("subagent.updated")
```

#### Path B: Chat Execution（Message 触发）

```
HTTP POST /threads/{id}/runs/stream
  → launch_thread_run()
    → RunManager.create_or_reject()
    → Celery: execute_run()
      → run_thread_turn()
        → ThreadTurnHandler.stream_turn()
          → make_lead_agent()
            → agent.ainvoke()
              → RedisStreamBridge.publish("content/reasoning/block/done")
```

**关键差异**：
- Path A 用 `TaskRecord`（DB 持久化），Path B 用 `RunRecord`（内存/Redis）
- Path A 用 Workspace pub/sub 事件，Path B 用 Redis Streams → SSE
- Path A 的 subagent 是后台线程 spawn，Path B 的 tool call 是同步 inline
- Path A 的取消是 Celery `revoke()`，Path B 的取消是 `abort_event.set()`

### 2.2 三个独立事件系统

| 系统 | Transport | 用途 | 消费者 |
|------|-----------|------|--------|
| **Workspace Events** | Redis pub/sub (`workspace:{id}:events`) | 粗粒度状态变更通知 | `useWorkspaceEventStream` |
| **Run Streams** | Redis Streams (`runtime:runs:stream:{run_id}`) | 细粒度 token 流 | `useThreadStore` (chat SSE) |
| **Task Progress** | Redis pub/sub (`task_progress:{task_id}`) | 任务进度百分比 | `/tasks/{id}/stream` (legacy) |

**问题**：这三个系统**不共享 schema、不共享时序保证**。同一个逻辑工作单元的 `task.updated` 事件和 run stream `done` 事件之间没有任何关联机制。

### 2.3 四种状态枚举

| 实体 | 状态枚举 | 值 |
|------|---------|-----|
| `TaskRecord` | `TaskStatus` | `pending`, `running`, `success`, `failed`, `cancelled` |
| `RunRecord` | `RunStatus` | `pending`, `running`, `success`, `error`, `interrupted` |
| `ExecutionSessionRecord` | `ExecutionSessionStatus` | `launching`, `running`, `completed`, `failed`, `advisory`, `cancelled` |
| `SubagentTaskRecord` | `SubagentStatus` | `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT` |

**问题**：没有统一的状态本体论（ontology）。前端 `workflow-store-support.ts` 手动把 task status 强制转换成 subagent status。

### 2.4 前端被迫做适配

当前 `workflow-store-support.ts` 的核心逻辑：

```typescript
// reduceTaskEvent: task 事件硬塞进 phase index -1
const phaseIdx = -1;
const snap: SubagentSnap = {
  task_id: task.task_id,
  status: task.status,  // 直接映射，但枚举不一致
  subagent_type: task.task_type ?? null,
  // ...其他字段缺失
};

// reduceSubagentEvent: subagent 事件按 workflow_phase_index 分组
const phaseIdx = asNumber(sa.workflow_phase_index) ?? 0;
```

**问题**：
- Task 事件和 subagent 事件的数据形状完全不同
- `execution_session_id` 在两种事件中含义不同（task 用它做 run key，subagent 也用它做 run key，但 task 事件可能缺失它）
- `reduceSubagentEvent` **不重新聚合 run status**——纯 subagent 创建的 run 永远保持 `running`
- `duration_ms` 字段是 dead UI（从未被事件或 reducer 填充）

### 2.5 已修复的 bug（治标）

在架构设计之前，我修复了四个关键 bug：

1. **Double SSE**：删除了 `useWorkflowSubscription.ts`，把 `task.updated`/`subagent.updated` 的 dispatch 合并进 `useWorkspaceEventStream.ts`。
2. **Run ID 分裂**：引入 `reduceTaskEvent()`，使用 `execution_session_id || task_id` 作为统一的 run key。
3. **Race condition**：`ensureWorkspaceThread` 添加了 `preCallMessagesLength` guard——如果 API 调用期间本地消息增加，跳过 messages 覆盖。
4. **Stream error 删除消息**：把 `multitask_strategy` 默认从 `"reject"` 改为 `"interrupt"`，并移除了 `streamAcceptedByServer` fallback。

---

## 3. 问题诊断：五大根因

### 根因 1：deer-flow 迁移从未完成

`agents/harness/deerflow_adapter.py` 里直接 `raise NotImplementedError`。项目使用 "native_wenjin" harness 替代了 deer-flow 的 harness。

**但部分 deer-flow 基础设施已经迁移**：
- `StreamBridge` / `MemoryStreamBridge`：wenjin 已有等价实现（`runtime/stream_bridge/`），但**仅用于 chat runs**
- `RunManager`：wenjin 已有 `runtime/runs/manager.py`，但**仅管理 chat runs**
- `RunJournal`：**从未迁移**，wenjin 没有审计日志系统
- `TaskTool`（子代理 spawn 机制）：wenjin 使用 `GlobalSubagentManager`，机制不同

**核心问题**：不是"什么都没迁移"，而是**迁移了一半**——chat 路径有流式基础设施，feature 路径完全没有，两者不共享任何组件。

**后果**：wenjin 的执行基础设施是"半吊子"——chat 路径有流式基础设施（`StreamBridge`、`RunManager`），feature 路径完全没有（靠 Workspace Events + DB 轮询），两者不共享任何组件。

### 根因 2：产品需求打破了 deer-flow 的核心假设

deer's 核心假设：**所有执行都是 thread 中的 message turn**。wenjin 的 Feature Execution 是用户直接从 Panel 点击触发的，不经过 chat。这创造了一个完全独立的执行路径。

**后果**：两条路径需要各自的状态机、事件系统、持久化层。任何需要在两种路径间共享的逻辑（如 subagent 管理、token 统计）都需要写两遍。

### 根因 3：事件系统缺乏统一设计

Workspace Events、Run Streams、Task Progress 是三个不同的人在不同时间为了解决不同问题而创建的。它们之间没有统一的 schema、没有版本控制、没有文档。

**后果**：前端被迫在三个不同的地方消费事件，然后在一个 reducer 里把不兼容的形状硬塞进同一棵树。

### 根因 4：数据模型没有聚合根

`TaskRecord`、`ExecutionSessionRecord`、`RunRecord`、`SubagentTaskRecord` 各自为政，没有明确的聚合根。一个 feature execution 会同时产生这四种记录，但它们之间的关联关系是隐式的、分散的。

**后果**：查询"一个 workspace 的所有活跃工作"需要查四张表。状态更新需要在四个地方同步。取消操作需要四种不同的逻辑。

### 根因 5：ComputeSession 和 ExecutionSession 职责重叠

`ExecutionSession` 被设计为"feature business state 的 SSOT"，`ComputeSession` 被设计为"UI projection"。但两者都发布事件、都被持久化、`ComputeSessionService.touch_session_by_execution()` 在每次 execution 更新时都被调用。

**后果**：分布式更新级联（cascade）难以推理事务边界。一个更新可能触发 3-4 个独立的服务调用。

---

## 4. 统一方案：Execution 模型

### 4.1 核心原则

1. **SSOT**：`ExecutionRecord` 是所有执行状态的单一真相源。`ExecutionStream` 是所有执行事件的单一真相源。
2. **Event-Driven**：后端发射细粒度事件，前端 reduce 成派生状态。不再"推送整个对象"。
3. **Graph-First**：无论 chat turn 还是 feature execution，都抽象为 `nodes[] + edges[]` 的图。
4. **Compatibility Layers**：迁移期间保留旧 API 作为透传包装，Phase 4 后删除。

### 4.2 统一执行层

#### ExecutionRecord（数据库 SSOT）

```python
class ExecutionRecord(Base):
    __tablename__ = "executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    thread_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # 执行类型鉴别器
    execution_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # "chat_turn", "feature", "document_preprocess", "reference_preprocess"

    # Feature 专属字段
    feature_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    entry_skill_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    workspace_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # 统一状态（所有执行类型共享同一套枚举）
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    # pending, running, completed, failed, cancelled, interrupted,
    # awaiting_user_input, advisory

    # 请求/结果
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 图拓扑（静态，执行开始时或早期确定）
    graph_structure: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {nodes: [{id, type, label, phase_index, metadata}],
    #  edges: [{from, to, label}]}

    # 节点状态（动态，执行过程中更新）
    node_states: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # {node_id: {status, output_preview, started_at, completed_at, token_usage}}

    runtime_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    artifact_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    next_actions: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    advisory_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 父子关系（子代理 spawn → child execution）
    parent_execution_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("executions.id"), nullable=True
    )
    child_execution_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # 调度追踪
    dispatch_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    worker_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, onupdate=utcnow
    )
```

**索引**：
- `(user_id, status)` — "我的活跃工作"查询
- `(workspace_id, feature_id, status)` — workspace feature 列表
- `(thread_id, created_at)` — thread 执行历史
- `(parent_execution_id)` — 树遍历
- `(execution_type, status)` — 按类型过滤

#### ExecutionNodeRecord（可选的细粒度持久化）

用于节点级审计追踪。V1 可以用 `ExecutionRecord.node_states` 替代，但推荐尽早引入：

```python
class ExecutionNodeRecord(Base):
    __tablename__ = "execution_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    execution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("executions.id"), nullable=False, index=True
    )
    parent_node_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("execution_nodes.id"), nullable=True
    )

    node_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # LangGraph 节点名、subagent ID 或 tool call ID

    node_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # "agent", "tool", "subagent", "middleware", "human_input"

    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    input_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    thinking: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)

    token_usage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

#### ExecutionService

所有执行生命周期的单一入口：

```python
class ExecutionService:
    async def create_execution(
        self,
        *,
        execution_type: str,
        user_id: str,
        workspace_id: str | None = None,
        thread_id: str | None = None,
        feature_id: str | None = None,
        params: dict | None = None,
        parent_execution_id: str | None = None,
    ) -> ExecutionRecord

    async def dispatch_execution(
        self, execution_id: str, *, queue: str = "default", priority: int = 5
    ) -> None
    # Celery: execute.apply_async(args=[execution_id])

    async def start_execution(self, execution_id: str) -> None

    async def update_node_state(
        self, execution_id: str, node_id: str, *,
        status: str | None = None,
        output_preview: str | None = None,
        token_usage: dict | None = None,
        thinking: str | None = None,
        tool_calls: list[dict] | None = None,
    ) -> None

    async def complete_execution(
        self, execution_id: str, *,
        status: str, result: dict | None = None,
        error: str | None = None, result_summary: str | None = None,
    ) -> None

    async def cancel_execution(self, execution_id: str) -> bool

    async def list_executions(...) -> list[ExecutionRecord]

    async def get_execution_graph(self, execution_id: str) -> dict
    # 返回 graph_structure + 当前 node_states 的合并结果
```

#### 统一 Celery 入口

替换 `execute_task` 和 `execute_run`：

```python
@shared_task(bind=True, name="src.executions.execute")
def execute(self, execution_id: str) -> dict:
    # 1. Reset DB engine + Redis for forked worker
    # 2. Load ExecutionRecord
    # 3. execution_service.start_execution(execution_id)
    # 4. Build ExecutionStream bridge
    # 5. Dispatch to engine:
    #    "chat_turn" → ChatExecutionEngine.run()
    #    "feature" → FeatureExecutionEngine.run()
    # 6. execution_service.complete_execution(execution_id, ...)
    # 7. Publish execution.completed event
    # 8. Cleanup
```

#### 执行引擎

```python
class ExecutionEngine(ABC):
    @abstractmethod
    async def run(self, execution: ExecutionRecord, bridge: ExecutionStream) -> None:
        """执行工作单元，所有事件发布到 bridge。"""

class ChatExecutionEngine(ExecutionEngine):
    """包装现有的 ThreadTurnHandler + lead agent pipeline。"""
    async def run(self, execution, bridge):
        # 1. make_lead_agent()
        # 2. 将 ExecutionStream 作为 callback 注入（替代 RedisStreamBridge）
        # 3. agent.ainvoke()
        # 4. 通过 LangGraph callbacks 捕获节点级事件
        #    on_chain_start → execution.node.started
        #    on_llm_new_token → execution.node.delta
        #    on_tool_end → execution.node.completed (with tool_calls)
        #    on_chain_end → execution.node.completed

class FeatureExecutionEngine(ExecutionEngine):
    """包装现有的 FeatureLeaderRuntime + ParallelExecutor。"""
    async def run(self, execution, bridge):
        # 1. FeatureLeaderRuntime 构建 feature graph
        # 2. 早期发布 graph_structure 事件
        # 3. 执行计划阶段
        # 4. 每个 subagent spawn → child ExecutionNodeRecord
        #    → publish execution.node.started
        # 5. 每个 subagent completion → publish execution.node.completed
        #    (包含 input/output/thinking)
```

### 4.3 统一事件流（ExecutionStream）

#### 设计：扩展现有 `RedisStreamBridge`

> **关键发现**：wenjin 已拥有完整的 `RedisStreamBridge` 实现（`backend/src/runtime/stream_bridge/redis.py`），使用 Redis Streams（`XADD`/`XREAD`），bounded buffer 512，TTL 86400s，key prefix `runtime:runs:stream`。它目前**仅用于 chat runs**。Feature execution 完全没有使用流式抽象。

deer's `MemoryStreamBridge`（`backend/packages/harness/deerflow/runtime/stream_bridge/memory.py`）是纯内存的（bounded buffer 256）。wenjin 已经超越了 deer 的内存实现，拥有 Redis Streams 后端。统一方案**不需要新建流式抽象**，只需要：
1. **扩展 `RedisStreamBridge`** 使其同时覆盖 feature execution
2. **统一 key prefix**：chat runs 用 `runtime:runs:stream:{run_id}`，executions 用 `execution:stream:{execution_id}`
3. **统一事件 schema**：从 run-specific（`content`/`reasoning`/`block`/`done`）迁移到 execution-generic（`execution.node.*`/`execution.status`/`execution.completed`）

```
┌─────────────────┐     publish()      ┌─────────────────┐
│  ExecutionEngine │ ─────────────────► │  Redis Stream   │
│  (Celery worker) │                    │  key:           │
└─────────────────┘                    │  execution:{id}:stream
                                       └─────────────────┘
                                                ▲
                                                │ subscribe()
                                       ┌─────────────────┐
                                       │  Gateway SSE    │
                                       │  Consumer       │
                                       │  (per-request)  │
                                       └─────────────────┘
                                                │
                                                ▼ HTTP SSE
                                       ┌─────────────────┐
                                       │  Frontend       │
                                       │  useExecutionStream
                                       └─────────────────┘
```

**与 deer 的关键差异**：
- **后端存储**：Redis Streams（持久化，跨 worker 共享）替代内存列表
- **Replay**：`XREAD` 带 `LAST_ID` 替代线性数组扫描
- **TTL**：Redis key 24h 过期（可配置）
- **无 asyncio.Condition**：Redis blocking read（`XREAD BLOCK`）处理背压

#### 事件 Schema

统一信封：

```typescript
interface ExecutionStreamEvent {
  id: string;           // Redis stream entry ID (timestamp-sequence)
  execution_id: string;
  type: string;
  timestamp: string;    // ISO 8601
  payload: unknown;
}
```

事件类型：

| 类型 | 触发时机 | Payload |
|------|---------|---------|
| `execution.metadata` | 执行开始 | `{execution_id, thread_id, execution_type, feature_id}` |
| `execution.graph_structure` | 图拓扑已知 | `{nodes: ExecutionNode[], edges: ExecutionEdge[]}` |
| `execution.node.started` | 节点开始执行 | `{node_id, input, started_at}` |
| `execution.node.delta` | 流式 token/content | `{node_id, content_delta?, reasoning_delta?}` |
| `execution.node.completed` | 节点完成 | `{node_id, output, thinking?, tool_calls?, token_usage?, completed_at}` |
| `execution.node.failed` | 节点错误 | `{node_id, error}` |
| `execution.status` | 执行状态变更 | `{status, progress, message}` |
| `execution.completed` | 执行完成 | `{result?, token_usage?, duration_ms}` |
| `execution.error` | 执行级错误 | `{error, error_type}` |
| `execution.end` | 流终止 | `null` |

#### Workspace Events（精简版）

保留 Workspace Events SSE，但大幅精简为**非流式通知**：

| 保留 | 移除 |
|------|------|
| `workspace.refresh` | `task.updated` |
| `thread.updated` | `subagent.updated` |
| `thread.status` | `execution.created` |
| `thread.deleted` | `execution.updated` |
| `activity.created` (新增) | `execution.completed` |
| `compute.created/updated` | `execution.failed` |

**迁移路径**：Phase 1-3 期间，`task.updated` 和 `subagent.updated` 继续与 `execution.*` 事件**双发**。Phase 4 移除旧事件。

### 4.4 前端状态层

#### execution-store.ts（新增）

```typescript
interface ExecutionState {
  executions: Map<string, Execution>;
  currentExecutionId: string | null;
  upsertExecutionEvent(event: ExecutionStreamEvent): void;
  setCurrentExecution(id: string | null): void;
  removeExecution(id: string): void;
}

interface Execution {
  id: string;
  executionType: string;
  status: ExecutionStatus;
  threadId: string | null;
  workspaceId: string | null;
  featureId: string | null;
  graph: ExecutionGraph | null;
  nodes: Map<string, ExecutionNode>;
  progress: number;
  message: string | null;
  startedAt: string | null;
  completedAt: string | null;
}

interface ExecutionGraph {
  nodes: ExecutionGraphNode[];
  edges: ExecutionEdge[];
}

interface ExecutionGraphNode {
  id: string;
  type: "agent" | "tool" | "subagent" | "middleware" | "human_input";
  label: string;
  phaseIndex?: number;
  metadata?: Record<string, unknown>;
}

interface ExecutionEdge {
  from: string;
  to: string;
  label?: string;
}

interface ExecutionNode {
  id: string;
  status: NodeStatus;
  input?: unknown;
  output?: unknown;
  thinking?: string;
  toolCalls?: ToolCall[];
  tokenUsage?: TokenUsage;
  startedAt?: string;
  completedAt?: string;
}
```

**Reducer**：纯函数 `reduceExecutionEvent(executions, event) → executions`，可独立测试。

#### useExecutionStream.ts（新增）

```typescript
function useExecutionStream(executionId: string | null) {
  // 1. 连接 GET /executions/{id}/stream
  // 2. 收到消息：executionStore.upsertExecutionEvent(event)
  // 3. 断开：用 Last-Event-ID header 重连
  // 4. execution.end：关闭连接
}
```

#### workflow-store.ts（兼容层）

Phase 1-3 期间，`workflow-store.ts` **从 execution-store 派生** `Run[]`：

```typescript
function executionsToRuns(executions: Execution[]): Run[] {
  return executions.map(e => ({
    id: e.id,
    thread_id: e.threadId ?? "",
    title: deriveTitle(e),
    phases: executionToPhases(e),
    status: mapExecutionStatus(e.status),
    started_at: e.startedAt ?? e.createdAt,
  }));
}
```

**这意味着 `LiveWorkflowPanel` + `RunList` + 所有子组件在 Phase 1-3 零改动。**

---

## 5. 数据流全景

### 5.1 Chat Turn（统一后）

```
1. 用户发送 "请帮我总结这篇论文"
   Frontend: threadStore.sendMessage()
   → POST /threads/{id}/executions

2. Gateway
   ExecutionService.create_execution(
     execution_type="chat_turn",
     thread_id=...,
     params={messages: [{role:"user", content:"..."}]}
   )
   → DB: ExecutionRecord (status=pending)
   ExecutionEventPublisher.publish("execution.created")
   → Workspace Events（轻量通知）

   ExecutionService.dispatch_execution(execution_id)
   → Celery: execute.apply_async(args=[execution_id])

   返回 {execution_id, status: "pending"}

3. Frontend 启动 useExecutionStream(execution_id)
   → SSE GET /executions/{id}/stream

4. Celery Worker
   execute(execution_id)
   → ExecutionService.start_execution() → status=running
   → ChatExecutionEngine.run()

   4a. 构建 lead agent
       make_lead_agent() → 20+ middlewares + DynamicToolNode

   4b. 发布 metadata
       bridge.publish("execution.metadata", {execution_id, thread_id, type})

   4c. Agent 循环
       on_chain_start → bridge.publish("execution.node.started", {node_id: "agent", type: "agent"})

       on_chat_model_start → bridge.publish("execution.node.delta", {reasoning_delta: "..."})
       on_llm_end → bridge.publish("execution.node.delta", {content_delta: "..."})

       Tool call: launch_feature →
         bridge.publish("execution.node.started", {node_id: "tool:launch_feature", type: "tool", input: {...}})
         → 创建 child ExecutionRecord (execution_type="feature")
         → bridge.publish("execution.node.completed", {node_id: "tool:launch_feature", output: {child_execution_id}})

       on_chain_end → bridge.publish("execution.node.completed", {node_id: "agent", output: {...}})

   4d. 完成
       ExecutionService.complete_execution(status="completed", result=...)
       bridge.publish("execution.completed", {result, token_usage})
       bridge.publish("execution.end")

       _append_execution_thread_message() → 写入 result card 到 Thread.messages
       publish_thread_updated() → Workspace Events

5. Frontend 事件处理
   useExecutionStream 接收事件：
   - "execution.metadata" → executionStore 设置元数据
   - "execution.node.started" → Panel 显示新节点（黄色/运行中）
   - "execution.node.delta" → ChatPanel 追加文本到 assistant message
   - "execution.node.completed" → Panel 节点变绿
   - "execution.completed" → ChatPanel 完成消息
   - "execution.end" → 关闭 SSE 连接
```

### 5.2 Feature Execution（统一后）

```
1. 用户在 Panel 点击 "撰写论文"
   Frontend: workspaceStore.launchFeature("thesis_writing")
   → POST /workspaces/{id}/executions
   Body: {execution_type: "feature", feature_id: "thesis_writing", params: {...}}

2. Gateway
   ExecutionService.create_execution(...)
   → DB: ExecutionRecord

   // 同时：在 thread 中插入系统消息
   Thread.messages.append({role:"system", content:"用户请求执行 feature: 撰写论文"})
   publish_thread_updated()

   dispatch_execution()
   → Celery: execute.apply_async()

3. Frontend
   useWorkspaceEventStream 接收 thread.updated → threadStore 同步
   useExecutionStream(execution_id) 启动 → Panel 订阅

4. Celery Worker
   FeatureExecutionEngine.run()

   4a. 构建 feature graph
       FeatureLeaderRuntime.execute_feature()
       → build_dynamic_feature_workflow_plan()

   4b. 发布 graph 结构
       > **发射点**：`subagents/parallel.py` 的 `execute_plan()`，验证依赖后、执行循环开始前。
       > `PhasedPlan` 在执行前已包含完整的 phases/tasks/dependencies 拓扑。
       
       bridge.publish("execution.graph_structure", {
         nodes: [
           {id: "phase0:outline", type: "subagent", label: "生成大纲", phaseIndex: 0},
           {id: "phase1:lit_review", type: "subagent", label: "文献综述", phaseIndex: 1},
           {id: "phase1:methodology", type: "subagent", label: "研究方法", phaseIndex: 1},
           {id: "phase2:draft", type: "subagent", label: "撰写正文", phaseIndex: 2},
         ],
         edges: [
           {from: "phase0:outline", to: "phase1:lit_review"},
           {from: "phase0:outline", to: "phase1:methodology"},
           {from: "phase1:lit_review", to: "phase2:draft"},
           {from: "phase1:methodology", to: "phase2:draft"},
         ]
       })

   4c. 执行阶段
       ParallelExecutor.execute_plan()

       Phase 0:
         spawn subagent "outline"
         → bridge.publish("execution.node.started", {node_id: "phase0:outline", input: prompt})
         → ExecutionNodeRecord.create(...)

         subagent 完成
         → bridge.publish("execution.node.completed", {
             node_id: "phase0:outline",
             output: outline_text,
             thinking: reasoning_trace,
             tool_calls: [{name:"search", arguments:{...}}],
             token_usage: {input: 1200, output: 800}
           })
         → ExecutionNodeRecord.update(...)

       Phase 1（并行）:
         spawn "lit_review" + "methodology"
         → bridge.publish("execution.node.started", ...) × 2
         → 各自完成 → bridge.publish("execution.node.completed", ...) × 2

       Phase 2:
         spawn "draft"
         → bridge.publish("execution.node.started", ...)
         → 完成 → bridge.publish("execution.node.completed", ...)

   4d. 完成
       ExecutionService.complete_execution(status="completed", result={artifacts: [...]})
       bridge.publish("execution.completed", {result, artifact_ids: [...]})
       bridge.publish("execution.end")

       _append_execution_thread_message() → thread 中的 result card
       publish_thread_updated() + publish_workspace_event("activity.created")

5. Frontend
   Panel:
   - "execution.graph_structure" → 渲染图布局（节点卡片 + 边连线）
   - "execution.node.started" → 节点变黄（运行中）
   - "execution.node.completed" → 节点变绿，显示 token usage
   - 点击节点 → GET /executions/{id}/nodes/{node_id} → drawer 展示 input/output/thinking/tools

   Chat:
   - thread.updated → 显示 result card
```

---

## 6. API 设计

### 6.1 新端点

```
POST   /threads/{thread_id}/executions
       Body: {message, attachments?, model?, skill?, metadata?}
       Response: {execution_id, thread_id, status}

POST   /workspaces/{workspace_id}/executions
       Body: {execution_type, feature_id, params?, thread_id?}
       Response: {execution_id, status}

GET    /executions/{execution_id}
       Response: ExecutionRecord

GET    /executions/{execution_id}/stream
       SSE: ExecutionStreamEvent

GET    /executions/{execution_id}/graph
       Response: {nodes, edges}

GET    /executions/{execution_id}/nodes/{node_id}
       Response: ExecutionNode（完整 input/output/thinking/tools）

DELETE /executions/{execution_id}
       Response: {cancelled: bool}

GET    /workspaces/{workspace_id}/executions
       Query: ?type=&status=&limit=
       Response: {items: ExecutionRecord[], total}
```

### 6.2 兼容端点（透传包装）

Phase 1-3 期间旧端点保留：

```python
# gateway/routers/runs.py
@router.post("/threads/{thread_id}/runs/stream")
async def stream_run(...):
    # 1. 创建 ExecutionRecord (execution_type="chat_turn")
    # 2. 分发执行
    # 3. 从 /executions/{id}/stream 代理 SSE
    # 4. 将 execution.* 事件转回 content/reasoning/block/done 格式

# gateway/routers/features.py
@router.post("/workspaces/{id}/features/{feature_id}/execute")
async def execute_feature(...):
    # 1. 创建 ExecutionRecord (execution_type="feature")
    # 2. 分发执行
    # 3. 返回 {execution_id}
```

### 6.3 事件转换层

旧客户端消费 `/runs/stream`（content/reasoning/block/done 格式），网关提供**协议适配器**：

```
ExecutionStreamEvent "execution.node.delta" {content_delta}
    → SSE "content" {text: content_delta}

ExecutionStreamEvent "execution.node.delta" {reasoning_delta}
    → SSE "reasoning" {text: reasoning_delta}

ExecutionStreamEvent "execution.node.completed" {output, tool_calls}
    → SSE "block" {type: "tool_result", ...}

ExecutionStreamEvent "execution.completed"
    → SSE "done"

ExecutionStreamEvent "execution.end"
    → SSE "end"
```

---

## 7. deer-flow 迁移清单

### 7.1 直接复用（少量适配）

| deer-flow 组件 | wenjin 目的地 | 适配需求 |
|---------------|-------------|---------|
| `StreamBridge` interface | `runtime/stream_bridge/base.py`（已有） | 扩展 event schema 支持 `execution.*` 事件类型 |
| `RedisStreamBridge` | `runtime/stream_bridge/redis.py`（已有） | 添加可配置 `key_prefix`，从 `runtime:runs:stream` 扩展到 `execution:stream` |
| `RunJournal` | `execution/journal.py`（新建） | wenjin 无审计日志系统，需全新创建；添加节点级事件捕获；写入 `execution_nodes`
| `RunManager` | `execution/manager.py` | RunRecord → ExecutionRecord |
| `RunWorker.run_agent()` | `execution/engines/chat.py` | bridge 参数 → ExecutionStream |
| `TaskTool` | `tools/builtins/launch_feature.py` | 创建 child ExecutionRecord |
| `SubagentExecutor` | `execution/subagent_engine.py` | 包装为 ExecutionEngine 接口 |

### 7.2 需要适配

| deer-flow 组件 | 问题 | 方案 |
|---------------|------|------|
| `MemoryStreamBridge._streams` dict | 不跨 worker 共享 | Redis Streams (`XADD`/`XREAD`) |
| `MemoryStreamBridge._counters` | 非分布式 | Redis `INCR` 或 stream entry ID |
| `RunJournal` → SQLite `RunEventStore` | wenjin 用 PostgreSQL | 异步 SQLAlchemy writer → `execution_nodes` |
| `make_lead_agent()` middleware chain | deer 14 个，wenjin 20+ | 保留 wenjin 20+，添加 deer 缺失的 4 个 |
| `thread_runs.py` router | deer 用 LangGraph SDK 格式 | 保留 wenjin 格式，添加 `Content-Location` header |

### 7.3 中间件迁移优先级（修正后）

> **重要修正**：经核实，wenjin 已有 **18 个中间件**（比 deer-flow 还多），其中 deer-flow 的 12 个中间件 wenjin 已经实现。真正缺失的只有 **2 个**。

**wenjin 已有的中间件**（无需迁移）：

| deer-flow 中间件 | wenjin 等价实现 | 文件路径 |
|-----------------|----------------|---------|
| LoopDetectionMiddleware | ✅ `LoopDetectionMiddleware` | `agents/middlewares/loop_detection.py` |
| ClarificationMiddleware | ✅ `ClarificationMiddleware` | `agents/middlewares/clarification.py` |
| DanglingToolCallMiddleware | ✅ `DanglingToolCallMiddleware` | `agents/middlewares/dangling_tool_call.py` |
| ToolErrorHandlingMiddleware | ✅ `ToolErrorHandlingMiddleware` | `agents/middlewares/tool_error_handling.py` |
| SummarizationMiddleware | ✅ `SummarizationMiddleware` | `agents/middlewares/summarization.py` |
| TitleMiddleware | ✅ `TitleMiddleware` | `agents/middlewares/title.py` |
| MemoryMiddleware | ✅ `MemoryMiddleware` | `agents/middlewares/memory.py` |
| SandboxMiddleware | ✅ `SandboxMiddleware` | `agents/middlewares/sandbox.py` |
| ViewImageMiddleware | ✅ `ViewImageMiddleware` | `agents/middlewares/view_image.py` |
| TodoMiddleware | ✅ `TodoListMiddleware` | `agents/middlewares/todo_list.py` |
| ThreadDataMiddleware | ✅ `ThreadDataMiddleware` | `agents/middlewares/thread_data.py` |
| UploadsMiddleware | ✅ `UploadsMiddleware` | `agents/middlewares/uploads.py` |

**wenjin 独有的中间件**（deer-flow 没有）：
- `ExecutionMiddleware` — chat → compute 桥梁
- `WorkspaceContextMiddleware` — workspace 配置注入
- `LiteratureContextMiddleware` — 文献上下文
- `KnowledgeContextMiddleware` — 知识图谱上下文
- `DisciplineContextMiddleware` — 学科规范注入
- `CitationContextMiddleware` — 引用验证
- `SandboxAuditMiddleware` — sandbox 命令审计
- `LLMErrorHandlingMiddleware` — LLM 错误分类 + 熔断

**真正缺失的中间件**（需要迁移）：

1. **`SubagentLimitMiddleware`** (P1) — 限制并行 subagent spawn 数量。wenjin 的 `ParallelExecutor` 有 semaphore 但无 middleware 级别的截断。
2. **`GuardrailMiddleware`** (P1) — 工具调用安全护栏。wenjin 的 `SandboxAuditMiddleware` 只审计 bash 命令，缺少通用 guardrails。

**不迁移的中间件**（wenjin 已有等价）：见上表。

---

## 8. 数据库迁移

### 8.1 Migration 1: 创建 `executions` 表

```sql
CREATE TABLE executions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    workspace_id VARCHAR(36),
    thread_id VARCHAR(36),
    execution_type VARCHAR(20) NOT NULL,
    workspace_type VARCHAR(50),
    feature_id VARCHAR(100),
    entry_skill_id VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    params JSONB NOT NULL DEFAULT '{}',
    result JSONB,
    error TEXT,
    result_summary TEXT,
    graph_structure JSONB,
    node_states JSONB NOT NULL DEFAULT '{}',
    runtime_state JSONB,
    progress INTEGER NOT NULL DEFAULT 0,
    message TEXT,
    artifact_ids JSONB NOT NULL DEFAULT '[]',
    next_actions JSONB NOT NULL DEFAULT '[]',
    advisory_code VARCHAR(100),
    last_error TEXT,
    dispatch_mode VARCHAR(20),
    worker_task_id VARCHAR(36),
    parent_execution_id VARCHAR(36) REFERENCES executions(id),
    child_execution_ids JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_executions_user_status ON executions(user_id, status);
CREATE INDEX ix_executions_workspace_feature ON executions(workspace_id, feature_id, status);
CREATE INDEX ix_executions_thread ON executions(thread_id, created_at);
CREATE INDEX ix_executions_parent ON executions(parent_execution_id);
```

### 8.2 Migration 2: 创建 `execution_nodes` 表

```sql
CREATE TABLE execution_nodes (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id VARCHAR(36) NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    parent_node_id VARCHAR(36) REFERENCES execution_nodes(id),
    node_id VARCHAR(100) NOT NULL,
    node_type VARCHAR(20) NOT NULL,
    label VARCHAR(200),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    input_data JSONB,
    output_data JSONB,
    thinking TEXT,
    tool_calls JSONB,
    token_usage JSONB,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_execution_nodes_execution ON execution_nodes(execution_id);
CREATE INDEX ix_execution_nodes_node_id ON execution_nodes(execution_id, node_id);
```

### 8.3 Migration 3: 数据回填

```sql
-- execution_sessions → executions
INSERT INTO executions (...)
SELECT id, user_id, workspace_id, thread_id, 'feature', ...
FROM execution_sessions;

-- task_records（未被 execution_sessions 覆盖的）
INSERT INTO executions (...)
SELECT id, user_id, workspace_id, thread_id,
       CASE task_type WHEN 'workspace_feature' THEN 'feature' ELSE task_type END, ...
FROM task_records
WHERE execution_session_id IS NULL
  AND id NOT IN (SELECT id FROM executions);

-- workspace_run → executions (chat_turn)
INSERT INTO executions (...)
SELECT id, workspace_id, thread_id, 'chat_turn', ...
FROM workspace_run
WHERE deleted_at IS NULL
  AND id NOT IN (SELECT id FROM executions);
```

### 8.4 Migration 4: `subagent_task_records` 添加 `execution_id`

```sql
ALTER TABLE subagent_task_records ADD COLUMN execution_id VARCHAR(36) REFERENCES executions(id);
CREATE INDEX ix_subagent_task_records_execution ON subagent_task_records(execution_id);

UPDATE subagent_task_records
SET execution_id = execution_session_id
WHERE execution_session_id IN (SELECT id FROM executions);
```

---

## 9. 实施路线图

### Phase 1: 基础设施（Week 1-2）
**目标**：新基础设施与旧系统并存，用户无感知。

**Week 1: 数据层 + 服务层**

| Day | 任务 | 文件路径 | 验收标准 |
|-----|------|---------|---------|
| 1 | Alembic migration：`executions` 表 | `backend/alembic/versions/...create_executions_table.py` | `alembic upgrade head` 成功，表结构符合 §8.1 |
| 1 | Alembic migration：`execution_nodes` 表 | `backend/alembic/versions/...create_execution_nodes_table.py` | `alembic upgrade head` 成功，FK 约束正确 |
| 2 | `ExecutionRecord` model | `backend/src/database/models/execution.py` | SQLAlchemy 模型定义完整，包含所有字段和索引 |
| 2 | `ExecutionNodeRecord` model | `backend/src/database/models/execution_node.py` | 模型定义完整，FK 级联删除 |
| 3 | `ExecutionService` CRUD | `backend/src/services/execution_service.py` | `create_execution()`、`list_executions()`、`get_execution_graph()` 单元测试通过 |
| 3 | `ExecutionService` 生命周期 | `backend/src/services/execution_service.py` | `start_execution()`、`complete_execution()`、`cancel_execution()` 测试通过 |
| 4 | `ExecutionEventPublisher` | `backend/src/services/execution_event_publisher.py` | 能同时发布到 Workspace Events + ExecutionStream |
| 4 | Feature flags | `backend/src/config/feature_flags.py` | `enable_execution_record`、`enable_execution_stream` 等开关可配置 |
| 5 | 数据回填脚本 | `backend/scripts/backfill_executions.py` | 幂等回填，验证查询无异常 |

**Week 2: 流式层 + Celery 层**

| Day | 任务 | 文件路径 | 验收标准 |
|-----|------|---------|---------|
| 6 | 扩展 `RedisStreamBridge` | `backend/src/runtime/stream_bridge/redis.py` | 支持可配置 `key_prefix`（`runtime:runs:stream` → `execution:stream`） |
| 6 | `ExecutionStream` wrapper | `backend/src/execution/stream.py` | 封装 `RedisStreamBridge`，提供 `publish_execution_event()` |
| 7 | 统一 Celery task `execute` | `backend/src/task/tasks/execute.py` | `execute.apply_async(args=[execution_id])` 能正确分发到队列 |
| 7 | `ChatExecutionEngine` shell | `backend/src/execution/engines/chat.py` | 能包装现有 `ThreadTurnHandler`，通过 `ExecutionStream` 发布事件 |
| 8 | `FeatureExecutionEngine` shell | `backend/src/execution/engines/feature.py` | 能包装现有 `FeatureLeaderRuntime`，通过 `ExecutionStream` 发布事件 |
| 8 | `ExecutionNodeRecord` writer | `backend/src/execution/node_writer.py` | LangGraph callback 触发时写入 `ExecutionNodeRecord` |
| 9 | Worker fork 安全 | `backend/src/task/worker.py` | 重置 `ExecutionStream` Redis client（复用现有 `reset_stream_client()`） |
| 9 | Gateway SSE consumer | `backend/src/gateway/services/execution_sse.py` | 新端点 `/executions/{id}/stream` 返回 SSE |
| 10 | 集成测试 | — | Chat + Feature 都能创建 `ExecutionRecord`，事件通过 `ExecutionStream` 发布和消费 |

**前端（Week 1-2 并行）**

| 任务 | 文件路径 | 验收标准 |
|------|---------|---------|
| TypeScript 类型定义 | `frontend/lib/api/types.ts` | `Execution`、`ExecutionNode`、`ExecutionGraph`、`ExecutionStreamEvent` 类型完整 |
| `execution-store.ts` + reducer | `frontend/stores/execution-store.ts` | `upsertExecutionEvent()` 能正确处理所有事件类型 |
| `useExecutionStream.ts` | `frontend/hooks/useExecutionStream.ts` | SSE 连接、断线重连、`Last-Event-ID` 重放正常工作 |
| `executionToRun` 适配器 | `frontend/stores/workflow-store-compat.ts` | `executionsToRuns()` 单元测试通过，输出兼容现有 `Run[]` |
| API client | `frontend/lib/api/executions.ts` | `createExecution()`、`subscribeExecutionEvents()`、`getExecutionGraph()` 封装完成 |

### Phase 2: Chat 路径迁移（Week 3）
**目标**：Chat turn 创建 `ExecutionRecord`，走 `ExecutionStream`。

**后端**：
1. `launch_thread_run()` 创建 `ExecutionRecord`（execution_type="chat_turn"）
2. `run_thread_turn()` 使用 `ChatExecutionEngine` + `ExecutionStream`
3. LangGraph callbacks 捕获节点事件
4. 旧 `/runs/stream` 保持透传适配器
5. `thread-store.sendMessage()` 调用 `/threads/{id}/executions`

**前端**：
1. `thread-store.sendMessage()` 调新端点
2. Chat 消息流消费 `useExecutionStream`
3. `execution.node.delta` → assistant message content
4. 旧客户端通过适配器继续工作

**测试**：
- E2E: Chat 消息 → ExecutionRecord 创建 → SSE 事件 → 消息渲染
- E2E: 断线重连，`Last-Event-ID` 重放缓冲事件

### Phase 3: Feature 路径迁移（Week 4-5）
**目标**：Feature execution 创建 `ExecutionRecord`，发布 graph 事件。

**后端**：
1. `FeatureLaunchCommand` 创建 `ExecutionRecord`（execution_type="feature"）
2. `FeatureLeaderRuntime` 使用 `FeatureExecutionEngine`
3. 工作流计划构建时发布 `execution.graph_structure`
4. 每个 subagent spawn → `execution.node.started`
5. 每个 subagent completion → `execution.node.completed`（含 thinking/tools）
6. 旧 `/features/{id}/execute` 保持透传

**前端**：
1. `LiveWorkflowPanel` 订阅 `useExecutionStream`
2. Graph 渲染：`execution.graph_structure` 的 nodes + edges
3. 节点状态更新：`execution.node.started/completed`
4. Node detail drawer：`GET /executions/{id}/nodes/{node_id}`
5. 兼容适配器保证 `RunList` 继续工作

**测试**：
- E2E: Feature 启动 → graph structure 事件 → 节点渲染
- E2E: Subagent 完成 → 节点变绿
- E2E: 点击节点 → drawer 展示 input/output/thinking

### Phase 4: 收敛与清理（Week 6）
**目标**：移除旧事件类型，前端完全迁移到 Execution 模型。

**后端**：
1. 停止发布 `task.updated` / `subagent.updated`
2. 停止在 Workspace Events 中发布 `execution.created/updated/completed/failed`
3. `TaskService` 委托给 `ExecutionService`
4. `ExecutionSessionService` 委托给 `ExecutionService`
5. 移除透传 API 适配器（旧端点直接调用新端点）

**前端**：
1. `workflow-store.ts` 内部改用 `Execution[]`
2. `LiveWorkflowPanel` 原生渲染 `ExecutionGraph`（无适配器）
3. `useWorkspaceEventStream` 停止处理 `task.updated` / `subagent.updated`
4. 移除兼容适配器代码

**测试**：
- 全量回归：chat + feature + panel
- 性能：100 并发执行，流延迟 < 100ms

### Phase 5: 遗留表废弃（Week 7+）
**目标**：验证期后删除遗留表。

1. 停止写入 `task_records`、`execution_sessions`、`workspace_run`
2. 监控是否有代码仍在读取遗留表
3. 30 天验证期后：删除遗留表（或归档）

---

## 10. 风险与缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| Redis Streams 高并发性能瓶颈 | 中 | 高 | Redis Cluster；按 `execution_id` hash 分片；监控 `XLEN` |
| Redis 故障导致 ExecutionStream 事件丢失 | 低 | 高 | 事件是 best-effort 流；DB `ExecutionRecord` + `ExecutionNodeRecord` 是持久 SSOT；前端可重新查询 |
| 迁移期间前端状态不一致 | 中 | 中 | Phase 1-3 双发；旧 `task.updated` 与新 `execution.*` 同时发射 |
| Celery task 名变更导致在途任务中断 | 低 | 高 | 新 `execute` task 注册时保留 `execute_task` 和 `execute_run` 别名 |
| LangGraph callback 开销拖慢执行 | 中 | 中 | 基准测试；callbacks 异步非阻塞；无订阅者时跳过 callbacks |
| Feature graph 结构无法提前获知 | 中 | 高 | 动态计划：计划构建后 emit graph_structure；前端显示 "planning..." spinner |
| Node detail 数据过大不适合流式传输 | 中 | 中 | Stream 只传 `node_id` + status；完整 input/output/thinking 按需 REST 查询 |
| 数据库 migration 锁表 | 低 | 高 | `CREATE TABLE`（非 `ALTER`）；批量回填；低流量窗口执行 |
| 中间件链排序冲突 | 中 | 中 | deer-flow 中间件是增量添加；生产启用前隔离测试 |
| StreamBridge bounded buffer 丢事件 | 中 | 低 | Redis Streams 无 bounded buffer（仅 TTL）；重连用 `Last-Event-ID` |

---

## 11. 开放问题

| # | 问题 | 推荐方案 | 状态 |
|---|------|---------|------|
| 1 | Graph 布局：前端 dagre.js 自算，还是后端带 `{x,y}`？ | **前端自算**，后端只传拓扑 | 待确认 |
| 2 | Thinking 可见性：全部用户可见，还是仅 owner/dev mode？ | **默认全部可见**，workspace 级可配置 | 待确认 |
| 3 | Subagent 嵌套：同 execution 嵌套节点，还是独立 child ExecutionRecord？ | **独立 child ExecutionRecord**（支持独立取消和监控） | 待确认 |
| 4 | Rollback 支持：引入 deer-flow 的 checkpoint rollback？ | **Phase 4 再加**，先只做 `interrupt` | 待确认 |

---

## 附录：核实修正记录

本章节记录文档初稿发布后，通过代码审计发现的不准确之处及修正。

### 修正 1：deer-flow 核心包路径

| 初稿 | 修正后 |
|------|--------|
| `deer-flow/backend/app/` 被误认为 runtime | **runtime 在 `deer-flow/backend/packages/harness/deerflow/`**，`backend/app/` 只是 FastAPI Gateway |
| Gateway 和 runtime 双向耦合 | **单向耦合**：gateway 导入 runtime，runtime 零依赖 gateway |

**影响**：迁移清单中的 deer-flow 组件路径全部需要指向 `packages/harness/deerflow/`。

### 修正 2：中间件迁移清单严重偏误

| 初稿判断 | 核实后 |
|---------|--------|
| 6 个 deer-flow 中间件"缺失待迁移" | **仅 2 个真正缺失**（`SubagentLimitMiddleware`、`GuardrailMiddleware`） |
| `LoopDetectionMiddleware` 待迁移 | **wenjin 已存在**（`agents/middlewares/loop_detection.py`） |
| `ClarificationMiddleware` 待迁移 | **wenjin 已存在**（`agents/middlewares/clarification.py`） |
| `DanglingToolCallMiddleware` 待迁移 | **wenjin 已存在**（`agents/middlewares/dangling_tool_call.py`） |
| `ToolErrorHandlingMiddleware` 待迁移 | **wenjin 已存在**（`agents/middlewares/tool_error_handling.py`） |
| `SummarizationMiddleware` 待迁移 | **wenjin 已存在**（`agents/middlewares/summarization.py`） |
| `TitleMiddleware` 待迁移 | **wenjin 已存在**（`agents/middlewares/title.py`） |

**wenjin 实际中间件链**：20 个中间件（比 deer-flow 还多 6 个），包括 deer-flow 没有的学术专属中间件（`WorkspaceContext`、`LiteratureContext`、`KnowledgeContext`、`DisciplineContext`、`CitationContext`、`ExecutionMiddleware`）。

**影响**：中间件迁移工作量从"6 个"骤减为 **"2 个"**。

### 修正 3：`ExecutionStream` 设计假设

| 初稿假设 | 核实后 |
|---------|--------|
| wenjin 没有流式抽象，需要全新创建 `ExecutionStream` | wenjin **已有 `StreamBridge`**（`runtime/stream_bridge/`）+ **`RedisStreamBridge`**（Redis Streams 后端，bounded buffer 512，TTL 86400s），但**仅用于 chat runs** |
| Feature execution 有某种流式机制待替换 | Feature execution **完全没有流式抽象**，subagent 进度通过 Workspace Events 发布 |

**影响**：`ExecutionStream` 不是"新建"，而是**直接复用现有 `RedisStreamBridge`**（改 key prefix + 扩展 event schema），使其同时覆盖 feature execution。Celery worker 已有 fork 安全重置机制（`reset_stream_client()`）。

### 修正 4：Feature 执行路径细节

| 初稿假设 | 核实后 |
|---------|--------|
| `FeatureLeaderRuntime` 直接调用 `ParallelExecutor` | `FeatureLeaderRuntime` → `AgentHarness.run_session()` → `ParallelExecutor` |
| `GlobalSubagentManager.spawn()` 同步返回结果 | `spawn()` 是 **fire-and-forget**（创建 asyncio task 后立即返回），调用方需 `wait_for_completion()` 轮询 |
| Subagent 结果存储在自定义流中 | 结果存储在 **DB `subagent_task_records`** + **内存 `ThreadContext`** + **Workspace Events** |

**影响**：`ExecutionNodeRecord` 的设计需要兼容现有的 `SubagentTaskStore` + `ThreadContext` 双存储模型。

---

*文档结束*


---

## 12. 深度补充：监控与可观测性

### 12.1 关键指标

| 指标 | 类型 | 采集方式 | 告警阈值 |
|------|------|---------|---------|
| `execution_stream_latency_p99` | Histogram | Gateway SSE consumer 从 `subscribe()` 到首帧的时间 | > 500ms |
| `execution_stream_event_rate` | Counter | 每秒 `ExecutionStream.publish()` 调用次数 | 无（趋势监控） |
| `execution_stream_reconnect_rate` | Counter | 前端 SSE 重连次数/分钟 | > 5/min |
| `execution_node_duration` | Histogram | 每个 node 的 `completed_at - started_at` | 按 node_type 分桶 |
| `execution_completion_rate` | Counter | 成功/失败/取消的 execution 计数 | 失败率 > 5% 告警 |
| `execution_db_query_p99` | Histogram | `ExecutionService.list_executions()` 查询时间 | > 200ms |
| `redis_stream_memory` | Gauge | `XLEN` 所有 execution stream keys 的总长度 | > 10000 |
| `celery_worker_fork_reset_time` | Histogram | worker fork 后 DB/Redis 重置耗时 | > 500ms |

### 12.2 日志规范

所有 execution 相关日志必须包含 `execution_id` 和 `execution_type` 字段：

```python
logger.info(
    "Execution started",
    extra={"execution_id": execution.id, "execution_type": execution.execution_type}
)
```

### 12.3 分布式追踪

在 `ExecutionService.create_execution()` 中注入 trace context，所有子调用（Celery task、subagent spawn、DB query）携带相同的 trace ID。

---

## 13. 深度补充：降级策略

### 13.1 功能开关（Feature Flags）

```python
# config/feature_flags.py
class ExecutionUnificationFlags(BaseSettings):
    # Phase 1: 新基础设施创建
    enable_execution_record: bool = False
    enable_execution_stream: bool = False

    # Phase 2: chat 路径迁移
    enable_chat_execution_path: bool = False

    # Phase 3: feature 路径迁移
    enable_feature_execution_path: bool = False

    # Phase 4: 旧事件弃用
    disable_task_events: bool = False
    disable_subagent_events: bool = False
```

### 13.2 降级路径

| 场景 | 降级行为 |
|------|---------|
| `ExecutionStream.publish()` Redis 不可用 | 降级为同步 DB 写入（`ExecutionRecord.node_states`），不阻塞执行 |
| `ExecutionStream.subscribe()` Redis 不可用 | Gateway 返回 `503 Retry-After`，前端回退到轮询 `/executions/{id}` |
| `ExecutionService.create_execution()` DB 失败 | 降级为旧路径（直接创建 `TaskRecord`/`RunRecord`） |
| 新 Celery task `execute` 未注册 | 回退到旧 task 名（`execute_task`/`execute_run`） |
| 前端无法消费 `execution.*` 事件 | 继续消费 `task.updated`/`subagent.updated`（双发期间） |

---

## 14. 深度补充：数据回填幂等性策略

### 14.1 核心原则

所有回填 SQL 必须是**幂等的**——多次执行不产生副作用。

### 14.2 具体策略

```sql
-- 策略：ON CONFLICT DO NOTHING
INSERT INTO executions (id, user_id, workspace_id, ...)
SELECT id, user_id, workspace_id, ...
FROM execution_sessions
ON CONFLICT (id) DO NOTHING;

-- 策略：WHERE NOT EXISTS
INSERT INTO executions (id, ...)
SELECT id, ...
FROM task_records
WHERE execution_session_id IS NULL
  AND id NOT IN (SELECT id FROM executions);

-- 策略：INSERT + UPDATE（upsert）
INSERT INTO executions (id, status, ...)
SELECT id, status, ...
FROM workspace_run
ON CONFLICT (id) DO UPDATE SET
    status = EXCLUDED.status,
    result = EXCLUDED.result,
    updated_at = NOW();
```

### 14.3 回填顺序

1. `execution_sessions` → `executions`（feature 类型）
2. `task_records` → `executions`（补充未被 execution_sessions 覆盖的）
3. `workspace_run` → `executions`（chat_turn 类型，upsert 模式）
4. `subagent_task_records` → 添加 `execution_id` 列并回填

### 14.4 验证查询

```sql
-- 验证无重复
SELECT id, COUNT(*) FROM executions GROUP BY id HAVING COUNT(*) > 1;

-- 验证所有 execution_sessions 已回填
SELECT COUNT(*) FROM execution_sessions WHERE id NOT IN (SELECT id FROM executions);

-- 验证所有 workspace_run 已回填
SELECT COUNT(*) FROM workspace_run WHERE deleted_at IS NULL AND id NOT IN (SELECT id FROM executions);
```

---

## 15. 深度补充：Feature graph_structure 发射点

### 15.1 何时产生 Graph Topology

经代码审计确认，`PhasedPlan` 在 **`build_dynamic_feature_workflow_plan()`** 构建时即包含完整的拓扑信息：

- 所有 phase 名称
- 每个 phase 的 `depends_on` 列表（edges）
- 每个 phase 内的 task 列表（nodes）

### 15.2 理想发射点

**首选位置**：`subagents/parallel.py` 的 `execute_plan()` 方法，验证依赖后、执行循环开始前（约第 181 行）：

```python
# subagents/parallel.py — execute_plan()
async def execute_plan(self, plan: PhasedPlan, context=None, phase_callback=None) -> list[PhaseResult]:
    # ... 合并 context，创建 phase_events ...
    # ... 验证 depends_on 引用存在 ...

    # ←←← 在这里 emit execution.graph_structure
    if execution_stream:
        await execution_stream.publish(
            execution_id,
            "execution.graph_structure",
            {
                "nodes": [
                    {
                        "id": f"phase{idx}:{task.subagent_type}",
                        "type": "subagent",
                        "label": task.subagent_type,
                        "phase_index": idx,
                    }
                    for idx, phase in enumerate(plan.phases)
                    for task in phase.tasks
                ],
                "edges": [
                    {"from": f"phase{plan.phases.index(dep_phase)}:{dep_task.subagent_type}",
                     "to": f"phase{idx}:{task.subagent_type}"}
                    for idx, phase in enumerate(plan.phases)
                    for task in phase.tasks
                    for dep in task.depends_on
                    for dep_phase in plan.phases
                    for dep_task in dep_phase.tasks
                    if dep_task.task_id == dep
                ],
            }
        )

    # ... 执行循环 ...
```

**备选位置**：`agents/harness/native.py` 的 `NativeWenjinAgentHarness.run_session()`，在调用 `executor.execute_plan()` 之前。

### 15.3 动态发现 vs 静态声明

- **Feature execution**：graph 结构在执行前已知（`PhasedPlan` 包含所有 phases/tasks/dependencies）
- **Chat execution**：graph 结构是**动态发现**的——agent 循环中 tool call 产生新节点，无法提前预知全部拓扑

对于 chat execution，采用**增量 graph_structure** 策略：
- 初始：`execution.graph_structure` 只包含根节点 `{id: "agent", type: "agent", label: "Lead Agent"}`
- 每次 tool call：追加新节点 + 边，重新发布 `execution.graph_structure`（前端增量 merge）

---

## 16. 深度补充：前端 Store 集成细节

### 16.1 Zustand 模式

wenjin 前端使用**纯 Zustand**（无 immer），通过 spread 更新状态：

```typescript
// 正确模式（与现有 stores 一致）
export const useExecutionStore = create<ExecutionState>((set) => ({
  executions: new Map(),
  currentExecutionId: null,

  upsertExecutionEvent(event) {
    set((state) => {
      const nextExecutions = new Map(state.executions);
      // ... reducer logic ...
      return { executions: nextExecutions };
    });
  },
}));
```

### 16.2 Store 组合规则

- **不跨 store import**：`execution-store` 不导入 `workflow-store` 或 `thread-store`
- **通过 Hook 组合**：`useExecutionStream` 调用 `useExecutionStore.getState().upsertExecutionEvent()`
- **通过 Event 联动**：Workspace Events 的 `thread.updated` 由 `useWorkspaceEventStream` 分发到 `thread-store`

### 16.3 兼容性适配器生命周期

```typescript
// workflow-store-compat.ts
// Phase 1-3: 适配器存在
export function executionsToRuns(executions: Execution[]): Run[] { ... }

// Phase 4: 适配器标记为 @deprecated，LiveWorkflowPanel 直接消费 Execution[]
// Phase 5: 删除适配器，workflow-store 直接引用 execution-store
```

### 16.4 测试模式

```typescript
// Reset store state between tests
beforeEach(() => {
  useExecutionStore.setState({ executions: new Map(), currentExecutionId: null });
});

// Mock API layer at module boundary
vi.mock("@/lib/api", () => ({
  subscribeExecutionEvents: vi.fn(),
  getExecutionGraph: vi.fn(),
}));
```

---

*文档结束（深度补充版）*
