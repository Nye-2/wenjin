# Release Gate Checklist

更新时间: 2026-05-21

用于发布前 Go/No-Go 决策，覆盖五类 workspace 的核心可用性。

最新验证：2026-05-21 DataService / Prism / Conversation cleanup：backend full pytest 1943 passed；ThreadService facade/conversation target tests 30 passed；Workspace Prism adapter boundary target tests 22 passed；task persistence DataService target tests 118 passed；admin audit-log DataService target tests 25 passed；credit/admin-log integration target tests 41 passed；workspace activity thread-summary DataService target tests 26 passed；workspace metadata/dashboard DataService projection target tests 81 passed；gateway workspace helper/serializer target tests 72 passed；artifact payload DataService target tests 56 passed；generation usage DataService target tests 16 passed；Workspace/Artifact/Thread/GenerationRecord/TaskRecord/AdminLog runtime-import architecture guard 5 passed；owner invariant target tests 11 passed；review transaction target tests 14 passed；execution commit DataService target tests 34 passed；execution engine run-history event tests 16 passed；workspace run-history route cutover target tests 28 passed；room direct-DataService route target tests 34 passed；sandbox route cutover target tests 32 passed；library route cutover target tests 44 passed；documents route cutover target tests 34 passed；frontend typecheck / lint passed；Alembic single head 为 `075_enforce_workspace_owner_membership`。2026-05-20 workspace Prism rollout baseline：frontend unit 200 passed / production build 通过；full Playwright E2E 19 passed, 1 skipped；`docker compose config --quiet` 通过。

## 1. Core Gate (必须全绿)

1. capability 执行主链路可用（提交、轮询、终态可见）。
2. workspace workbench capability 入口可用（入口卡片 / artifact follow-up / activity retry 均能落到 `/workspaces/{workspace_id}?feature=...` 并保留 orchestration seed）。
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
13. 统一门禁命令（发布前需要运行）：
  - `cd backend && uv run python -m src.quality.release_gate_cli`
14. 当前 Core Gate 覆盖:
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
15. 前端静态检查通过:
  - `npm run typecheck`
  - `npm run lint`
  - `npm run build`

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
7. 完成态 artifact destination 对应 `open_artifact`，rerun action 和 activity retry 都带 `source_artifact_id/context_artifact_ids`，前端 route 保留这些 seed。
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
