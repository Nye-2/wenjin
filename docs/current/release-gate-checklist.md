# Release Gate Checklist

更新时间: 2026-06-09

用于发布前 Go/No-Go 决策，覆盖五类 workspace 的核心可用性。

2026-06-09 最新增量验证：Native harness release gate 已进入 core checks；release-gate service/config suite 12 passed；native harness gate command 164 passed，覆盖 harness filesystem、sandbox file tools、command audit、policy/registry、output budget/loop/diff、LangChain adapter、harness context assembly、workspace sandbox metadata、workspace layout、sandbox artifact discovery、citation/source audit、team quality gates、mock sandbox E2E。

最新增量验证：2026-05-30 Model catalog/pricing runtime convergence：backend full pytest 2201 passed；backend ruff `src tests` passed；frontend typecheck/lint/build passed；frontend vitest 242 passed；Browser route-guard smoke passed（`/dashboard/admin/models` -> login redirect preserved）。2026-05-30 Gateway/Worker DataService lifecycle convergence：backend full pytest 2041 passed；gateway/worker/execution-commit/thread-helper target suite 80 passed；architecture boundary suite 41 passed；runtime DB/session scan no matches；changed-file ruff passed。2026-05-30 Audit/Reference contract boundary convergence：backend full pytest 2036 passed；audit/reference target suite 32 passed；architecture boundary suite 38 passed；changed-file ruff passed。2026-05-30 Production source legacy label cleanup：backend full pytest 2034 passed；migration bootstrap/architecture target suite 7 passed；architecture boundary suite 36 passed；production source legacy scan no matches；changed-file ruff passed。2026-05-30 Workspace capability runtime comment convergence：backend full pytest 2033 passed；frontend typecheck passed；runtime comment guard passed；architecture boundary suite 35 passed；changed-file ruff passed。2026-05-30 DataService stale naming cleanup：backend full pytest 2032 passed；source/rooms/architecture target suite 21 passed；architecture boundary suite 34 passed；DataService stale keyword scan no matches；changed-file ruff passed。2026-05-30 Execution generation usage naming convergence：backend full pytest 2031 passed；execution-contract architecture target 1 passed；architecture boundary suite 33 passed；changed-file ruff passed。2026-05-30 Conversation block canonical payload convergence：backend full pytest 2030 passed；conversation/architecture target suite 5 passed；architecture boundary suite 32 passed；changed-file ruff passed。2026-05-30 Source reference projection naming convergence：backend full pytest 2029 passed；source provenance/architecture target suite 17 passed；architecture boundary suite 31 passed；changed-file ruff passed。2026-05-30 Catalog skill canonical skill_json convergence：backend full pytest 2028 passed；catalog/foundation/resolver/admin-skill/architecture target suite 43 passed；architecture boundary suite 30 passed；changed-file ruff passed。2026-05-30 DataService Prism adapter metadata convergence：backend full pytest 2026 passed；Prism adapter/service/router/architecture target suite 15 passed；architecture boundary suite 29 passed；changed-file ruff passed。2026-05-30 frontend feature action explicit-goal convergence：frontend feature action unit 4 passed；frontend typecheck passed。2026-05-30 React requested-tools explicit failure convergence：backend full pytest 2025 passed；React/runtime/compiler/architecture target suite 43 passed；architecture boundary suite 29 passed；changed-file ruff passed。2026-05-30 workspace upload canonical stored path convergence：backend full pytest 2023 passed；upload/template/reference/middleware/preprocess/architecture target suite 28 passed；architecture boundary suite 28 passed；changed-file ruff passed。2026-05-30 feature action explicit-goal convergence：backend full pytest 2021 passed；feature action/activity/architecture target suite 36 passed；architecture boundary suite 27 passed；changed-file ruff passed。2026-05-30 feature launch canonical params convergence：backend full pytest 2020 passed；launch context/tool/chat integration/architecture target suite 18 passed；architecture boundary suite 26 passed；changed-file ruff passed。2026-05-30 execution workspace type no-default convergence：backend full pytest 2019 passed；execution/runtime/architecture target suite 49 passed；architecture boundary suite 25 passed；changed-file ruff passed。

最新验证：2026-05-30 Prism adapter metadata canonical field convergence：backend full pytest 2017 passed；Prism service/workspace Prism/execution/architecture target suite 23 passed；architecture boundary suite 25 passed；changed-file ruff passed。2026-05-30 gateway auth subject DataService boundary convergence：backend full pytest 2016 passed；gateway routers/auth-subject architecture target suite 210 passed；architecture boundary suite 24 passed；changed-file ruff passed。2026-05-30 workspace asset metadata boundary convergence：backend full pytest 2015 passed；document room/activity/architecture target suite 41 passed；architecture boundary suite 23 passed；changed-file ruff passed。2026-05-30 catalog/academic facade DataService boundary convergence：backend full pytest 2014 passed；capability/workspace/generation/router/architecture target suite 45 passed；architecture boundary suite 22 passed；changed-file ruff passed。2026-05-30 legacy helper DataService boundary convergence：backend full pytest 2014 passed；execution/task/upload/skill/architecture target suite 66 passed；architecture boundary suite 21 passed；changed-file ruff passed。2026-05-30 runtime service facade DataService boundary convergence：backend full pytest 2014 passed；thread/template/activity/admin-analytics/gateway/architecture target suite 101 passed；architecture boundary suite 20 passed；changed-file ruff passed。2026-05-30 Reference Library DataService boundary convergence：backend full pytest 2013 passed；reference/bibtex/access-control/architecture target suite 29 passed；architecture boundary suite 19 passed；changed-file ruff passed。2026-05-30 admin catalog DataService boundary convergence：backend full pytest 2012 passed；admin catalog service/loader/seed/integration/architecture target suite 42 passed；architecture boundary suite 18 passed；changed-file ruff passed。2026-05-30 workspace runtime DataService boundary convergence：backend full pytest 2011 passed；workspace route/middleware/Prism route/architecture target suite 46 passed；changed-file ruff passed；`git diff --check` passed。2026-05-30 dashboard runtime DataService boundary convergence：backend full pytest 2009 passed；dashboard/summary/router/architecture target suite 43 passed；changed-file ruff passed；`git diff --check` passed。2026-05-30 memory runtime DataService knowledge boundary convergence：backend full pytest 2008 passed；memory/knowledge/uploads target suite 52 passed；architecture boundary suite 15 passed；changed-file ruff passed；`git diff --check` passed。2026-05-30 thread gateway DataService dependency convergence：backend full pytest 2007 passed；thread/run/upload/artifact/task/architecture target suite 223 passed。2026-05-30 thread run/progress/sse DataService boundary convergence：backend full pytest 2007 passed；task/run/progress/sse target suite 54 passed；task/run/architecture suite 150 passed。2026-05-30 task worker DataService boundary convergence：backend full pytest 2007 passed；task/upload/architecture suite 141 passed；base worker architecture guard passed；`git diff --check` passed。2026-05-30 worker execution DataService boundary convergence：backend full pytest 2007 passed；execution/runtime target suite 59 passed；worker architecture guard passed；`git diff --check` passed。2026-05-30 runtime boundary convergence：backend full pytest 2005 passed；frontend `npm run typecheck` passed；frontend `npm run build` passed；backend Prism/LaTeX/Reference/architecture target suite 88 passed；frontend Prism adapter API unit 5 passed；`git diff --check` passed。2026-05-22 Prism writing review E2E：backend target suite 53 passed（Lead runtime Prism staging、DataService review batch/action log、Prism workflow gate、workspace Prism projection、Runs projection）；frontend Playwright `iteration.spec.ts prism-surface.spec.ts --project=chromium` 5 passed；Docker local-build 重建 gateway / worker / dataservice / bootstrap-admin 后服务 healthy；真实浏览器 smoke 通过：runtime staging -> canonical `review_items` pending -> workspace Prism route -> diff preview -> apply -> `review_summary.pending_count=0/applied_count=1`。workspace execution UX convergence：frontend `npx vitest run` 205 passed；frontend `npm run typecheck` passed；backend target suite 32 passed；`git diff --check` passed；Docker local-build 重建 gateway / worker / frontend 后服务 healthy；Browser smoke 通过：workspace query seed 启动 `sci_literature_positioning` -> chat launch receipt -> LiveWorkflowPanel Current run running -> completed -> Runs drawer 历史记录。Super Agent capability cutover target suite：backend 122 passed；frontend `npm run typecheck` passed；frontend `npx vitest run` 198 passed。DataService / Prism / Conversation cleanup 基线：backend full pytest 1952 passed；frontend typecheck / lint passed；Alembic single head 为 `075_enforce_workspace_owner_membership`。2026-05-20 workspace Prism rollout baseline：frontend unit 200 passed / production build 通过；full Playwright E2E 19 passed, 1 skipped；`docker compose config --quiet` 通过。

## 1. Core Gate (必须全绿)

1. capability 执行主链路可用（提交、轮询、终态可见）。
2. workspace workbench capability 入口可用（入口卡片 / artifact follow-up / activity retry 均能落到 `/workspaces/{workspace_id}?feature=<mission_id>` 并保留 orchestration seed）。
3. Chat structured block action 契约全绿：所有 AgentBlock（`text`、`status_line`、`question_card`、`result_card`）的 action 都在前端白名单中，并有真实处理或显式兜底。
4. Chat block 持久化只保存 canonical `kind`，不得写入旧 kind/type 的 shadow 字段。
5. 文献检索只以 Semantic Scholar `verified_papers` 作为可导入事实来源，`model_synthesis` 和 `unverified_leads` 不进入文献库。
6. 大文件上传预处理状态可见：pending/running 时 Chat 明确提示 Agent 暂不能引用全文，succeeded 后可引用 Markdown 摘要。
7. Prism 写入链路可见：写作任务完成后优先进入 pending review，不能绕过 preview 直接覆盖主稿。
8. Reference Library 写作闭环可回归：Evidence Pack、usage event、`refs.bib` sync、citation validation 保持同一 workspace SSOT。
9. Artifact refresh 闭环可回归：feature 产物持久化后必须发布 `workspace.refresh(["artifacts"])`，前端必须重新拉取 artifact 列表。
10. Artifact follow-up 闭环可回归：任务完成卡片必须显式输出 `open_artifact` 与带 `source_artifact_id/context_artifact_ids` 的 rerun seed，activity retry 必须复用任务结果 artifact。
11. Failure recovery 闭环可回归：失败卡片必须显示明确错误；有 `execution_id` 时才暴露 resume；重试必须保留原始参数和 artifact seed。
12. Prism Review 闭环可回归：主稿待确认写入必须进入 canonical `review_items` / Compute projection / Prism Changes，preview/apply/reject/revert 后状态回流，并产生 workspace activity。
13. Auth Email 闭环可回归：SMTP 开启时注册必须验证 code；验证码只能一次性消费；前端注册页必须先请求验证码并提交 `verification_code`。
14. Capability v2 cutover gate：
  - seed/admin/loader/runtime 只接受 `capability.v2` / `capability_skill.v2`
  - 旧 workflow-step id 不允许作为 seed id 或 runtime launch id
  - Dashboard / workspace summary 由 DataService Catalog + execution history 生成 mission progress
  - Catalog skill projection 必须读取 canonical `skill_json`，不得从旧字段读时合成 skill pack
15. Execution UX convergence gate：
  - Chat stream 必须显示 `launch_feature` 的 `tool_invocation` 与 `tool_result`
  - `tool_result.status == "launched"` 必须驱动 chat run receipt、Current run 焦点、Runs toolbar 提示
  - `tool_result.status == "advisory"` / `code == "missing_params"` 必须只渲染补充上下文提示，不得创建 execution、credit reservation、Current run 或外部搜索
  - LiveWorkflowPanel 与 Runs drawer 必须消费同一 `RunView` 投影，不得各自推导状态
  - `/api/workspaces/{workspace_id}/runs` 必须返回 Prism handoff、failure category、progress 等 RunView 所需字段
  - Browser smoke 必须覆盖 launch -> running -> completed -> Runs drawer，无需手动刷新
16. Prism writing review E2E gate：
  - Writing capability 的 `prism_file_change` output declaration 必须进入 canonical `review_items`，不得进入普通 room `outputs`
  - `research_question_to_paper` 与 `idea_to_thesis_manuscript` 的 writer 输出必须 stage 到 workspace primary Prism project
  - DataService review batch 创建必须先持久化 batch/items，再写 action log，避免 Postgres FK 顺序失败
  - Browser smoke 必须覆盖 pending diff 可见、apply 成功、`review_summary` 回流
17. Runtime boundary convergence gate：
  - Auth dependencies / token helpers / `UserService` 必须只走 Account DataService subject/client，不得重新引入 request-time DB session
  - Artifact runtime surface 必须使用 WorkspaceArtifact / Asset DataService 命名和 client contract，不得恢复 `legacy_artifact` runtime naming
  - Prism manuscript adapter API 必须位于 `/api/prism/latex-adapter/*`；`/api/latex/*` 不得提供兼容层或 redirect
  - Prism adapter routers 和 LaTeX/WorkspacePrism services 不得接受或存储 runtime DB session
  - Worker `execute_execution` 必须通过 Execution/Conversation/Catalog DataService client 完成运行记录、result_card 写回和 capability 解析，不得打开 DB session 或向 `LeadAgentRuntime` 注入 DB session
  - Generic `execute_task` worker 与 gateway TaskService dependency 必须通过 Task/Conversation DataService client 完成任务状态、结果卡片和预处理附件状态写回，不得打开 DB session 或通过 `ThreadService` 变更线程
  - Thread run worker、ProgressTracker stage transition flush、Task SSE initial snapshot 必须使用 DataService client，不得打开 DB session 或 reset DB engine
  - Gateway thread/workspace dependencies and ThreadTurnHandler runtime construction must use DataService-backed services, not request DB sessions
  - Long-term memory runtime、memory compaction、Celery memory capture、workspace-context upload memory note 和 `KnowledgeService` facade 必须使用 Knowledge DataService client，不得打开 DB session、reset DB engine 或保留 `db/self.db/_db`
  - Dashboard runtime dependencies、`DashboardService` 和 `WorkspaceSummaryService` 必须通过 DataService-backed service construction，不得注入 request DB session 或保留 DB fallback execution listing
  - Workspace route/action context 和 WorkspaceContextMiddleware 必须通过 Workspace/Catalog/Template DataService-backed services，不得注入 `get_db` 或自行打开 `get_db_session`
  - Admin capability / skill catalog router、service、validator、loader 必须通过 Catalog DataService client，不得打开 `get_db_session`、注入 request DB session 或保存 `db/self.db`
  - Reference Library router、BibTeX export/validation、Prism `refs.bib` sync 必须通过 Source/Asset/Prism DataService client，不得注入 `get_db`、`AsyncSession`、保存 `self.db` 或导入 DB reference model contract 作为运行时 enum/request schema
  - Execution commit 的 Library materialization 必须通过当前 Source/Prism DataService client 同步 Prism `refs.bib`，不得从 execution service 读取或传递 DB session
  - `AuditService` 必须只暴露 Audit DataService client 边界，不得接受 `session_factory`、ORM model 或 `AsyncSession` 形状的构造参数
  - Gateway / Worker process lifecycle 不得拥有 DB engine lifecycle；Gateway readiness 必须检查 standalone DataService `/readyz`，Worker bootstrap/shutdown 不得调用 `init_db`、`close_db` 或 `reset_db_engine`
  - Runtime helper type hints must use DataService payload contracts, not DB `Thread` / `Workspace` models
  - ThreadService、TemplateService、WorkspaceActivityService、AdminAnalyticsService 和 workspace skill label helpers 不得保留可选 DB constructor、`self.db` 或 session-based workspace type lookup
  - Gateway common deps 不得导出 `get_db`；ExecutionService、TaskStore、SkillResolver、CapabilityResolver、WorkspaceService、GenerationService 不得接受 DB/session constructor 或保存 DB session state
  - Documents room / workspace activity 的 asset projection 不得读取 `legacy_*` metadata 字段；历史字段归一化必须发生在迁移或 DataService 内部
  - Gateway routers 的 auth subject 类型必须使用 `AccountAuthSubject`，不得导入 DB `User` model 作为 `current_user` / admin 注解
  - Prism adapter metadata 必须使用 canonical `source_metadata`；DataService helper 与 runtime surface 均不得暴露 `legacy_metadata`
  - Worker execution 解析 workspace type 必须来自 DataService workspace projection；不得在缺失时默认使用 thesis
  - Feature execution params 必须使用 canonical TaskBrief wrapper；不得保留 plain-param parser 或旧参数兼容入口
  - Artifact follow-up / rerun action state 必须需要显式 mission params 或 source artifact；前后端不得用 workspace description/name、`fallbackTaskName` 或“未命名任务”合成 goal
  - Workspace upload stored path 必须是 workspace-relative path 或 workspace-root 内绝对路径；不得接受 cwd-relative workspace-root-prefixed 历史路径
  - React subagent 请求 tools 但解析不到 callable 时必须显式失败；不得静默降级为普通模型调用
  - Model catalog / pricing / credit reservation runtime 必须通过 DataService client；Gateway/admin UI 不得直连 DB session 或暴露明文 API Key
  - Gateway/worker runtime model cache 必须从 DataService runtime model catalog 刷新；生产路径不得从 `LLM_MODELS` env 自动 fallback
  - Admin model update 必须支持显式清空 `pricing_policy_id` / timeout / retry / headers 等可空字段，同时空 API Key 必须保持原密钥
  - Admin pricing simulator 必须读取当前 enabled `global_credit` / `model_usage` policy；缺失时只允许 UI 默认模板估算，不写回配置
  - Admin dashboard token usage summary 必须遵守 DataService list 上限；全量统计需要 DataService aggregate endpoint，不得在 gateway facade 使用超大 limit 或绕过 DB 边界
18. Native Harness quality gate：
  - `native_harness_quality_gate` 必须进入 release gate core checks，不得只停留在文档或手动约定。
  - 覆盖 harness filesystem / file tools / command audit / policy-registry / output-budget-loop-diff / LangChain adapter / context assembly / workspace sandbox metadata / native harness architecture boundary / DataService sandbox domain / workspace layout / sandbox artifact discovery / citation-source audit / team quality gates / mock sandbox E2E。
  - 发布前至少运行 `cd backend && PYTHONPATH=. uv run pytest tests/agents/harness/test_scheduler_and_python_tool.py tests/agents/harness/test_sandbox_file_tools.py tests/agents/harness/test_command_audit.py tests/agents/harness/test_policy_and_registry.py tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py tests/agents/harness/test_langchain_adapter.py tests/agents/harness/test_context_assembly.py tests/agents/lead_agent/v2/test_workspace_sandbox_manager.py tests/architecture/test_native_harness_boundaries.py tests/dataservice/test_sandbox_domain.py tests/sandbox/test_workspace_layout.py tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py tests/agents/lead_agent/v2/test_citation_source_audit.py tests/agents/lead_agent/v2/test_team_quality_gates.py tests/integration/test_harness_mock_sandbox_e2e.py -q`。
19. 统一门禁命令（发布前需要运行）：
  - `cd backend && uv run python -m src.quality.release_gate_cli`
20. 当前 Core Gate 覆盖:
  - `tests/workspace_features/test_workspace_e2e_matrix.py`
  - `tests/gateway/routers/test_features.py`
  - `tests/application/services/test_feature_submission_service.py`
  - `tests/workspace_features/test_five_workspace_smoke.py`
  - `tests/task/test_executor.py tests/task/test_service_executor.py`
  - `tests/observability/test_sentry.py`
  - `tests/observability/test_prometheus.py`
  - `tests/task/test_agent_status.py`
  - `tests/application/services/test_feature_submission_workspace_lock.py`
  - `tests/task/test_task_metrics.py`
  - `tests/academic/literature/test_search_service.py`
  - `tests/gateway/routers/test_uploads.py tests/task/test_document_preprocess_handler.py`
  - `frontend/tests/unit/lib/thread-store-support.test.ts`
  - `tests/task/test_workspace_feature_handler_matrix.py tests/task/test_store.py::TestTaskStorePostgres::test_mark_task_completed_publishes_canonical_task_activity tests/task/test_workspace_feature_frontend_sync.py`
  - `tests/services/test_artifact_followup_workflow_gate.py tests/agents/lead_agent/test_thread_feature_flow.py tests/services/test_workspace_activity_service.py::test_task_activity_promotes_result_artifact_as_retry_seed`
  - `tests/services/test_failure_recovery_workflow_gate.py tests/agents/lead_agent/test_thread_feature_flow.py tests/task/test_workspace_feature_frontend_sync.py`
  - `tests/services/test_reference_writing_workflow_gate.py`
  - `tests/services/test_prism_review_workflow_gate.py tests/compute/test_projection_service.py`
  - `tests/workspace_features/services/test_sci_feature_service.py`
  - `tests/services/test_auth_email_workflow_gate.py tests/gateway/routers/test_auth.py tests/services/test_email_service.py`
21. 前端静态检查通过:
  - `npm run typecheck`
  - `npm run lint`
  - `npm run build`
22. Execution UX 建议回归:
  - `cd frontend && npx vitest run tests/unit/lib/execution-run-view.test.ts tests/unit/stores/chat-store.test.ts tests/unit/hooks/useWorkspaceEventStream.test.tsx tests/unit/v2/rooms/RunsDrawer.test.tsx tests/unit/v2/ExecutionCard.test.tsx`
  - `cd backend && .venv/bin/python -m pytest tests/application/intents/test_launch_text.py tests/application/services/test_feature_launch_context.py tests/application/handlers/test_thread_turn_handler.py tests/gateway/routers/test_workspace_rooms_router.py::TestRunsRoom::test_list_runs_happy tests/integration/test_chat_to_feature_launch.py tests/tools/test_launch_feature_tool.py -v`
23. Prism writing review 建议回归:
  - `cd backend && .venv/bin/python -m pytest tests/dataservice/test_review_batch_service.py tests/dataservice/test_foundation.py::test_dataservice_client_prism_review_contract_methods tests/agents/lead_agent/v2/test_output_mapping.py tests/agents/lead_agent/v2/test_runtime.py tests/services/test_prism_review_workflow_gate.py tests/services/test_workspace_prism_service.py tests/gateway/routers/test_workspace_rooms_router.py::TestRunsRoom::test_list_runs_happy -v`
  - `cd frontend && npm run test:e2e -- iteration.spec.ts prism-surface.spec.ts --project=chromium`

## 2. Workspace Functional Gate (本轮新增)

用于覆盖 Chat-first Workspace、Compute 工作现场、Prism、上传预处理、Semantic Scholar 文献闭环。

后端建议命令：

```bash
cd backend
uv run ruff check src tests
uv run pytest tests/academic/literature/test_search_service.py tests/tools/test_reference_builtins.py tests/services/test_reference_import_service.py tests/workspace_features/services/test_sci_feature_service.py tests/agents/graphs/sci/test_literature_search.py tests/agents/graphs/thesis/test_deep_research.py tests/agents/graphs/thesis/test_literature_management.py tests/agents/middlewares/test_uploads_middleware.py tests/gateway/routers/test_uploads.py tests/task/test_document_preprocess_handler.py tests/task/test_thread_writeback.py tests/task/test_workspace_feature_runtime.py tests/agents/lead_agent/test_thread_feature_flow.py tests/task/test_workspace_feature_frontend_sync.py
```

前端建议命令：

```bash
cd frontend
npm run typecheck
npm run lint
npm test
```

验收断言：

1. `WorkspaceThreadMessages.tsx` 只有一套 AgentBlock 渲染分支（`text`、`status_line`、`question_card`、`result_card`）。
2. `SUPPORTED_BLOCK_ACTIONS` 覆盖 `trigger_feature`、`continue_thread`、`open_feature`、`rerun_from_artifact`、`open_prism`、`preview_prism_changes`、`open_artifact`、`rerun_feature`、`resume_execution`、`import_references`。
3. 失败态 recovery action 不输出内部 `resume`，只输出官方 action。
4. 文献检索完成态展示 Semantic Scholar verified trust，并明确显示已自动同步到参考库。
5. Reference artifact 导入只读取 `verified_papers` 等已核验候选，不读取 LLM 合成的 `seminal_works/recent_works`。
6. capability 产物持久化后，任务结果带 `refresh_targets=["artifacts"]`，TaskStore 发布 workspace refresh，前端事件流调用 `fetchArtifacts`。
7. 完成态 artifact destination 对应 `open_artifact`，rerun action 和 activity retry 使用 canonical mission capability id，前端 route 保留 `source_artifact_id/context_artifact_ids` 等 seed。
8. 失败态 recovery action 只有在存在 `execution_id` 时输出 `resume_execution`，rerun action 保留失败任务的参数种子。
9. Prism pending change 优先展示 `preview_prism_changes`，并携带 `review_item_id` / `logical_key` 聚焦到 workspace Prism route。
10. 上传附件 pending/running 时 UI 和 prompt 都明确不可引用全文。
11. SMTP enabled 时注册必须验证 6 位邮箱验证码，验证码校验成功后立即失效。
12. Prism source links 可以从 context rail deep-link 回 Library / Documents；protected section 会进入后续 agent manuscript context。

## 3. Extended Gate

1. 工具链/集成测试覆盖:
   - `tests/integration/test_tool_chain.py`
   - `tests/mcp`
   - `tests/integration/test_http_client.py`

## 4. Admin Release Gate API

- Endpoint: `GET /api/dashboard/admin/release-gate?include_extended=true`
- 权限: admin
- 用途: 统一输出发布门禁报告

## 5. Launch Checklist

- [x] 五个 workspace 页面路由可达，无 404
- [x] capability 入口卡片、artifact follow-up、activity retry 均进入 `/workspaces/{workspace_id}?feature=...` 且首条消息保留 seed 上下文
- [x] 空上下文 capability 卡片点击返回 missing_params advisory，不创建 execution、不扣积分、不触发外部检索
- [x] capability 可提交并返回 canonical `execution_id`
- [x] 任务状态可从 pending/running 进入 success 或 failed
- [x] 失败态有明确错误提示且可重试
- [x] artifact 列表可反映最新产出
- [x] 文献检索和 thesis deep research 的 Semantic Scholar 结果会进入参考库，且只导入 `verified_papers`
- [x] 大 PDF 上传后 pending -> preprocess -> ready/failed 状态可见
- [x] 写作结果进入 Prism pending review，apply/reject/revert 后状态可观察
- [x] SMTP 验证码链路（如启用）可稳定工作
- [x] workspace execution UX smoke：启动回执、Current run、完成态、Runs drawer 历史记录可见
- [x] Admin 模型目录 smoke：新增/编辑/禁用/启用/设默认/测试配置可用，列表不暴露明文 API Key
- [x] Admin 定价策略 smoke：global/model usage policy 可编辑，模拟器按当前启用策略估算积分与毛利
- [x] Admin dashboard smoke：首页 overview 可加载，token usage summary 不因 DataService limit 抛错
