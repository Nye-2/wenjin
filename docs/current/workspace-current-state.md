# Workspace 当前状态

更新时间：2026-05-20
状态：Current
适用项目：`wenjin`

本文件是 workspace/thread/capability 执行协作行为的当前事实源。

## 1. 用户入口

1. canonical workspace route：`/workspaces/{workspace_id}`
2. canonical workspace Prism route：`/workspaces/{workspace_id}/prism`
3. capability 入口：通过 chat 面板对话触发，lead-agent 识别意图后调用 `launch_feature`
4. 旧 `/chat` 语义已收敛到当前 workspace chat / execution 体系，不再作为独立 feature 流程事实源
5. 旧 workspace-owned `/latex/{project_id}` 页面入口已移除；主稿只通过 workspace Prism surface 进入

## 2. 双 Agent 拓扑

1. **Chat Agent**（左面板）：处理对话、意图识别、调度 capability
2. **Lead Agent v2**（右面板）：执行 capability graph，运行 subagent，产出结构化结果
3. 1:1 映射：lead-busy 时阻塞新的 dispatch

## 3. Capability 数据驱动

1. Capability 定义在 YAML seed 文件（`backend/seed/capabilities/{workspace_type}/`），DB-backed
2. `CapabilityResolver` 加载并校验 capability，包括 `outputs` 声明
3. 每个 capability 的 `graph_template` 定义执行阶段和任务
4. `LeadAgentRuntime` 解析 graph → `compile_graph` → 执行 subagent nodes → `_collect_outputs`
5. `OutputMappingResolver` 将 subagent 输出转换为 5 种 typed `ResultOutput`（library_item, document, memory_fact, decision, task）

## 4. 8 Workspace Rooms

1. **Library** — 文献条目（library_item outputs commit 到此）
2. **Documents** — 文档（document outputs）
3. **Decisions** — 决策记录（decision outputs）
4. **Memory** — 事实和偏好（memory_fact outputs）
5. **Run History** — 执行历史记录
6. **Sandbox** — 代码执行沙箱
7. **Tasks** — 后续任务（task outputs）
8. **Settings** — 工作区设置

## 5. Result Card 闭环流程

1. capability 执行完成 → `TaskReport` 含 `outputs[]`
2. SSE `execution.completed` 事件 → 前端 execution-store
3. `useWorkspaceEventStream` 统一拥有 execution 发现和 execution stream 订阅，从 ExecutionRecord 提取 TaskReport → 构造 ResultCardData → chat store
4. ResultCard 在聊天面板渲染：按 kind 分组、checkbox 选取；Prism 写作变更渲染为 DB-backed review item
5. Prism review item 可从 ResultCard / CompletedView / chat block 进入 `/workspaces/{workspace_id}/prism?focus=file_changes&review_item_id=...&logical_key=...`
6. 用户 commit → `POST /api/executions/{id}/commit` → `ExecutionCommitService` 按 kind 路由到对应 room service
7. Prism 写作变更必须先走 Prism apply/reject/defer/revert；接受后才写入稿件文件
8. commit / apply 后通过 canonical `workspace.refresh` 事件刷新 room drawers、workspace activity 和 Prism context

## 6. Prism 主稿协作面

1. Prism 是 workspace 的第二主 surface，canonical route 为 `/workspaces/{workspace_id}/prism`
2. `LatexProject.workspace_id + surface_role=primary_manuscript` 是 workspace 与主稿项目的绑定事实
3. `prism_review_items` 是文件变更 review 状态事实源；ResultCard、CompletedView、Compute、Prism Changes 共享同一 projection
4. `prism_source_links` 记录稿件变更与 Library / Documents / execution 输出的 provenance
5. `prism_protected_sections` 记录用户手动保护的稿件范围，并进入后续 agent launch context
6. `WorkspacePrismService` 对外提供 surface projection：main file、target files、pending/applied review items、source links、protected sections、activity、compile status
7. `TaskBrief.manuscript_context` 只注入 lightweight manuscript projection，不传完整正文、完整 diff 或 PDF

## 7. 前端信息架构

1. **Workspace shell**：提供 Workbench / Prism 两个主 surface switch
2. **Workbench 左面板**（Chat）：对话与结果卡片入口
3. **Workbench 右面板**（Execution / Compute）：execution graph、node 详情、room drawers、Compute Stage
4. **Prism surface**：LaTeX editor、compile/PDF、Changes review、workspace context rail
5. Room drawers（顶部 toolbar）：Library / Documents / Tasks / Runs 等
6. Settings page：Memory / Decisions / Sandbox / Settings 管理

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
7. Prism apply / reject / defer / revert / protect 会写入 canonical review state、protected section 或 workspace activity，不走 frontend-only 状态。
8. 当前 UX 约定：
   - 支持候选切换、inline/side-by-side、hunk 折叠、空白改动过滤、重生成、复制候选。
   - 支持快捷键：`Ctrl/Cmd + Enter` 应用候选，`Esc` 取消预览。
