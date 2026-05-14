# Workspace 当前状态

更新时间：2026-05-14
状态：Current
适用项目：`wenjin`

本文件是 workspace/thread/feature 协作行为的当前事实源。

## 1. 用户入口

1. canonical workspace route：`/workspaces/{workspace_id}/v2`
2. feature 入口：通过 chat 面板对话触发，lead-agent 识别意图后调用 `launch_feature`
3. 旧 `/chat` 语义已收敛到当前 workspace chat / execution 体系，不再作为独立 feature 流程事实源

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

1. Capability 执行完成 → `TaskReport` 含 `outputs[]`
2. SSE `execution.completed` 事件 → 前端 execution-store
3. `useWorkspaceEventStream` 统一拥有 execution 发现和 execution stream 订阅，从 ExecutionRecord 提取 TaskReport → 构造 ResultCardData → chat store
4. ResultCard 在聊天面板渲染：按 kind 分组、checkbox 选取
5. 用户 commit → `POST /api/executions/{id}/commit` → `ExecutionCommitService` 按 kind 路由到对应 room service
6. commit 后通过 canonical `workspace.refresh` 事件刷新 room drawers

## 6. 前端信息架构

1. **左面板**（Chat）：对话与结果卡片入口
2. **右面板**（Execution / Compute）：execution graph、node 详情、room drawers、Compute Stage
3. Room drawers（顶部 toolbar）：Library / Documents / Tasks / Runs 等
4. Settings page：Memory / Decisions / Sandbox / Settings 管理

## 7. 线程模型

1. single-thread-per-workspace 的主体验模型
2. thread 仍是服务端持久化单元，用于恢复和历史
3. assistant thread message 的 `metadata.orchestration.execution_id` 会持久化，用于 result card 归属与刷新后恢复

## 8. 文档优先级

1. 当前行为以本文件、`workspace-feature-catalog.md`、`docs/architecture/README.md` 为准。
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
6. ComputeStage 和 WenjinPrism 编辑器都可以处理待确认写入和已应用写入。
7. 当前 UX 约定：
   - 支持候选切换、inline/side-by-side、hunk 折叠、空白改动过滤、重生成、复制候选。
   - 支持快捷键：`Ctrl/Cmd + Enter` 应用候选，`Esc` 取消预览。
