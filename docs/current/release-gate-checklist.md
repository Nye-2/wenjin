# Release Gate Checklist

更新时间: 2026-05-30

用于发布前 Go/No-Go 决策，覆盖五类 workspace 的核心可用性。

最新验证：2026-05-30 worker execution DataService boundary convergence：backend full pytest 2007 passed；execution/runtime target suite 59 passed；worker architecture guard passed；`git diff --check` passed。2026-05-30 runtime boundary convergence：backend full pytest 2005 passed；frontend `npm run typecheck` passed；frontend `npm run build` passed；backend Prism/LaTeX/Reference/architecture target suite 88 passed；frontend Prism adapter API unit 5 passed；`git diff --check` passed。2026-05-22 Prism writing review E2E：backend target suite 53 passed（Lead runtime Prism staging、DataService review batch/action log、Prism workflow gate、workspace Prism projection、Runs projection）；frontend Playwright `iteration.spec.ts prism-surface.spec.ts --project=chromium` 5 passed；Docker local-build 重建 gateway / worker / dataservice / bootstrap-admin 后服务 healthy；真实浏览器 smoke 通过：runtime staging -> canonical `review_items` pending -> workspace Prism route -> diff preview -> apply -> `review_summary.pending_count=0/applied_count=1`。workspace execution UX convergence：frontend `npx vitest run` 205 passed；frontend `npm run typecheck` passed；backend target suite 32 passed；`git diff --check` passed；Docker local-build 重建 gateway / worker / frontend 后服务 healthy；Browser smoke 通过：workspace query seed 启动 `sci_literature_positioning` -> chat launch receipt -> LiveWorkflowPanel Current run running -> completed -> Runs drawer 历史记录。Super Agent capability cutover target suite：backend 122 passed；frontend `npm run typecheck` passed；frontend `npx vitest run` 198 passed。DataService / Prism / Conversation cleanup 基线：backend full pytest 1952 passed；frontend typecheck / lint passed；Alembic single head 为 `075_enforce_workspace_owner_membership`。2026-05-20 workspace Prism rollout baseline：frontend unit 200 passed / production build 通过；full Playwright E2E 19 passed, 1 skipped；`docker compose config --quiet` 通过。

## 1. Core Gate (必须全绿)

1. capability 执行主链路可用（提交、轮询、终态可见）。
2. workspace workbench capability 入口可用（入口卡片 / artifact follow-up / activity retry 均能落到 `/workspaces/{workspace_id}?feature=<mission_id>` 并保留 orchestration seed）。
3. Chat structured block action 契约全绿：所有 AgentBlock（`text`、`status_line`、`question_card`、`result_card`）的 action 都在前端白名单中，并有真实处理或显式兜底。
4. 文献检索只以 Semantic Scholar `verified_papers` 作为可导入事实来源，`model_synthesis` 和 `unverified_leads` 不进入文献库。
5. 大文件上传预处理状态可见：pending/running 时 Chat 明确提示 Agent 暂不能引用全文，succeeded 后可引用 Markdown 摘要。
6. Prism 写入链路可见：写作任务完成后优先进入 pending review，不能绕过 preview 直接覆盖主稿。
7. Reference Library 写作闭环可回归：Evidence Pack、usage event、`refs.bib` sync、citation validation 保持同一 workspace SSOT。
8. Artifact refresh 闭环可回归：feature 产物持久化后必须发布 `workspace.refresh(["artifacts"])`，前端必须重新拉取 artifact 列表。
9. Artifact follow-up 闭环可回归：任务完成卡片必须显式输出 `open_artifact` 与带 `source_artifact_id/context_artifact_ids` 的 rerun seed，activity retry 必须复用任务结果 artifact。
10. Failure recovery 闭环可回归：失败卡片必须显示明确错误；有 `execution_id` 时才暴露 resume；重试必须保留原始参数和 artifact seed。
11. Prism Review 闭环可回归：主稿待确认写入必须进入 canonical `review_items` / Compute projection / Prism Changes，preview/apply/reject/revert 后状态回流，并产生 workspace activity。
12. Auth Email 闭环可回归：SMTP 开启时注册必须验证 code；验证码只能一次性消费；前端注册页必须先请求验证码并提交 `verification_code`。
13. Capability v2 cutover gate：
  - seed/admin/loader/runtime 只接受 `capability.v2` / `capability_skill.v2`
  - 旧 workflow-step id 不允许作为 seed id 或 runtime launch id
  - Dashboard / workspace summary 由 DataService Catalog + execution history 生成 mission progress
14. Execution UX convergence gate：
  - Chat stream 必须显示 `launch_feature` 的 `tool_invocation` 与 `tool_result`
  - `tool_result.status == "launched"` 必须驱动 chat run receipt、Current run 焦点、Runs toolbar 提示
  - LiveWorkflowPanel 与 Runs drawer 必须消费同一 `RunView` 投影，不得各自推导状态
  - `/api/workspaces/{workspace_id}/runs` 必须返回 Prism handoff、failure category、progress 等 RunView 所需字段
  - Browser smoke 必须覆盖 launch -> running -> completed -> Runs drawer，无需手动刷新
15. Prism writing review E2E gate：
  - Writing capability 的 `prism_file_change` output declaration 必须进入 canonical `review_items`，不得进入普通 room `outputs`
  - `research_question_to_paper` 与 `idea_to_thesis_manuscript` 的 writer 输出必须 stage 到 workspace primary Prism project
  - DataService review batch 创建必须先持久化 batch/items，再写 action log，避免 Postgres FK 顺序失败
  - Browser smoke 必须覆盖 pending diff 可见、apply 成功、`review_summary` 回流
16. Runtime boundary convergence gate：
  - Auth dependencies / token helpers / `UserService` 必须只走 Account DataService subject/client，不得重新引入 request-time DB session
  - Artifact runtime surface 必须使用 WorkspaceArtifact / Asset DataService 命名和 client contract，不得恢复 `legacy_artifact` runtime naming
  - Prism manuscript adapter API 必须位于 `/api/prism/latex-adapter/*`；`/api/latex/*` 不得提供兼容层或 redirect
  - Prism adapter routers 和 LaTeX/WorkspacePrism services 不得接受或存储 runtime DB session
  - Worker `execute_execution` 必须通过 Execution/Conversation/Catalog DataService client 完成运行记录、result_card 写回和 capability 解析，不得打开 DB session 或向 `LeadAgentRuntime` 注入 DB session
17. 统一门禁命令（发布前需要运行）：
  - `cd backend && uv run python -m src.quality.release_gate_cli`
18. 当前 Core Gate 覆盖:
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
19. 前端静态检查通过:
  - `npm run typecheck`
  - `npm run lint`
  - `npm run build`
20. Execution UX 建议回归:
  - `cd frontend && npx vitest run tests/unit/lib/execution-run-view.test.ts tests/unit/stores/chat-store.test.ts tests/unit/hooks/useWorkspaceEventStream.test.tsx tests/unit/v2/rooms/RunsDrawer.test.tsx tests/unit/v2/ExecutionCard.test.tsx`
  - `cd backend && .venv/bin/python -m pytest tests/application/handlers/test_thread_turn_handler.py tests/gateway/routers/test_workspace_rooms_router.py::TestRunsRoom::test_list_runs_happy tests/integration/test_chat_to_feature_launch.py tests/tools/test_launch_feature_tool.py -v`
21. Prism writing review 建议回归:
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
- [x] capability 可提交并返回 task_id
- [x] 任务状态可从 pending/running 进入 success 或 failed
- [x] 失败态有明确错误提示且可重试
- [x] artifact 列表可反映最新产出
- [x] 文献检索和 thesis deep research 的 Semantic Scholar 结果会进入参考库，且只导入 `verified_papers`
- [x] 大 PDF 上传后 pending -> preprocess -> ready/failed 状态可见
- [x] 写作结果进入 Prism pending review，apply/reject/revert 后状态可观察
- [x] SMTP 验证码链路（如启用）可稳定工作
- [x] workspace execution UX smoke：启动回执、Current run、完成态、Runs drawer 历史记录可见
