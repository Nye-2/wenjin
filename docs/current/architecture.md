# Wenjin Architecture

更新时间：2026-06-09
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

`ExecutionRecord.graph_structure` 只描述静态拓扑；节点详情事实源必须从 `execution_nodes` 读取运行态数据。Gateway/API 返回 execution list/detail 时可以由 `ExecutionService` 把 `ExecutionNodeRecord` hydrate 回 `ExecutionRecord.node_states`，但这只是前端 `RunView` 的展示投影，不改变 `execution_nodes` 的事实源地位。TeamKernel 的 graph projection 只保留 `team_prepare`、`team_recruit`、`team_dispatch`、`team_quality_gate`、`team_finish` 五个用户可理解流程节点；实名成员模板和 harness activity 由 hydrated `agent_invocation` node states 投影到 team roster，不再作为 `team_template_*` 流程占位节点展示。

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
| Agent Harness | `backend/src/agents/harness/` | Lead/subagent 专用工具执行 substrate：policy、tool registry、business context tools、sandbox file tools、Python job adapter、scheduler、events、output budget、loop guard、diff tracking |
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
43. Execution node detail 的运行态事实源是 `ExecutionNodeRecord`；`ExecutionRecord.node_states` 不得作为 gateway/API 的节点详情事实源。Gateway/API 可以在 read path 由 `ExecutionService` 从 `execution_nodes` hydrate `node_states` 给前端展示，但不能反向把 `node_states` 当成运行态写入或节点详情来源
44. DataService client 的 execution / generation API 必须通过领域 mixin 承载，避免 `AsyncDataServiceClient` 主文件继续膨胀成跨领域热点
45. Agent harness 只能由 Lead Agent graph / TeamKernel subagent 调用；不得由 Chat Agent、router、前端或新 execution stream 直接调用；tool calls、diff、事件和产物必须投影回现有 `ExecutionNodeRecord`、DataService execution events、sandbox job/artifact 和 review/result-card 流。`library_read` / `document_read` / `memory_read` / `prism_read` / `citation_parser` / `artifact_create` 是 subagent business-context tools，只能读取 bounded workspace snapshot 或返回 staged payload，不能直接提交 rooms、写 Prism 或物化 artifact。
46. Codex 和 deer-flow 只能作为 harness 模式参考：可借鉴 argv-first command contract、output budget、diff tracking、protected paths、tool error recovery、dangling tool-call repair、loop guard 和 sandbox provider hygiene；不得引入 Codex SDK/app-server、deer-flow agent factory、cc-switch bridge、第二套 thread/run model、第二套 execution stream 或通用 bash runtime 作为当前 Wenjin 执行事实源。

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

TeamKernel 的任务进展也由这个 presenter 统一派生：progress list 只展示五步流程，状态来自整体 run status、实名成员状态和质量门状态；成员模板不进入 progress list。`runtime_state.quality_gates` 会按 gate id 聚合为当前质量检查展示，使用最新状态，避免历史 quality gate event 在默认团队面板中重复刷屏。证据相关质量门不只检查字段存在：QualityContract 会从当前 `workspace_data.library_context` / `related_documents` 注入 `allowed_citation_keys` 和 `allowed_source_ids`；`claim_evidence_map_required` 要求每条 supported claim 同时带有 claim 文本和当前 workspace 允许的 `source_id` 或 `citation_key`，否则进入 `revise_existing`，避免无来源或跨工作区的 claim map 被当作已闭环证据。`source-quality-auditor` / `citation-auditor` 的 skill gates 也会触发结构化质量门：`source_authority_checked`、`metadata_completeness_checked`、`weak_support_flagged`、`no_fabricated_citations`、`claim_source_binding_checked`、`style_consistency_checked` 必须输出 `citation_key_audit`、`missing_sources`、`fabrication_risks` 或 `bibtex_projection_notes` 等结构化字段；其中 citation/source refs 若出现，必须来自当前 workspace allowlist；`fabricated`、`not_ready`、`replace`、`missing`、`unsupported`、`weak` 等风险状态或 `high/critical/blocking` severity 会让对应 gate fail。LiveWorkflow Evidence tab 会把 `wenjin.quality.citation_source_audit_finding.v1` 压成只读中文证据项，例如对象、风险、问题、建议和 bounded claim，不展示 schema id 或 raw auditor JSON。

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

Sandbox 是 Lead Agent / subagent-operated infrastructure，不是用户可操作 room。公开 workspace API 不提供任意 sandbox exec；Chat Agent 不 acquire sandbox，也不暴露 bash/file execution tools。每个 workspace 最多一个 active sandbox environment，provider key 固定为 `workspace-{workspace_id}`。Docker container 仍是短生命周期任务容器，但 `/workspace`、`/workspace/.wenjin/env/python` 和 package cache 会随 workspace sandbox 持久化复用，用于长程实验的文件、数据集、脚本和依赖连续性。DataService sandbox environment / job / lease / artifact 只作为 Lead Agent、subagent、agent harness 和 Compute projection 的内部事实源。用户通过 execution/run detail 查看只读 sandbox traces、日志摘要、脚本、产物和 provenance。

Workspace sandbox 文件系统契约由 `backend/src/sandbox/workspace_layout.py` 统一定义，provider acquire 时必须调用 `ensure_workspace_sandbox_layout()`，不得在 Docker/Local provider 或 harness tool 内重复硬编码目录。这个模块也是路径分类事实源：`normalize_workspace_virtual_path()`、`classify_workspace_path()`、`is_workspace_protected_path()`、`is_workspace_internal_path()`、`is_workspace_guidance_path()` 和 `is_user_reviewable_workspace_artifact_path()` 统一约束文件工具、artifact discovery 和 sandbox review staging。Agent 可见根目录固定为 `/workspace`，标准目录为：

- `/workspace/main`：主项目文件，承载论文、代码、实验入口等混合型工作内容
- `/workspace/datasets`：数据集与用户上传后进入 sandbox 的输入材料，包含可编辑 `/workspace/datasets/manifest.json`
- `/workspace/scripts`：可复用实验脚本和 agent 生成的执行脚本
- `/workspace/outputs`：图表、实验结果、编译产物和可展示 artifacts
- `/workspace/reports`：阶段性分析记录、运行总结和交付报告
- `/workspace/tmp`：临时 scratch，不默认作为用户可审阅产物
- `/workspace/.wenjin/env`：Lead-owned Python/runtime 环境，model tools 不可读写
- `/workspace/.wenjin/cache`：受控 package/runtime cache，model tools 不可读写
- `/workspace/.wenjin/manifest.json`：机器可读 layout manifest，作为 runtime 契约文件而非项目文件

所有 workspace type 共用这套目录，不为 `sci`、`thesis`、`proposal`、`software_copyright` 或 `patent` 分叉 provider layout。垂直差异通过 `workspace_profile(schema=wenjin.workspace_sandbox.type_profile.v1)` 进入 `.wenjin/manifest.json`、DataService sandbox environment metadata 与 harness context：profile 只声明推荐 `primary_files`、`script_paths`、`output_paths`、`report_paths` 和简短规则，例如 `sci` 推荐 `/workspace/main/main.tex`、`/workspace/main/refs.bib`、`/workspace/scripts/analysis.py`、`/workspace/outputs/figures`、`/workspace/reports/experiment-report.md`。`WORKSPACE_SUPPORTED_TYPES` 和 `validate_workspace_type_profile()` 会在测试中确保所有 workspace type profile 仍使用这套通用 layout 根目录，不落入 protected/internal 路径。未知 workspace type 使用 `generic` profile。Lead-owned sandbox runtime 在 acquire 后会用 Lead 已知的 workspace type 刷新 mounted `/workspace/.wenjin/manifest.json`，并在 `get_or_create_environment` 时写入轻量 `workspace_layout` / `workspace_profile` metadata；已有 active environment 会合并新的 runtime metadata，避免 provider 初始 generic manifest、DataService 管理面与 subagent context profile 分裂。新增类型应优先扩展 profile，不应新增平行目录或 provider 分支。

初始化会写入 `/workspace/main/README.md`、`/workspace/datasets/README.md`、`/workspace/outputs/README.md`、`/workspace/reports/README.md`、空的 `/workspace/datasets/manifest.json(schema=wenjin.workspace_sandbox.dataset_provenance.v1)` 和空的 `/workspace/reports/artifacts.json(schema=wenjin.workspace_sandbox.artifact_manifest.v1)`；已有 README、dataset manifest 或 artifact manifest 不会被覆盖。layout guidance 路径由 `is_workspace_guidance_path()` 统一识别，包含这些 README、manifest 和 `.gitkeep`，在 `classify_workspace_path()` 中归为 `hidden`，不能被注册为用户可审阅 artifact。dataset manifest 是 agent/用户可维护的数据来源清单，用于记录 `/workspace/datasets/**` 下可复用输入材料的 `source_id`、`content_hash`、license 和 preparation notes；secrets、API keys、credentials 和 private tokens 不得写入其中。Lead-owned `sandbox.run_python` 会在同一个 workspace lease 内、脚本执行前把 bounded `workspace_file_summary.dataset_provenance` 安全合并进 `/workspace/datasets/manifest.json`：只接受 `/workspace/datasets/**` 数据文件，拒绝 manifest/README/.gitkeep、protected/internal/non-workspace refs，并按 path 保留用户已有条目优先权。tool-using agent 若被 capability/skill 同时授予 `sandbox.register_dataset`、`filesystem.write` 和 `filesystem.diff`，也可以通过这个专用工具追加一条安全 dataset provenance；该工具只写 `/workspace/datasets/manifest.json`，复用同一套 sanitization 和用户已有条目优先规则，并返回普通 harness `file_change`，不允许把 host path、secret refs 或 `/workspace/outputs/harness/**` 注册成数据集。`/workspace/reports/artifacts.json` 是 agent/用户可维护的产物元数据清单，用于给 `/workspace/outputs/**` 和 `/workspace/reports/**` 的用户可审阅产物补充 title、description、artifact_kind、source_script、dataset_paths 和 notes；`sandbox.register_artifact` 是唯一 model-facing artifact metadata 写工具，同样要求 `filesystem.write` 与 `filesystem.diff`，会拒绝 non-artifact、protected/internal、guidance 和 host path refs，并返回 manifest `file_change`。

受保护路径由同一 layout 常量下发给 harness policy：`.git/**`、`.env`、`*.pem`、`*.key`、`.wenjin/env/**`、`.wenjin/cache/**`、`.wenjin/manifest.json`。`HarnessPolicy` 默认值也绑定这组 layout protected paths，直接构造 policy 的 mock、测试或未来工具入口不得得到更宽的文件系统可见性。`/workspace/outputs/harness/**` 统一分类为 internal，只能作为 tool 大输出引用，不可注册为用户产物；`/workspace/outputs/**` 和 `/workspace/reports/**` 的非 internal 文件才可进入 sandbox artifact review。`sandbox.list_dir`、`sandbox.glob` 和 `sandbox.grep` 也必须过滤 protected/internal 路径，不只是 `read_file` / write tools 拦截直接访问；这些工具还必须按 resolved physical target 跳过指向 workspace 外部、protected target 或 internal target 的 symlink，不能把外部文件、受保护文件、内部 refs 或 physical host path 投影给 agent。`sandbox.read_file`、`sandbox.write_file`、`sandbox.str_replace` 和 `sandbox.apply_patch` 会直接拒绝 protected/internal 路径，并在调用 provider 前校验目标 resolved physical path 仍位于 `/workspace`，且反推回 workspace virtual path 后不是 protected/internal target；symlink escape 或 provider-specific security failure 会统一归一成 harness path policy error。Local provider listing 对 workspace 内部 symlink 保留链接自身的 virtual path，不把 entry path 改写成目标文件路径。新 harness 链路不再引入 `/mnt/user-data` alias；旧 thread artifact / upload helper 若仍出现该路径，只能作为待迁移的非 harness 历史边界存在。

带 sandbox 工具的 ReactSubagent 会通过 `backend/src/agents/harness/context_assembly.py` 接收同一份 bounded harness context：默认 user payload 中包含 `_harness_context(schema=wenjin.harness.context_bundle.v1)`，system prompt 也会追加 `Harness context bundle`。因此即使 skill 使用自定义 `user_template`，模型仍能看到任务摘要、workspace 类型、`/workspace/datasets`、`/workspace/scripts`、`/workspace/outputs`、`/workspace/reports`、protected paths、`/workspace/outputs/harness/**` 内部路径规则、recent execution evidence 和 context budget。`build_agent_workspace_contract()` 还会提供机器可读 `path_classes`：workspace、datasets、scripts、artifacts、scratch、runtime、protected、internal、guidance；`context_assembly.py` 将其投影为 `sandbox.path_classes` 和 `sandbox.guidance_paths`，让成员按稳定 schema 判断写稿、数据、脚本、产物、临时文件和内部引用位置，而不是解析提示词。这个 bundle 也是团队成员执行上下文 schema，top-level 提供 `capability_goal`、`member_role`、`allowed_tools`、`workspace_roots`、`search_ignored_names`、最新 file-change / sandbox-execution / reproducibility summaries、`harness_replan_signals` 和 `upstream_artifact_candidates`，让工作流质量优化依赖稳定字段而不是散落 prompt 文本。Lead runtime 加载 workspace source context 时统一读取 DataService `list_sources_page().items[].assets`，把已经显式位于 `/workspace/datasets/**` 的 source asset 投影为 `workspace_file_summary.dataset_provenance`；context assembly 仍会二次过滤，只保留 `/workspace/datasets/**` 安全路径和 bounded provenance 字段，并过滤 protected/internal workspace refs；`sandbox.run_python` 再把这份安全 provenance 同步到 sandbox 内 dataset manifest，确保后续长程实验和新成员可以从文件系统看到同一份数据来源清单。文件系统规范不得只停留在 provider 建目录层，必须进入 tool-using agent 的运行上下文。

工具大输出统一写入 `/workspace/outputs/harness/{execution_id}/{node_id}/{invocation_id}/`，模型只接收 bounded preview、refs、`truncated` 和 `externalized` 标记。当前已覆盖 `sandbox.read_file` 的大文件读取、Lead-owned `sandbox.run_python` 的 stdout/stderr，以及 `sandbox.write_file` / `sandbox.str_replace` / `sandbox.apply_patch` 的大 unified diff；完整内容留在 workspace sandbox 内，`/workspace/outputs/harness/**` refs 不能再通过 direct `sandbox.read_file` 读回模型上下文。`sandbox.read_file(max_chars=...)`、`sandbox.glob(max_matches=...)` 和 `sandbox.grep(max_matches=...)` 的调用参数只能进一步收窄 policy 上限，不能放大 `read_max_chars` 或 `search_max_matches`；externalized output 的 head/tail 正文片段同样会被 fallback budget 钳制，不能通过 `preview_head_chars` / `preview_tail_chars` 重新放大模型可见内容。`sandbox.list_dir` 的 preview 与 structured `entries` 共用 `search_max_matches` 上限，并返回 `total_entries` / `returned_entries`；`sandbox.glob` / `sandbox.grep` 的 `matches` 同样受上限约束，并返回 `returned_matches` / `match_limit`，避免大目录或大搜索结果把完整列表塞进 tool JSON。`sandbox.grep` 还会按 `grep_max_file_bytes` / `grep_max_line_chars` 控制扫描成本，跳过超大文件、二进制文件和超长行，并在 payload 中返回 `scanned_files` 与 skipped 计数；非法 regex 返回 recoverable JSON tool error，不扫描文件、不中断 agent loop，并在 tool record / completed event 上投影 `recoverable_error` 与 `error_code`。普通 tool 输出通过 `output_refs` 投影到 tool call record 与 `execution.harness.output_externalized` 事件；文件改动 diff 通过 `file_change.diff_output_refs`、`diff_externalized`、`diff_truncated` 投影到 tool call record、`execution.harness.file_change` 事件和节点摘要。实现上不得把完整 stdout/stderr、大文件内容、大目录列表、大搜索结果或大 diff 重新塞进 model-visible tool payload。

Lead-owned `sandbox.run_python` 在同一个 workspace lease 内发现用户可审阅产物：扫描 `/workspace/outputs` 与 `/workspace/reports`，排除 `/workspace/outputs/harness/**` 内部大输出引用和所有 layout guidance 路径（README、manifest、`.gitkeep`），并在 job payload 中返回 `generated_artifacts[]`。候选项字段包括 `schema=wenjin.sandbox.generated_artifact_candidate.v1`、`path`、`root`、`artifact_kind`、`mime_type`、`size`、可选 `content_hash`、`review_surface=sandbox_artifact` 与 `materialization_status=candidate`；若 artifact manifest 里存在同 path 安全条目，discovery 会用 title、description、artifact_kind、source_script、dataset_paths 和 notes 丰富候选项。ReactSubagent harness adapter 会把这些候选项连同 `sandbox_job_id` / `sandbox_environment_id` 投影到 tool call record 和 `execution.harness.tool_call.completed` 事件，前端/运行历史不需要解析 raw tool JSON。普通 LangGraph runtime 与 TeamKernel 都会把可信候选注册为 DataService `workspace_asset(storage_backend=sandbox)` 和 `sandbox_artifact`，由 DataService 自动生成 `target_domain=sandbox,target_kind=sandbox_artifact` 的 review item；用户接受后才 mark materialized。

`sandbox.write_file`、`sandbox.str_replace` 与 `sandbox.apply_patch` 会记录 hash + unified diff 的 `file_change`，并由 ReactSubagent harness adapter 投影到 tool call record、`execution.harness.tool_call.completed` 和专门的 `execution.harness.file_change` 事件。`sandbox.apply_patch` 是结构化多文件 patch 工具，只支持 `replace` 和 `write` edit，会先校验全部 edit、唯一匹配和路径边界，再执行任何 mutation；它返回 `file_changes[]`，供节点聚合多文件净变更。写工具在实际 mutation 前必须同时具备 `filesystem.write` 与 `filesystem.diff`，底层 `SandboxFileTools` 也会执行同一边界校验，不能只依赖上层 policy resolver。小 diff 保留在 `unified_diff`；大 diff 的 `unified_diff` 是 head/tail 预览，完整 diff 写入 `/workspace/outputs/harness/**`，并通过 `diff_output_refs` 保留引用。Lead runtime 与 TeamKernel 会从这些 tool call record 聚合 path/hash 级净文件变更摘要，写入 `ExecutionNodeRecord.node_metadata.harness.file_change_summary`，schema 为 `wenjin.harness.file_change_summary.v1`，摘要中的 compact diff 同样保留大 diff refs。failed / recoverable harness tool calls 也会聚合到 `ExecutionNodeRecord.node_metadata.harness.tool_failure_summary`，schema 为 `wenjin.harness.tool_failure_summary.v1`；`sandbox.run_python` 的 manifest、failure classification 与 generated artifact evidence 还会聚合到 `ExecutionNodeRecord.node_metadata.harness.sandbox_execution_summary`，schema 为 `wenjin.harness.sandbox_execution_summary.v1`，包含 Python run 数、失败数、recoverable failure 数、sandbox job/environment ids、failure codes 和 generated artifact count。`ExecutionNodeRecord.node_metadata.harness.run_journal_summary(schema=wenjin.harness.run_journal_summary.v1)` 是给 RunView/历史恢复读取的产品化成员进度摘要，优先表达工具异常、实验修订、生成产物、文件更新等结论，不要求前端解析 raw tool JSON。每条 `execution.harness.*` event envelope 也可携带 `journal(schema=wenjin.harness.journal_event.v1)`，作为现有 execution event path 上的精简进度条目；不新增 run journal table 或第二套 stream。`python_exit_nonzero`、`sandbox_queue_timeout`、`tool_forbidden` / `tool_unknown` 会进一步生成 `wenjin.harness.replan_signal.v1`，TeamKernel 只把这些信号写入 blackboard 和 `harness_replan_signal` quality gate：用户代码非零退出可触发一次同模板修订，queue timeout 与 forbidden/unknown tool 只给 warning/stop，不通过重复招募绕过权限。citation/source quality gates 还会把 high-risk `citation_key_audit`、`missing_sources`、`fabrication_risks` 与 `bibtex_projection_notes` 规范化为 `wenjin.quality.citation_source_audit_finding.v1`，挂在现有 `QualityGateResult.findings[*].citation_source_audit` 下；该 evidence 只保留 bounded claim/message、当前 workspace 可信 source/citation refs 或 unknown refs、risk/severity 和 suggested action，不引入新表、新 stream 或 raw member-output UI 解析。这些都供 Lead、Run History 和后续 replanning 使用，不需要解析 raw tool JSON，也不是新的 harness run table。

Sandbox 依赖安装由 Lead-owned runtime 负责，不由 subagent 自行拼装系统命令。`sandbox_python` 只传 `dependency_hints`；runtime 在 workspace lease 内确保 Python venv 存在、按受控 pip command 自动安装 hints、遇到 `ModuleNotFoundError` 时最多安装缺失包并重试一次。`sandbox.run_python` 的 `script_name` 在 harness 边界和 runner 内复用同一 sanitizer，最终脚本只能作为安全 `.py` 文件名写入 `/workspace/scripts/{safe_name}`。安装 job 记录为 `operation=install_dependencies` 且 `billable=false`，实际 Python run / smoke check job 保持 billable 并通过 credit reservation 结算。安装网络只通过 `package_index_only` profile 开启，普通运行默认 `none`。每次 harness `sandbox.run_python` 返回都会携带 `execution_manifest(schema=wenjin.harness.run_python.execution_manifest.v1)`，记录 workspace/execution/node/invocation、safe script path、dependency hints、sandbox job/environment、network profile 和 effective timeout；`reproducibility_manifest` 会携带 retry count、已同步 dataset provenance 的 bounded 路径/source/hash 摘要；`experiment_narrative(schema=wenjin.harness.run_python.experiment_narrative.v1)` 会携带 status、script path、dataset/artifact paths、dependency names、command risk 和 next actions，帮助后续成员接续长程实验；`report_markdown` 会追加用户可读的 Experiment narrative 段落。用户代码非零退出会保留 runner payload，不再在 harness tool 层丢失 stdout/stderr/exit_code，并附加 `failure_classification(schema=wenjin.harness.run_python.failure_classification.v1)`、`error_code=python_exit_nonzero` 和 bounded Recovery guidance，供 Lead、Run History 和 replanning 判断。

Agent harness 是 Lead/subagent 的工具执行层，不是新的 agent framework。当前第一版内置 `sandbox.list_dir`、`sandbox.glob`、`sandbox.grep`、`sandbox.read_file`、`sandbox.write_file`、`sandbox.str_replace`、`sandbox.apply_patch`、`sandbox.register_dataset`、`sandbox.register_artifact` 和 `sandbox.run_python`；`sandbox_python` / `sandbox_exec` 在 TeamKernel 与 ReactSubagent 入口 canonicalize 为 `sandbox.run_python`。Capability policy 是最大权限包络，skill/template 只能收窄；未知或禁用工具显式失败，不降级成 plain LLM。文件工具只允许 `/workspace` 下路径，并复用 workspace layout 的 protected/internal path 分类；默认 protected paths 覆盖 `.git/**`、根目录和子目录 `.env` / `.env.*`、`*.pem`、`*.key`、`.wenjin/env/**`、`.wenjin/cache/**` 与 `.wenjin/manifest.json`；读/list/search 工具在实现边界也要求 `filesystem.read`，写工具、`sandbox.apply_patch`、`sandbox.register_dataset` 和 `sandbox.register_artifact` 要求 `filesystem.write` / `filesystem.diff`，不能只依赖上层 registry 过滤；list/search 不返回 protected/internal 路径，直接读写也会拒绝 protected/internal 路径，以及 resolved target 落到 workspace 外、protected 或 internal 的 symlink target；写入会记录 hash + bounded unified diff；大输出与大 diff 通过 `backend/src/agents/harness/output_budget.py` 外部化到 workspace harness outputs。ReactSubagent 的 harness adapter 会把单次工具执行异常降级成 bounded JSON error result，记录 `status=failed` tool call 并发布 `execution.harness.tool_call.failed`，让模型可以继续选择替代工具；TeamKernel 会把 failed / recoverable tool calls 聚合成 `node_metadata.harness.tool_failure_summary`，让上层可以判断局部失败与恢复情况；`sandbox.run_python` 的 manifest 与 failure classification 会投影到 tool record metadata 和 completed event metadata，运行详情不需要解析 raw JSON；LangGraph 控制流信号和 loop guard hard stop 仍保持硬停止。重复相同工具调用达到 warning 阈值时发布 `execution.harness.loop_warning`，visibility 为 `team_visible`，不在 assistant tool call 与 tool result 之间插入任何消息。`backend/src/agents/harness/command_audit.py` 已提供 argv-first command audit 与 `policy_decision(schema=wenjin.harness.command_policy_decision.v1)`；Lead-owned `run_python`、`install_dependencies` 和 smoke check sandbox jobs 在创建 job 前执行 allow/forbid guard，并把 `metadata.command_audit` 写入 DataService sandbox job，其中 harness `sandbox.run_python` 会把 run/install 审计带回 payload、tool record、`execution.harness.tool_call.completed` 和 `execution.harness.command_audit(team_visible)`。通用 `sandbox.run_command` 仍未启用，需完整 DataService command policy、输出预算和事件投影评审后再加。

Agent template seed 也是 harness 合同的一部分，不只是显示名称和 prompt。`backend/src/subagents/v2/registry.py` 维护当前 team tool catalog：业务工具（如 `web_search`、`library_read`、`prism_change_staged`、`artifact_create`）与内置 sandbox 工具共用同一校验入口；`backend/src/services/agent_template_loader.py` 在 seed 写入 DataService 前调用该校验。Seed/admin 模板不得声明未知工具，不得继续使用 `sandbox_python` / `sandbox_exec` 旧别名；实验/图表类成员若请求 `sandbox.run_python`，`risk_profile.code_execution` 必须是 `optional` 或 `required`；模板若请求 `sandbox.write_file` / `sandbox.str_replace` / `sandbox.apply_patch`，`risk_profile.filesystem` 必须是 `sandbox_only`。这些校验只约束模板声明，实际可用工具仍由 capability/workspace/user 三层 policy 收窄，避免成员 prompt 扩张权限。

当前代码边界：

- sandbox provider primitives：`backend/src/sandbox/providers/`
- workspace sandbox filesystem contract：`backend/src/sandbox/workspace_layout.py`
- workspace sandbox manager：`backend/src/agents/lead_agent/v2/workspace_sandbox.py`
- Lead-owned sandbox runtime：`backend/src/agents/lead_agent/v2/sandbox_runtime.py`
- sandbox runtime session / lease：`backend/src/agents/lead_agent/v2/sandbox_runtime_session.py`
- sandbox job orchestration：`backend/src/agents/lead_agent/v2/sandbox_job_runner.py`
- sandbox Python script execution：`backend/src/agents/lead_agent/v2/sandbox_script_executor.py`
- sandbox dataset manifest sync：`backend/src/agents/lead_agent/v2/sandbox_dataset_manifest.py`
- sandbox stdout/stderr budgeting：`backend/src/agents/lead_agent/v2/sandbox_stream_budgeting.py`
- sandbox output shaping：`backend/src/agents/lead_agent/v2/sandbox_artifact_collector.py`
- sandbox artifact discovery：`backend/src/agents/lead_agent/v2/sandbox_artifact_discovery.py`
- sandbox artifact review staging：`backend/src/agents/lead_agent/v2/sandbox_artifact_review.py`
- Lead/subagent harness：`backend/src/agents/harness/`
- command audit contract：`backend/src/agents/harness/command_audit.py`
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
