# Workspace 功能完善收尾：下一阶段任务书

更新时间：2026-04-30
状态：Implemented seed / 可继续扩展
适用范围：`/home/cjz/wenjin`

本文承接已经完成的 Chat-first Workspace、Compute Agent 工作现场、Prism 状态卡片、大文件异步预处理、Semantic Scholar 单源文献检索等工作，目标不是继续扩张功能面，而是把现有能力串成稳定、可验收、可继续迭代的用户闭环。

## 1. 当前整合基线

已经完成并应视为下一阶段的实现基线：

1. Chat 是用户主操作入口，用户不需要进入 Compute 才能推进任务。
2. Compute 已被重塑为 Agent 工作现场，负责展示执行过程、runtime blocks、artifacts、Prism 相关状态。
3. Thread structured blocks 已拆分为独立组件，支持 `context_brief`、`task_proposal`、`missing_input`、`task_progress`、`task_result`、`task_failure`、`prism_status`、`next_steps`。
4. `WorkspaceProjectStatusStrip` 已抽出，用于展示 workspace 阶段、执行状态、产物数、Prism 待确认/已写入数量。
5. 后端 `thread_feature_cards.py` 已能输出完成态、失败态、缺参态、Prism 状态和下一步动作。
6. 大 PDF 上传已具备 `document_preprocess` 异步任务闭环，pending attachment 不应被 agent 当作已解析全文引用。
7. SCI 文献检索已收敛为 Semantic Scholar-only，不再保留 `papers/top_hits/search_strategy=llm_synthesis` 旧契约。
8. 文献检索新契约为 `verified_papers`、`model_synthesis`、`unverified_leads`、`retrieval`、`source=semantic_scholar`。

下一阶段不要重复实现以上内容。所有新任务应围绕“闭环、验收、清理、跨 feature 一致性”展开。

## 2. 收尾目标

下一阶段的核心目标：

```text
用户在 Chat 里提出目标
  -> 系统给出任务提案或缺失信息
  -> Agent 在 Compute 执行
  -> Chat 显示可理解的过程和结果
  -> 产物进入 Artifact / Literature / Prism 的正确位置
  -> 下一步动作可点击且真的有效
  -> 状态条、Chat blocks、Compute、Prism 对同一事实源保持一致
```

判断标准：

1. 用户不需要理解 feature/task/execution/session 的内部概念。
2. 每个 Chat 卡片按钮都能解释清楚去哪里、做什么、失败时如何恢复。
3. 每个长任务都有 `pending/running/succeeded/failed/recoverable` 的可见状态。
4. 每个写作类产物都有明确去向：只读 artifact、可导入文献、Prism 待确认写入、已写入主稿。
5. 每个证据类产物都有可信边界：已验证、模型综合、未验证线索。

## 3. 下一阶段任务拆分

### Task G：统一 Chat Block Action 契约

问题：

前端已经支持更多 action types，后端也开始输出 `next_steps`，但下一步需要确认所有 action 都是可执行动作，而不是 UI 上看起来可点但没有可靠落点。

目标：

建立 Chat structured block action 的完整契约，保证每个 action type 都有明确的前端处理、后端来源、失败兜底和测试覆盖。

范围：

1. 盘点 `BlockActionType` 与 `thread_feature_cards.py` 输出的所有 action。
2. 明确 action 分类：导航类、任务类、Prism 类、恢复类、补充输入类。
3. 对 `open_prism`、`preview_prism_changes`、`rerun_feature`、`resume_execution` 做端到端验收。
4. 对暂时不能执行的 action，不允许展示为主按钮；应降级为说明或隐藏。
5. 增加前后端 action contract 测试，避免后续新增 block 时出现悬空 action。

建议改动位置：

```text
frontend/app/(workbench)/workspaces/[id]/components/WorkspaceThreadMessages.tsx
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/shared.tsx
backend/src/application/presenters/thread_feature_cards.py
backend/tests/agents/lead_agent/test_thread_feature_flow.py
backend/tests/task/test_workspace_feature_frontend_sync.py
```

验收：

1. 每个 action type 至少有一个前端处理分支或显式不可用策略。
2. `task_result -> open_prism` 能定位到 Prism 面板或相关 workspace route。
3. `task_failure -> rerun/resume` 不会静默失败。
4. 新增 action 时测试失败，直到前端处理和后端输出都更新。

### Task H：文档上传到可引用上下文的闭环

问题：

大文件异步预处理已经有后台任务，但用户视角还需要更清楚地看到“文件是否可被引用”，agent 也需要稳定区分 pending、parsed、failed。

目标：

让上传材料从 attachment 状态进入可引用上下文，形成清晰链路：

```text
upload
  -> attachment pending
  -> document_preprocess running
  -> markdown manifest ready
  -> Chat context 可引用摘要
  -> Literature/Paper/Artifact 可选导入
```

范围：

1. Chat 结果或状态条中明确展示上传文件解析状态。
2. `UploadsMiddleware` 对 pending 文件输出硬约束：不可引用全文，只能说明正在解析。
3. 解析完成后，Chat prompt 能拿到 markdown excerpt 和 manifest 摘要。
4. 解析失败时有 `task_failure` 或 attachment metadata 错误提示。
5. 后续可选：将成功解析的论文与 `Paper`/`WorkspaceLiterature` 做半自动关联。

建议改动位置：

```text
backend/src/agents/middlewares/uploads.py
backend/src/gateway/routers/uploads.py
backend/src/task/handlers/document_preprocess_handler.py
backend/src/services/thread_service.py
frontend/hooks/useWorkspaceEventStream.ts
frontend/stores/thread.ts
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/*
```

验收：

1. 上传大 PDF 后，Chat 明确显示“解析中”，不会假装已读全文。
2. 解析完成后，再次对话可引用 markdown 摘要。
3. 解析失败后，用户能看到失败原因和重新上传/重试建议。
4. 相关 SSE/event store 更新不会导致 attachment metadata 丢失。

### Task I：Semantic Scholar 文献检索到文献库的闭环

问题：

SCI 文献检索已转为 `verified_papers`，但用户下一步需要能把检索结果变成工作区文献资产，而不是只停留在 artifact 里。

目标：

形成：

```text
Semantic Scholar search
  -> verified_papers
  -> task_result 展示可信来源
  -> 用户选择导入
  -> WorkspaceLiterature / Paper 记录
  -> 后续综述、写作、引用可复用
```

范围：

1. `task_result` 对 `verified_papers` 展示 source、external_id、DOI、verified_at、citation count。
2. Reference Library import 只接受 `verified_papers`，不再接受旧 `papers/top_hits`。
3. `WorkspaceReference` 统一保留 `doi/source/citations/venue/abstract/external_ids/verified_at/evidence_level`。
4. 检索产物可以保存在 artifact 中，但文献事实必须通过 Reference Library 导入后才能被引用或投影到 BibTeX。
5. `model_synthesis` 只作为分析，不可被当作文献条目导入。

建议改动位置：

```text
backend/src/academic/literature/search_service.py
backend/src/workspace_features/services/sci_feature_service.py
backend/src/services/references/service.py
backend/src/application/presenters/thread_feature_cards.py
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/TaskResultBlock.tsx
```

验收：

1. 文献检索结果中不存在旧字段 `papers/top_hits/search_strategy`。
2. 导入文献时只读取 `verified_papers`。
3. Chat/Compute 对检索结果显示“Semantic Scholar verified”，而不是“AI 找到”。
4. 未验证线索只能作为下一轮检索建议，不能进入文献库。

### Task J：Prism 写入确认链路收口

问题：

Prism 状态已经能显示，但写作类 feature 的最终闭环必须是“产物可预览、可应用、可回滚、可编译”，否则用户仍然不知道正式稿在哪里。

目标：

所有写作类产物必须明确进入以下状态之一：

```text
artifact_only
prism_pending_review
prism_applied
prism_reverted
compile_failed
compile_passed
```

范围：

1. `task_result` block 展示写作产物是否产生 Prism change。
2. `prism_status` block 展示 pending/applied/compile 状态。
3. `open_prism` 和 `preview_prism_changes` 必须能定位到相关 change。
4. 写作类 feature 完成后，Chat 的下一步优先推荐 Prism review，而不是继续生成更多草稿。
5. 编译失败时，失败信息应回到 Chat/Compute，形成可恢复动作。

建议改动位置：

```text
backend/src/workspace_features/latex_sync.py
backend/src/application/presenters/thread_feature_cards.py
frontend/components/compute/PrismPanel.tsx
frontend/components/compute/ReviewGatePanel.tsx
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/PrismStatusBlock.tsx
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/TaskResultBlock.tsx
```

验收：

1. 写作任务完成后，用户能从 Chat 进入 Prism 预览。
2. Apply/revert 后状态条和 Chat block 不再显示过期 pending 数。
3. 编译失败能显示失败摘要和下一步修复动作。
4. 不允许绕过 preview 直接写入正式稿。

### Task K：跨 workspace feature 的结果卡片一致性

问题：

SCI 已经开始证据驱动，Chat blocks 也更完整，但 thesis/proposal/patent/software copyright 的结果结构还可能各自为政。

目标：

统一所有 workspace feature 的 Chat 输出语义：

```text
context_brief
missing_input
task_proposal
task_progress
task_result
task_failure
next_steps
```

范围：

1. 每个 workspace type 至少选一个主 feature 做端到端 block 验收。
2. 失败态不能只返回普通文本，必须有 `task_failure`。
3. 缺参态不能只问一句话，必须有 `missing_input` 和可继续动作。
4. 结果态必须有 artifact 去向、下一步动作、可信边界。
5. 对研究类 feature，先区分 evidence、model synthesis、unverified leads；不强行一次性改成完整证据图。

建议改动位置：

```text
backend/src/application/presenters/thread_feature_cards.py
backend/src/workspace_features/services/*_feature_service.py
backend/src/task/workspace_feature_artifacts.py
backend/tests/workspace_features/test_workspace_e2e_matrix.py
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/*
```

验收：

1. 五类 workspace smoke tests 覆盖新 block 输出。
2. 用户在 Chat 中能理解每个任务的完成状态、产物位置和下一步。
3. 不再出现“任务完成但不知道去哪里看结果”的情况。

### Task L：功能发布门禁和回归矩阵

问题：

当前并行开发已经覆盖多个子系统，如果没有收口测试矩阵，后续每次改 feature 都容易破坏 Chat/Compute/Prism/Task 任一环。

目标：

建立功能层面的 release gate，不追求全量慢测，但要覆盖主路径。

建议矩阵：

1. Chat 发起 SCI 文献检索：Semantic Scholar verified result。
2. Chat 发起 SCI 写作：artifact + Prism pending review。
3. 大 PDF 上传：pending -> preprocess -> ready。
4. 任务失败：task_failure block + rerun/resume action。
5. 缺参：missing_input block + 继续补充。
6. Prism apply/revert：状态条和 Prism block 更新。
7. Literature import：只从 `verified_papers` 导入。

建议命令：

```bash
cd backend
uv run ruff check src tests
uv run pytest tests/agents/graphs/sci/test_literature_search.py \
  tests/workspace_features/services/test_sci_feature_service.py \
  tests/task/test_workspace_feature_runtime.py \
  tests/task/test_workspace_feature_frontend_sync.py \
  tests/services/test_literature_service.py \
  tests/gateway/routers/test_uploads.py

cd frontend
npm run typecheck
npm test
npm run lint
```

验收：

1. 形成一条固定的“功能收尾回归命令”。
2. 每个新增 block/action/feature 输出至少有一个后端 contract 测试和一个前端渲染/类型测试。
3. release gate 文档更新到 Current 文档，不只停留在 refactor 计划中。

## 4. 建议执行顺序

优先级按用户闭环风险排序：

1. Task G：先收 action contract，否则 UI block 越多越容易出现假按钮。
2. Task J：再收 Prism 写入确认，否则写作系统没有终稿闭环。
3. Task H：收上传可引用状态，否则 agent 容易误用 pending 文件。
4. Task I：收文献检索到文献库，否则证据驱动检索无法沉淀资产。
5. Task K：推广到其他 workspace type。
6. Task L：最后固化 release gate。

如果只安排一个 agent，建议按 G -> J -> H -> I 顺序做。

如果安排多个 agent，并行方式如下：

1. Agent 1：Task G，独占 thread block action contract。
2. Agent 2：Task J，独占 Prism block、ReviewGate、latex_sync。
3. Agent 3：Task H，独占 uploads/document_preprocess/middleware。
4. Agent 4：Task I，独占 literature search/import/result trust display。

并行约束：

1. 多个 agent 不要同时改 `WorkspaceThreadMessages.tsx`，先由 Task G 定 action contract。
2. 多个 agent 不要同时改 `thread_feature_cards.py`，如果必须改，先约定 block schema。
3. Prism 相关改动不要绕开现有 preview/apply/discard/revert API。
4. 文献检索不重新引入 web search、多源 search 或 LLM 生成论文条目。

## 5. 非目标

下一阶段明确不做：

1. 不重做 workspace 类型选择。
2. 不把 Compute 变成用户必须操作的主入口。
3. 不引入 web search、多源文献检索或 AI 自带 search 作为事实源。
4. 不做完整 AI Scientist 或科研指令库产品化。
5. 不做多人协作和权限复杂化。
6. 不新增大而全的 workflow builder。
7. 不保留旧 `papers/top_hits` 文献检索契约。

## 6. 完成定义

下一阶段完成时，系统应达到：

1. 用户只通过 Chat 就能完成一次调研、写作、预览、写入、修订的主路径。
2. Compute 只承担可观察工作现场，不要求用户进入其中完成关键操作。
3. Prism 是正式稿唯一确认写入位置。
4. 上传材料、文献检索、写作结果都有明确状态和可信边界。
5. 所有 Chat 下一步动作都是真动作，不是假按钮。
6. SCI 文献检索结果全部来自 Semantic Scholar verified metadata，LLM 只做综合分析。
7. 主要路径有 release gate 覆盖，后续改动能及时发现断链。

## 7. 2026-04-30 首轮落地记录

本轮已把 G-L 中最高风险的“闭环断点”落到代码，作为后续继续扩展的实现基线。

已完成：

1. Chat block action 契约集中到 `SUPPORTED_BLOCK_ACTIONS`，新增 `isBlockActionType`，`next_steps` 只从白名单解析 action。
2. 清理 `WorkspaceThreadMessages.tsx` 里的重复旧 `next_steps` 分支，避免同一 block 两套渲染逻辑并存。
3. `task_failure.recovery_actions` 改为官方 action：`resume_execution`、`continue_thread`，不再输出内部 `resume` 字符串。
4. `resume_execution` 前端不再只回到 chat，而是带 `entry=resume`、`execution_session_id` 进入 thread seed，并由 `ThreadPanel` 发送 `intent=resume`。
5. Prism 完成态中，若存在 `pending_file_changes`，`next_steps` 优先显示 `preview_prism_changes`，再显示 `open_prism`。
6. `prism_status` block 将 `url` 写入 data，前端 `open_prism` / `preview_prism_changes` 都可直接带 URL 或 project id 跳转。
7. 上传附件 UI 对 `preprocess.pending/running/succeeded/failed` 显示“是否可引用全文”的明确提示，pending 时说明 Agent 暂不能引用全文。
8. 文献检索完成卡片显示 Semantic Scholar evidence：source、verified count、unverified leads count、retrieval status、verified_at、论文预览。
9. 文献检索结果写入 `reference_import`，后端通过 `ReferenceImportService` 同步到 `/workspaces/{workspace_id}/references` 并刷新参考库。
10. `ReferenceImportService` 只读取 `verified_papers` / `semantic_scholar_results`，忽略 `works/seminal_works/recent_works/unverified_leads/model_synthesis` 等非导入来源。
11. 增加 action contract、Prism pending review、Semantic Scholar import、上传 preprocess、workspace frontend sync 等测试覆盖。

已通过的本轮回归：

```bash
cd backend
uv run ruff check src tests
uv run pytest tests/academic/literature/test_search_service.py tests/tools/test_reference_builtins.py tests/services/test_reference_import_service.py tests/workspace_features/services/test_sci_feature_service.py tests/agents/graphs/sci/test_literature_search.py tests/agents/graphs/thesis/test_deep_research.py tests/agents/middlewares/test_uploads_middleware.py tests/gateway/routers/test_uploads.py tests/task/test_document_preprocess_handler.py tests/task/test_thread_writeback.py tests/task/test_workspace_feature_runtime.py tests/agents/lead_agent/test_thread_feature_flow.py tests/task/test_workspace_feature_frontend_sync.py

cd frontend
npm run typecheck
npm run lint
npm test
```

后续仍可继续推进但不阻塞当前功能收口的事项：

1. 为 `WorkspaceLiterature` 增加 `external_id`、`verified_at`、`evidence_level`、`raw_metadata` 字段需要数据库迁移，当前先保留在 artifact 与 result trust 中。
2. `open_artifact?artifact=...` 目前只把 artifact id 带回 chat route，若要做真正 artifact drawer，需要 WorkspaceInspector 增加 query 驱动定位。
3. Prism apply/revert 后历史 Chat block 的 pending 数属于“当时结果快照”，实时状态以状态条和 Compute Prism panel 为准；若要历史卡片自动刷新，需要 block 与 projection 建立引用式渲染。
