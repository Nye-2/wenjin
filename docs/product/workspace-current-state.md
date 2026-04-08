# Workspace 当前状态

更新时间: 2026-04-03
状态: Current
适用项目: `wenjin`

本文件是 workspace/chat 相关产品行为的当前事实源。

## 1. 路由与入口

1. Chat canonical route: `/workspaces/{workspace_id}/chat`
2. Feature 入口: `/workspaces/{workspace_id}/chat?feature={feature_id}[&skill={skill_id}...]`
3. Onboarding 入口: `/workspaces/{workspace_id}/chat?onboarding=true`
4. 旧路由 `/chat/new`、`/chat/[threadId]` 不再作为用户主入口。

## 2. 线程模型

1. 用户侧采用 single-thread-per-workspace 体验模型。
2. `thread` 仍保留在数据层与服务层，用于持久化与恢复。
3. 前端不再暴露 thread list 作为主导航。

## 3. Chat 信息架构

1. 顶部为一行状态条（阶段、skill、产出、下一步建议）。
2. 长任务运行态主展示位于右侧 `Inspector`，不在 chat 顶部堆叠大面板。
3. 对话输入区保留 `AgentStatusBar` 用于轻量执行状态反馈。

## 4. Feature 编排契约

1. 首条编排消息通过 `metadata.orchestration.feature_id + params` 传递。
2. feature 卡片、artifact follow-up、activity retry 均应落到 `/chat` 并保留 orchestration seed。
3. 任务执行统一走 canonical feature pipeline（`/features/{feature_id}/execute`）。

## 5. 文档优先级

1. 当前行为以本文件 + `frontend-feature-plugin-contract.md` + `release-gate-checklist.md` 为准。
2. `workspace-chat-centered-redesign.md` 与 `workspace-chat-centered-implementation-plan.md` 为历史方案/实施文档，供追溯，不作为当前事实源。
