# 问津 Wenjin

更新时间：2026-04-29

问津是一个面向学术研究与写作交付的 AI 工作台，核心场景覆盖论文、学位论文、申报书、专利与软著材料。项目当前收口到 execution-first 主链路：

`workspace chat intent -> launch_feature tool -> ExecutionRecord + ComputeSession -> Celery execute_execution -> ExecutionEngineV2 -> LeadAgentRuntime -> TaskReport / artifact / WenjinPrism writeback -> Compute projection`

## 当前产品形态

- 五类 workspace：`thesis`、`sci`、`proposal`、`software_copyright`、`patent`
- 单 workspace 主对话：chat 是统一入口，skills 作为 capability 的会话级入口语义
- Compute 工作面：长任务过程、runtime blocks、sandbox 文件、日志、Review Gate 和 WenjinPrism 写入状态统一展示
- 确定性 capability 执行：显式 launch/resume 由 workspace ChatPanel 的 thread orchestration 进入 `launch_feature`
- 任务与结果闭环：`task`、`artifact`、`activity`、runtime blocks、SSE 事件统一回写
- LaTeX 主稿台：项目文件树、编译、PDF 预览、点评改写、SyncTeX 联动、file-change preview/apply/revert
- Subagents：作为 Compute 内部 worker 能力存在，由 feature runtime / AgentHarness 调用

## 架构概览

### Frontend

- Next.js App Router
- React 19
- TypeScript
- Tailwind CSS
- Zustand

职责：

- workspace 工作台 UI
- chat / compute / feature / activity / knowledge 面板
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
- capability graph 调度
- Compute projection 聚合
- 长任务执行、进度、状态与事件发布
- subagent 运行与持久化

### Storage and Infra

- PostgreSQL + pgvector
- Redis
- Nginx
- Prometheus + Grafana

## 关键模块

- `backend/src/gateway/`：FastAPI 网关、SSE、middleware、routers
- `backend/src/application/`：应用层 handler，例如 thread turn、result card presenter、workspace seed 解析
- `backend/src/compute/`：ComputeSession 与 projection
- `backend/src/agents/lead_agent/`：主 chat agent、workspace read tools、skill prompt
- `backend/src/agents/harness/`：AgentHarness contract/provider
- `backend/src/tools/builtins/launch_feature.py`：capability launch tool，创建/复用 ExecutionRecord 并分发任务
- `backend/src/execution/engine.py`：ExecutionEngineV2，统一执行 LeadAgentRuntime
- `backend/seed/capabilities/` + `backend/src/services/capability_resolver.py`：capability schema 与解析
- `backend/seed/skills/` + `backend/src/database/models/capability_skill.py`：capability skills
- `backend/src/task/`：任务提交、worker、progress、runtime blocks、artifact writeback
- `backend/src/subagents/`：subagent manager、context snapshot、academic subagent registry
- `frontend/app/(workbench)/workspaces/[id]/`：workbench 主界面与各面板
- `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`：右侧 execution / compute 工作面
- `frontend/stores/`：chat/compute/latex/workspace 等前端状态管理

## Prompt Strategy

当前 prompt 体系分三层：

1. lead-agent prompt：处理 pure chat、workspace read、建议与收口
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
BACKEND_GATEWAY_IMAGE=junze0514/wenjin-backend:latest
LANGGRAPH_IMAGE=junze0514/wenjin-langgraph:latest
FRONTEND_IMAGE=junze0514/wenjin-frontend:latest
TEXLIVE_IMAGE_NAME=junze0514/wenjin-texlive:2024
DOCKER_GID=0
ADMIN_PASSWORD=change-this-admin-password
GRAFANA_PASSWORD=change-this-grafana-password
EOF

docker compose up -d
```

默认 Compose 使用预构建镜像，不依赖本机构建 Node/Python base image。需要本地重建应用镜像时显式加 local-build override：

```bash
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build
```

默认入口：

- Frontend: `http://localhost:3000`
- Nginx: `http://localhost:2026`
- Grafana: `http://localhost:3001`

### 本地开发

```bash
# （可选）交互式初始化与健康检查
python scripts/setup_wizard.py
python scripts/doctor.py

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

- 全量导航：`docs/current/documentation-map.md`
- 总览：`docs/README.md`
- 架构：`docs/current/architecture.md`
- 工作台当前状态：`docs/current/workspace-current-state.md`
- 产品契约：`docs/current/frontend-feature-plugin-contract.md`
- 文献中心：`docs/current/workspace-reference-library.md`
- 长期方向种子：`docs/current/strategy-seed.md`
- 基础设施：`docs/current/troubleshooting.md`
- 后端专项：`backend/docs/README.md`
- 前端专项：`frontend/README.md`

## 文档治理

- 只保留“当前事实源”文档，历史方案与阶段性执行稿已清理
- 架构、接口、运行方式变化后，必须同步更新 README 和对应 docs
- 实现与文档冲突时，以实现为准，并立即回补文档
- 提交前建议按 `docs/current/documentation-map.md` 的维护清单做一次最小回归
