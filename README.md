# 问津 Wenjin

更新时间：2026-07-12

问津是一个面向科研工作的 AI 工作台，服务从选题、文献、实验、写作到成果管理的完整研究流程。它不是通用聊天机器人，也不是单点论文润色工具，而是以 workspace 为核心的科研生产系统：用户在一个研究工作区里沉淀资料、决策、实验、主稿和团队协作记录，AI 研究团队在同一个上下文中持续推进任务。

## 项目定位

问津的目标是把科研任务从“和模型反复聊天”收敛成可执行、可追踪、可审阅的工作流：

- 研究导航：把模糊想法转成研究问题、检索计划、gap 判断和下一步行动
- 文献工作台：围绕主题组织检索、证据、引用、综述矩阵和创新点
- 实验工作台：每个 workspace 绑定一个 sandbox，支持代码、数据、图表和实验产物连续沉淀
- 写作工作台：围绕 LaTeX 主稿进行起草、改写、批注、编译、PDF 对照和版本化修改
- 自主研究团队：WorkspaceAgent 按目标动态派遣隔离 worker，在统一 Mission 上沉淀过程与交付物
- 审阅闭环：受保护的证据、论断、记忆和文档变更进入逐项复核，确认后才写入工作区

## 核心形态

- 六类科研 workspace：`sci`、`thesis`、`proposal`、`software_copyright`、`math_modeling`、`patent`
- 左侧 Chat：WorkspaceAgent 统一负责对话、任务判断、Mission 启动和动态调整
- 右侧 Mission Console：默认关闭，按需展示 worker、关键进展、证据、候选结果和历史
- Wenjin Prism：面向论文主稿的 LaTeX 编辑、编译、PDF 对照和 AI 改稿界面
- Wenjin Harness：为科研 agent 提供受控工具、Docker sandbox、阶段验收和可复现收据
- DataService：拥有 Mission、workspace、模型目录、积分、来源、记忆和复核提交的数据库事务
- Admin Console：管理模型、定价、积分与系统运行配置

## 架构概览

主链路已经收敛为 chat-native Mission runtime：

```text
Workspace Chat
  -> WorkspaceAgent
  -> MissionRuntime
  -> SubagentRuntime / ToolOrchestrator / SandboxRuntime
  -> StageAcceptance
  -> MissionReviewItem / MissionCommit
  -> MissionView / Prism / Workspace Rooms
```

关键原则：

- WorkspaceAgent 是唯一任务导航 agent，不存在独立 conversational/leader 层
- MissionPolicy 约束目标、质量、工具和权限；WorkerSkill 只提供紧凑方法指导，内部计划由 agent loop 决定
- `MissionRun`、`MissionItem`、`MissionReviewItem`、`MissionCommit` 是长任务唯一持久模型
- Chat 与 Mission Console 共享服务端 `MissionView`，前端不拼接第二套运行事实
- 高风险写入逐项复核；Sandbox、工具和模型能力均以结构化收据或探针证据为准
- Docker Compose 是唯一标准启动方式，旧的本地一键启动脚本已移除

## 技术栈

- Frontend：Next.js 16、React 19、TypeScript、Tailwind CSS、Zustand
- Backend：FastAPI、SQLAlchemy async、Pydantic v2、Celery、LangGraph
- Data：PostgreSQL + pgvector、Redis
- Runtime：Docker sandbox、Wenjin Harness、Prometheus、Grafana、Nginx

## 快速开始

### Docker Compose

```bash
git clone git@github.com:JunzeCai/wenjin.git
cd wenjin
cp .env.example .env

# 编辑 .env：把 WENJIN_PROJECT_DIR 改成当前仓库绝对路径，
# 并替换 ADMIN_PASSWORD、GRAFANA_PASSWORD、DATASERVICE_INTERNAL_TOKEN、
# JWT_SECRET_KEY、MODEL_SECRET_KEY、DOCKER_GID 和模型 API Key。

docker compose up -d
```

默认入口：

- Nginx: `http://localhost:2026`
- Frontend container: `http://localhost:3000`
- Grafana: `http://localhost:3001`

需要本地重建应用镜像时使用 local-build override：

```bash
# 如需国内镜像源，可把 deploy/env/compose.local-build-cn.example 中的
# 构建镜像变量复制到根目录 .env。
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build
```

### 开发者单服务调试

正式运行仍以 `docker compose up -d` 为准。下面命令只用于开发者单独调试某个服务。

```bash
python scripts/setup_wizard.py
python scripts/doctor.py

cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn src.gateway.app:app --reload --port 8001

cd ../frontend
npm install
npm run dev
```

## 关键目录

- `backend/src/agents/workspace_agent/`：统一对话、Mission 启动和 agent loop
- `backend/src/mission_runtime/`：Mission 生命周期、驱动、恢复和投影
- `backend/src/subagent_runtime/`：隔离 worker 生命周期
- `backend/src/tools/orchestrator/`：规范工具目录、调用状态、租约和收据
- `backend/src/sandbox/`：Docker-only sandbox、安全策略和可复现收据
- `backend/src/dataservice_app/`：DataService API
- `backend/seed/mission_policies/`：各 workspace 的 MissionPolicy 与阶段验收合同
- `backend/seed/skills/`：WorkerSkill 指导与示例
- `backend/seed/latex_templates/`：Prism LaTeX 模板注册表与内置模板包
- `frontend/app/(workbench)/workspaces/[id]/`：科研工作台主界面
- `frontend/lib/mission-view.ts`：Mission 服务端投影规范化
- `deploy/env/`：Docker Compose 环境模板
- `docs/current/`：当前事实源文档

## 文档入口

- 全量导航：`docs/current/documentation-map.md`
- 当前架构：`docs/current/architecture.md`
- 工作区状态：`docs/current/workspace-current-state.md`
- 前后端契约：`docs/current/frontend-mission-contract.md`
- MissionPolicy/WorkerSkill 目录：`docs/current/workspace-mission-catalog.md`
- UI/UX 规范：`docs/current/wenjin-research-navigation-uiux.md`
- 部署手册：`docs/current/deployment-runbook.md`
- 排障手册：`docs/current/troubleshooting.md`

## 文档治理

- README 只保留项目定位、核心能力、启动方式和文档入口
- 详细架构、接口、运行时行为以 `docs/current/` 为当前事实源
- 运行方式变化必须同步更新 README、deployment runbook 和 troubleshooting
- 真实 `.env`、API Key、模型密钥和本地运行产物不得提交
