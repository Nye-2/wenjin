# Release Gate Checklist

更新时间: 2026-04-30

用于发布前 Go/No-Go 决策，覆盖五类 workspace 的核心可用性。

## 1. Core Gate (必须全绿)

1. workspace feature 执行主链路可用（提交、轮询、终态可见）。
2. `thread-route(/chat)` feature 入口可用（feature 卡片 / artifact follow-up / activity retry 均能落到 `/chat` 并保留 orchestration seed）。
3. Chat structured block action 契约全绿：所有 `next_steps` action 都在前端白名单中，并有真实处理或显式兜底。
4. 文献检索只以 Semantic Scholar `verified_papers` 作为可导入事实来源，`model_synthesis` 和 `unverified_leads` 不进入文献库。
5. 大文件上传预处理状态可见：pending/running 时 Chat 明确提示 Agent 暂不能引用全文，succeeded 后可引用 Markdown 摘要。
6. Prism 写入链路可见：写作任务完成后优先进入 pending review，不能绕过 preview 直接覆盖主稿。
7. 关键回归通过:
  - `tests/workspace_features/test_workspace_e2e_matrix.py`
  - `tests/gateway/routers/test_features.py`
  - `tests/application/services/test_feature_submission_service.py`
8. 前端静态检查通过:
  - `npx tsc --noEmit`

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

1. `WorkspaceThreadMessages.tsx` 只有一套 `next_steps` 渲染分支。
2. `SUPPORTED_BLOCK_ACTIONS` 覆盖 `trigger_feature`、`continue_thread`、`open_feature`、`rerun_from_artifact`、`open_prism`、`preview_prism_changes`、`open_artifact`、`rerun_feature`、`resume_execution`、`import_references`。
3. 失败态 recovery action 不输出内部 `resume`，只输出官方 action。
4. 文献检索完成态展示 Semantic Scholar verified trust，并明确显示已自动同步到参考库。
5. Reference artifact 导入只读取 `verified_papers` 等已核验候选，不读取 LLM 合成的 `seminal_works/recent_works`。
6. Prism pending change 优先展示 `preview_prism_changes`。
7. 上传附件 pending/running 时 UI 和 prompt 都明确不可引用全文。

## 3. Extended Gate (建议全绿)

1. 工具链/集成测试通过:
   - `tests/integration/test_tool_chain.py`
   - `tests/mcp/test_academic_tools.py`
   - `tests/integration/test_http_client.py`

## 4. Admin Release Gate API

- Endpoint: `GET /api/dashboard/admin/release-gate?include_extended=true`
- 权限: admin
- 用途: 统一输出发布门禁报告

## 5. Launch Checklist

- [ ] 五个 workspace 页面路由可达，无 404
- [ ] feature 卡片、artifact follow-up、activity retry 均进入 `/chat` 且首条消息保留 seed 上下文
- [ ] feature 可提交并返回 task_id
- [ ] 任务状态可从 pending/running 进入 success 或 failed
- [ ] 失败态有明确错误提示且可重试
- [ ] artifact 列表可反映最新产出
- [ ] 文献检索和 thesis deep research 的 Semantic Scholar 结果会进入参考库，且只导入 `verified_papers`
- [ ] 大 PDF 上传后 pending -> preprocess -> ready/failed 状态可见
- [ ] 写作结果进入 Prism pending review，apply/revert 后状态可观察
- [ ] SMTP 验证码链路（如启用）可稳定工作
