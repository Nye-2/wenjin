# 问津 Wenjin

问津是一个面向学术研究与写作交付的 AI 工作台，核心场景覆盖论文、学位论文、申报书、专利与软著材料。项目当前已经收口到一条明确主链路：

`chat -> run_workspace_feature -> FeatureExecutionHandler -> task/worker -> workspace feature graph/service -> artifact/activity/task writeback`

## 当前产品形态

- 五类 workspace：`thesis`、`sci`、`proposal`、`software_copyright`、`patent`
- 单 workspace 主对话：chat 是统一入口，skills 作为 feature 的会话级入口语义
- 确定性 feature 执行：`run_workspace_feature` 是 chat 到 feature 的唯一执行入口
- 任务与结果闭环：`task`、`artifact`、`activity`、runtime blocks、SSE 事件统一回写
- LaTeX 主稿台：项目文件树、编译、PDF 预览、点评改写、SyncTeX 联动
- Subagents：作为 workflow/worker 能力存在，由 feature 或 lead-agent 在需要时调用

## 架构概览

### Frontend

- Next.js App Router
- React 19
- TypeScript
- Tailwind CSS
- Zustand

职责：

- workspace 工作台 UI
- chat / feature / activity / knowledge 面板
- 任务轮询与 SSE 消费
- LaTeX 主稿台与文档交互

### Backend Gateway

- FastAPI
- Pydantic
- SQLAlchemy async

职责：

- API 入口与鉴权
- 请求校验与错误处理
- chat / feature / artifact / paper / latex / dashboard 路由

### Execution Runtime

- LangGraph（进程内图执行，不依赖独立外部 LangGraph 服务）
- Celery worker
- Redis

职责：

- chat lead-agent 运行
- workspace feature graph 调度
- 长任务执行、进度、状态与事件发布
- subagent 运行与持久化

### Storage and Infra

- PostgreSQL + pgvector
- Redis
- Nginx
- Prometheus + Grafana

## 关键模块

- `backend/src/gateway/`：FastAPI 网关、SSE、middleware、routers
- `backend/src/application/`：应用层 handler，例如 chat turn 与 feature execution
- `backend/src/agents/lead_agent/`：主 chat agent、tool 编排、skill prompt、feature bridge 卡片
- `backend/src/agents/graphs/`：按 workspace type 组织的 feature graphs
- `backend/src/workspace_features/`：feature registry、service 层、LaTeX sync
- `backend/src/task/`：任务提交、worker、progress、runtime blocks、artifact writeback
- `backend/src/subagents/`：subagent manager、task tool、context snapshot、academic subagent registry
- `frontend/app/(workbench)/workspaces/[id]/`：workbench 主界面与各面板
- `frontend/stores/`：chat/workspace 等前端状态管理

## Prompt Strategy

当前 prompt 体系分三层：

1. lead-agent prompt：处理 chat 主对话、skill 选择、feature 触发策略
2. feature/service prompts：面向结构化生成，统一走 JSON-only helper 约束
3. subagent prompts：面向特定 worker 角色，依赖 context snapshot 获取裁剪后的上下文

Prompt 优化原则：

- 只使用已知上下文，不编造论文、专利号、实验结果或引用
- 优先生成可直接执行或可直接落稿的内容
- 区分已知事实、合理推断与待补充信息
- 对结构化生成统一约束 schema、输出语言与缺失字段处理

## 快速开始

### Docker Compose

```bash
git clone git@github.com:JunzeCai/AcademiaGPT-V2.git
cd AcademiaGPT-V2
cp backend/.env.example backend/.env

cat > .env <<EOF
WENJIN_PROJECT_DIR=$PWD
ADMIN_PASSWORD=change-this-admin-password
GRAFANA_PASSWORD=change-this-grafana-password
EOF

docker compose up -d --build
```

默认入口：

- Frontend: `http://localhost:3000`
- Nginx: `http://localhost:2026`
- Grafana: `http://localhost:3001`

### 本地开发

```bash
# backend
cd backend
uv sync --extra dev
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn src.gateway.app:app --reload --port 8001

# worker（新终端）
cd backend
uv run python -m src.task.worker

# frontend（新终端）
cd frontend
npm install
npm run dev
```

如需单独调试 lead-agent graph，可选：

```bash
cd backend
make debug-langgraph
```

这不是主链路运行依赖。

## 文档入口

- 总览：`docs/README.md`
- 架构：`docs/architecture/README.md`
- 产品契约：`docs/product/README.md`
- 基础设施：`docs/infrastructure/README.md`
- 后端专项：`backend/docs/README.md`
- 前端专项：`frontend/README.md`

## 文档治理

- 只保留“当前事实源”文档，历史方案与兼容迁移说明已清理
- 架构、接口、运行方式变化后，必须同步更新 README 和对应 docs
- 实现与文档冲突时，以实现为准，并立即回补文档
