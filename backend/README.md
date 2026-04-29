# 问津 Wenjin Backend

更新时间：2026-04-29

后端当前采用 Compute-centered 分层执行架构：

`gateway -> ChatTurnRouter / FeatureIngressService -> ExecutionSession + ComputeSession -> task runtime -> workspace feature graphs/services -> persistence/writeback`

thread（路由仍为 `/chat`）是用户入口；显式 feature launch/resume 不进入 lead-agent tool loop，而是通过 `FeatureCommandHandler` 直接进入 `FeatureIngressService`。Compute projection 是长任务工作台读取面，不成为第二套业务事实源。

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
- chat 主链路：线程、流式 SSE、skill 选择、显式 feature command routing
- workspace feature 执行：五类 workspace、23 个 canonical features
- Compute：compute sessions、projection、runtime/files/logs/review gate/Prism 聚合
- subagent runtime：execution-bound spawn、状态、事件、持久化回写
- LaTeX 主稿台：文件读写、编译、反馈改写、file-change preview/apply/revert、PDF/SyncTeX
- observability：Prometheus 指标、Sentry/日志钩子、相关健康检查
- 模型路由：统一从 `backend/.env` 的 `LLM_*_MODELS` 加载并按类别路由，不在业务代码硬编码模型 ID

## 目录结构

```text
backend/
├── src/
│   ├── gateway/                 # FastAPI app, routers, middleware, serializers
│   ├── application/            # Application handlers (chat turn/router, feature command/execution, etc.)
│   ├── compute/                # Compute sessions and projection service
│   ├── agents/
│   │   ├── lead_agent/         # Chat lead-agent, prompt template, workspace read catalog
│   │   ├── feature_leader/     # Feature runtime facade and graph registry
│   │   ├── graphs/             # Workspace feature graphs by workspace type
│   │   ├── harness/            # AgentHarness contract/provider
│   │   └── middlewares/        # Lead-agent runtime context middlewares
│   ├── workspace_features/     # Feature registry, runtime profiles, service layer, latex sync
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
- chat turn routing：`src/application/handlers/chat_turn_router.py`
- chat feature command adapter：`src/application/handlers/feature_command_handler.py`
- lead-agent：`src/agents/lead_agent/agent.py`
- skills 目录：`src/agents/lead_agent/thread_skill_catalog.py`
- workspace read tools：`src/tools/builtins/workspace.py`

当前 skill 是 chat 层的 feature 入口语义，不再是独立执行框架。真正执行始终走 `FeatureIngressService`；pure chat 不创建 execution session、compute session 或 task record。

### 6. Compute

- 位置：`src/compute/`
- API：`src/gateway/routers/compute.py`
- 角色：execution session 的用户可见工作台 shell 与 projection
- 来源：execution、task、subagent、runtime blocks、sandbox files、logs、artifacts、WenjinPrism metadata
- 约束：Compute 不做业务状态决策，不替代 ExecutionSession

### 7. Subagents

- 位置：`src/subagents/`
- 角色：Compute 内部 worker，而不是单独的 public API 或主执行平面
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
