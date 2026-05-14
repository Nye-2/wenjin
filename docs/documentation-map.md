# Documentation Map

更新时间：2026-05-14
状态：Current

本文档是问津项目的文档总导航，用于统一入口、减少重复事实源，并明确每类变更应更新哪些文档。

## 1. 根入口文档

| 文档 | 作用 | 何时更新 |
|---|---|---|
| `README.md` | 项目总览、主链路、快速启动、文档入口 | 架构主链、启动方式、模块划分变化 |
| `backend/README.md` | 后端分层、核心能力、开发与测试命令 | 后端目录职责、路由入口、开发流程变化 |
| `frontend/README.md` | 前端工作台能力、交互主线、开发命令 | 前端路由模型、状态管理、联调方式变化 |

## 2. `docs/` 文档

### 2.1 架构文档（`docs/architecture/`）

| 文档 | 作用 |
|---|---|
| `README.md` | 架构文档入口与原则 |
| `README.md` | 唯一当前架构总览，含 execution / task / compute / feature / routes / 文档治理规则 |

### 2.2 产品文档（`docs/product/`）

| 文档 | 作用 |
|---|---|
| `README.md` | 产品文档入口 |
| `workspace-current-state.md` | workspace / thread / Compute / WenjinPrism 当前行为事实源 |
| `workspace-feature-catalog.md` | workspace type、feature、skill 目录 |
| `workspace-reference-library.md` | workspace 文献中心、证据、BibTeX 和 usage trace 当前事实源 |
| `frontend-feature-plugin-contract.md` | 前后端 feature 合约与刷新约束 |
| `release-gate-checklist.md` | 发布门禁检查项 |

### 2.3 战略种子文档（`docs/strategy/`）

| 文档 | 作用 |
|---|---|
| `wenjin-long-term-direction-seed.md` | 长期产品方向、数据产品路径和 AI Scientist 路线种子；不是当前实现事实源 |

### 2.4 基础设施文档（`docs/infrastructure/`）

| 文档 | 作用 |
|---|---|
| `README.md` | 基础设施文档入口 |
| `deployment-runbook.md` | 本地与 Compose 部署运行手册 |
| `environment-variables.md` | 环境变量基线与建议 |
| `troubleshooting.md` | 常见运行故障排查 |

## 3. 后端专项文档（`backend/docs/`）

| 文档 | 作用 |
|---|---|
| `README.md` | 后端专项文档入口 |
| `architecture/langgraph-workspace-architecture.md` | workspace graph 执行架构 |
| `async-task-system.md` | 任务系统职责与运行模型 |

## 4. 文档维护清单（提交前）

1. 变更 API/路由：更新 `docs/architecture/README.md` 与相关 README。
2. 变更执行链路：更新 `docs/architecture/README.md`。
3. 变更 feature/skill 目录：更新 `docs/product/workspace-feature-catalog.md`。
4. 变更部署或环境变量：更新 `docs/infrastructure/deployment-runbook.md` 与 `docs/infrastructure/environment-variables.md`。
5. 变更线程/前端/Compute 交互契约：更新 `docs/product/workspace-current-state.md` 与 `docs/product/frontend-feature-plugin-contract.md`。
6. 变更 execution / task / compute 边界：优先更新 `docs/architecture/README.md`。
7. 完成后同步检查入口：`README.md`、`docs/README.md`、`backend/README.md`、`frontend/README.md`。
8. 变更长期产品战略或数据产品判断：更新 `docs/strategy/wenjin-long-term-direction-seed.md`，并保持其 Seed 状态，避免混入 Current 事实源。
