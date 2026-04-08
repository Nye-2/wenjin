# 问津 Wenjin

问津是面向学术写作与研究交付的工作台，覆盖 workspace 对话编排、文献流程、Feature 执行链路和 LaTeX 主稿台（WenjinPrism）。

## 当前能力

- 五类工作区：`thesis` / `sci` / `proposal` / `software_copyright` / `patent`
- 会话驱动执行：单 workspace 主对话 + feature orchestration
- 可追踪产物：artifact / task / activity 全链路可回溯
- LaTeX 主稿台：项目管理、文件树编辑、编译预览、点评改写、PDF/TeX 联动

## 架构概览

- 前端：Next.js + React + TypeScript
- 网关：FastAPI（`backend/src/gateway`）
- 执行：LangGraph + Task Service + Celery
- 存储：PostgreSQL（含 pgvector）+ Redis

## 快速开始

### Docker Compose

```bash
git clone git@github.com:JunzeCai/AcademiaGPT-V2.git
cd AcademiaGPT-V2
cp backend/.env.example backend/.env
# 按需填写 backend/.env

docker compose up -d --build
```

前端默认入口：`http://localhost:3000`

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
uv run celery -A src.task.celery_app worker --loglevel=info

# frontend（新终端）
cd frontend
npm install
npm run dev
```

## 文档入口

- 总览：`docs/README.md`
- 架构：`docs/architecture/README.md`
- 产品契约：`docs/product/README.md`
- 部署与配置：`docs/infrastructure/README.md`
- 后端专项：`backend/docs/README.md`

## 文档治理

- 仅保留“当前事实源”文档；历史计划/过渡方案已清理。
- 行为变更时，先改实现，再同步更新对应文档。
- 发现文档与实现不一致时，以实现为准并立即修正文档。
