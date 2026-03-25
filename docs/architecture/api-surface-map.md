# API Surface Map

Generated: 2026-03-20
Source of truth: `backend/src/gateway/app.py` + routers under `backend/src/gateway/routers/` + `backend/src/api/subagents.py`

## Global Endpoints

| Method | Path | Status | Notes |
|---|---|---|---|
| GET | `/health` | Active | Gateway health check |

## Active Route Groups

| Group | Prefix / Core Paths | Auth | Notes |
|---|---|---|---|
| Auth | `/api/auth/*` | Mixed | 注册、登录、刷新 token、邮箱验证码、当前用户 |
| Models | `/api/models*` | Bearer | 前端可选模型列表与详情 |
| Chat | `/api/threads*`, `/api/chat*` | Bearer | 会话管理、会话级 skill 选择、流式聊天 |
| Subagents | `/api/subagents*` | Bearer | 子代理任务创建、状态、取消、SSE 事件 |
| Workspaces | `/api/workspaces*` | Bearer | workspace CRUD、workspace 论文关联、workspace dashboard |
| Features | `/api/workspaces/{workspace_id}/features*` | Bearer | 动态 feature 列表 + feature 执行 |
| Literature | `/api/workspaces/{workspace_id}/literature*` | Bearer | 文献 CRUD、批量导入、数量统计 |
| Papers | `/api/papers*` | Bearer | 论文 CRUD、提取、检索、章节 |
| Artifacts | `/api/workspaces/{workspace_id}/artifacts*` | Bearer | Canonical workspace-scoped 成果 CRUD、lineage |
| Tasks | `/api/tasks*` | Bearer | 任务状态、SSE 进度、取消；不再提供任务创建入口 |
| Dashboard | `/api/dashboard/*` | Bearer | 用户看板 + 管理员看板/积分/发布门禁 |

## Removed Compatibility Surface

以下兼容入口已从网关移除，不再提供服务：

| Group | Prefix | Status |
|---|---|---|
| Thesis API | `/api/thesis/*` | Removed |
| Academic router (legacy `/academic/papers`) | `/api/*` | Removed |

## Notes for API Consumers

- 新能力只应接入 `/api/workspaces/{workspace_id}/features/{feature_id}/execute`。
- artifact 的读写应统一接入 `/api/workspaces/{workspace_id}/artifacts*`。
- thread skill 属于会话级状态，服务端持久化在 `chat_threads.skill`。
- `POST /api/tasks` 已删除；新任务必须走 feature execute 或 papers extract 等 domain 入口。
- 对长时任务，前端应使用 `/api/tasks/{task_id}` 或 `/api/tasks/{task_id}/stream` 获取进度。
- `/api/chat/stream` 与 `/api/tasks/{task_id}/stream` 均为 SSE，需要反向代理禁用缓冲。
