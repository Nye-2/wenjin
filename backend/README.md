# 问津 Wenjin Backend

更新时间：2026-04-20

后端当前采用分层执行架构：

`gateway -> application handlers -> task runtime -> workspace feature graphs/services -> persistence/writeback`

thread（路由仍为 `/chat`）主链与 feature 主链已经收口到同一套运行时，不再依赖旧 skill 子系统，也不要求独立外部 LangGraph 服务参与生产主流程。

## 技术栈

- Python 3.12
- FastAPI
- Pydantic
- SQLAlchemy 2.x async
- PostgreSQL + pgvector
- Redis
- Celery
- LangGraph / LangChain

## 当前核心能力

- 认证、用户、workspace、paper、artifact、dashboard、LaTeX API
- chat 主链路：线程、流式 SSE、skill 选择、feature orchestration
- workspace feature 执行：五类 workspace、23 个 canonical features
- subagent runtime：spawn、状态、事件、持久化回退
- LaTeX 主稿台：文件读写、编译、反馈改写、PDF/SyncTeX
- observability：Prometheus 指标、Sentry/日志钩子、相关健康检查
- 模型路由：统一从 `backend/.env` 的 `LLM_*_MODELS` 加载并按类别路由，不在业务代码硬编码模型 ID

## 目录结构

```text
backend/
├── src/
│   ├── gateway/                 # FastAPI app, routers, middleware, serializers
│   ├── application/            # Application handlers (chat turn, feature execution, etc.)
│   ├── agents/
│   │   ├── lead_agent/         # Chat lead-agent, prompt template, bridge cards/catalog
│   │   ├── graphs/             # Workspace feature graphs by workspace type
│   │   ├── middlewares/        # Lead-agent runtime context middlewares
│   │   └── workspace_lead_agent.py
│   ├── workspace_features/     # Feature registry, service layer, latex sync
│   ├── task/                   # Task service, worker, progress, runtime blocks
│   ├── subagents/              # Subagent manager, graph factory, prompts, context snapshot
│   ├── services/               # Shared domain services
│   ├── academic/               # Literature / paper / citation services
│   ├── database/               # Models, session, migrations bootstrap hooks
│   └── execution/              # File/code/image/latex execution providers
├── tests/
├── docs/
└── Dockerfile
```

## 架构说明

### 1. Gateway

- 位置：`src/gateway/`
- 负责：
  - API 路由
  - 鉴权依赖注入
  - 请求校验与错误序列化
  - chat / tasks SSE

### 2. Application Layer

- 位置：`src/application/handlers/`
- 负责：
  - workspace owner 校验
  - feature lookup
  - quota / policy / credit 检查
  - thread 与 chat turn orchestration

### 3. Task Runtime

- 位置：`src/task/`
- 负责：
  - 长任务提交与执行
  - 进度、状态、runtime blocks、workspace events
  - artifact/activity writeback

### 4. Feature Execution

- registry：`src/workspace_features/registry.py`
- graphs：`src/agents/graphs/`
- services：`src/workspace_features/services/`

graph 负责 orchestration 与结果整形，service 负责模型调用、payload 规范化与 feature 级业务逻辑。

### 5. Chat / Skills / Features

- chat 入口（runs + threads）：`src/gateway/routers/threads.py`、`src/gateway/routers/thread_runs.py`、`src/gateway/routers/runs.py`
- lead-agent：`src/agents/lead_agent/agent.py`
- skills 目录：`src/agents/lead_agent/thread_skill_catalog.py`
- tool bridge：`src/tools/builtins/workspace.py`

当前 skill 是 chat 层的 feature 入口语义，不再是独立执行框架。真正执行始终走 `run_workspace_feature`。

### 6. Subagents

- 位置：`src/subagents/`
- 角色：workflow worker，而不是单独的主执行平面
- 上下文：通过 context snapshot 注入，而不是复用整套主 agent middleware

## 本地开发

```bash
cd backend
uv sync --extra dev
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn src.gateway.app:app --reload --port 8001
```

worker：

```bash
cd backend
uv run python -m src.task.worker
```

可选调试入口：

```bash
cd backend
make debug-langgraph
```

这只用于调试 lead-agent graph，不是生产主链依赖。

## 测试

```bash
cd backend
uv run pytest
```

常用：

```bash
uv run pytest tests/agents/ -q
uv run pytest tests/gateway/ -q
uv run pytest tests/workspace_features/ -q
uv run pytest tests/subagents/ -q
```

## 参考文档

- `../README.md`
- `../docs/documentation-map.md`
- `../docs/architecture/workspace-execution-pipeline.md`
- `../docs/architecture/api-surface-map.md`
- `docs/README.md`
- `docs/architecture/langgraph-workspace-architecture.md`
- `docs/async-task-system.md`
