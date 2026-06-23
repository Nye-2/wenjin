# 问津 Wenjin

更新时间：2026-06-23

问津是一个面向科研工作的 AI 工作台，服务从选题、文献、实验、写作到成果管理的完整研究流程。它不是通用聊天机器人，也不是单点论文润色工具，而是以 workspace 为核心的科研生产系统：用户在一个研究工作区里沉淀资料、决策、实验、主稿和团队协作记录，AI 研究团队在同一个上下文中持续推进任务。

## 项目定位

问津的目标是把科研任务从“和模型反复聊天”收敛成可执行、可追踪、可审阅的工作流：

- 研究导航：把模糊想法转成研究问题、检索计划、gap 判断和下一步行动
- 文献工作台：围绕主题组织检索、证据、引用、综述矩阵和创新点
- 实验工作台：每个 workspace 绑定一个 sandbox，支持代码、数据、图表和实验产物连续沉淀
- 写作工作台：围绕 LaTeX 主稿进行起草、改写、批注、编译、PDF 对照和版本化修改
- 专家团队：Lead Agent 根据 capability 动态招募实名专家成员，按任务分工产出过程摘要和交付物
- 审阅闭环：AI 产物先进入候选结果，用户通过 review gate 决定是否写入资料库、记忆、文档或主稿

## 核心形态

- 五类科研 workspace：`thesis`、`sci`、`proposal`、`software_copyright`、`patent`
- 左侧 Chat Agent：负责对话、意图识别、需求确认和 capability 启动
- 右侧 Research Workbench：展示专家团队、关键进展、证据预览、候选结果和运行历史
- Wenjin Prism：面向论文主稿的 LaTeX 编辑、编译、PDF 对照和 AI 改稿界面
- Wenjin Harness：为科研 agent 提供 sandbox 文件读写、代码执行、实验产物发现和安全边界
- DataService：统一管理 workspace 数据、capability、专家模板、模型目录、积分和 review item
- Admin Console：管理模型、定价、积分、capability 与系统运行配置

## 架构概览

主链路已经收敛为 execution-first：

```text
Workspace Chat
  -> Chat Agent
  -> launch_feature
  -> ExecutionRecord
  -> LeadAgentRuntime
  -> TeamKernel / ReactSubagent
  -> Wenjin Harness / DataService
  -> TaskReport / Review Item
  -> RunView / ResultCard / Prism / Workspace Rooms
```

关键原则：

- Chat 是统一入口，不绕过 chat_agent -> lead_agent 主链路
- capability 数据驱动，YAML seed + DB 配置共同构成运行时能力目录
- 专家团队、sandbox、result card、workspace rooms 都围绕同一个 execution 记录投影
- 默认不展示 raw log，把过程压缩成用户可理解的专家进度、证据和候选结果
- Docker Compose 是唯一标准启动方式，旧的本地一键启动脚本已移除

## 技术栈

- Frontend：Next.js 16、React 19、TypeScript、Tailwind CSS、Zustand
- Backend：FastAPI、SQLAlchemy async、Pydantic v2、Celery、LangGraph
- Data：PostgreSQL + pgvector、Redis
- Runtime：Docker sandbox、Wenjin Harness、Prometheus、Grafana、Nginx

## 快速开始

### Docker Compose

```bash
git clone git@github.com:JunzeCai/AcademiaGPT-V2.git
cd AcademiaGPT-V2
cp backend/.env.example backend/.env
cp deploy/env/compose.prebuilt.example .env

# 编辑 .env：把 WENJIN_PROJECT_DIR 改成当前仓库绝对路径，
# 并替换 ADMIN_PASSWORD、GRAFANA_PASSWORD、DATASERVICE_INTERNAL_TOKEN、DOCKER_GID。

docker compose up -d
```

默认入口：

- Nginx: `http://localhost:2026`
- Frontend container: `http://localhost:3000`
- Grafana: `http://localhost:3001`

需要本地重建应用镜像时使用 local-build override：

```bash
cp deploy/env/compose.local-build-cn.example .env
# 编辑 .env 后再启动。
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build
```

### 开发者单服务调试

正式运行仍以 `docker compose up -d` 为准。下面命令只用于开发者单独调试某个服务。

```bash
python scripts/setup_wizard.py
python scripts/doctor.py

cd backend
uv sync --extra dev
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn src.gateway.app:app --reload --port 8001

cd ../frontend
npm install
npm run dev
```

## 关键目录

- `backend/src/agents/chat_agent/`：Chat Agent、block 协议、意图与 capability 启动
- `backend/src/agents/lead_agent/v2/`：Lead Agent runtime、TeamKernel、专家编排
- `backend/src/agents/harness/`：sandbox 工具、文件策略、执行记录、产物发现
- `backend/src/dataservice_app/`：DataService API
- `backend/seed/capabilities/`：workspace capability seed
- `backend/seed/skills/`：capability skill seed
- `frontend/app/(workbench)/workspaces/[id]/`：科研工作台主界面
- `frontend/lib/execution-run-view.ts`：执行状态统一投影
- `deploy/env/`：Docker Compose 环境模板
- `docs/current/`：当前事实源文档

## 文档入口

- 全量导航：`docs/current/documentation-map.md`
- 当前架构：`docs/current/architecture.md`
- 工作区状态：`docs/current/workspace-current-state.md`
- 前后端契约：`docs/current/frontend-feature-plugin-contract.md`
- capability 目录：`docs/current/workspace-feature-catalog.md`
- UI/UX 规范：`docs/current/wenjin-research-navigation-uiux.md`
- 部署手册：`docs/current/deployment-runbook.md`
- 排障手册：`docs/current/troubleshooting.md`

## 文档治理

- README 只保留项目定位、核心能力、启动方式和文档入口
- 详细架构、接口、运行时行为以 `docs/current/` 为当前事实源
- 运行方式变化必须同步更新 README、deployment runbook 和 troubleshooting
- 真实 `.env`、API Key、模型密钥和本地运行产物不得提交
