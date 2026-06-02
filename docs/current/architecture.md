# Wenjin Architecture

更新时间：2026-06-02
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
- graph structure
- artifact linkage
- advisory / next actions
- parent-child execution 关系

节点级运行详情由 `ExecutionNodeRecord` 拥有：

- node lifecycle status
- node input / output / thinking
- tool calls / token usage
- started_at / completed_at

`ExecutionRecord.graph_structure` 只描述静态拓扑；节点详情接口必须从 `execution_nodes` 读取运行态数据。

### 1.2 支撑模型

- `TaskRecord`：异步任务运行记录，不是产品执行 SSOT
- `ComputeSessionRecord`：工作台 shell / projection 绑定，不拥有业务执行状态
- `SubagentTaskRecord`：子执行投影，绑定 canonical `execution_id`
- `ExecutionNodeRecord`：节点级运行详情，绑定 canonical `execution_id`

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
- 工作区主稿 route：`/workspaces/{workspace_id}/prism`
- historical workspace-owned `/latex/{project_id}` UI/page route 已移除，不作为兼容入口

### 2.2 后端主分层

| Layer | 主要位置 | 职责 |
|---|---|---|
| Router | `backend/src/gateway/routers/` | HTTP 协议适配、鉴权、响应组装 |
| Application | `backend/src/application/` | launch / resume / thread turn / use case 编排 |
| Execution | `backend/src/services/execution_service.py` `backend/src/execution/` | execution lifecycle、统一执行引擎、runtime provider |
| Task | `backend/src/task/` | Celery dispatch、runtime state、durable task history |
| Compute | `backend/src/compute/` | workbench projection、files/logs/review gate |
| Capability Domain | `backend/seed/capabilities/` `backend/src/dataservice/domains/catalog/` `backend/src/services/capability_loader.py` | `capability.v2` mission schema、DataService Catalog SSOT、graph_template、policy preload |
| Capability Skill Domain | `backend/seed/skills/` `backend/src/dataservice/domains/catalog/` `backend/src/agents/middlewares/capability_skill_preload.py` | `capability_skill.v2` worker instruction packs、skill preload、subagent prompt/runtime config |
| Account / Credit Domain | `backend/src/dataservice/domains/account/` `backend/src/dataservice/domains/credit/` `backend/src/services/credit_service.py` | account、credit ledger、redeem code、referral、dashboard credit projection 的 DataService SSOT |
| Model / Pricing Domain | `backend/src/dataservice/domains/model_catalog/` `backend/src/dataservice/domains/pricing/` `backend/src/services/model_catalog_cache.py` `backend/src/services/credit_service.py` | admin-managed OpenAI-compatible model catalog、encrypted model secrets、pricing policy、credit reservation、runtime model cache |
| Agent Runtime | `backend/src/agents/lead_agent/` | graph compile、subagent orchestration、TaskReport |
| Prism Manuscript Domain | `backend/src/dataservice/prism_api.py` `backend/src/dataservice/prism_review_api.py` `backend/src/services/workspace_prism_service.py` | workspace-owned manuscript review、source links、protected sections、surface projection |

DataService client 按领域拆分 domain mixin；`AsyncDataServiceClient` 只保留 HTTP shell、通用请求处理和未拆分领域的临时方法。新增 execution / generation client 方法必须放在 `backend/src/dataservice_client/execution_client.py`，不得回流到主 client shell。

### 2.3 前端主分层

| Layer | 主要位置 | 职责 |
|---|---|---|
| Route / page | `frontend/app/(workbench)/workspaces/[id]/` | 页面编排、面板装配、路由入口 |
| API client | `frontend/lib/api*` | HTTP / SSE 协议适配、类型定义 |
| Store | `frontend/stores/` | execution / compute / workspace / chat 状态管理 |
| Integration hook | `frontend/hooks/useWorkspaceEventStream.ts` | workspace 事件、execution 发现、execution stream 单入口 |
| Presenter | `frontend/lib/execution-run-view.ts` | `ExecutionRecord` / Runs `RunRecord` / chat `result_card` 到 `RunView` 的映射 |
| View components | `frontend/app/(workbench)/workspaces/[id]/components/` | execution card、compute 面板、chat 面板展示 |

### 2.4 非协商边界

1. Router 不编排业务流程
2. Compute 不拥有业务执行状态
3. Task 不替代产品 execution 事实源
4. capability / capability skill 才是执行定义事实源；`feature_id` 只允许作为传输字段名，其值必须是 canonical mission capability id
5. execution payload 优先复用 canonical serializer
6. 前端 execution 状态不能再维护第二套并行运行态
7. workspace event hook 必须继续是 execution 发现与订阅单入口
8. workspace-owned Prism 只通过 `/workspaces/{workspace_id}/prism` 进入；manuscript adapter API 只允许走 `/api/prism/latex-adapter/*`，不得恢复公网 `/api/latex/*`
9. account / credit / referral / redeem-code runtime 服务只能通过 DataService client 读写，不得重新打开 DB session 或导入迁移后的 ORM enum/model
10. workspace artifact runtime surface 使用 `WorkspaceArtifact*` / Asset DataService 契约；`legacy_artifact` 只允许出现在历史文档、迁移说明或测试断言中
11. 长期记忆 runtime、memory compaction、Celery memory capture 和 workspace-context upload memory note 只能通过 Knowledge DataService client 读写；`KnowledgeService` facade 不接受或保存 DB session
12. Dashboard runtime dependencies 和 summary/dashboard facade 只能通过 DataService-backed construction，不能注入 request DB session 或保留 DB fallback 查询
13. Workspace route/action context 和 WorkspaceContextMiddleware 只能通过 Workspace/Catalog/Template DataService-backed services，不能注入 `get_db` 或自行打开 `get_db_session`
14. Admin capability / skill catalog runtime 只能通过 Catalog DataService client 读写和 seed load；router、service、validator、loader 均不得接受或保存 DB session
15. Reference Library runtime 和 Prism `refs.bib` sync 只能通过 Source/Asset/Prism DataService client 读写；gateway references router 与 `SourceBibliographyService` 不接受 DB session，运行时 enum / request contract 从 `dataservice_client.contracts.source` 取得，不得导入 DB reference model contract
16. DataService-backed runtime facades（ThreadService、TemplateService、WorkspaceActivityService、AdminAnalyticsService、workspace skill label helpers）不得保留可选 DB constructor 或 `self.db`
17. Gateway 不再导出通用 `get_db` dependency；ExecutionService、TaskStore、SkillResolver、CapabilityResolver、WorkspaceService、GenerationService 不接受历史 DB/session constructor，运行时只允许通过 DataService client 边界访问持久化
18. Workspace asset runtime projection 只读取 canonical metadata 字段（`kind`、`parent_id`、`version`、`artifact_type` 等），不得在 router/activity projection 层读取 `legacy_*` metadata
19. Gateway routers 的鉴权 subject 必须使用 `AccountAuthSubject`，不得为了类型注解导入 DB `User` model
20. Prism adapter metadata 只能暴露 canonical `source_metadata`，DataService adapter helper 与 runtime surface 均不得把 project metadata 以 `legacy_metadata` 形式带出
21. Execution runtime 解析 workspace type 必须来自 DataService workspace projection；workspace 或 type 缺失时失败，不得默认降级到 thesis
22. Feature execution params 只能使用 canonical TaskBrief wrapper shape；不得保留 plain-param parser 或旧执行参数兼容入口
23. Feature action rerun/follow-up state 只能从显式 mission params 或 source artifact 推导 goal；前后端不得从 workspace description/name、`fallbackTaskName` 或“未命名任务”合成 goal
24. Workspace upload stored path 只允许 workspace-relative path 或 workspace-root 内绝对路径；不得接受 cwd-relative workspace-root-prefixed 历史路径
25. React subagent 若声明 tools 但无法解析到 callable，必须显式失败；不得静默降级为 plain model invoke
26. Catalog skill projection 必须读取 DB 中的 canonical `skill_json`；空缺或空对象直接失败，不得从旧字段读时合成 skill pack
27. Source domain 的 Library reference projection 是当前契约，不得用 `compat` 命名承载当前 API shape
28. Conversation block payload 持久化只保留 canonical `kind`，不得写入旧 kind 的 shadow 字段
29. Execution generation usage contract 是当前 DataService projection，不得以 legacy usage 命名描述
30. DataService / DataService app / DataService client 源码不得保留 stale `legacy` / `compat` / `fallback` 命名；真正的容错必须用当前领域语义命名
31. Chat Agent 与 workspace seed runtime 注释必须描述当前 DB-backed capability routing，不得保留已退役 resolver/prompt 路径描述
32. Production source 中不得保留未限定的 `legacy` 标签；历史行为只允许出现在测试、迁移断言或文档追溯中
33. `AuditService` 只能暴露 Audit DataService client 构造边界；不得接受或保存 `session_factory`、ORM model、`AsyncSession` 等 DB-shaped 参数
34. Gateway / Worker 进程生命周期不拥有 DB engine；Gateway readiness 检查 DataService `/readyz`，Worker bootstrap/shutdown 只初始化 runtime dependencies，不调用 `init_db` / `close_db` / `reset_db_engine`
35. Runtime helper 的类型注解也使用 DataService client payload contract，不再从 DB model 导入 `Thread` / `Workspace`
36. Model catalog、pricing policy、credit reservation 是 DataService SSOT；Gateway/admin UI 只能通过 DataService facade 读写，不得绕过到 DB session
37. 生产运行时模型发现来自 DataService runtime model catalog cache；`LLM_MODELS` / `LLM_IMAGE_MODELS` 只作为 seed/test 输入，不得作为生产 fallback
38. 模型 API Key 只允许 DataService 内部加密保存和 runtime 内部解密投递；admin/public projection 不得暴露明文 API Key
39. Worker 执行 chat turn 或 capability execution 前必须刷新 runtime model cache；管理员后台模型变更应影响后续任务，不要求重启 worker
40. Workspace sandbox 只能按 workspace 维度拥有一个 active environment；runtime provider key 为 `workspace-{workspace_id}`，不得再按 execution/node 生成独立 sandbox 基座
41. Credit admission 和普通扣费必须以 `spendable_credits = credits - reserved_credits` 为边界；active reservation 不能被 thread/feature/sandbox 普通消费穿透使用
42. Execution credit reservation metadata 只能通过 `src.billing.reservation_metadata` 读取和合并；feature launch、execution engine、DataService reconcile 不得各自手写 `billing.credit_reservation_id` 解析逻辑
43. Execution node detail 的运行态事实源是 `ExecutionNodeRecord`；`ExecutionRecord.node_states` 不得作为 gateway/API 的节点详情来源
44. DataService client 的 execution / generation API 必须通过领域 mixin 承载，避免 `AsyncDataServiceClient` 主文件继续膨胀成跨领域热点

## 3. Execution-First Main Chain

主链：

```text
User action
  -> workspace ChatPanel / tool intent
  -> thread run stream
  -> Chat Agent launch intent
  -> launch_feature tool
  -> context gate
      -> advisory: chat tool_result only, stop before execution/billing
      -> launched: chat tool_result launch receipt
  -> ExecutionRecord create
  -> ComputeSession ensure
  -> Celery execute_execution
  -> ExecutionEngineV2
  -> LeadAgentRuntime
  -> TaskReport / execution stream
  -> execution store / compute projection / ResultCard
  -> commit to rooms / Prism review/apply / activity refresh
```

### 3.1 Launch

- `launch_feature` 是 capability 执行统一入口，只接受 `schema_version == "capability.v2"` 的记录
- launch / resume 主语义基于 `execution_id`
- lead-busy 通过 active execution 判定
- Chat Agent 通过 thread run stream 调用 `launch_feature`；`tool_invocation` / `tool_result` 是 canonical chat block，不是模型文本约定
- `launch_feature` 成功返回 `status=launched`、`execution_id`、`feature_id`、`capability_name`，前端据此建立 run receipt 和 Current run 焦点
- workbench capability 卡片只负责选择 `capability_id`，卡片 prompt / follow-up 文案不等于任务 goal；缺少具体研究主题、材料、问题、query、keywords、dataset 或 source artifact 时，`launch_feature` 必须返回 `status=advisory`、`code=missing_params`
- `status=advisory` 不创建 `ExecutionRecord`、不创建 credit reservation、不分发 Celery、不触发外部搜索；前端只把它渲染为 chat advisory，右侧 Current run 保持 idle
- context gate 不得从 workspace name / description、capability name、generic launch prompt 或“未命名任务”合成 mission goal

#### Launch 代码入口

- tool：`backend/src/tools/builtins/launch_feature.py`
- launch context：`backend/src/application/services/feature_launch_context.py`
- chat stream extraction：`backend/src/application/handlers/thread_turn_handler.py`
- run stream publisher：`backend/src/runtime/runs/worker.py`
- execution dispatch：`backend/src/task/tasks/execution.py`

#### Launch 改动规则

如果你要改“功能如何发起”：

1. 先看 `launch_feature`
2. 再看 `feature_launch_context`
3. 再看 `launch_text`
4. 最后看 `execute_execution` / `ExecutionEngineV2`

不要绕过这条链直接在 router、前端或 graph 层创建 execution。改 capability 启动文案时必须同步检查“空上下文不会 launch”的测试。

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
- Prism 文件改动必须走 DB-backed review item → preview/apply/reject/revert
- `kind: prism_file_change` 是 review item declaration，不是普通 `ResultOutput`
- Prism apply/reject/revert 和 protected-section 操作写入 workspace activity / Prism projection

#### Commit 代码入口

- commit router：`backend/src/gateway/routers/execution_commit.py`
- commit service：`backend/src/services/execution_commit_service.py`
- room services：对应 `backend/src/services/rooms/` 或相关 room service
- Prism review service：`backend/src/dataservice/prism_review_api.py`

## 4. Frontend Contract

### 4.1 Canonical Execution Shape

前端统一消费 `ExecutionRecord`：

- execution store
- workspace execution list
- compute projection execution payload
- `RunView` presenters / panels

开发规则：

1. 任何 execution UI 新需求，先看是否能直接基于 `ExecutionRecord`
2. 不要再引入新的“execution summary”或“session view model”作为后端事实源
3. 需要 UI 映射时，只允许在 presenter 层做衍生视图

`frontend/lib/execution-run-view.ts` 是当前执行体验的唯一前端 presenter：

- `runViewFromExecution(record)`：live execution card / Current run
- `runViewFromRunRecord(record, workspaceId)`：Runs drawer 历史记录
- `runViewFromResultCard(data, workspaceId)`：chat completion summary
- `mergeRunViews(live, historical)`：同一 run 在 live/history 中合并展示

`frontend/stores/run-ui-store.ts` 只保存 UI 焦点和提示徽标，不保存 execution lifecycle。

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
- Chat run SSE 事件包含 `reasoning`、`content`、`block`、`tool_invocation`、`tool_result`、`done`、`error`

### 5.2 Executions

- `/api/executions`
- `/api/executions/{execution_id}`
- `/api/executions/{execution_id}/stream`
- `/api/executions/{execution_id}/commit`

### 5.3 Workspace / compute

- `/api/workspaces/{workspace_id}/executions`
- `/api/workspaces/{workspace_id}/runs`
- `/api/workspaces/{workspace_id}/compute/sessions`
- `/api/compute/sessions/{compute_session_id}`
- `/api/compute/sessions/{compute_session_id}/projection`

### 5.4 Workspace Prism

- `GET /api/workspaces/{workspace_id}/prism`
- `POST /api/workspaces/{workspace_id}/prism/ensure`
- `POST /api/prism/latex-adapter/projects/{project_id}/file-changes/preview`
- `POST /api/prism/latex-adapter/projects/{project_id}/file-changes/apply`
- `POST /api/prism/latex-adapter/projects/{project_id}/file-changes/discard`
- `POST /api/prism/latex-adapter/projects/{project_id}/file-changes/revert`
- `POST /api/prism/latex-adapter/projects/{project_id}/protected-sections`

`/api/latex/*` 已移除，不提供 redirect、fallback 或 tombstone compatibility handler。

### 5.5 Model / Admin Billing

- Public model discovery:
  - `GET /api/models`
  - `GET /api/models/{model_id}`
- Admin model catalog:
  - `GET /api/admin/models`
  - `POST /api/admin/models`
  - `PATCH /api/admin/models/{model_id}`
  - `POST /api/admin/models/{model_id}/disable`
  - `POST /api/admin/models/{model_id}/set-default`
  - `POST /api/admin/models/{model_id}/test`
- Admin pricing:
  - `GET /api/admin/pricing-policies`
  - `POST /api/admin/pricing-policies`
  - `PATCH /api/admin/pricing-policies/{policy_id_or_key}`
  - `POST /api/admin/pricing-policies/{policy_id_or_key}/disable`
  - `POST /api/admin/pricing/simulate`

模型目录和定价策略的 canonical 写入面只在 admin API；公开模型发现只返回可展示能力，不返回 `api_key` 或 runtime secret。

Admin dashboard token usage summary 是展示用近似聚合，必须遵守 DataService list API 的分页/limit 上限；当前服务侧使用受控采样上限 200 条 execution，不允许用超大 limit 穿透 DataService 边界。若后台需要全量 token / 成本汇总，应新增 DataService aggregate endpoint，而不是在 gateway facade 里循环或绕过数据库边界。

### 5.6 读取与写入面区分

读取面：

- executions 查询
- compute projection
- workspace activity / summary / artifacts / references
- workspace Prism surface projection

写入面：

- `launch_feature`
- execution commit
- Prism preview/apply/reject/revert/protect

新功能优先扩写入面或读取面中的一个，不要把读取接口偷偷变成写入接口。

## 6. Supporting Domain Truths

### 6.1 Capability Domain

- capability seed + DataService Catalog DB-backed
- capability seed 必须是 `schema_version: capability.v2`
- capability skill seed 必须是 `schema_version: capability_skill.v2`
- Catalog skill DB row 必须持久化完整 canonical `skill_json`；projection/preload 只投影事实源，不补写或合成旧形态 skill pack
- `CapabilityLoader` / admin save / DataService Catalog 写入路径使用同一套 v2 schema
- capability skills 由 `CapabilitySkillPreloadMiddleware` 注入 task spec / prompt 上下文
- 多步 capability graph 必须用阶段依赖表达执行顺序；下游写作、审查和制图节点通过 `upstream_outputs: "{{phases}}"` 消费上游 planner/search/analysis 输出，避免同 phase 并行导致上下文丢失
- skill seed 的 `role_prompt` 必须是可执行 instruction pack，包含 operating rules、output contract 和领域 quality gates；内容设计记录见 `docs/current/capability-skill-content-optimization.md`
- `LeadAgentRuntime` 将 `mission`、`context_policy`、`sandbox_policy`、`review_policy`、`quality_gates` 注入 `capability_policy`
- Compute 从 `sandbox_policy.mode` 推导 sandbox requirement
- `OutputMappingResolver` 是结构化输出映射事实源
- Chat Agent 不持有 sandbox provider、sandbox state、bash/file tools 或 sandbox middleware；它只能通过 `launch_feature` 调度 capability
- Capability launch context 只从用户显式输入、query seed、route params、source artifact 和已提交的 room context 读取；generic workbench launch text 只能作为触发意图，不能作为执行参数
- Sandbox execution 只能由 Lead Agent graph 内的 subagent 节点根据 `capability_policy.sandbox_policy` 显式触发

当前工作台里 `feature_id` 仅为传输字段名，不再代表旧 workflow catalog。执行事实源为：

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
6. 前端 mission entry / stage mapping

不要从前端按钮、旧 feature catalog 或临时 tool 参数反推 capability 定义。

### 6.2 Model Catalog / Pricing / Credit Reservation

- Model catalog 由 DataService `model_catalog_entries` 持久化，是运行时模型发现、默认模型、模型能力标记和 provider config 的事实源。
- Admin model API 只接受 OpenAI-compatible provider 形态；当前后台配置字段是 `model_id`、`model_name`、`base_url`、`api_key`、能力 flags、默认/启用状态和 `pricing_policy_id`。
- API Key 在 DataService 内用 `MODEL_SECRET_KEY` / `MODEL_SECRET_KEY_FILE` 加密；admin list/edit projection 只返回 `api_key_redacted`，编辑时空 API Key 表示不替换原密钥。
- Runtime model cache 位于 `backend/src/services/model_catalog_cache.py`。Gateway lifespan 会 best-effort warmup；worker bootstrap best-effort warmup；`execute_run` 和 `execute_execution` 在每次任务进入 LLM runtime 前强制从 DataService refresh。
- `ModelCatalogService.test_model` 是 runtime config validation：它刷新 runtime cache，确认 enabled runtime config 能被解密并包含必要 provider 字段后标记 healthy；缺失、停用或解密/配置错误标记 failed。
- Pricing policy 由 DataService `pricing_policies` 持久化，当前 policy kinds 包括 `global_credit`、`model_usage`、`capability`、`tool`、`sandbox`。Pydantic config schema 使用 `extra="forbid"`，避免旧字段静默进入计费。
- Model usage 计费采用 value-pricing：先计算 weighted tokens，再与 raw-cost guard 和 surface minimum 取最大值。`credits_per_cny` 只作为收入/成本锚点，不等于 token 直接兑换。
- Credit reservation 用于 capability / sandbox 等可能长耗时任务的预授权、结算、释放/退款闭环；Execution 结果里保留 reservation/billing linkage。
- User credit summary 暴露 `credits`、`reserved_credits`、`spendable_credits`；admission check 使用 spendable，DataService 扣费时也按 spendable + overdraft floor 做原子校验。
- Admin pricing simulator 读取当前 enabled `global_credit` 与 `model_usage` policy；缺失时只用默认模板做 UI 估算，不改变 DataService 配置。

### 6.3 Rooms

当前用户可见 rooms：

- Library
- Documents
- Decisions
- Memory
- Run History
- Tasks
- Settings

Sandbox 是 Lead Agent / subagent-operated infrastructure，不是用户可操作 room。公开 workspace API 不提供任意 sandbox exec；Chat Agent 不 acquire sandbox，也不暴露 bash/file execution tools。每个 workspace 最多一个 active sandbox environment，provider key 固定为 `workspace-{workspace_id}`。Docker container 仍是短生命周期任务容器，但 `/workspace`、`/workspace/.wenjin/env/python` 和 package cache 会随 workspace sandbox 持久化复用，用于长程实验的文件、数据集、脚本和依赖连续性。DataService sandbox environment / job / lease / artifact 只作为 Lead Agent、subagent 和 Compute projection 的内部事实源。用户通过 execution/run detail 查看只读 sandbox traces、日志摘要、脚本、产物和 provenance。

Sandbox 依赖安装由 Lead-owned runtime 负责，不由 subagent 自行拼装系统命令。`sandbox_python` 只传 `dependency_hints`；runtime 在 workspace lease 内确保 Python venv 存在、按受控 pip command 自动安装 hints、遇到 `ModuleNotFoundError` 时最多安装缺失包并重试一次。安装 job 记录为 `operation=install_dependencies` 且 `billable=false`，实际 Python run / smoke check job 保持 billable 并通过 credit reservation 结算。安装网络只通过 `package_index_only` profile 开启，普通运行默认 `none`。

当前代码边界：

- sandbox provider primitives：`backend/src/sandbox/providers/`
- workspace sandbox manager：`backend/src/agents/lead_agent/v2/workspace_sandbox.py`
- Lead-owned sandbox runtime：`backend/src/agents/lead_agent/v2/sandbox_runtime.py`
- sandbox subagent：`backend/src/subagents/v2/types/sandbox.py`
- hidden diagnostic capability：`backend/seed/capabilities/sci/internal_sandbox_smoke.yaml`

### 6.4 Prism Manuscript Domain

- `LatexProject.workspace_id + surface_role=primary_manuscript` 是 workspace 与主稿的绑定事实
- Canonical `review_items` 是 Prism review state 的事实源
- Canonical `provenance_links` 是稿件变更 provenance 的事实源
- Canonical `prism_protected_scopes` 是用户保护稿件范围的事实源
- Prism adapter metadata 使用 canonical `source_metadata` 承接原始 project metadata；`legacy_metadata` 不属于 DataService adapter helper、运行时 API 或 surface projection
- `WorkspacePrismService` 聚合 editor state、review items、source links、protected sections、activity 和 compile status
- `TaskBrief.manuscript_context` 只接收 lightweight manuscript projection，不接收完整正文或 PDF
- Lead runtime 负责把 writer output stage 到 DataService review batch；DataService review action log 写入必须发生在 batch/items flush 之后
- LaTeX 只作为 Prism manuscript adapter 存在；gateway adapter routers、`LatexProjectService`、`LatexTemplateService`、`LatexCompileService`、`WorkspaceLatexProjectService` 和 `WorkspacePrismService` 均通过 `AsyncDataServiceClient` 访问 persistence，不接受 runtime DB session
- DataService 内部仍拥有 Latex/Prism/Review/Source 持久化接口；这是服务内边界，不是用户或前端可调用的 standalone LaTeX 产品面

### 6.5 Runtime DataService Boundary

- Auth dependencies 返回 `AccountAuthSubject`，由 Account DataService projection 构造；请求鉴权路径不再注入 `get_db`
- Auth token helper、`UserService`、account dashboard/admin analytics 通过 Account DataService 读写 account state
- Asset runtime 使用 WorkspaceArtifact contracts 和 `/internal/v1/assets/artifacts` DataService API；`legacy_artifact` 命名不允许回到 runtime contract
- Prism LaTeX adapter、Compute projection、Reference BibTeX sync、Lead runtime manuscript context 均通过 DataService client 读取/写入 manuscript、review、source、provenance facts
- Long-term memory runtime 使用 Knowledge DataService client：`user_memory_service`、`memory_compaction`、Celery `capture_memory` 和 workspace-context upload memory note 不打开 DB session，不 reset DB engine，不执行 request-time commit/rollback
- Dashboard runtime dependencies、`DashboardService` 和 `WorkspaceSummaryService` 通过 DataService-backed construction 读取 dashboard/summary/execution facts，不再注入 request DB session 或保留 DB fallback execution listing
- Workspace route/action context 使用 Workspace/Catalog/Asset DataService client；WorkspaceContextMiddleware 使用 DataService-backed TemplateService 加载 active template，不再打开 DB session
- Admin capability / skill catalog router、service、cross-ref validator 和 seed loader 使用 Catalog DataService client，不接受或保存 DB session；`bootstrap_admin` 的账号创建 DB bootstrap 不向 catalog loader 传递 session
- Reference Library router、execution commit Library materialization 和 BibTeX/Prism sync 使用 Source/Asset/Prism DataService client，不注入 `get_db`，`SourceBibliographyService` 不保存 DB session
- Gateway process 不初始化或关闭 DB；readiness 中的 persistence check 指向 standalone DataService `/readyz`
- Worker process 不 reset/init/close DB；worker 任务持久化均通过 DataService client 完成
- ThreadService、TemplateService、WorkspaceActivityService、AdminAnalyticsService 与 workspace skill label helpers 均为 DataService-backed facade；构造器不接受 DB session，不保存 `self.db`
- Gateway common deps 只导出 `get_dataservice_client` 等 domain services，不再提供通用 `get_db`；ExecutionService、TaskStore、SkillResolver、CapabilityResolver、WorkspaceService、GenerationService 的构造器只接受 runtime adapters 和 DataService client，不接受 DB/session 参数
- Workspace document room projection 和 workspace activity projection 只读取 canonical asset metadata，不再读取 `legacy_kind` / `legacy_parent_id` / `legacy_version`
- Gateway routers 统一以 `AccountAuthSubject` 标注 `get_current_user` / `get_current_admin` 注入结果，不再导入 DB `User` 作为 auth subject 类型
- ModelCatalogService / PricingPolicyService 是 gateway facade，不保存 DB session；Admin model/pricing routers 只能通过 DataService client 写入模型目录、定价策略和模型健康状态
- `llm_config` 只消费已安装的 runtime model catalog snapshot；生产路径不得从 env 模型列表自动 fallback
- Worker task runtime 使用 `src.task.model_catalog_runtime.refresh_runtime_model_catalog` 刷新模型目录，确保 admin 修改对后续任务生效
- 架构守卫覆盖 auth DB dependency、gateway/worker DB lifecycle boundary、runtime type hint DataService contract boundary、runtime legacy artifact naming、Prism adapter public route prefix、Prism adapter DB session dependency、memory runtime Knowledge DataService boundary、dashboard runtime DataService boundary、workspace runtime DataService boundary、admin catalog runtime DataService boundary、reference library runtime DataService boundary、runtime service facade DB constructor boundary、legacy gateway/execution helper DB session boundary、catalog/academic facade DB constructor boundary、workspace asset legacy metadata boundary、gateway router auth subject DB model boundary、Prism adapter metadata canonical field boundary、execution workspace type no-default boundary、feature launch canonical params boundary、feature action explicit goal boundary、workspace upload canonical stored path boundary、React requested-tools explicit failure boundary、Catalog skill canonical `skill_json` boundary、Source reference projection naming boundary、conversation block canonical payload boundary、execution generation usage naming boundary、DataService internal stale naming boundary、workspace capability routing comment boundary、production source unscoped legacy label boundary

### 6.6 Task Runtime

- Celery + Redis + PostgreSQL
- Redis 提供 live runtime state / SSE responsiveness
- PostgreSQL 提供 durable task history
- `execute_execution` 只通过 DataService workspace projection 解析 workspace type；缺失 workspace 或 type 会使 execution 失败并写回错误，不再默认使用 thesis

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
3. `frontend/lib/execution-run-view.ts`
4. `frontend/stores/run-ui-store.ts`（仅限 UI 焦点 / 徽标）
5. 面板组件

不要做：

- 在组件本地维护第二份 execution 生命周期
- 重新引入平行 SSE 订阅
- 让 Runs drawer 和 LiveWorkflowPanel 各自推导不同的状态/时长/动作

### 7.4 我要改 result card / commit

改这些地方：

1. `TaskReport` / output contracts
2. execution completed payload
3. 前端 result card mapping
4. commit router / commit service / room service
5. Prism review service / workspace Prism projection（如涉及稿件变更）

不要做：

- 让未确认产物直接落 room
- 绕过 commit service 直接写 room

## 8. Documentation Policy

### 8.1 Current vs Historical

- 本文件是唯一架构总览事实源
- 历史设计稿、重构计划、专项 spec 不得再被当成 current architecture
- 历史材料如需保留，只能作为背景记录或 Git 历史参考

### 8.2 Future Changes

未来如发生下列变化，必须优先更新本文件：

1. execution / task / compute 边界变化
2. launch / runtime / commit 主链变化
3. public execution payload contract 变化
4. canonical route 或 canonical store 变化
5. workspace-owned Prism projection、review contract、source/protected-section contract 变化
6. Chat run SSE block contract、RunView 投影、Runs drawer / LiveWorkflowPanel 执行体验变化

## 9. Summary

Wenjin 当前已收敛为单一执行架构：

- `ExecutionRecord` 负责产品级执行状态
- `TaskRecord` 负责异步运行机制
- `ComputeSessionRecord` 负责工作台 shell / projection

这是当前系统的最终技术真相基线。
