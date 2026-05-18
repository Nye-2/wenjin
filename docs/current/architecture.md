# Wenjin Architecture

更新时间：2026-05-14
状态：Current

本文件是 Wenjin 当前架构的唯一总览事实源。
后续开发应以本文件为准，不再并行维护多份“当前架构”文档。

## 1. Canonical Truth

### 1.1 执行域

- `ExecutionRecord` 是唯一产品级执行事实源
- `execution_id` 是唯一 canonical execution 标识
- `ExecutionSession*` 运行时概念已退役

`ExecutionRecord` 拥有：

- 执行身份与类型
- 生命周期状态
- feature / workspace / thread 上下文
- graph structure / node states
- artifact linkage
- advisory / next actions
- parent-child execution 关系

### 1.2 支撑模型

- `TaskRecord`：异步任务运行记录，不是产品执行 SSOT
- `ComputeSessionRecord`：工作台 shell / projection 绑定，不拥有业务执行状态
- `SubagentTaskRecord`：子执行投影，绑定 canonical `execution_id`

### 1.3 为什么这样拆

这三个模型的拆分是刻意设计，不应再混回去：

- `ExecutionRecord` 回答“产品层发生了什么”
- `TaskRecord` 回答“后台任务如何被调度和推进”
- `ComputeSessionRecord` 回答“用户工作台现在该恢复成什么样子”

如果某个需求同时想改这三者，开发时必须先判断：

1. 这是产品语义变化？
2. 这是异步执行机制变化？
3. 这是 UI 工作面恢复变化？

只有先回答清楚，代码才不会再次耦回双轨。

## 2. System Topology

### 2.1 用户体验层

- 左面板：Chat / result card / orchestration 入口
- 右面板：Execution / Compute / rooms / Prism review
- 工作区 route：`/workspaces/{workspace_id}`

### 2.2 后端主分层

| Layer | 主要位置 | 职责 |
|---|---|---|
| Router | `backend/src/gateway/routers/` | HTTP 协议适配、鉴权、响应组装 |
| Application | `backend/src/application/` | launch / resume / thread turn / use case 编排 |
| Execution | `backend/src/services/execution_service.py` `backend/src/execution/` | execution lifecycle、统一执行引擎、runtime provider |
| Task | `backend/src/task/` | Celery dispatch、runtime state、durable task history |
| Compute | `backend/src/compute/` | workbench projection、files/logs/review gate |
| Capability Domain | `backend/seed/capabilities/` `backend/src/database/models/capability.py` `backend/src/services/capability_resolver.py` | capability schema、graph_template、brief_schema、trigger_phrases、缓存失效 |
| Capability Skill Domain | `backend/seed/skills/` `backend/src/database/models/capability_skill.py` `backend/src/agents/middlewares/capability_skill_preload.py` | reusable subagent instruction packs、skill preload、subagent prompt/runtime config |
| Agent Runtime | `backend/src/agents/lead_agent/` | graph compile、subagent orchestration、TaskReport |

### 2.3 前端主分层

| Layer | 主要位置 | 职责 |
|---|---|---|
| Route / page | `frontend/app/(workbench)/workspaces/[id]/` | 页面编排、面板装配、路由入口 |
| API client | `frontend/lib/api*` | HTTP / SSE 协议适配、类型定义 |
| Store | `frontend/stores/` | execution / compute / workspace / chat 状态管理 |
| Integration hook | `frontend/hooks/useWorkspaceEventStream.ts` | workspace 事件、execution 发现、execution stream 单入口 |
| Presenter | `frontend/lib/execution-presenters.ts` | `ExecutionRecord` 到 UI view model 的映射 |
| View components | `frontend/app/(workbench)/workspaces/[id]/components/` | execution card、compute 面板、chat 面板展示 |

### 2.4 非协商边界

1. Router 不编排业务流程
2. Compute 不拥有业务执行状态
3. Task 不替代产品 execution 事实源
4. capability / capability skill 才是执行定义事实源；feature 只允许作为工作台入口与兼容 UI 目录
5. execution payload 优先复用 canonical serializer
6. 前端 execution 状态不能再维护第二套并行运行态
7. workspace event hook 必须继续是 execution 发现与订阅单入口

## 3. Execution-First Main Chain

主链：

```text
User action
  -> chat / tool intent
  -> launch capability intent
  -> FeatureIngressService / FeatureLaunchService
  -> ExecutionRecord create
  -> ComputeSession ensure
  -> TaskService submit
  -> Celery worker
  -> ExecutionEngineV2
  -> LeadAgentRuntime
  -> TaskReport / execution stream
  -> execution store / compute projection / ResultCard
  -> commit to rooms / Prism review / refresh
```

### 3.1 Launch

- `launch_feature` 是 capability 执行统一入口
- launch / resume 主语义基于 `execution_id`
- lead-busy 通过 active execution 判定

#### Launch 代码入口

- tool：`backend/src/tools/builtins/launch_feature.py`
- application service：`backend/src/application/services/feature_launch_service.py`
- submission：`backend/src/application/services/feature_submission_service.py`

#### Launch 改动规则

如果你要改“功能如何发起”：

1. 先看 `launch_feature`
2. 再看 `FeatureLaunchService`
3. 最后看 `TaskService.submit_task`

不要绕过这条链直接在 router、前端或 graph 层创建 execution。

### 3.2 Runtime

- execution stream keyed by `execution_id`
- workspace events 只承担轻量发现 / refresh
- 前端 `useWorkspaceEventStream` 是 execution 发现与订阅单入口

#### Runtime 代码入口

- worker task：`backend/src/task/tasks/execution.py`
- engine：`backend/src/execution/engine.py`
- runtime：`backend/src/agents/lead_agent/v2/runtime.py`
- execution event publisher：`backend/src/services/execution_event_publisher.py`

#### Runtime 改动规则

如果你要改“执行过程如何流动”：

1. 优先改 execution stream payload
2. 不要让 workspace event 承担全量运行时状态
3. 不要在 chat message 里持久化 execution 当前状态

### 3.3 Result And Commit

- `TaskReport` 是结构化执行结果
- `ResultOutput` 经用户确认后 commit 到 rooms
- Prism 文件改动必须走 preview/apply/discard/revert

#### Commit 代码入口

- commit router：`backend/src/gateway/routers/execution_commit.py`
- commit service：`backend/src/services/execution_commit_service.py`
- room services：对应 `backend/src/services/rooms/` 或相关 room service

## 4. Frontend Contract

### 4.1 Canonical Execution Shape

前端统一消费 `ExecutionRecord`：

- execution store
- workspace execution list
- compute projection execution payload
- execution presenters / panels

开发规则：

1. 任何 execution UI 新需求，先看是否能直接基于 `ExecutionRecord`
2. 不要再引入新的“execution summary”或“session view model”作为后端事实源
3. 需要 UI 映射时，只允许在 presenter 层做衍生视图

线程历史里的 assistant message 允许持久化 `metadata.orchestration.execution_id`
作为 result card 与 execution 的归属锚点；但它不是实时执行状态源。

`execution_type` 是开放 contract，已知值包括：

- `chat_turn`
- `feature`
- `subagent`
- `tool`
- `advisory`
- `capability`
- `latex_compile`
- `python_plot`
- `mermaid_diagram`
- `ai_image`

### 4.2 Compute

- `ComputeSessionRecord` 只做 shell state
- compute projection 聚合 execution / task / subagent / logs / files / Prism
- execution payload 与 execution API 保持同一 canonical shape

#### Compute 改动规则

如果你要改 Compute：

1. shell 恢复能力看 `ComputeSessionRecord`
2. 聚合视图看 `backend/src/compute/projection_service.py`
3. 前端工作台 hydration 看 `frontend/stores/compute.ts`

不要把新的业务状态字段写进 `ComputeSessionRecord`。

## 5. Current Public Surfaces

### 5.1 Chat / runs

- `/api/threads/{thread_id}/runs/*`
- `/api/runs/*`

### 5.2 Executions

- `/api/executions`
- `/api/executions/{execution_id}`
- `/api/executions/{execution_id}/stream`
- `/api/executions/{execution_id}/commit`

### 5.3 Workspace / compute

- `/api/workspaces/{workspace_id}/executions`
- `/api/workspaces/{workspace_id}/compute/sessions`
- `/api/compute/sessions/{compute_session_id}`
- `/api/compute/sessions/{compute_session_id}/projection`

### 5.4 读取与写入面区分

读取面：

- executions 查询
- compute projection
- workspace activity / summary / artifacts / references

写入面：

- `launch_feature`
- execution commit
- Prism preview/apply/discard/revert

新功能优先扩写入面或读取面中的一个，不要把读取接口偷偷变成写入接口。

## 6. Supporting Domain Truths

### 6.1 Capability Domain

- capability seed + DB-backed
- `CapabilityResolver` 校验能力定义
- capability skills 由 `CapabilitySkillPreloadMiddleware` 注入 task spec / prompt 上下文
- `OutputMappingResolver` 是结构化输出映射事实源

当前工作台里仍保留 `feature_id` / feature catalog 等兼容 UI 语义，但执行事实源应视为：

1. `Capability`
2. `CapabilitySkill`
3. `ExecutionRecord`

而不是 `workspace_features/*`。

#### 新增 capability 的标准路径

新增 capability 时，按这个顺序改：

1. `backend/seed/capabilities/{workspace_type}/*.yaml`
2. `backend/src/database/models/capability.py`
3. `backend/src/services/capability_resolver.py`
4. 如涉及 skill pack，同步更新 `backend/seed/skills/*.yaml`
5. `capability_skill_preload` / subagent runtime / output mapping
6. 前端 capability entry / catalog / UI 兼容层

不要从前端按钮、兼容 feature catalog 或临时 tool 参数反推 capability 定义。

### 6.2 Rooms

当前 8 个 rooms：

- Library
- Documents
- Decisions
- Memory
- Run History
- Sandbox
- Tasks
- Settings

### 6.3 Task Runtime

- Celery + Redis + PostgreSQL
- Redis 提供 live runtime state / SSE responsiveness
- PostgreSQL 提供 durable task history

#### Task 改动规则

如果你要改 task：

1. 先判断是任务系统机制改动，还是 execution 业务状态改动
2. 机制改动进 `TaskService` / `TaskStore`
3. 业务状态改动优先进 `ExecutionService`

不要重新让 task 变成用户可见执行事实源。

## 7. Developer Playbooks

### 7.1 我要新增一个 capability

改这些地方：

1. capability YAML seed
2. 必要的 capability ORM / loader / resolver 契约
3. 相关 capability skill YAML
4. 如有结构化产物，补 output mapping
5. 前端 capability entry 展示与结果面

检查：

- 是否需要 compute
- 是否需要 sandbox
- 是否需要 Prism review gate
- 是否需要新的 execution output kind

### 7.2 我要新增一种 execution runtime

改这些地方：

1. `backend/src/execution/providers/`
2. `backend/src/execution/types.py` 或 provider 注册相关位置
3. `ExecutionRecord.execution_type` 的使用面
4. 前端 `KnownExecutionType`
5. 必要的 execution serializer / panel 呈现

检查：

- 是否需要 artifact 输出
- 是否需要 node-level detail
- 是否需要 compute projection 暴露 files/logs

### 7.3 我要改 execution panel

改这些地方：

1. `frontend/stores/execution-store.ts`
2. `frontend/hooks/useWorkspaceEventStream.ts`
3. `frontend/lib/execution-presenters.ts`
4. 面板组件

不要做：

- 在组件本地维护第二份 execution 生命周期
- 重新引入平行 SSE 订阅

### 7.4 我要改 result card / commit

改这些地方：

1. `TaskReport` / output contracts
2. execution completed payload
3. 前端 result card mapping
4. commit router / commit service / room service

不要做：

- 让未确认产物直接落 room
- 绕过 commit service 直接写 room
## 8. Documentation Policy

### 7.1 Current vs Historical

- 本文件是唯一架构总览事实源
- 历史设计稿、重构计划、专项 spec 不得再被当成 current architecture
- 历史材料如需保留，只能作为背景记录或 Git 历史参考

### 7.2 Future Changes

未来如发生下列变化，必须优先更新本文件：

1. execution / task / compute 边界变化
2. launch / runtime / commit 主链变化
3. public execution payload contract 变化
4. canonical route 或 canonical store 变化

## 9. Summary

Wenjin 当前已收敛为单一执行架构：

- `ExecutionRecord` 负责产品级执行状态
- `TaskRecord` 负责异步运行机制
- `ComputeSessionRecord` 负责工作台 shell / projection

这是当前系统的最终技术真相基线。
