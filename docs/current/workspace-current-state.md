# Workspace 当前状态

更新时间：2026-05-30
状态：Current
适用项目：`wenjin`

本文件是 workspace/thread/capability 执行协作行为的当前事实源。

## 1. 用户入口

1. canonical workspace route：`/workspaces/{workspace_id}`
2. canonical workspace Prism route：`/workspaces/{workspace_id}/prism`
3. capability 入口：通过 chat 面板对话触发，Chat Agent 根据 mission catalog 识别意图后调用 `launch_feature`
4. 旧 `/chat` 语义已收敛到当前 workspace chat / execution 体系，不再作为独立 feature 流程事实源
5. 旧 workspace-owned `/latex/{project_id}` 页面入口已移除；主稿只通过 workspace Prism surface 进入

## 2. 双 Agent 拓扑

1. **Chat Agent**（左面板）：处理对话、意图识别、调度 capability
2. **Lead Agent v2**（右面板）：执行 capability graph，运行 subagent，产出结构化结果
3. 1:1 映射：lead-busy 时阻塞新的 dispatch
4. Chat turn 本身通过 `/api/threads/{thread_id}/runs/stream` 运行；当 Chat Agent 调用 `launch_feature` 时，stream 会显式输出 `tool_invocation` 与 `tool_result`
5. `launch_feature` 的 `tool_result.status == "launched"` 必须包含 canonical `execution_id`，前端据此建立 run receipt 与右侧 Current run 焦点
6. Chat Agent 不注册 sandbox-backed bash/file tools，不持有 sandbox state，也不通过 middleware acquire sandbox；sandbox 只能在右侧 Lead Agent graph 的 subagent 节点里执行

## 3. Capability 数据驱动

1. Capability 定义在 YAML seed 文件（`backend/seed/capabilities/{workspace_type}/`），并由 DataService Catalog 持久化为 SSOT。
2. 当前 capability schema 为 `capability.v2`；旧 workflow-step id 已删除，不提供 alias、fallback 或双读兼容层。
3. Capability Skill 定义在 `backend/seed/skills/`，当前 schema 为 `capability_skill.v2`；skill 是 worker instruction pack，不是用户入口。
4. 每个 capability 的 `mission` 定义产品目标、主 surface、document role 和允许交付物。
5. 每个 capability 的 `context_policy`、`sandbox_policy`、`review_policy`、`quality_gates` 会进入 Lead Agent v2 `capability_policy`。
6. 每个 capability 的 `graph_template` 定义执行阶段和 subagent task。
7. `OutputMappingResolver` 将 subagent 输出转换为 typed `ResultOutput`；`kind: prism_file_change` 不进入普通 room outputs，而由 Lead runtime stage 到 DB-backed review item。

## 4. User-Facing Workspace Rooms

1. **Library** — 文献条目（library_item outputs commit 到此）
2. **Documents** — 文档（document outputs）
3. **Decisions** — 决策记录（decision outputs）
4. **Memory** — 事实和偏好（memory_fact outputs）；长期记忆读取、提取写入和压缩通过 Knowledge DataService client 完成
5. **Run History** — 执行历史记录
6. **Tasks** — 后续任务（task outputs）
7. **Settings** — 工作区设置

Sandbox 不再是用户可操作 room。Sandbox 是 Lead Agent / subagent 使用的内部执行基座；用户只在 execution/run detail、ResultCard 和 review item 中查看只读计算记录、脚本摘要、日志、产物和 provenance。内部诊断 capability 可以被 Chat Agent 调度，但实际 Docker sandbox 运行必须发生在 LeadAgentRuntime 的 `sandbox_python` subagent。

## 5. Result Card 闭环流程

1. Chat Agent 调用 `launch_feature` → chat stream 输出 `tool_invocation` / `tool_result`
2. `tool_result.status == "launched"` → ChatPanel 渲染启动回执，`run-ui-store` 标记 active run
3. capability 执行完成 → `TaskReport` 含 `outputs[]`
4. SSE `execution.completed` 事件 → 前端 execution-store
5. `useWorkspaceEventStream` 统一拥有 execution 发现和 execution stream 订阅，从 ExecutionRecord 提取 TaskReport → 构造 ResultCardData → chat store
6. ResultCard 在聊天面板渲染：按 kind 分组、checkbox 选取；Prism 写作变更渲染为 DB-backed review item
7. Prism review item 可从 ResultCard / CompletedView / chat block 进入 `/workspaces/{workspace_id}/prism?focus=file_changes&review_item_id=...&logical_key=...`
8. 用户 commit → `POST /api/executions/{id}/commit` → `ExecutionCommitService` 按 kind 路由到对应 room service
9. Prism 写作变更必须先走 Prism apply/reject/revert；接受后才写入稿件文件
10. commit / apply 后通过 canonical `workspace.refresh` 事件刷新 room drawers、workspace activity 和 Prism context

## 5.1 Execution UX 当前收敛

1. `frontend/lib/execution-run-view.ts` 是前端执行展示投影事实源，负责从 `ExecutionRecord`、Runs `RunRecord`、chat `result_card` 派生统一 `RunView`
2. `frontend/stores/run-ui-store.ts` 只保存 UI 焦点：active / focused / highlighted / completed run ids；不拥有执行状态事实
3. LiveWorkflowPanel 会 pin 当前 run：running 时自动展开执行卡，completed 后保持 Current run 摘要
4. Runs toolbar 按钮显示运行中/已完成提示；Runs drawer 合并 live execution store 与 `/api/workspaces/{workspace_id}/runs` 历史记录
5. `/api/workspaces/{workspace_id}/runs` projection 已补齐 `workspace_id`、`thread_id`、`capability_id`、`progress`、`primary_surface`、`review_items_count`、`has_prism_changes`、`failure_category`、`failure_message`
6. Prism tab / result card / Runs drawer 在存在 review items 时显示 pending handoff；Prism review state 仍以 canonical `review_items` 为准
7. 浏览器 smoke 已验证：workspace query seed 启动 `sci_literature_positioning` → chat launch receipt → right panel Current run running → completed → Runs drawer 历史记录，无需手动刷新
8. 浏览器 smoke 已验证：runtime-staged Prism writing review item → `/workspaces/{workspace_id}/prism` pending diff → `应用到 Prism` → `review_summary.pending_count=0/applied_count=1`

## 6. Prism 主稿协作面

1. Prism 是 workspace 的第二主 surface，canonical route 为 `/workspaces/{workspace_id}/prism`
2. `LatexProject.workspace_id + surface_role=primary_manuscript` 是 workspace 与主稿项目的绑定事实
3. LaTeX editor/compile/file-change endpoints 只作为 Prism adapter 暴露在 `/api/prism/latex-adapter/*`；旧 `/api/latex/*` 不提供兼容层、fallback 或 redirect
4. Canonical `review_items` 是文件变更 review 状态事实源；ResultCard、CompletedView、Compute、Prism Changes 共享同一 projection
5. Canonical `provenance_links` 记录稿件变更与 Library / Documents / execution 输出的 provenance
6. Canonical `prism_protected_scopes` 记录用户手动保护的稿件范围，并进入后续 agent launch context
7. `WorkspacePrismService` 对外提供 surface projection：main file、target files、pending/applied review items、source links、protected sections、activity、compile status
8. `TaskBrief.manuscript_context` 只注入 lightweight manuscript projection，不传完整正文、完整 diff 或 PDF
9. `research_question_to_paper` 与 `idea_to_thesis_manuscript` 的 `manuscript_writer` 输出已声明为 `prism_file_change`，runtime 完成后写入 canonical review item。
10. DataService review batch/action log 是 Prism review 的事务边界；batch/items 先 flush，action log 后写入，保证独立 DataService + Postgres 部署下 FK 顺序稳定。
11. Prism adapter routers 和 LaTeX/WorkspacePrism runtime services 通过 DataService client 访问 Latex/Prism/Review/Source facts，不再携带 runtime DB session。
12. Long-term memory runtime、memory compaction、Celery memory capture 与 workspace-context upload memory note 通过 Knowledge DataService client 访问 persistence，不再携带 runtime DB session 或执行 request-time commit/rollback。
13. DashboardService / WorkspaceSummaryService 和 gateway dashboard dependencies 通过 DataService-backed construction 访问 dashboard、summary 和 execution facts，不再携带 runtime DB session。
14. Workspace capability action resolve 和 WorkspaceContextMiddleware 通过 Workspace/Catalog/Template DataService-backed services 访问 workspace/action/template facts，不再注入 `get_db` 或自行打开 `get_db_session`。
15. Admin capability / skill catalog 的 router、service、validator 和 seed loader 通过 Catalog DataService client 访问 persistence，不再携带 runtime DB session；seed/admin/runtime 共用 `capability.v2` / `capability_skill.v2` schema。
16. Reference Library、BibTeX export/validation 和 Prism `refs.bib` sync 通过 Source/Asset/Prism DataService client 访问 persistence，不再在 references router 或 `SourceBibliographyService` 中注入 DB session。
17. Thread、Template、WorkspaceActivity、AdminAnalytics 和 workspace skill label helper 均已收敛为 DataService-backed facade，不再保留可选 DB 构造参数。
18. Gateway common deps 已移除通用 `get_db`；ExecutionService、TaskStore、SkillResolver、CapabilityResolver、WorkspaceService、GenerationService 均不再接受历史 DB/session 构造参数，workspace 运行链路只通过 DataService client 触达持久化。
19. Documents room 和 workspace activity 的 asset projection 只读取 canonical metadata 字段，不再在运行时读取 `legacy_kind`、`legacy_parent_id`、`legacy_version`。
20. Gateway routers 的 `current_user` / admin subject 均以 `AccountAuthSubject` 标注，不再导入 DB `User` model 作为运行时鉴权类型。
21. Prism adapter metadata 对外只暴露 `source_metadata`，不再把历史 project metadata 放进 `legacy_metadata` 字段。
22. Worker execution 解析 workspace type 时只读取 DataService workspace projection；workspace 或 type 缺失会显式失败，不再默认降级为 thesis。
23. Feature execution params 只保留 canonical TaskBrief wrapper；旧 plain-param execution params 解析入口已移除。

## 7. 前端信息架构

1. **Workspace shell**：提供 Workbench / Prism 两个主 surface switch
2. **Workbench 左面板**（Chat）：对话与结果卡片入口
3. **Workbench 右面板**（Execution / Compute）：Current run、execution graph、node 详情、room drawers、Compute Stage
4. **Prism surface**：LaTeX editor、compile/PDF、Changes review、workspace context rail
5. Room drawers（顶部 toolbar）：Library / Documents / Tasks / Runs 等；Runs drawer 是执行历史与审计面，不是第二套运行状态源
6. Settings page：Memory / Decisions / Settings 管理；Sandbox 不在 Settings 或顶栏 room 中暴露为用户操作台

### 7.1 全站 UIUX 收敛原则

1. Workbench、Prism、rooms、admin、settings 统一遵守“自动适配 + 信息分层”原则。
2. 页面应根据 viewport、当前 run、完成态和选中项自动调整展示面；不得要求用户理解或手动恢复内部 focus/lock 状态。
3. 窄区域默认 list-first；点击条目后进入详情面或 fullscreen split view。宽屏才并列展示列表与详情。
4. 二级导航、筛选和次级操作应轻量化：icon-only + tooltip、compact segmented controls、pills 优先，避免重复文字按钮和大卡片堆叠。
5. 列表中的长标题、作者、文件名、URL 和 run 名必须截断；完整内容只在详情区展示。

## 8. 线程模型

1. single-thread-per-workspace 的主体验模型
2. thread 仍是服务端持久化单元，用于恢复和历史
3. assistant thread message 的 `metadata.orchestration.execution_id` 会持久化，用于 result card 归属与刷新后恢复

## 9. 文档优先级

1. 当前行为以本文件、`workspace-feature-catalog.md`、`docs/current/architecture.md` 为准。
2. 历史方案和阶段性过渡文档已清理；追溯请查看 Git 历史。
3. WenjinPrism 划词改写采用 `preview -> apply -> revert`：
   - `preview` 只生成候选和 diff，不写文件。
   - `apply` 在后端执行签名/哈希校验、结构门禁和编译门禁，通过后写文件。
   - `revert` 使用 `apply` 返回的撤销 payload 做一次性回滚。
4. 结构性风险由后端强约束兜底；前端 risk/diff 主要用于语义判断与人工审阅，不承担安全职责。
5. 写作类 feature 对已有 Prism 文件不直接覆盖，生成内容进入 `file_changes`：
   - `file-changes/preview` 生成 diff 和签名。
   - `file-changes/apply` 必须携带 preview 签名。
   - `file-changes/discard` 丢弃待确认写入。
   - `file-changes/revert` 使用 `applied_file_changes` 中的签名和文件 hash 撤回。
6. Workbench ResultCard、CompletedView、chat result block 和 Prism Changes 共享 `WorkspacePrismReviewItem` / `PrismReviewList`。
7. Prism apply / reject / revert / protect 会写入 canonical review state、protected scope 或 workspace activity，不走 frontend-only 状态。
8. 当前 UX 约定：
   - 支持候选切换、inline/side-by-side、hunk 折叠、空白改动过滤、重生成、复制候选。
   - 支持快捷键：`Ctrl/Cmd + Enter` 应用候选，`Esc` 取消预览。
