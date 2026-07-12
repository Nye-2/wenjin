# 问津 Wenjin Backend

更新时间：2026-07-12

后端是问津科研工作台的 API、Mission 编排、DataService 与 agent runtime。当前主链路为：

```text
Gateway thread/run API
  -> WorkspaceAgent
  -> MissionRuntime
  -> SubagentRuntime / ToolOrchestrator / SandboxRuntime
  -> StageAcceptance
  -> MissionReviewItem / MissionCommit
  -> MissionView / Workspace Rooms
```

Workspace ChatPanel 是用户入口。普通回答停留在 ChatTurnRun；长任务由 WorkspaceAgent 创建或调整 Mission。DataService 拥有 workspace、Mission、catalog、model、pricing、credit、sandbox、source、review/commit 等数据库事务。

## 技术栈

- Python 3.13
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x async
- PostgreSQL + pgvector
- Redis
- Celery
- LangGraph / LangChain

## 当前核心能力

- 认证、用户、workspace、paper、artifact、dashboard、Prism API
- WorkspaceAgent：线程上下文、流式对话、Mission 启动/steer 与结构化 agent loop
- MissionRuntime：单 active driver、lease fencing、bounded drive slice、恢复与 MissionView
- SubagentRuntime / ToolOrchestrator：隔离 worker、规范工具目录、幂等 operation 与 typed receipts
- Wenjin Harness：Docker sandbox、文件安全、Python 执行、artifact discovery 和可复现收据
- DataService Catalog：MissionPolicy、WorkerSkill、model catalog、pricing 与 credit policy
- Reference Library：Source/Provenance/Asset canonical 数据域
- Prism：LaTeX 主稿读写、编译、AI 改稿、file-change preview/apply/revert、PDF/SyncTeX
- Observability：Prometheus 指标、Sentry/日志钩子、健康检查

## 关键目录

```text
backend/
├── src/
│   ├── gateway/                 # FastAPI app, routers, middleware, serializers
│   ├── application/             # Thread turn application handlers
│   ├── agents/
│   │   ├── workspace_agent/     # Unified conversation and Mission agent loop
│   │   └── harness/             # Stage acceptance and research evaluation
│   ├── mission_runtime/         # Mission lifecycle, drive slices and projections
│   ├── subagent_runtime/        # Isolated worker runtime
│   ├── tools/orchestrator/      # Canonical tools, leases, receipts and failures
│   ├── review_commit_runtime/   # Item review and idempotent materialization
│   ├── dataservice/             # DataService domains and clients
│   ├── dataservice_app/         # DataService FastAPI app
│   ├── sandbox/                 # Docker-only operations and security policies
│   ├── services/                # Application/domain services
│   ├── task/                    # Celery workers and Mission delivery
│   ├── academic/                # Literature / paper / citation services
│   └── database/                # Models, migrations, bootstrap hooks
├── seed/
│   ├── mission_policies/        # Workspace policy and stage contracts
│   └── skills/                  # WorkerSkill guidance
├── tests/
├── docs/
└── Dockerfile
```

## Runtime Boundaries

- Production runtime model discovery comes from DataService model catalog cache. `LLM_MODELS` / `LLM_IMAGE_MODELS` are seed/test inputs, not production fallback.
- MissionPolicy and WorkerSkill definitions are DataService-backed, content-addressed and schema-validated.
- Gateway/worker should not bypass DataService by reaching directly into request DB sessions for catalog, pricing, credit, source or review state.
- Harness tools only operate inside `/workspace` virtual paths and must preserve protected/internal path boundaries.
- Protected content enters MissionReviewItem before writing rooms or Prism.

## 本地调试

标准运行方式见仓库根目录 `README.md` 和 `docs/current/deployment-runbook.md`，项目主启动只保留 Docker Compose。

单独调试后端服务：

```bash
cd ..
cp .env.example .env
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn src.gateway.app:app --reload --port 8001
```

worker：

```bash
cd backend
uv run python -m src.task.worker
```

## 测试

```bash
cd backend
uv run pytest
uv run ruff check src tests
```

常用 focused suites：

```bash
uv run pytest tests/agents/ -q
uv run pytest tests/gateway/ -q
uv run pytest tests/subagent_runtime/ -q
uv run pytest tests/dataservice/ -q
```

## 参考文档

- `../README.md`
- `../docs/current/documentation-map.md`
- `../docs/current/architecture.md`
- `../docs/current/workspace-current-state.md`
- `../docs/current/workspace-mission-catalog.md`
- `../docs/current/deployment-runbook.md`
- `docs/async-task-system.md`
