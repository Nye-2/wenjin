# API Surface Map

Generated: 2026-04-14
Source of truth: `backend/src/gateway/app.py` + routers under `backend/src/gateway/routers/` + `backend/src/api/subagents.py`

## Global Endpoints

| Method | Path | Status | Notes |
|---|---|---|---|
| GET | `/livez` | Active | Gateway liveness check |
| GET | `/readyz` | Active | Gateway readiness check |

## Active Route Groups

| Group | Prefix / Core Paths | Auth | Notes |
|---|---|---|---|
| Auth | `/api/auth/*` | Mixed | 注册、登录、刷新 token、邮箱验证码、当前用户 |
| Models | `/api/models*` | Bearer | 前端可选模型列表与详情 |
| Thread Management | `/api/threads*`, `/api/workspaces/{workspace_id}/thread` | Bearer | 会话管理、会话级 skill 选择 |
| Threads (Platform) | `/api/threads/search`, `/api/threads/{thread_id}/state`, `/api/threads/{thread_id}/history` | Bearer | Platform 风格线程检索、状态快照、历史快照 |
| Runs | `/api/threads/{thread_id}/runs*`, `/api/runs*` | Bearer | Run 生命周期、流式对话（SSE）、断线续流 |
| Subagents | `/api/subagents*` | Bearer | 子代理任务创建、状态、取消、SSE 事件 |
| Workspaces | `/api/workspaces*` | Bearer | workspace CRUD、workspace 论文关联、workspace dashboard |
| Features | `/api/workspaces/{workspace_id}/features*` | Bearer | 动态 feature 列表 + feature 执行 |
| Literature | `/api/workspaces/{workspace_id}/literature*` | Bearer | 文献 CRUD、批量导入、数量统计 |
| Papers | `/api/papers*` | Bearer | 论文 CRUD、提取、检索、章节 |
| Artifacts | `/api/workspaces/{workspace_id}/artifacts*` | Bearer | Canonical workspace-scoped 成果 CRUD、lineage |
| Tasks | `/api/tasks*` | Bearer | 任务状态、SSE 进度、取消；不再提供任务创建入口 |
| Dashboard | `/api/dashboard/*` | Bearer | 用户看板 + 管理员看板/积分/发布门禁 |
| LaTeX | `/api/latex/*` | Bearer | 主稿项目管理、文件读写、编译、PDF/SyncTeX、反馈修订 |

## Removed Compatibility Surface

以下兼容入口已从网关移除，不再提供服务：

| Group | Prefix | Status |
|---|---|---|
| Thesis API | `/api/thesis/*` | Removed |
| Academic router (legacy `/academic/papers`) | `/api/*` | Removed |
| Health alias | `/health` | Removed |

## Notes for API Consumers

- 新能力只应接入 `/api/workspaces/{workspace_id}/features/{feature_id}/execute`。
- artifact 的读写应统一接入 `/api/workspaces/{workspace_id}/artifacts*`。
- thread skill 属于会话级状态，服务端持久化在 `threads.skill`。
- `POST /api/tasks` 已删除；新任务必须走 feature execute 或 papers extract 等 domain 入口。
- 对长时任务，前端应使用 `/api/tasks/{task_id}` 或 `/api/tasks/{task_id}/stream` 获取进度。
- `/api/chat` 与 `/api/chat/stream` 已删除，chat 统一走 runs API（`/api/threads/{thread_id}/runs/stream`、`/api/runs/stream`、`/api/runs/wait`）。
- `/api/threads/{thread_id}/runs/stream`、`/api/runs/stream`、`/api/runs/{run_id}/stream` 与 `/api/tasks/{task_id}/stream` 均为 SSE，需要反向代理禁用缓冲。

## LaTeX Rewrite API (Current)

WenjinPrism 划词改写当前采用 `preview -> apply -> revert` 三段式：

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/latex/projects/{project_id}/feedback/rewrite/preview` | 生成候选改写 + 结构化 diff |
| POST | `/api/latex/projects/{project_id}/feedback/rewrite/apply` | 应用候选（签名/哈希校验 + 结构门禁 + 编译门禁） |
| POST | `/api/latex/projects/{project_id}/feedback/rewrite/revert` | 撤销最近一次改写（签名 + 文件哈希校验） |

关键约束：

- `apply` 必须携带 `candidate_signature`、`base_file_hash`、`base_range_hash`。
- `apply` 若失败并返回 `rewrite_compile_failed`，后端已自动回滚文件内容。
- `revert` 必须使用 `apply` 返回的 `undo` payload，防止越权或错位回滚。
