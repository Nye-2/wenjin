# 问津 Wenjin Backend

更新时间：2026-06-23

后端是问津科研工作台的 API、执行编排、DataService 与 agent runtime 层。当前主链路是 execution-first：

```text
Gateway thread/run API
  -> chat_agent
  -> launch_feature
  -> ExecutionRecord
  -> Celery worker
  -> ExecutionEngineV2
  -> LeadAgentRuntime / TeamKernel / ReactSubagent
  -> Wenjin Harness / DataService
  -> TaskReport / ReviewItem / Prism writeback
```

Workspace ChatPanel 是用户入口；显式 capability launch/resume 统一进入 `launch_feature`。DataService 是 workspace、catalog、model、pricing、credit、sandbox、source、review 和 execution persistence 的边界。

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
- Chat Agent 主链路：线程、流式 SSE、capability/skill 入口、execution-first orchestration
- Lead Agent / TeamKernel：按 capability 动态招募实名专家，产出 bounded 过程摘要和结果
- Wenjin Harness：sandbox 文件工具、Python 执行、依赖安装、artifact discovery、command audit 和 output refs
- DataService Catalog：capability、skill、agent template、model catalog、pricing、credit policy
- Reference Library：Source/Provenance/Asset canonical 数据域
- Prism：LaTeX 主稿读写、编译、AI 改稿、file-change preview/apply/revert、PDF/SyncTeX
- Observability：Prometheus 指标、Sentry/日志钩子、健康检查

## 关键目录

```text
backend/
├── src/
│   ├── gateway/                 # FastAPI app, routers, middleware, serializers
│   ├── application/             # Thread turn, result presenters, launch context
│   ├── agents/
│   │   ├── chat_agent/          # Chat Agent, block protocol, launch_feature routing
│   │   ├── lead_agent/v2/       # LeadAgentRuntime, TeamKernel, compiler, output mapping
│   │   └── harness/             # Sandbox tools, context assembly, command audit, eval
│   ├── dataservice/             # DataService domains and clients
│   ├── dataservice_app/         # DataService FastAPI app
│   ├── execution/               # ExecutionEngineV2 and runtime adapters
│   ├── sandbox/                 # Workspace layout, providers, policies
│   ├── services/                # Application/domain services
│   ├── subagents/               # Subagent registry and runtime adapters
│   ├── task/                    # Celery app, worker, progress, runtime blocks
│   ├── academic/                # Literature / paper / citation services
│   └── database/                # Models, migrations, bootstrap hooks
├── seed/
│   ├── capabilities/            # Workspace capability seed
│   └── skills/                  # Capability skill seed
├── tests/
├── docs/
└── Dockerfile
```

## Runtime Boundaries

- Production runtime model discovery comes from DataService model catalog cache. `LLM_MODELS` / `LLM_IMAGE_MODELS` are seed/test inputs, not production fallback.
- Capability, skill and agent template definitions are DataService-backed and schema-validated.
- Gateway/worker should not bypass DataService by reaching directly into request DB sessions for catalog, pricing, credit, source or review state.
- Harness tools only operate inside `/workspace` virtual paths and must preserve protected/internal path boundaries.
- Generated content enters review items before writing rooms or Prism unless the current contract explicitly says otherwise.

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

可选 graph 调试：

```bash
cd backend
make debug-langgraph
```

`make debug-langgraph` 只用于调试 lead-agent graph，不是生产主链路依赖。

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
uv run pytest tests/subagents/ -q
uv run pytest tests/dataservice/ -q
```

## 参考文档

- `../README.md`
- `../docs/current/documentation-map.md`
- `../docs/current/architecture.md`
- `../docs/current/workspace-current-state.md`
- `../docs/current/workspace-feature-catalog.md`
- `../docs/current/deployment-runbook.md`
- `docs/async-task-system.md`
