# API Surface Map

Generated: 2026-05-11
Source of truth: `backend/src/gateway/app.py` + routers under `backend/src/gateway/routers/`

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
| Workspaces | `/api/workspaces*` | Bearer | workspace CRUD、workspace dashboard |
| Compute | `/api/workspaces/{workspace_id}/compute/sessions`, `/api/compute/sessions*` | Bearer | Compute session shell 与 projection 读取面 |
| Features | `/api/workspaces/{workspace_id}/features*` | Bearer | 动态 feature 列表（仅读取，执行走 executions） |
| Executions | `/api/executions*` | Bearer | 统一执行创建、状态查询、流式事件、取消、commit |
| References | `/api/workspaces/{workspace_id}/references*` | Bearer | workspace-scoped Reference Library、上传、Semantic Scholar 导入、page-index、BibTeX/Prism 同步 |
| Artifacts | `/api/workspaces/{workspace_id}/artifacts*` | Bearer | Canonical workspace-scoped 成果 CRUD、lineage |
| Tasks | `/api/tasks*` | Bearer | 任务状态（已移除旧 SSE 入口，任务通过 executions 管理） |
| Dashboard | `/api/dashboard/*` | Bearer | 用户看板 + 管理员看板/积分/发布门禁 |
| LaTeX | `/api/latex/*` | Bearer | 主稿项目管理、文件读写、编译、PDF/SyncTeX、反馈修订 |

## Removed Compatibility Surface

以下兼容入口已从网关移除，不再提供服务：

| Group | Prefix | Status |
|---|---|---|
| Thesis API | `/api/thesis/*` | Removed |
| Academic router (legacy `/academic/papers`) | `/api/*` | Removed |
| Literature/Papers API | `/api/workspaces/{workspace_id}/literature*`, `/api/papers*` | Removed |
| Health alias | `/health` | Removed |
| Public Subagents | `/api/subagents*` | Removed |

## Notes for API Consumers

- Capability 执行统一走 `/api/executions`（创建、查询、流式事件、取消、commit）。
- Capability 结果 commit：`POST /api/executions/{execution_id}/commit`，按 kind 路由到 workspace rooms。
- 旧 Features 执行入口 (`/api/workspaces/{id}/features/{feature_id}/execute`) 和 Tasks SSE (`/api/tasks/{id}/stream`) 已移除。
- Compute 当前状态只从 `/api/compute/sessions/{compute_session_id}/projection` 或 workspace events 水合，不从 thread message 推断。
- artifact 的读写应统一接入 `/api/workspaces/{workspace_id}/artifacts*`。
- `/api/threads/{thread_id}/runs/stream`、`/api/runs/stream`、`/api/runs/{run_id}/stream` 与 `/api/executions/{execution_id}/stream` 均为 SSE，需要反向代理禁用缓冲。

## Compute API (Current)

Compute 是长任务工作台读取面，不提供业务写入口。

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/workspaces/{workspace_id}/compute/sessions` | 列出 workspace 下的 compute sessions |
| GET | `/api/compute/sessions/{compute_session_id}` | 读取单个 compute session shell |
| GET | `/api/compute/sessions/{compute_session_id}/projection` | 读取 execution/task/subagent/runtime/files/logs/Prism 聚合投影 |

关键约束：

- ComputeSession 与 ExecutionSession 一一绑定。
- Compute projection 不持有业务状态，只聚合现有事实源。
- Capability launch 通过 `launch_feature` tool → `ExecutionService` → Celery worker → `LeadAgentRuntime`。

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

## LaTeX File Change API (Current)

WenjinPrism 与写作类 feature 的文件落稿采用 `preview -> apply -> discard/revert`：

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/latex/projects/{project_id}/file-changes/preview` | 生成待确认写入 diff 与 `change_signature` |
| POST | `/api/latex/projects/{project_id}/file-changes/apply` | 使用 preview 签名写入 Prism 文件，并记录 undo payload |
| POST | `/api/latex/projects/{project_id}/file-changes/discard` | 丢弃待确认写入 |
| POST | `/api/latex/projects/{project_id}/file-changes/revert` | 使用 apply 后的 `revert_signature` 和当前文件 hash 撤回写入 |

关键约束：

- feature 生成内容不得直接覆盖已有 Prism 文件。
- `apply` 必须携带 preview 产生的签名。
- `revert` 必须使用 `applied_file_changes` 中记录的签名，并校验当前文件 hash。
