# Wenjin Workspace 重构 — 设计文档

> **状态**: 已冻结，待 review
> **作者**: Claude (in collab with Ze)
> **日期**: 2026-05-09
> **关联文档**:
> - [2026-05-08-execution-unification-convergence.md](../../architecture/2026-05-08-execution-unification-convergence.md) — 上一轮 execution 层重构的基线，本设计在其之上扩展
> - [2026-05-08-workflow-panel-redesign.md](./2026-05-08-workflow-panel-redesign.md)
> - 历史架构总览已收敛到 [architecture/README.md](../../architecture/README.md)

---

## 目录

- [1. 执行摘要](#1-执行摘要)
- [2. Goals & Non-Goals](#2-goals--non-goals)
- [3. 架构总览](#3-架构总览)
- [4. 详细设计](#4-详细设计)
- [5. API 设计](#5-api-设计)
- [6. 数据模型](#6-数据模型)
- [7. 实施路线图](#7-实施路线图)
- [8. 风险与缓解](#8-风险与缓解)
- [9. 开放问题](#9-开放问题)
- [附录 A: V1 Capability 启动目录](#附录-a-v1-capability-启动目录)
- [附录 B: Subagent 类型注册表](#附录-b-subagent-类型注册表)
- [附录 C: 数据迁移要点](#附录-c-数据迁移要点)

---

## 1. 执行摘要

本次重构是**对 wenjin workspace 体验的产品级重塑**。它不是修补 2026-05-08 那份执行层收敛文档遗留的 bug，而是在那份基础设施投资之上，**重新定义 chat / panel / harness 三套子系统的关系与产品形态**。

### 1.1 核心问题

当前 wenjin 处于"基础设施已建好但前端没接上"的中间态——`ExecutionRecord` / `ExecutionStream` / publish_execution_event 全部就位，但 `LiveWorkflowPanel` 仍消费旧 workflow-store，chat 气泡渲染遗漏 reasoning。更深层的问题是：

1. **agent 职责未分层**——单个 lead_agent 既负责对话又负责调度，导致响应性与执行隔离冲突
2. **capability 写死在 Python 代码里**——无法热扩展，admin 无法干预
3. **workspace 概念缺失**——只有 thread + execution，没有"长期工作空间"的状态承载
4. **panel UX 是 run/phase/subagent 树**——和图布局、节点 drawer 这种现代 agent 系统标配差距大

### 1.2 解决方案

本设计围绕 **10 条核心决策**展开：

1. **双 agent 拓扑**：Chat Agent（左, 1:1）↔ Lead Agent（右 panel）。User 只对 chat 说话，panel 是 lead agent 工作展板。
2. **Capability 数据驱动**：YAML seed + DB-backed，admin 后台可热扩展（V2）。Phased plan graph_template。
3. **1 workspace = 1 session**：auto-compact，Memory 仅存重要的少数。
4. **8 房间数据层**：Library / Documents / Decisions / Memory / Run History / Sandbox / Tasks / Settings。
5. **UI 节制**：默认 chat + panel；房间走顶栏角标 / 齿轮入口；sandbox 默认隐藏。
6. **Run output curated**：result_card 默认全勾 + 一键 ✓ 全部接受。
7. **Lead busy 期**：chat 仍响应（含进度查询），禁止新 dispatch。
8. **Cancel 双入口**：panel 一键终止 + chat 命令。
9. **平台层 V1 全做**：Auth / Quota / Audit / Observability / Model Gateway / Capability Registry / Event Bus。
10. **Failure 兜底**：ToolErrorHandling 中间件 + result_card 显示部分完成 + 重试入口。

### 1.3 实施策略

**Approach C · 分层渐进 + 单 cutover**（12 周，4 phase）：

| Phase | 周次 | 目标 |
|-------|-----|------|
| 1. Foundation | W1-3 | 平台层 7 项 + 8 房间 schema + capability registry 骨架 |
| 2. Capability + Agents | W4-6 | YAML loader + chat agent + lead agent + 5 个种子 capability |
| 3. Frontend Rewrite | W7-10 | 新 chat + panel + drawer + result_card curated 流 |
| 4. Cutover | W11-12 | 数据 migration + 切换 + 旧代码清理 |

后端可灰度，前端 single-cutover。

### 1.4 与 2026-05-08 文档的关系

**保留**（继续投资）：
- `ExecutionRecord` + `ExecutionNodeRecord` 数据模型
- `RedisStreamBridge` + `publish_execution_event` 流式抽象
- `ExecutionService` 生命周期
- `/executions/*` 端点骨架

**重新设计**（不再适用）：
- `ChatExecutionEngine` vs `FeatureExecutionEngine` 双引擎 → **统一为 Lead Agent 引擎**（feature 路径消失，所有触发走 chat）
- `task.updated` / `subagent.updated` workspace 事件 → 全部退役（V1 cutover 后）
- `LiveWorkflowPanel` Run/Phase/Subagent 树 → 重写为 capability graph 渲染

**新增**：
- 两层 agent（chat + lead）
- Capability 数据层（registry + YAML + DB）
- Workspace 8 房间 service 层
- 平台基础设施层 7 组件

---

## 2. Goals & Non-Goals

### 2.1 Goals

**产品级**：
- G1. 用户「在 chat 里聊天就行」，但能直观看到 panel 里 lead agent 在干活
- G2. 5 种 workspace 类型（sci / 毕业论文 / 申报书 / 软著 / 专利）行为一致但内容差异化
- G3. capability 可由 admin 热扩展，不再每次发版

**架构级**：
- G4. 单一执行 SSOT：`ExecutionRecord` + `ExecutionStream`（继承 2026-05-08）
- G5. 单一 chat session 与 lead agent 解耦：chat 永远响应，lead 状态隔离
- G6. workspace 是头等实体，是所有数据的聚合根
- G7. 平台基础设施层与业务隔离，可独立演进

**质量级**：
- G8. 后端测试覆盖 ≥ 80%，前端关键路径 E2E 覆盖
- G9. SSE 流延迟 P99 < 200ms
- G10. Capability 热加载延迟 < 5s（admin 编辑后到生效）

### 2.2 Non-Goals

- N1. **多人协作**：V1 单用户。多人评审/共享是 V2+
- N2. **多 session 一 workspace**：V1 一 workspace 一 session
- N3. **Workspace 实例级 capability override**：靠 lead agent 运行时适配，不做结构化覆盖配置
- N4. **可视化 graph 编辑器**：V1 admin UI 是表单 + YAML 编辑；可视化拖拽是 V2+
- N5. **跨 workspace 的全局记忆**：每个 workspace memory 隔离
- N6. **运行时换 capability**：run 启动后用的 capability version freeze 至 run 完成
- N7. **取消 mid-flight steering**：用户中途无法"补一句话"修改正在跑的 run；只能 cancel 然后重启

---

## 3. 架构总览

### 3.1 三层结构

```
┌────────────────────────────────────────────────────────────────────┐
│ UI 层（用户感知）                                                  │
│  ┌──────────┬──────────────────────┬──────────────────────────┐   │
│  │ Chat     │ Live Workflow Panel  │ Rooms 入口（顶栏 + 齿轮）│   │
│  │ (左)     │ (右, 仅当前 run)     │ Documents/Library/...    │   │
│  └──────────┴──────────────────────┴──────────────────────────┘   │
├────────────────────────────────────────────────────────────────────┤
│ 数据层（workspace 资产, 8 房间）                                   │
│  Library · Documents · Decisions · Memory · Run History            │
│  Sandbox · Tasks · Settings                                        │
├────────────────────────────────────────────────────────────────────┤
│ 平台层（跨 workspace 共享, 7 组件）                                │
│  Auth · Quota · Audit Log · Observability · Model Gateway          │
│  Capability Registry · Event Bus                                   │
└────────────────────────────────────────────────────────────────────┘
```

每层有清晰的依赖方向：UI → 数据 → 平台。下层不知道上层存在。

### 3.2 双 Agent 拓扑

```
┌────────────────────┐                  ┌─────────────────────┐
│      User          │                  │                     │
│                    │                  │      Lead Agent     │
└────────────────────┘                  │   (per-execution)   │
        │                                │                     │
        │ 说话                           │  spawn 1..N         │
        ▼                                │  subagent           │
┌────────────────────┐  TaskBrief        │  (langgraph)        │
│   Chat Agent       │ ───────────────►  │                     │
│   (per-session)    │                   │                     │
│                    │  TaskReport       │                     │
│   - 对话           │ ◄───────────────  │                     │
│   - 意图识别       │                   │                     │
│   - capability     │                   │                     │
│     选择           │                   └─────────────────────┘
│   - 决策提取       │                            │
│   - 进度查询       │                            ▼
│   - cancel 转发    │                   ┌─────────────────────┐
└────────────────────┘                   │  Subagents          │
        ▲                                │  (search / writer / │
        │                                │   clusterer / ...)  │
        │ 读                              └─────────────────────┘
        ▼
┌──────────────────────────────────────────────────────────────────┐
│  Workspace Data (8 rooms) + Platform infrastructure              │
└──────────────────────────────────────────────────────────────────┘
```

**关键不变量**：
- I1. **1:1 chat:lead**：一 workspace 同一时刻最多一个活跃 lead agent execution
- I2. **顺序执行**：lead agent 忙时，chat agent 不能 dispatch 新 task（必须排队但 V1 不做队列，直接拒绝并提示）
- I3. **chat 永远响应**：即使 lead 在跑，chat agent 仍能聊天 + 回答进度查询
- I4. **lead → chat 单向报告**：lead agent 完成或失败时通过 `TaskReport` 把结果还给 chat agent；chat agent 决定如何呈现给用户
- I5. **panel 是 lead 的展板**：用户不向 panel 输入，只看；panel 显示的所有信息源自 `ExecutionRecord` + `ExecutionStream`
- I6. **capability 是 chat ↔ lead 协议的承载**：每个 dispatch 必须指明 `capability_id`

### 3.3 数据流速览

```
User msg
   ↓
Chat Agent
   ├─ 读 Memory / Decisions / Run History（注入 prompt 上下文）
   ├─ 识别意图 → 选 capability_id
   ├─ 检查 required_decisions → 缺啥追问
   ├─ 提取新决策 → 写 Decisions
   ├─ Lead 忙? → 是: 友好拒绝, 否: dispatch
   ▼
POST /workspaces/{ws}/executions
   {capability_id, brief, raw_message, decisions}
   ↓
ExecutionService.create_execution()
   → DB: ExecutionRecord (status=pending)
   → dispatch Celery: src.executions.execute(execution_id)
   ↓
Lead Agent (in Celery worker)
   ├─ CapabilityResolver.resolve(capability_id, ws_type, ws_id)
   ├─ compile graph_template → langgraph
   ├─ 注入 system_prompt + brief + decisions + workspace context
   ├─ run langgraph (可能 spawn N subagents)
   ├─ events publish to ExecutionStream
   ▼
Frontend
   ├─ useExecutionStream → execution-store
   ├─ Live Workflow Panel: graph 渲染 + 节点状态色 + token 消耗
   ↓
Lead 完成
   ├─ 产物 staged 到 ExecutionRecord.result.staged_outputs
   ├─ publish "execution.completed"
   ├─ 写 system message "execution_completed" 到 thread (见 §4.2.3)
   ▼
Chat Agent (server-triggered, 不需用户输入)
   ├─ 读 system message + staged_outputs
   ├─ 生成 assistant message 含 result_card AgentBlock
   ↓
Frontend
   ├─ 渲染 result_card（默认全勾）
   ↓
User 点 ✓ 全部接受 (前端 UI 直接发请求)
   ↓
POST /executions/{id}/commit
   → ExecutionService.commit_outputs(execution_id, accepted_ids)
     → 单一事务: 写 Library / Documents / Memory / Decisions / Tasks
     → 总是写 Run History 摘要（无关用户选择）
   → publish "workspace.refresh" → 顶栏角标 +N
   → chat 收 ack message ("✓ 已保存。综述见 Documents.")
```

---

## 4. 详细设计

### 4.1 Chat Agent

#### 4.1.1 职责

- 对话（含闲聊、解释、引导）
- 意图识别（自然语言 → capability_id）
- Required decisions 收集（capability 缺关键参数时追问用户）
- Decisions 提取（在对话中识别用户偏好、风格、约束并写 Decisions 房间）
- Dispatch（构造 `TaskBrief` 调 `/executions` 接口）
- 进度回答（lead 在跑时查询 `ExecutionRecord.node_states` 给用户友好概括）
- Cancel 转发（用户说"停"时调 cancel API）
- Result_card 生成（lead 完成时把 TaskReport 渲染成 result_card）
- Memory / Decisions 读取（注入自身 prompt）

#### 4.1.2 实现：LangGraph create_react_agent

Chat agent 是一个轻量 react agent，不调用 subagent，仅有少量 tools：

| Tool | 用途 |
|------|-----|
| `dispatch_capability` | 构造 TaskBrief → POST /executions |
| `query_run_progress` | 读当前 run 的 node_states 给用户答 |
| `cancel_run` | 取消当前 run |
| `write_decision` | 写一条用户决策到 Decisions 房间 |
| `read_decisions` | 读 Decisions 房间（自动注入也可以） |
| `read_memory` | 读 Memory facts |
| `read_run_history` | 读 Run History 摘要 |
| `read_documents_meta` | 列出 Documents 房间内容（不读全文） |
| `read_library_meta` | 列出 Library 房间引用 |

> Note: result_card 上的 ✓/✗ 操作由前端 UI 直接 POST 到 `/executions/{id}/commit`，**不**经过 chat agent —— 那是用户对结果的明确动作，不是对话语义。

**System prompt 结构**：
```
你是 wenjin 的研究助手，正在协助用户完成 {workspace_type} 类型的工作。

# 当前 workspace
- ID: {workspace_id}
- 类型: {workspace_type}
- 已有产物: {document_count} 篇文档, {library_count} 条文献

# 你能调度的 capability（{N} 项）
{capability_list_with_brief_description}

# 用户决策（来自历史对话）
{decisions_top_15}

# 长期记忆
{memory_facts_top_15}

# 行为规范
1. 听到用户陈述明确意图时，识别 capability 并 dispatch
2. capability 的 required_decisions 缺项时，追问用户
3. lead agent 在跑时（_check_lead_busy()），不允许新 dispatch
4. 听到偏好类陈述（"我都用 APA"）→ write_decision
5. 听到 "停 / 取消"类指令 → cancel_run
6. 不要尝试自己执行 capability 的工作；那是 lead agent 的事
```

#### 4.1.3 与 thread session 的对应

- Workspace ID == Thread ID（1:1）
- chat agent 维护的 LangGraph state 即 thread checkpoint
- session 的 turn 累计到 token 阈值（默认 80%）→ 触发 auto-compact

#### 4.1.4 Auto-compact 流程

1. 阈值检测：每收一条新 message 检查累计 token
2. 触发后：把最近 N 个 turns 之前的所有 turns 交给 compact agent（独立 LLM 调用）
3. Compact agent 输出：
   - 浓缩后的 system message（替换被压的 turns）
   - 应写入 Memory 的 facts（带 confidence）
   - 应写入 Decisions 的偏好/约束
4. State 更新：thread state 的 messages 替换头部为浓缩 + 保留近期 N turns
5. 副作用：Memory.facts 追加，Decisions 追加

```python
# 伪代码
class CompactMiddleware(AgentMiddleware):
    async def before_model(self, state, config):
        if not should_compact(state):
            return state

        old_turns = state.messages[:-COMPACT_KEEP_LAST]
        compact_result = await compact_agent.ainvoke({
            "old_turns": old_turns,
            "workspace_type": state.workspace_type,
        })

        await memory_service.add_facts(
            state.workspace_id, compact_result.facts
        )
        await decisions_service.add_decisions(
            state.workspace_id, compact_result.decisions
        )

        return state.with_messages([
            SystemMessage(compact_result.summary),
            *state.messages[-COMPACT_KEEP_LAST:]
        ])
```

### 4.2 Lead Agent

#### 4.2.1 职责

- 接受 `TaskBrief` + capability_id
- 通过 `CapabilityResolver` 加载 capability 实例
- 编译 `graph_template` → 实际 LangGraph
- 注入 capability.system_prompt + workspace context
- 执行 LangGraph（spawn 1..N subagents）
- 发 `execution.*` 事件到 ExecutionStream
- 完成后产出 `TaskReport`

#### 4.2.2 不做的事

- ❌ 不直接和用户对话（chat agent 才面向用户）
- ❌ 不写 workspace 房间（产物先 staged 到 ExecutionRecord.result，由 UI 触发 `/commit` 后才落房间）
- ❌ 不持久化跨 run 状态（除非通过 chat agent 提议写决策/记忆）

#### 4.2.3 Chat ← Lead 完成回路（关键架构细节）

`dispatch_capability` tool 是 **fire-and-forget**：调 `POST /executions` 即返回 `execution_id`，chat agent 立即可继续响应用户其他对话。

那 chat agent 怎么知道 lead 完成 / 怎么生成 result_card？通过 **ExecutionCompletionDelivery** 机制：

```
Lead agent 完成
  → publish_execution_event("execution.completed", {...task_report})
  → 同时：ExecutionService 写 message 到 thread:
       Message {
         role: "system",
         kind: "execution_completed",
         payload: { execution_id, task_report, result_card_outputs }
       }
  → publish_thread_event("thread.message_added")

Chat agent (下次被触发时)
  → 看到 head 上有未处理的 system "execution_completed" message
  → 不需要用户输入，直接生成 assistant turn:
     - assistant message 含一条 result_card AgentBlock
     - 渲染到 chat 流

Frontend
  → SSE 收到 thread.message_added
  → 立即触发 chat agent turn (server-side trigger or just refresh)
```

**触发 chat agent 的方式**有两种实现，选其一：
- **A · Server-push**：execution 完成时，gateway 把"系统消息"塞进 thread 历史，并主动调 chat agent runtime 跑一轮（chat agent 看到新 system message → 输出 result_card）
- **B · Frontend-poke**：execution 完成 SSE 推到前端 → 前端调 `POST /chat/messages?type=system_trigger` → chat agent 跑一轮

V1 用 **A**：纯后端机制，前端不需要协调；离线用户重连后也能看到 result_card。

#### 4.2.4 不做的事补充：Lead 不直接 commit 输出

Lead agent 的产物全部写入 `ExecutionRecord.result.staged_outputs`（JSONB array, schema 同 §4.7.5 ResultOutput）。**只有 UI 通过 `/commit` 端点把 staged_outputs 落房间**。这保留了 curated 流的"用户审核"语义。

#### 4.2.5 运行时裁量权

Capability 是脚手架不是契约。Lead agent 收到 TaskBrief 时，可以基于以下信号微调：

- 用户 raw_message 里有特殊要求（"快速版本就行"）
- workspace context 里某个产物已存在（"大纲已经生成过，跳过"）
- decisions 里和 default 冲突的偏好

裁量行为通过 lead agent 的 system prompt 显式授权：

```
你收到的 capability.graph_template 是默认脚手架。
你可以：
1. 跳过冗余阶段（已在 workspace 中存在的产物）
2. 调整阶段内 task 的 prompt（基于 decisions 微调）
3. 在阶段中插入额外步骤（基于 raw_message 的特殊要求）

你不能：
1. 改变 capability_id（你接到什么就是什么）
2. 跨越 capability 边界（如果用户实际想要别的，应当 fail 掉，让 chat agent 重新 dispatch）
3. 不发 execution.* 事件（每个 spawn / completion 必须发）
```

#### 4.2.6 与 LangGraph 集成

Lead agent 本身是一个 LangGraph 父图。其节点结构：

```
START
  ↓
[load_capability]   resolver.resolve(capability_id, ws_type)
  ↓
[plan]              基于 graph_template 生成实际执行 plan（含裁量）
  ↓
[publish_graph]     publish_execution_event("execution.graph_structure", ...)
  ↓
[execute_phases]    顺序执行 plan.phases
  │   每个 phase 内部:
  │     - publish "execution.node.started" for each task
  │     - 并行 spawn subagents (semaphore-bounded)
  │     - wait_all
  │     - publish "execution.node.completed" for each task
  ↓
[finalize]          组装 TaskReport
  ↓
[publish_completed] publish_execution_event("execution.completed", ...)
  ↓
END
```

#### 4.2.7 Subagent spawn 机制

- Subagent 类型来自代码注册表（[附录 B](#附录-b-subagent-类型注册表)）
- 每个 subagent 是一个独立的 LangChain runnable，运行在 lead agent 的 LangGraph 内部（**同一 langgraph，不再 cross-thread spawn**）
- 并发上限：每 phase 内最多 `N_SUBAGENTS_PER_PHASE`（默认 5）
- 取消传播：lead 收到 cancel 时，向所有未完成的 subagent 发 abort signal
- 嵌套限制：subagent 内不允许再 spawn subagent（嵌套深度 = 1）。复杂场景应通过额外 phase 表达
- Celery worker 死亡韧性：execute task 配置 `acks_late=True` + `soft_time_limit=3600`；worker 死亡后任务被重新分发；ExecutionRecord.attempts 计数防止无限重试（默认 3 次后标记 failed）

### 4.3 Capability 系统

Capability 是 chat agent 与 lead agent 之间的"能力契约"。它**是数据，不是代码**。

#### 4.3.1 Anatomy

完整字段定义：

```python
class Capability(BaseModel):
    # === Identity ===
    id: str                              # e.g., "deep_research"
    workspace_type: str                  # "thesis" | "sci" | "proposal" | "software_copyright" | "patent"
    version: int                         # 单调递增
    display_name: str                    # 中文展示名
    enabled: bool = True                 # admin 可禁用

    # === For chat agent ===
    intent_description: str              # 一句话描述什么样的用户请求映射到此
    trigger_phrases: list[str]           # 用户原话样例，用于 prompt 训练
    required_decisions: list[RequiredDecision]
                                         # 派工前 chat 必须问到的关键决策

    # === For lead agent ===
    brief_schema: dict                   # JSON Schema, TaskBrief.params 形状
    graph_template: PhasedPlan           # 见 4.3.2
    system_prompt: str                   # lead agent 执行此 capability 时的 prompt 片段
                                         # 模板变量: {{topic}}, {{decisions}}, {{workspace.documents}} 等

    # === For UI ===
    result_card_template: str            # 模板 ID, 渲染 result_card

    # === Metadata ===
    created_at: datetime
    updated_at: datetime
    notes: str | None = None             # admin 备注

class RequiredDecision(BaseModel):
    key: str                             # decision 字段名
    ask: str                             # chat agent 用来问用户的话
    type: Literal["string", "enum", "bool", "number"]
    enum_values: list[str] | None = None
    default: Any = None                  # 用户没给时的回退
```

#### 4.3.2 graph_template (PhasedPlan)

```python
class PhasedPlan(BaseModel):
    phases: list[Phase]

class Phase(BaseModel):
    name: str                            # "discover" / "organize" / "synthesize"
    depends_on: list[str] = []           # 其他 phase name
    tasks: list[TaskSpec]                # phase 内 task 并行

class TaskSpec(BaseModel):
    name: str                            # phase 内唯一
    subagent_type: str                   # 来自代码注册表（附录 B）
    prompt_template: str                 # 模板，变量同 Capability.system_prompt
    tools: list[str] = []                # 此 task 可用的 tool 名
    timeout_seconds: int = 300
    retry_on_failure: int = 0            # 失败重试次数
```

**编译规则**：
- 阶段间按 depends_on 拓扑排序，串行执行
- 阶段内 tasks 并行（semaphore-bounded）
- task 失败按 retry_on_failure 重试，仍失败 → ToolErrorHandling middleware 处理

#### 4.3.3 YAML 格式（admin 可读可编辑）

```yaml
# capabilities/thesis/deep_research.yaml
id: deep_research
workspace_type: thesis
version: 1
display_name: 深度文献调研
enabled: true

intent_description: 用户希望对某个主题做学术性的深度文献调研，产出综述性 review
trigger_phrases:
  - 调研一下
  - 找综述
  - 文献调研
  - 给我做 literature review
required_decisions:
  - key: topic_scope
    ask: 主题边界是？（比如"GAN" vs "conditional GAN" vs "GAN for image generation"）
    type: string
  - key: language
    ask: 中文 / 英文 / 双语？
    type: enum
    enum_values: [zh, en, both]
    default: both
  - key: time_range
    ask: 文献时间范围？（默认近 5 年）
    type: string
    default: "recent_5_years"

brief_schema:
  type: object
  required: [topic, language]
  properties:
    topic: { type: string }
    language: { type: string, enum: [zh, en, both] }
    time_range: { type: string }

graph_template:
  phases:
    - name: discover
      tasks:
        - name: scholar_search
          subagent_type: scholar_searcher
          prompt_template: |
            搜索关于 {{topic}} 的学术文献，语言: {{language}}, 时间窗: {{time_range}}.
            目标 20-30 篇高质量文献。
          tools: [scholar_search, web_search]
        - name: web_search
          subagent_type: web_searcher
          prompt_template: |
            补充非学术源（技术博客、新闻）以获取 {{topic}} 的近期动态.
          tools: [web_search]

    - name: organize
      depends_on: [discover]
      tasks:
        - name: cluster
          subagent_type: clusterer
          prompt_template: |
            对发现的文献做主题聚类。
            考虑用户已有的 decisions: {{decisions}}.

    - name: synthesize
      depends_on: [organize]
      tasks:
        - name: write_review
          subagent_type: critical_writer
          prompt_template: |
            写一篇批判性综述，主题 {{topic}}.
            用户偏好风格: {{decisions.style | default('学术批判性')}}.
            目标长度: {{decisions.length | default('4000-5000 字')}}.
          retry_on_failure: 1

system_prompt: |
  你是学术文献调研专家，正在为用户处理一个 deep_research 任务。
  按 graph_template 阶段执行，但允许根据用户实际诉求微调：
  - 如果 raw_message 提及"快速浏览"，可减少 phase discover 的搜索量
  - 如果 workspace.documents 已有同主题综述，可在 result_card 中提示用户

result_card_template: literature_review
```

#### 4.3.4 DB 模型

```sql
CREATE TABLE capabilities (
    id VARCHAR(100) NOT NULL,
    workspace_type VARCHAR(50) NOT NULL,
    version INTEGER NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    intent_description TEXT NOT NULL,
    trigger_phrases JSONB NOT NULL DEFAULT '[]',
    required_decisions JSONB NOT NULL DEFAULT '[]',
    brief_schema JSONB NOT NULL,
    graph_template JSONB NOT NULL,
    system_prompt TEXT NOT NULL,
    result_card_template VARCHAR(100) NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, workspace_type, version)
);

CREATE INDEX ix_capabilities_active
    ON capabilities (workspace_type, enabled)
    WHERE enabled = TRUE;

CREATE TABLE capability_active_versions (
    id VARCHAR(100) NOT NULL,
    workspace_type VARCHAR(50) NOT NULL,
    active_version INTEGER NOT NULL,
    PRIMARY KEY (id, workspace_type),
    FOREIGN KEY (id, workspace_type, active_version)
        REFERENCES capabilities(id, workspace_type, version)
);
```

注意：版本号自增（admin 编辑产生新行），`capability_active_versions` 指向当前生效版本。这让我们既支持立即覆盖（`UPDATE capability_active_versions SET active_version = N+1`）又有版本审计能力。

#### 4.3.5 CapabilityResolver

```python
class CapabilityResolver:
    """
    单例。在 Celery worker 进程中缓存 capability 实例。
    Capability 编辑后通过 Event Bus 失效本地缓存。
    """
    def __init__(self, db: AsyncSession, event_bus: EventBus):
        self._cache: dict[tuple[str, str], Capability] = {}
        # subscribe to capability.invalidated event for hot reload
        event_bus.subscribe("capability.invalidated", self._on_invalidate)

    async def resolve(
        self, capability_id: str, workspace_type: str
    ) -> Capability:
        key = (capability_id, workspace_type)
        if key not in self._cache:
            self._cache[key] = await self._load(capability_id, workspace_type)
        return self._cache[key]

    async def _load(self, capability_id: str, workspace_type: str) -> Capability:
        # JOIN capabilities + capability_active_versions
        ...

    def _on_invalidate(self, event: dict):
        key = (event["capability_id"], event["workspace_type"])
        self._cache.pop(key, None)
```

#### 4.3.6 V1 加载流程

启动时：
1. 检查 `capabilities` 表是否为空
2. 为空 → 扫描 `backend/seed/capabilities/**/*.yaml` → 灌库 → 写 `capability_active_versions`
3. 非空 → 跳过（DB 是 SSOT）

YAML seed 只在初次部署时使用，之后所有变更通过 admin API 或 SQL。

#### 4.3.7 Capability 校验

Admin 编辑 capability（V2）或 YAML seed 加载时，校验：

- `id` + `workspace_type` 唯一约束
- `graph_template.phases[*].depends_on` 引用必须解析到已存在的 phase name
- `graph_template.phases[*].tasks[*].subagent_type` 必须存在于 [Subagent 注册表](#附录-b-subagent-类型注册表)
- `graph_template.phases[*].tasks[*].tools` 必须是 subagent_type 允许的 tool 子集（subagent 注册表里声明）
- `brief_schema` 必须是合法 JSON Schema
- `system_prompt` / `prompt_template` 中的模板变量（`{{var}}`）声明在已知白名单内（参见 §4.3.8）
- `result_card_template` 必须存在于前端模板注册表

校验失败：admin 编辑场景返回 400 + 错误列表；YAML seed 启动时直接 fail-fast（部署应被阻断）。

#### 4.3.8 Capability 模板变量白名单

`prompt_template` / `system_prompt` 可用变量：

| 变量 | 来源 | 示例 |
|------|------|------|
| `{{topic}}`, `{{language}}`, ... | brief.params 字段 | YAML 中 brief_schema 声明的字段 |
| `{{decisions}}` | dict of decisions | `{citation_style: "APA", tone: "客观"}` |
| `{{decisions.citation_style}}` | 单条 decision | "APA" |
| `{{workspace.documents}}` | 文档列表元数据 | `[{id, name, kind}, ...]` |
| `{{workspace.library}}` | 文献列表元数据 | `[{id, title, year}, ...]` |
| `{{workspace.memory_facts_top_15}}` | top-N memory facts | string list |
| `{{raw_message}}` | 用户原话 | "深入调研一下 GAN 综述" |

未在白名单内的变量在编译时报错（防止 admin 写错变量名导致空 prompt）。

### 4.4 Workspace 数据层（8 房间）

每个房间是一个独立的 service + DB schema。所有房间都有：
- workspace_id 外键
- created_at / updated_at
- audit fields（who 写的）
- soft delete（deleted_at）

#### 4.4.1 Library（文献库）

存储文献、引用、专利、政策文件等"参考资料"。

```sql
CREATE TABLE library_items (
    id VARCHAR(36) PRIMARY KEY,
    workspace_id VARCHAR(36) NOT NULL,
    item_type VARCHAR(20) NOT NULL,    -- "paper" | "patent" | "policy" | "url"
    title VARCHAR(500) NOT NULL,
    authors JSONB,                     -- list of strings
    year INTEGER,
    venue VARCHAR(200),                -- journal / conf / patent_office
    doi VARCHAR(200),
    url VARCHAR(500),
    abstract TEXT,
    full_text_path VARCHAR(500),       -- 指向 Documents 或外部
    metadata JSONB DEFAULT '{}',       -- 类型特化字段
    tags JSONB DEFAULT '[]',
    cited_in_documents JSONB DEFAULT '[]',  -- 哪些 doc 引用了它
    added_by VARCHAR(20) NOT NULL,     -- "user" | "execution:{exec_id}"
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX ix_library_workspace ON library_items(workspace_id) WHERE deleted_at IS NULL;
```

API: `GET/POST/DELETE /workspaces/{ws}/library`

#### 4.4.2 Documents（文档产物）

用户的核心交付物（论文稿、章节、图表、导出文件）。

```sql
CREATE TABLE documents (
    id VARCHAR(36) PRIMARY KEY,
    workspace_id VARCHAR(36) NOT NULL,
    name VARCHAR(200) NOT NULL,        -- 文件名
    kind VARCHAR(30) NOT NULL,         -- "draft" | "outline" | "figure" | "export" | "upload"
    mime_type VARCHAR(100) NOT NULL,
    storage_path VARCHAR(500) NOT NULL, -- S3 / local FS
    size_bytes BIGINT NOT NULL,
    parent_id VARCHAR(36),             -- 版本链
    version INTEGER NOT NULL DEFAULT 1,
    metadata JSONB DEFAULT '{}',
    added_by VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX ix_documents_workspace ON documents(workspace_id) WHERE deleted_at IS NULL;
```

文档支持版本链（`parent_id`）。Lead agent 修订生成的新版本是子文档，原版保留。

API: `GET/POST/PUT/DELETE /workspaces/{ws}/documents`

#### 4.4.3 Decisions（用户决策记录）

Chat agent 从对话中提取的用户偏好/约束。

```sql
CREATE TABLE decisions (
    id VARCHAR(36) PRIMARY KEY,
    workspace_id VARCHAR(36) NOT NULL,
    key VARCHAR(100) NOT NULL,          -- "citation_style" | "tone" | ...
    value TEXT NOT NULL,                -- "APA" | "客观谨慎" | ...
    confidence REAL DEFAULT 1.0,        -- 0..1
    source_message_id VARCHAR(36),      -- chat 中哪条消息提取
    extracted_by VARCHAR(20) NOT NULL,  -- "chat_agent" | "compact_agent" | "user"
    superseded_by VARCHAR(36),          -- 后来的同 key decision id
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX ix_decisions_workspace_active
    ON decisions(workspace_id, key)
    WHERE deleted_at IS NULL AND superseded_by IS NULL;
```

读取约定：当 chat / lead agent 读 decisions 时，按 `(workspace_id, key)` 去重，取最新（superseded_by IS NULL）的。

#### 4.4.4 Memory（长期记忆）

Auto-compact 提取出的"重要的少数"事实。

```sql
CREATE TABLE memory_facts (
    id VARCHAR(36) PRIMARY KEY,
    workspace_id VARCHAR(36) NOT NULL,
    category VARCHAR(50) NOT NULL,      -- "writing_style" | "domain_term" | "user_habit" | "context"
    content TEXT NOT NULL,              -- 一行简短陈述
    confidence REAL DEFAULT 1.0,
    last_referenced_at TIMESTAMPTZ,
    reference_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX ix_memory_workspace_category
    ON memory_facts(workspace_id, category)
    WHERE deleted_at IS NULL;
```

容量管理：每 workspace 上限 N facts（默认 100）。超过时按 `(reference_count ASC, created_at ASC)` 淘汰（很少用且很旧的先走）。

#### 4.4.5 Run History（历次运行摘要）

每次 lead agent execution 完成后，写一条简洁摘要。区别于 ExecutionRecord：那是技术细节；Run History 是 user-facing 摘要。

```sql
CREATE TABLE run_history (
    id VARCHAR(36) PRIMARY KEY,
    workspace_id VARCHAR(36) NOT NULL,
    execution_id VARCHAR(36) NOT NULL UNIQUE,  -- 1:1 with ExecutionRecord
    capability_id VARCHAR(100) NOT NULL,
    title VARCHAR(200) NOT NULL,        -- "深度调研: conditional GAN"
    summary TEXT NOT NULL,              -- 1-2 句, ≤ 200 字
    status VARCHAR(20) NOT NULL,        -- "completed" | "failed" | "cancelled"
    artifact_count INTEGER DEFAULT 0,
    duration_seconds INTEGER NOT NULL,
    token_usage JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX ix_run_history_workspace
    ON run_history(workspace_id, created_at DESC)
    WHERE deleted_at IS NULL;
```

#### 4.4.6 Sandbox（隔离执行环境）

每 workspace 一个 sandbox 实例（lazy-acquired）。复用 deer-flow 的 LocalSandboxProvider 设计。

```sql
CREATE TABLE sandboxes (
    workspace_id VARCHAR(36) PRIMARY KEY,
    sandbox_id VARCHAR(64) NOT NULL,     -- provider-specific ID
    provider VARCHAR(50) NOT NULL,       -- "local" | "modal" | future
    state VARCHAR(20) NOT NULL,          -- "active" | "stopped" | "error"
    workspace_path VARCHAR(500),
    last_active_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Sandbox 由 `SandboxMiddleware` 在 lead agent 启动时 acquire，写入 `ExecutionRecord.runtime_state.sandbox_id`。Workspace 关闭后空闲 24h 自动释放（cron job）。

API（开发者模式开放）: `POST /workspaces/{ws}/sandbox/exec` 执行 bash + 返回 stdout/stderr。

**安全护栏**：
- 命令白名单 + 黑名单（沿用现有 `SandboxAuditMiddleware`）
- 禁止逃逸（`sudo` / `su` / 容器穿透命令一律拒）
- Resource limit：CPU 秒数 + 内存上限 + 单次输出 size 上限
- 用户 dev-mode 开关需要在 Settings 显式打开，且 audit log 记录每次开关
- 生产环境 lead agent 自身可以用 sandbox（subagent `code_executor` 走 SandboxMiddleware acquire）；用户 dev-mode 是另一回事，默认关

#### 4.4.7 Tasks（用户跨 run 待办）

```sql
CREATE TABLE tasks (
    id VARCHAR(36) PRIMARY KEY,
    workspace_id VARCHAR(36) NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending | in_progress | done
    priority INTEGER DEFAULT 0,
    related_execution_ids JSONB DEFAULT '[]',
    created_by VARCHAR(20) NOT NULL,    -- "user" | "chat_agent" | "lead_agent"
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX ix_tasks_workspace_active
    ON tasks(workspace_id, status, priority DESC)
    WHERE deleted_at IS NULL;
```

API: `GET/POST/PUT /workspaces/{ws}/tasks`

#### 4.4.8 Settings（workspace 配置）

```sql
CREATE TABLE workspace_settings (
    workspace_id VARCHAR(36) PRIMARY KEY,
    default_model VARCHAR(100),
    thinking_enabled BOOLEAN DEFAULT TRUE,
    sandbox_provider VARCHAR(50) DEFAULT 'local',
    auto_compact_threshold REAL DEFAULT 0.8,
    capability_overrides JSONB DEFAULT '{}',  -- V2: per-workspace capability tweaks
    metadata JSONB DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 4.5 平台基础设施层（7 组件）

#### 4.5.1 Auth

复用现有 wenjin auth（FastAPI dependency `get_current_user`）。新增：
- 每 workspace 关联 `user_id`（owner）
- API 中间件验证 `user_id` 与请求 `workspace_id` 匹配
- V1 单用户，无 sharing；V2 加 collaborators

#### 4.5.2 Quota

跨 workspace 的成本/资源管控。

```python
class QuotaService:
    async def check(self, user_id: str, kind: str) -> bool:
        """kind ∈ {tokens_daily, executions_concurrent, storage_bytes}"""
    async def consume(self, user_id: str, kind: str, amount: int): ...
    async def get_usage(self, user_id: str) -> QuotaUsage: ...
```

V1 配额：
- tokens_daily: 1M / user / day
- executions_concurrent: 1 / workspace（已经由 lead-busy 约束保证）
- storage_bytes: 5GB / user

#### 4.5.3 Audit Log

所有关键事件的不可变日志。

```sql
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(36),
    workspace_id VARCHAR(36),
    action VARCHAR(100) NOT NULL,       -- "execution.created" | "capability.updated" | ...
    target_type VARCHAR(50),
    target_id VARCHAR(36),
    payload JSONB,
    ip_address VARCHAR(50),
    user_agent VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_audit_workspace_time ON audit_logs(workspace_id, created_at DESC);
CREATE INDEX ix_audit_user_time ON audit_logs(user_id, created_at DESC);
```

写入策略：异步队列，best-effort（失败不阻塞业务）。30 天保留期。

#### 4.5.4 Observability

- **Metrics**: Prometheus + 现有 wenjin metric registry
- **Tracing**: OpenTelemetry，在 ExecutionService.create_execution() 注入 root span，所有子调用自动 propagate
- **Logging**: structlog, JSON output, 强制 `execution_id` / `workspace_id` / `user_id` 字段

关键指标（接续 2026-05-08 文档 §12.1，V1 必须就位）：
- `execution_stream_latency_p99`
- `execution_node_duration{node_type}`
- `chat_agent_response_latency_p95`
- `capability_resolve_cache_hit_rate`
- `lead_agent_busy_rejection_count`
- `auto_compact_trigger_count`

#### 4.5.5 Model Gateway

统一的 LLM 调用代理。所有 chat agent / lead agent / subagent 都走这里。

```python
class ModelGateway:
    async def chat_completion(
        self, messages, model: str, *,
        workspace_id: str, execution_id: str | None = None,
    ) -> CompletionResult:
        # 1. quota check
        # 2. 路由（OpenAI / Anthropic / 本地等）
        # 3. retry on transient errors
        # 4. 成本计算 + audit log
        ...
```

**成本追踪去向**：每次 LLM 调用产生的 `(input_tokens, output_tokens, model, cost_usd)` 写入：
- `executions.token_usage` JSONB（per-execution 累计）
- `audit_logs.payload` 详细记录每次 call
- `quota` 内存 counter（实时配额检查）
没有独立 cost 表 V1，避免重复持久化。

#### 4.5.6 Capability Registry

见 §4.3.5 + §4.3.6。

#### 4.5.7 Event Bus

跨进程发布/订阅。基于 Redis Pub/Sub + Streams 双通道：
- **Pub/Sub** 用于轻量通知（`capability.invalidated` / `workspace.refresh`）
- **Streams** 用于 `execution.*` 事件（保证 replay）

```python
class EventBus:
    async def publish(self, channel: str, event: dict): ...
    def subscribe(self, channel: str, handler: Callable): ...
```

### 4.6 前端事件流融合（FE 架构补充）

前端同时订阅两条 SSE 流：
- `GET /workspaces/{ws}/chat/stream` — chat agent 输出（assistant blocks, reasoning, tool calls）
- `GET /executions/{id}/stream` — 当前 active execution（仅当有 active run 时连）

各自喂不同 store：

| 流 | 消费者 | 影响 UI |
|---|---|---|
| chat.* | `chat-store` (新, 替代 thread-store) | Chat 列表 |
| execution.graph_structure | `execution-store` | Panel 渲染图 |
| execution.node.* | `execution-store` | 节点状态色 + drawer 数据 |
| execution.completed | `execution-store` + `chat-store`（触发拉取最新 thread message）| Panel 标完成 + chat 显示 result_card |
| workspace.refresh | 顶层 `workspace-store` | 顶栏角标刷新 |

**Active execution 跟踪**：`execution-store` 维护 `currentExecutionId`。值由两处更新：
- chat agent 调 `dispatch_capability` 后，前端从响应中拿到 `execution_id` → 设值 + 启 SSE
- workspace 进入时，调 `GET /workspaces/{ws}/executions/active` → 若有 active run 则恢复订阅

**断线重连**：execution stream 用 `Last-Event-ID` header 重放（沿用现有 RedisStreamBridge replay 能力）。chat stream 用 thread checkpoint id 续接（新接口 `?since_message_id=`）。

### 4.7 UX 流程与状态机

#### 4.7.1 Run lifecycle

```
[chat dispatch]
       ↓
   pending     ──cancel──► cancelled
       │
       ▼
   running    ──cancel──► cancelling ──► cancelled
       │
       ▼
   ┌──────────────────────────┐
   │                          │
   ▼                          ▼
 completed                 failed
   │                          │
   ▼                          ▼
[result_card]            [error result_card]
   │                          │
   ▼                          ▼
[user ✓]                 [user retry?]
   │                          │
   ▼                          ▼
[outputs committed]      [new dispatch with same brief]
```

#### 4.7.2 Lead-busy 行为

Chat agent 在每次构造 `dispatch_capability` tool call 前检查：

```python
async def _check_lead_busy(workspace_id: str) -> str | None:
    active = await execution_service.get_active(workspace_id)
    if active is None:
        return None
    # 友好的拒绝消息
    return f"我正在跑「{active.capability_id}」（{active.progress}%）。等它完成后我们继续，要不要我先汇报下进度？"
```

如返回非 None，chat agent 把这条消息作为 assistant message 发给用户，不进入 dispatch。

但 `query_run_progress` / `cancel_run` / `read_*` tools 仍然可用——chat 不被冻结，只是 dispatch 这一种动作被锁。

#### 4.7.3 Cancel 流程

两个入口：

**入口 A · Panel 一键终止按钮**：
```
Panel UI button click
  → DELETE /executions/{id}
  → ExecutionService.cancel_execution()
    → ExecutionRecord.status = "cancelling"
    → publish_execution_event("execution.status", {status: "cancelling"})
    → set abort_event on lead agent's execution context
  → lead agent 的 LangGraph runtime 在下一个节点边界检测 abort
  → 通知所有未完成 subagents 中断
  → ExecutionRecord.status = "cancelled"
  → publish "execution.completed" with cancelled status
  → result_card 显示 "已取消，部分产物可保留"
```

**入口 B · Chat 命令**：
```
User: "停一下"
  → chat agent 识别为 cancel intent
  → 调 cancel_run tool → 同样路径
  → chat agent 反馈："好的，正在终止。已完成的部分会保留，要保留哪些？"
```

#### 4.7.4 Failure 处理

**Subagent-level failure**:
- 由 `ToolErrorHandling` middleware（继承自 wenjin existing）捕获
- 转为 `ToolMessage(content="error: ...")` 注入到 lead agent 的对话
- Lead agent 决定：retry（按 retry_on_failure）/ skip（继续后续 phase）/ abort（fail run）

**Run-level failure**:
- ExecutionRecord.status = "failed"
- 部分产物保留在 ExecutionRecord.result.partial_outputs
- TaskReport 标记 partial=true
- result_card 显示：
  - 已完成的 phases ✓
  - 失败的 phase ✗ + error message
  - "重试 / 仅保留已完成 / 全弃" 三按钮

**Reset semantics**:
- "重试" = chat agent 用同一 brief 重新 dispatch（new ExecutionRecord）
- 历史失败 run 在 Run History 留痕

#### 4.7.5 Curated result_card

完整 schema：

```typescript
interface ResultCard {
  kind: "result_card";
  execution_id: string;
  status: "completed" | "failed_partial" | "cancelled";
  capability_id: string;
  duration_seconds: number;
  token_usage?: { input: number; output: number };
  cost_estimate?: string;        // "¥0.42"
  narrative: string;             // 自然语言总结
  outputs: ResultOutput[];       // 待用户审核的产物
  errors?: ResultError[];        // 失败的部分
}

type ResultOutput =
  | { id: string; kind: "library_item"; preview: string; default_checked: boolean;
      data: { title: string; authors: string[]; year?: number; doi?: string; url?: string;
              abstract?: string; metadata?: Record<string, unknown> } }
  | { id: string; kind: "document"; preview: string; default_checked: boolean;
      data: { name: string; mime_type: string; storage_path: string; size_bytes: number;
              parent_id?: string; doc_kind: "draft"|"outline"|"figure"|"export" } }
  | { id: string; kind: "memory_fact"; preview: string; default_checked: boolean;
      data: { content: string; category: string; confidence: number } }
  | { id: string; kind: "decision"; preview: string; default_checked: boolean;
      data: { key: string; value: string; confidence: number } }
  | { id: string; kind: "task"; preview: string; default_checked: boolean;
      data: { title: string; description?: string; priority?: number } };
```

User 操作：
- 全部接受 → POST /executions/{id}/commit { accept_all: true }
- 仅勾选项 → POST /executions/{id}/commit { accepted_ids: [...] }
- 全弃 → POST /executions/{id}/commit { accepted_ids: [] }

`/commit` 端点：
1. 把 accepted outputs 写入对应房间
2. 总是写 Run History（无关用户选择）
3. 发 `workspace.refresh` 事件 → 顶栏角标更新
4. 发 chat ack message ("已保存。综述见 Documents.")

#### 4.7.6 Auto-compact

触发：
- chat session 累计 token 达到 `auto_compact_threshold * model_context_limit`
- 或：用户明确说"压缩一下上下文"

执行（在 chat agent 的 middleware）：
```
1. before_model hook 检测阈值
2. 取 messages[:-COMPACT_KEEP_LAST]
3. 调用 compact_agent (轻量 LLM):
     输入: 旧 turns + workspace_type
     输出: { summary, facts: [...], decisions: [...] }
4. 写 Memory.facts (compact_agent 抽取的)
5. 写 Decisions (新的偏好)
6. 替换 messages 头部为 SystemMessage(summary)
7. 保留 messages[-COMPACT_KEEP_LAST:]
```

`COMPACT_KEEP_LAST` 默认 8 turns（保证近期对话连续性）。

---

## 5. API 设计

### 5.1 Chat 通道

```
POST /workspaces/{ws_id}/chat/messages
  Body: { content, attachments? }
  Response: { message_id }
  Side: chat agent invoked, SSE stream below

GET /workspaces/{ws_id}/chat/stream
  SSE: AgentBlock events (text / status_line / question_card / result_card)
       + tool_invocation / tool_result events
```

### 5.2 Execution 通道（继承 2026-05-08）

```
POST /workspaces/{ws_id}/executions
  Body: { capability_id, brief, raw_message, decisions? }
  Response: { execution_id }
  调用方: chat agent (via dispatch_capability tool)
  约束: 同 workspace 必须无 active execution

GET /executions/{id}
  Response: ExecutionRecord

GET /executions/{id}/stream
  SSE: ExecutionStreamEvent

GET /executions/{id}/graph
  Response: { graph_structure, node_states }    [新增]

GET /executions/{id}/nodes/{node_id}
  Response: ExecutionNode (full input/output/thinking/tools)    [新增, 之前 missing]

POST /executions/{id}/commit
  Body: { accept_all?: bool, accepted_ids?: string[] }
  Response: { committed: { library: N, documents: M, ... } }    [新增 curated 流]

DELETE /executions/{id}
  Cancel
```

### 5.3 Workspace 房间通道

每个房间 RESTful：
```
GET    /workspaces/{ws}/library
POST   /workspaces/{ws}/library
DELETE /workspaces/{ws}/library/{id}

GET    /workspaces/{ws}/documents
POST   /workspaces/{ws}/documents
PUT    /workspaces/{ws}/documents/{id}
DELETE /workspaces/{ws}/documents/{id}

GET    /workspaces/{ws}/decisions
POST   /workspaces/{ws}/decisions
PUT    /workspaces/{ws}/decisions/{id}/supersede
DELETE /workspaces/{ws}/decisions/{id}

GET    /workspaces/{ws}/memory
POST   /workspaces/{ws}/memory
DELETE /workspaces/{ws}/memory/{id}

GET    /workspaces/{ws}/runs
GET    /workspaces/{ws}/runs/{id}

POST   /workspaces/{ws}/sandbox/exec    [开发模式]
GET    /workspaces/{ws}/sandbox/files
PUT    /workspaces/{ws}/sandbox/files/{path}

GET    /workspaces/{ws}/tasks
POST   /workspaces/{ws}/tasks
PUT    /workspaces/{ws}/tasks/{id}

GET    /workspaces/{ws}/settings
PUT    /workspaces/{ws}/settings
```

### 5.4 Admin 通道（V2，骨架 V1）

```
GET    /admin/capabilities?workspace_type=
POST   /admin/capabilities
PUT    /admin/capabilities/{id}/{ws_type}
GET    /admin/capabilities/{id}/{ws_type}/versions
POST   /admin/capabilities/{id}/{ws_type}/activate
                  Body: { version: int }
```

V1 只做 GET/POST 后端，admin UI 自身是 V2。

### 5.5 SSE 事件 schema 速览

继承 2026-05-08 文档 §4.3 的 ExecutionStreamEvent（保持兼容）：

| 事件 | 何时 | Payload |
|------|-----|---------|
| `execution.metadata` | run 启动 | `{execution_id, capability_id, workspace_id}` |
| `execution.graph_structure` | plan 编译完 | `{nodes, edges}` |
| `execution.node.started` | 节点开始 | `{node_id, started_at}` |
| `execution.node.delta` | 流式 token | `{node_id, content_delta}` |
| `execution.node.completed` | 节点完成 | `{node_id, output_summary, token_usage}` |
| `execution.node.failed` | 节点失败 | `{node_id, error}` |
| `execution.status` | 状态变更 | `{status}` |
| `execution.completed` | 整体完成 | `{result_card_data}` |
| `execution.end` | 流终止 | null |

新增（chat 通道）：

| 事件 | 何时 | Payload |
|------|-----|---------|
| `chat.assistant.block` | chat agent 产生 block | `{block: AgentBlock}` |
| `chat.assistant.thinking` | chat agent reasoning | `{delta}` |
| `chat.tool.invocation` | chat agent 调 tool | `{tool, args}` |
| `chat.tool.result` | tool 返回 | `{tool, result}` |

---

## 6. 数据模型

### 6.1 ER 概览

```
users
  ↓ 1:N
workspaces
  ├── 1:1 ── workspace_settings
  ├── 1:1 ── threads (workspace.thread_id, 强 1:1)
  │           ↓ 1:N
  │         executions
  │           ↓ 1:N
  │         execution_nodes
  ├── 1:N ── library_items
  ├── 1:N ── documents
  ├── 1:N ── decisions
  ├── 1:N ── memory_facts
  ├── 1:N ── run_history
  ├── 1:1 ── sandboxes
  └── 1:N ── tasks

capabilities (跨 workspace)
  ↓ 1:1 active
capability_active_versions

audit_logs (独立)
```

### 6.2 关键表（已在 §4 各小节给出）

完整列表：
- `workspaces` (新增) — workspace 头实体
- `workspace_settings` (新增)
- `threads` (复用 wenjin existing，但 workspace_id 1:1)
- `executions` (复用 2026-05-08)
- `execution_nodes` (复用 2026-05-08)
- `capabilities` (新增)
- `capability_active_versions` (新增)
- `library_items` (新增，承接旧 `references`)
- `documents` (新增，承接旧 `documents` + artifact 一并归并)
- `decisions` (新增)
- `memory_facts` (新增)
- `run_history` (新增)
- `sandboxes` (新增)
- `tasks` (新增)
- `audit_logs` (新增)

### 6.3 workspaces 表

```sql
CREATE TABLE workspaces (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    type VARCHAR(50) NOT NULL,         -- "thesis" | "sci" | "proposal" | "software_copyright" | "patent"
    name VARCHAR(200) NOT NULL,        -- 用户给的 workspace 名
    thread_id VARCHAR(36),             -- 1:1 with active session
    description TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX ix_workspaces_user ON workspaces(user_id) WHERE deleted_at IS NULL;
```

---

## 7. 实施路线图

**总周期**: 12 周, 4 phase. 后端可灰度，前端 single-cutover.

### 7.1 Phase 1 · Foundation (Week 1-3)

**目标**: 平台层 7 项 + 8 房间 schema + capability registry 骨架，后端可独立运行测试。

| Week | 任务 | 验收 |
|------|------|------|
| W1 | DB migrations（workspaces / 8 房间表 / capabilities / audit_logs）| `alembic upgrade head` 通过；schema 与 §6 一致 |
| W1 | `workspaces` model + service + tests | CRUD 单元测试通过 |
| W1 | 8 房间各自的 model + service（CRUD；Sandbox 仅薄封装包 sandbox provider）| 每个房间 GET/POST 端点，单元测试覆盖 80%+ |
| W2 | Capability model + Resolver + YAML loader | seed 5 个 thesis capability 并加载，resolver 缓存正确 |
| W2 | Audit Log service + middleware | API 调用产生 audit 行 |
| W2 | Quota service（基础配额检查）| 单测 |
| W2 | Model Gateway（统一 LLM 代理）| chat completion + retry + cost tracking |
| W3 | Event Bus（Redis Pub/Sub + Streams 双通道）| publish/subscribe 单测；与现有 RedisStreamBridge 协作 |
| W3 | Observability 钩子（metrics + tracing 注入点）| Prometheus 端点暴露 §4.5.4 关键指标 |
| W3 | 集成测试: 所有平台层组件能协作（无 chat/lead 也跑通）| 集成 test suite 通过 |

**Deliverable**: 完整后端基础设施层可独立测试，与现有 wenjin 业务代码零耦合。

### 7.2 Phase 2 · Capability + Agents (Week 4-6)

**目标**: 双 agent 实装 + 第一个 capability 端到端跑通。

| Week | 任务 | 验收 |
|------|------|------|
| W4 | Chat Agent 实装（LangGraph create_react_agent + 10 tools）| 单测每个 tool；chat agent 能识别 capability 并构造 brief |
| W4 | Compact middleware | 阈值触发、写 memory/decisions、保留近期 turns |
| W4 | TaskBrief / TaskReport pydantic models | schema 验证 |
| W5 | Lead Agent 实装（LangGraph 父图，§4.2.6）| capability_resolver → compile → run 流程通 |
| W5 | Subagent 注册表 + 5 种 subagent type 实现（[附录 B](#附录-b-subagent-类型注册表)）| 每个 subagent 独立单测 |
| W5 | ExecutionEngine 重构（替代 ChatExecutionEngine + FeatureExecutionEngine）| 端到端 deep_research 跑通 |
| W6 | Curated commit 流（result_card schema + /commit 端点）| outputs 正确写入对应房间；audit 留痕 |
| W6 | Cancel 流程（panel button + chat command 双入口）| 中断正在执行的 subagent；ExecutionRecord 状态正确 |
| W6 | Failure 处理（部分失败 result_card + 重试入口）| 模拟 subagent 失败，result_card 正确显示 |

**Deliverable**: 后端用 curl + SSE 客户端就能完整跑 deep_research，写入 8 房间。

### 7.3 Phase 3 · Frontend Rewrite (Week 7-10)

**目标**: 新前端实装，对接 Phase 2 后端，但旧 UI 保持运行（不切流量）。

| Week | 任务 | 验收 |
|------|------|------|
| W7 | 新 Workspace 路由 + 4 栏布局壳 | `/workspaces/[id]/v2` 能渲染 chat + panel + 顶栏角标 |
| W7 | Chat 组件重写（消息 / agent block 渲染 / SSE 订阅）| reasoning 与 content 顺序正确；result_card 渲染 |
| W7 | Result_card 交互（默认全勾 + 一键 ✓ / 仅勾选 / 全弃）| 用户操作触发 /commit |
| W8 | LiveWorkflowPanel 重写（reactflow 渲染图）| graph_structure → 节点 + 边；node 状态色 |
| W8 | Node 点击 → drawer 展示 input/output/thinking/tools | drawer 调 /executions/{id}/nodes/{nid} |
| W8 | execution-store + useExecutionStream 接入新 panel | 取代旧 workflow-store |
| W9 | 顶栏角标 + 各房间 drawer/page | Documents / Library / Runs / Tasks / Memory / Decisions / Settings |
| W9 | Sandbox console（开发者模式）| 终端样式输出 |
| W9 | Auto-compact UI 提示（"上下文已压缩，X 条事实已记入 Memory"）| compact 触发后显示 toast |
| W10 | E2E 测试覆盖（Playwright）| 主路径 + 失败/取消/curated 都覆盖 |
| W10 | 性能调优（panel 大图渲染、长 chat 滚动虚拟化）| P99 渲染 < 200ms |

**Deliverable**: V2 UI 在 `/v2` 路由下完整可用；用户切换 toggle 试用；旧 UI 仍跑。

### 7.4 Phase 4 · Cutover (Week 11-12)

**目标**: 数据迁移 + 切换 + 旧代码清理。

| Week | 任务 | 验收 |
|------|------|------|
| W11 | 数据迁移脚本（[附录 C](#附录-c-数据迁移要点)）| 旧 thread / task / subagent_task / reference / artifact → 新 8 房间，验证查询无差错 |
| W11 | 内部 dogfood：把开发团队 workspace 全切到 v2 | 1 周稳定无 P0 bug |
| W11 | 性能压测（100 并发 workspace, 流延迟 P99）| 满足 §2.1 G9 |
| W12 | 用户切换：新建 workspace 全部走 v2，旧 workspace 提示用户"是否迁移"| 切换成功率 ≥ 99% |
| W12 | 旧代码删除 PR（lead_agent 单 agent 路径 / workflow-store / FeatureExecutionEngine 等）| diff 减少 ≥ 30k 行 |
| W12 | CLAUDE.md 更新（"All chat through lead_agent" 改为新双 agent 模型）| 更新落地 |

**Deliverable**: V2 是唯一线路，旧代码删除，CLAUDE.md 与代码一致。

### 7.5 跨 Phase 的频繁动作

- 每 PR 跑 backend pytest + frontend typecheck（CI 强制）
- 每周 demo（10 分钟，无 deck）
- 关键决策更新到本文档「9. 开放问题」

---

## 8. 风险与缓解

| # | 风险 | 概率 | 影响 | 缓解 |
|---|------|------|------|------|
| R1 | Phase 3 前端工作量低估（4 周不够）| 中 | 高 | 提前在 W6 抽 1 人开始前端原型；W10 末有"必须砍"的范围决策点 |
| R2 | Capability YAML 表达力不够，admin 想改但改不了 | 中 | 中 | YAML 字段保留 `extra_metadata: {}` 给 escape hatch；V2 加可视化拖拽 |
| R3 | 8 房间 service 之间的事务边界出问题（curated commit 跨多个房间）| 中 | 高 | `/commit` 端点单一事务（PG）；commit 失败原子回滚；幂等 idempotency_key |
| R4 | Lead agent 运行时裁量过头，行为不可预测 | 中 | 中 | 强制 lead 把每次"裁量"事件 publish 到 ExecutionStream（`execution.lead.deviation`），observable |
| R5 | Auto-compact 误删重要信息 | 低 | 高 | compact 不动 messages，只生成 SystemMessage 头部 + 写 Memory；用户可在 Memory 面板回看 |
| R6 | Capability 热加载在 Celery 多 worker 下不一致 | 中 | 中 | Event Bus 广播 invalidate；resolver 缓存 TTL 30s 兜底 |
| R7 | 数据迁移 W11 复杂度高（旧 thread → 新 workspace 1:1 关系如何确定）| 中 | 高 | 迁移前 W10 写 dry-run 工具；W11 灰度迁移：每天 N 个 workspace |
| R8 | 用户在 lead-busy 期反复尝试 dispatch，体验恼火 | 低 | 中 | chat agent 友好拒绝 + 主动提供"查看进度"按钮 |
| R9 | sandbox 长期占用资源（workspace 关了但 sandbox 没回收）| 中 | 低 | cron job: 24h idle → release；workspace delete → cascade release |
| R10 | Result_card commit 用户走神，全部接受了不该接受的 | 低 | 中 | UI 让 commit 是"可撤销 24h"（软删 + restore 接口） |
| R11 | 现有 wenjin 用户 workspace 量大（>100），cutover 慢 | 低 | 中 | 迁移工具支持 batch + resume；老 workspace 可保留旧 UI 入口直到用户主动迁 |
| R12 | LangGraph 父图 + subagent 子图嵌套深度过深，token 爆炸 | 低 | 高 | 限制 subagent 嵌套层级=2；每层 token budget 在 capability 中 declare |

---

## 9. 开放问题

| # | 问题 | 推荐方向 | 决策时机 |
|---|------|---------|---------|
| O1 | Capability 编辑后正在运行的 run 是否中途切到新版本？| **不切**（freeze 至完成）| Phase 2 |
| O2 | result_card 的 24h 撤销窗口是否需要？| 倾向加，简单实现（soft delete + restore button） | Phase 2 末 |
| O3 | Memory facts 上限 100 是否合理？| 按 dogfood 数据调（W11 复盘时定）| Phase 4 |
| O4 | Sandbox provider V1 只做 local 还是 modal 也做？| 只做 local（Modal 是 V2）| Phase 1 |
| O5 | Admin UI V2 是 wenjin 内置还是独立站点？| 内置 `/admin` 路径，沿用 wenjin auth | V2 启动时定 |
| O6 | 5 种 workspace 类型是否需要不同的 chat agent system prompt？| **是**（核心差异点之一）；prompt 每类型一个 .py 文件 | Phase 2 |
| O7 | sci 类型的 sandbox 默认是否预装 numpy/pandas/matplotlib？| 是（预置 conda env）| Phase 1 |
| O8 | Subagent 类型是否需要工具白名单（capability 不能让 subagent 用任意 tool）？| 是；capability YAML 的 `tools` 字段是允许列表，registry 校验 | Phase 2 |
| O9 | Token 限额是 user-level 还是 workspace-level？| user-level（workspace 维度只做并发限）| Phase 1 |
| O10 | run output 没全部 commit，30 天后 ExecutionRecord.staged_outputs 怎么办？| cron 清理（保留 30 天） | Phase 4 |

### 9.1 Phase 2 实施债务（Phase 3 落实）

Phase 1+2 已交付 278 测试通过的可工作骨架，但以下工作显式延后到 Phase 3 处理（决策已确认，无歧义，仅待 wire-up）：

| # | 债务 | 当前状态 | Phase 3 落实方式 |
|---|------|---------|-----------------|
| D1 | **ResultOutput 的 capability-specific output mapping**：`LeadAgentRuntime._collect_outputs()` 当前返回空列表，subagent 输出未翻译为 `ResultOutput` | runtime 完整可跑 + commit 流端到端测过 | 引入 capability YAML 的 `output_mapping` 字段，描述 `{node_results.{task_name}.output → ResultOutput[]}` 翻译规则；runtime 应用翻译。Phase 3 中前端集成 result_card 渲染时一并落实 |
| D2 | **Chat agent 的真实 LLM 调用**：`create_chat_agent()` factory 的 `langchain_chat_model` 是可选；测试用 `_AgentStub` | 9 tools + 5 prompts + compact middleware 全部测过 | Phase 3 wire 真实 `ChatAnthropic` / `ChatOpenAI`（取自 ModelGateway 或直接构造）。前端 chat SSE 流上线时一并打通 |
| D3 | **4 个其他 workspace_type 的 capability seeds**：sci / proposal / 软著 / 专利各缺 5 个 seed YAML | 5 个 thesis capabilities 已 seed + 测过；seed loader 校验通过；架构无变化只需复制扩展 | 可延到 admin UI（V2）上线后由产品/运营按 spec §A.2-A.6 内容陆续灌库；Phase 3 不阻塞前端开发 |
| D4 | **真实 Cancel signal 的 Redis 注入**：`ExecutionService.__init__` 的 `redis` 是可选；abort 信号写入跳过当无 redis | cancel API + lead agent abort check 端到端测过（mocked redis） | Phase 3 wire ExecutionService 实例化时传入项目共用 Redis 客户端；同一时机也 wire EventBus 与 publish_event 的真实 Redis |

这 4 项都不影响 Phase 1+2 的测试覆盖与功能正确性，但需要在 Phase 3 完成 wire-up 才能让"系统真的跑起来"（vs "组件能 import 跑测试"）。

---

## 附录 A: V1 Capability 启动目录

每个 workspace 类型至少 5 个 V1 capability，共约 30 个。Phase 2 W4-W5 期间逐步实装+灌库。

### A.1 共享（所有 workspace 类型）

| capability_id | 简述 |
|--------------|-----|
| `deep_research` | 深度文献/资料调研 |
| `outline_generate` | 结构大纲生成 |
| `section_write` | 章节撰写 |
| `section_revise` | 章节修订 |
| `style_polish` | 语言润色 / 翻译 |
| `review_critique` | 评审 / 批判 |
| `export_format` | 导出 / 排版 |

每种共享 capability 在不同 workspace_type 下有不同 graph_template profile（参见 §4.3.3 deep_research 的样例）。

### A.2 sci 专属

| capability_id | 简述 |
|--------------|-----|
| `experiment_design` | 实验方案设计 |
| `data_analyze` | 数据分析（含 sandbox 跑 Python） |
| `figure_generate` | 图表生成（matplotlib / plotly） |
| `citation_manage` | 引用核查（针对 arxiv/PubMed） |

### A.3 毕业论文专属

| capability_id | 简述 |
|--------------|-----|
| `defense_qa` | 答辩问答准备 |
| `citation_manage` | 引用核查（学术规范） |
| `chapter_consistency` | 全文一致性核查 |
| `data_analyze` | 数据分析（如适用） |

### A.4 申报书专属

| capability_id | 简述 |
|--------------|-----|
| `feasibility_review` | 可行性论证 |
| `budget_estimate` | 预算估算 |
| `competitor_analyze` | 同类项目对比 |
| `risk_matrix_generate` | 风险矩阵生成 |

### A.5 软著专属

| capability_id | 简述 |
|--------------|-----|
| `code_doc_generate` | 代码文档生成（从源码逆推说明书） |
| `arch_diagram` | 架构图生成（需 sandbox） |
| `competitor_analyze` | 竞品技术对比 |
| `manual_chapter` | 用户手册章节 |

### A.6 专利专属

| capability_id | 简述 |
|--------------|-----|
| `claims_draft` | 权利要求书撰写 |
| `novelty_check` | 新颖性核查（vs 现有专利）|
| `figure_generate` | 专利图（流程/结构）|
| `prior_art_analysis` | 现有技术分析 |
| `claim_translate` | 权要翻译（中→英）|

每个 capability 的完整 YAML 在 `backend/seed/capabilities/{workspace_type}/{id}.yaml`。

---

## 附录 B: Subagent 类型注册表

代码定义的 subagent 积木（`backend/src/subagents/types/`），capability YAML 通过名字引用。

| subagent_type | 输入 | 输出 | 工具集 |
|--------------|-----|------|-------|
| `scholar_searcher` | topic + filters | papers list | scholar_search, web_search |
| `web_searcher` | query | results list | web_search, fetch_url |
| `patent_searcher` | topic + IPC | patents list | patent_db, fetch_url |
| `clusterer` | items list | clustered groups | (none, LLM-only) |
| `critical_writer` | sources + style | markdown | (none) |
| `outliner` | topic + sources | outline | (none) |
| `reviser` | doc + critique | revised doc | (none) |
| `translator` | text + target_lang | translated | (none) |
| `code_executor` | python_code | stdout/stderr | sandbox_exec |
| `figure_generator` | data + spec | image_path | sandbox_exec, present_file |
| `citation_checker` | doc + library | issues list | (none) |
| `claims_drafter` | invention_brief | claims_md | (none) |
| `novelty_analyzer` | invention + prior_art | analysis | (none) |
| `competitor_analyzer` | target + market | comparison | web_search, fetch_url |
| `feasibility_analyzer` | proposal | analysis | (none) |
| `budget_estimator` | proposal | budget_table | (none) |

每个 subagent 实现一个标准接口：

```python
class SubagentBase(ABC):
    @abstractmethod
    async def run(
        self, prompt: str, context: SubagentContext, *,
        tools: list[Tool], execution_stream: ExecutionStream,
    ) -> SubagentResult: ...
```

---

## 附录 C: 数据迁移要点

Phase 4 W11 执行。原则：幂等 + 可回滚。

### C.1 workspace 创建

旧 wenjin 没有显式 workspace 实体（`Thread` 当 workspace 用）。迁移：

```sql
INSERT INTO workspaces (id, user_id, type, name, thread_id, ...)
SELECT
  gen_random_uuid(),
  user_id,
  COALESCE(metadata->>'workspace_type', 'thesis'),  -- 默认 thesis
  COALESCE(title, 'Untitled'),
  id,                                                -- thread_id == workspace.thread_id
  created_at, NOW()
FROM threads
WHERE deleted_at IS NULL
  AND id NOT IN (SELECT thread_id FROM workspaces WHERE thread_id IS NOT NULL);
```

### C.2 references → library_items

```sql
INSERT INTO library_items (id, workspace_id, item_type, title, ...)
SELECT
  r.id,
  w.id,
  'paper',
  r.title,
  ...
FROM references r
JOIN workspaces w ON w.thread_id = r.thread_id
WHERE r.id NOT IN (SELECT id FROM library_items);
```

### C.3 documents（旧）+ artifacts → documents（新）

合并两个旧表（区分 kind 字段）。

### C.4 task_records / subagent_task_records / execution_sessions → executions

复用 2026-05-08 文档 §8.3 的回填脚本（已经定义过）。

### C.5 thread.messages 不变

LangGraph checkpointer 已存。Auto-compact 在新 chat agent 启动后自动开始工作。

### C.6 验证查询

```sql
-- 每个 workspace 必须有 1 个 thread_id
SELECT COUNT(*) FROM workspaces WHERE thread_id IS NULL;

-- 每个 workspace 的 library_items 数量
SELECT workspace_id, COUNT(*) FROM library_items GROUP BY workspace_id;

-- 验证 executions 表完整
SELECT COUNT(*) FROM executions WHERE workspace_id NOT IN (SELECT id FROM workspaces);
```

### C.7 回滚预案

迁移期间打开 `feature_flag.use_v2_workspace_model = false`（逐 user 灰度）。回滚 SQL：

```sql
DELETE FROM library_items WHERE workspace_id IN (SELECT id FROM workspaces WHERE created_at > '<migration_start>');
-- 类推其他房间
DELETE FROM workspaces WHERE created_at > '<migration_start>';
```

---

*文档结束 · 等待用户 review → 进 writing-plans 阶段*
