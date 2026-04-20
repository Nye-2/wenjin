# Workspace 当前状态

更新时间：2026-04-14
状态：Current
适用项目：`wenjin`

本文件是 workspace/thread/feature 协作行为的当前事实源。

## 1. 用户入口

1. canonical thread route（URL 保持 `/chat`）：`/workspaces/{workspace_id}/chat`
2. feature 入口：`/workspaces/{workspace_id}/chat?feature={feature_id}[&skill={skill_id}...]`
3. onboarding 入口：`/workspaces/{workspace_id}/chat?onboarding=true`
4. 旧路由 `/chat/new`、`/chat/[threadId]` 不再作为主入口

## 2. 线程模型

1. 用户侧维持 single-thread-per-workspace 的主体验模型。
2. `thread` 仍是服务端持久化单元，用于恢复、历史、状态和 skill 绑定。
3. 指定 `thread_id` 时必须命中，不再静默回退到其他线程。

## 3. Skills 与 Features

1. skill 是 thread 对话层的 feature 入口语义，不是独立执行框架。
2. 用户在 chat 中选中的 skill 会绑定当前 turn 的默认 feature / params 倾向。
3. 真正执行时统一走 `run_workspace_feature` -> canonical feature execute pipeline。
4. 入口可多样（chat/tool/panel/automation），但 feature 事务执行统一经过 `FeatureIngressService`。

## 4. Thread 面板信息架构

1. 顶部状态条展示阶段、skill、结果摘要和下一步建议。
2. 长任务主展示位于右侧 panel / inspector，而不是在 thread 消息区顶部堆叠巨型卡片。
3. 输入区保留轻量状态反馈（如 `AgentStatusBar`），不承载最终结果正文。

## 5. Feature 编排契约

1. 首轮编排消息通过 `metadata.orchestration.feature_id + params` 传递 seed。
2. feature 卡片、artifact follow-up、activity retry 都回落到 `/chat`。
3. 所有长任务执行统一走 `/api/workspaces/{workspace_id}/features/{feature_id}/execute`。
4. 缺参时 execution session 状态进入 `awaiting_user_input`，chat 下一轮携带 `metadata.orchestration.execution_session_id` 在同 session 续跑。
5. feature 完成后，UI 通过 `followUpPrompt` 和 activity detail 提供下一轮建议。

## 6. 结果与刷新

1. 任务结果通过 task status、workspace event、activity、artifact 同步到前端。
2. 前端根据 `refresh_targets` 刷新 `artifacts` / `papers` / `workspace`。
3. thread 和 agent status 会通过 chat / subagent 事件流持续更新。
4. 右侧 panel 承载过程态；thread 承载发起、追问与最终总结。

## 7. 文档优先级

1. 当前行为以本文件、`frontend-feature-plugin-contract.md`、`workspace-feature-catalog.md` 为准。
2. 历史方案和阶段性过渡文档已清理；追溯请查看 Git 历史。

## 8. WenjinPrism 协作现状

1. 编译/导出不再作为 workspace feature 暴露给用户；写作类结果统一回落到 WenjinPrism（`/latex`）处理工程操作。
2. 写作类 feature 完成后，前端应优先提供“打开 WenjinPrism”动作，并使用 `latex_project_id` 定位主稿工程。
3. WenjinPrism 划词改写采用 `preview -> apply -> revert`：
   - `preview` 只生成候选和 diff，不写文件。
   - `apply` 在后端执行签名/哈希校验、结构门禁和编译门禁，通过后写文件。
   - `revert` 使用 `apply` 返回的撤销 payload 做一次性回滚。
4. 结构性风险由后端强约束兜底；前端 risk/diff 主要用于语义判断与人工审阅，不承担安全职责。
5. 当前 UX 约定：
   - 支持候选切换、inline/side-by-side、hunk 折叠、空白改动过滤、重生成、复制候选。
   - 支持快捷键：`Ctrl/Cmd + Enter` 应用候选，`Esc` 取消预览。
